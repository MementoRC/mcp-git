"""Characterization tests pinning HTTPGitServer routes and JSON-RPC behaviour.

These drive the real FastAPI app in-process and pin the externally observable
behaviour so the module can be decomposed (#255) without changing it.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from mcp_server_git.repository_binding import (
    RemoteContaminationError,
    RepositoryBindingError,
)
from mcp_server_git.transport.http_server import HTTPGitServer

INIT_BODY = {"jsonrpc": "2.0", "method": "initialize", "id": 1}


def _call(name: str | None, arguments: dict | None = None, req_id: int = 7) -> dict:
    params: dict = {}
    if name is not None:
        params["name"] = name
    if arguments is not None:
        params["arguments"] = arguments
    return {"jsonrpc": "2.0", "method": "tools/call", "params": params, "id": req_id}


def _stub(server: HTTPGitServer, name: str, **kwargs) -> AsyncMock:
    mock = AsyncMock(**kwargs)
    setattr(server.session_manager, name, mock)
    return mock


@pytest.fixture
def server() -> HTTPGitServer:
    return HTTPGitServer()


@pytest.fixture
def default_server(tmp_path: Path) -> HTTPGitServer:
    return HTTPGitServer(default_repo=tmp_path)


def _client(srv: HTTPGitServer) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=srv.app), base_url="http://test"
    )


@pytest.fixture
async def client(server):
    async with _client(server) as c:
        yield c


@pytest.fixture
async def default_client(default_server):
    async with _client(default_server) as c:
        yield c


class TestRoutes:
    def test_routes_returns_expected_set_when_app_built(self, server):
        pairs = {
            (r.path, m)
            for r in server.app.routes
            for m in (getattr(r, "methods", None) or ())
            if m not in ("HEAD",)
        }
        assert pairs == {
            ("/openapi.json", "GET"),
            ("/docs", "GET"),
            ("/docs/oauth2-redirect", "GET"),
            ("/redoc", "GET"),
            ("/mcp/session/create", "POST"),
            ("/mcp/session/{session_id}", "DELETE"),
            ("/mcp/session/{session_id}/status", "GET"),
            ("/mcp", "POST"),
            ("/mcp", "GET"),
            ("/health", "GET"),
        }

    def test_app_returns_metadata_when_built(self, server):
        assert server.app.title == "MCP Git HTTP Server"
        assert server.app.version == "1.0.0"

    async def test_sse_returns_stream_response_when_get_mcp_called(self, server):
        route = next(
            r for r in server.app.routes if r.path == "/mcp" and "GET" in r.methods
        )
        response = await route.endpoint(mcp_session_id=None)

        assert response.media_type == "text/event-stream"
        assert response.headers["cache-control"] == "no-cache"
        assert response.headers["connection"] == "keep-alive"
        assert response.headers["x-accel-buffering"] == "no"
        first = await response.body_iterator.__anext__()
        assert first == ": heartbeat\n\n"
        await response.body_iterator.aclose()


class TestHealthAndSessions:
    async def test_health_returns_count_when_sessions_stubbed(self, server, client):
        server.session_manager.get_session_count = MagicMock(return_value=4)

        response = await client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "healthy", "active_sessions": 4}

    async def test_create_returns_201_when_binding_succeeds(self, server, client):
        ctx = MagicMock(session_id="s1")
        ctx.repository_binding.repository_path = Path("/bound/repo")
        mock = _stub(server, "create_session", return_value=ctx)

        response = await client.post(
            "/mcp/session/create",
            json={"repository_path": "/r", "expected_remote_url": "u"},
        )

        assert response.status_code == 201
        assert response.json() == {
            "session_id": "s1",
            "status": "bound",
            "repository_path": "/bound/repo",
        }
        mock.assert_awaited_once_with(repo_path=Path("/r"), expected_remote_url="u")

    async def test_create_returns_requested_path_when_binding_missing(
        self, server, client
    ):
        _stub(
            server,
            "create_session",
            return_value=MagicMock(session_id="s2", repository_binding=None),
        )

        response = await client.post(
            "/mcp/session/create",
            json={"repository_path": "/r", "expected_remote_url": "u"},
        )

        assert response.json()["repository_path"] == "/r"

    async def test_create_returns_409_when_value_error(self, server, client):
        _stub(server, "create_session", side_effect=ValueError("dup"))

        response = await client.post(
            "/mcp/session/create",
            json={"repository_path": "/r", "expected_remote_url": "u"},
        )

        assert response.status_code == 409
        assert response.json() == {"detail": "dup"}

    async def test_create_returns_400_when_other_error(self, server, client):
        _stub(server, "create_session", side_effect=RuntimeError("boom"))

        response = await client.post(
            "/mcp/session/create",
            json={"repository_path": "/r", "expected_remote_url": "u"},
        )

        assert response.status_code == 400
        assert response.json() == {"detail": "Failed to create session: boom"}

    async def test_create_returns_422_when_body_invalid(self, client):
        response = await client.post("/mcp/session/create", json={})

        assert response.status_code == 422

    async def test_close_returns_closed_when_session_exists(self, server, client):
        mock = _stub(server, "close_session", return_value=True)

        response = await client.delete("/mcp/session/abc")

        assert response.status_code == 200
        assert response.json() == {"status": "closed"}
        mock.assert_awaited_once_with("abc")

    async def test_close_returns_404_when_session_missing(self, server, client):
        _stub(server, "close_session", return_value=False)

        response = await client.delete("/mcp/session/abc")

        assert response.status_code == 404
        assert response.json() == {"detail": "Session not found: abc"}

    async def test_status_returns_info_when_session_exists(self, server, client):
        info = {
            "session_id": "abc",
            "created_at": 1.0,
            "last_activity": 2.0,
            "age": 3.0,
            "idle_time": 4.0,
            "binding_info": {"k": "v"},
        }
        _stub(server, "get_session_info", return_value=info)

        response = await client.get("/mcp/session/abc/status")

        assert response.status_code == 200
        assert response.json() == info

    async def test_status_returns_404_when_session_missing(self, server, client):
        _stub(server, "get_session_info", return_value=None)

        response = await client.get("/mcp/session/abc/status")

        assert response.status_code == 404
        assert response.json() == {"detail": "Session not found: abc"}


class TestInitialize:
    async def test_initialize_returns_session_headers_when_no_default_repo(
        self, client
    ):
        response = await client.post("/mcp", json=INIT_BODY)

        assert response.status_code == 200
        assert response.json() == {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": True}},
                "serverInfo": {"name": "mcp-git", "version": "1.0.0"},
            },
        }
        assert response.headers["MCP-Session-Id"].startswith("mcp-")
        assert response.headers["MCP-Protocol-Version"] == "2024-11-05"

    async def test_initialize_creates_session_when_default_repo_set(
        self, default_server, default_client, tmp_path
    ):
        mock = _stub(default_server, "create_session")

        response = await default_client.post("/mcp", json=INIT_BODY)

        sid = response.headers["MCP-Session-Id"]
        mock.assert_awaited_once_with(
            repo_path=tmp_path, expected_remote_url=None, session_id=sid
        )

    @pytest.mark.parametrize(
        ("exc", "status", "code", "error_type", "message"),
        [
            (FileNotFoundError("x"), 200, -32602, "path_not_found", None),
            (RemoteContaminationError("rc"), 200, -32602, "remote_mismatch", None),
            (RepositoryBindingError("rb"), 200, -32602, "binding_error", None),
            (ValueError("dup"), 200, -32602, "session_conflict", "dup"),
            (RuntimeError("bad"), 500, -32603, "internal_error", None),
        ],
    )
    async def test_initialize_returns_error_when_session_creation_fails(
        self,
        default_server,
        default_client,
        tmp_path,
        exc,
        status,
        code,
        error_type,
        message,
    ):
        _stub(default_server, "create_session", side_effect=exc)

        response = await default_client.post("/mcp", json=INIT_BODY)

        assert response.status_code == status
        assert "MCP-Session-Id" not in response.headers
        data = response.json()
        assert data["id"] == 1
        assert data["error"]["code"] == code
        assert data["error"]["data"] == {"error_type": error_type}
        if message:
            assert data["error"]["message"] == message
        elif error_type == "path_not_found":
            assert data["error"]["message"] == f"Invalid repository path: {tmp_path}"
        elif error_type == "remote_mismatch":
            assert data["error"]["message"].startswith("Remote URL validation failed")
        elif error_type == "binding_error":
            assert data["error"]["message"].startswith("Repository binding failed")
        else:
            assert data["error"]["message"] == (
                "Internal error during session initialization: bad"
            )


class TestEnvelope:
    async def test_post_returns_parse_error_when_body_not_json(self, client):
        response = await client.post("/mcp", content=b"{nope")

        assert response.status_code == 400
        assert response.json() == {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32700, "message": "Parse error"},
        }

    async def test_post_returns_invalid_request_when_version_wrong(self, client):
        response = await client.post(
            "/mcp", json={"jsonrpc": "1.0", "method": "tools/list", "id": 9}
        )

        assert response.status_code == 200
        assert response.json() == {
            "jsonrpc": "2.0",
            "id": 9,
            "error": {
                "code": -32600,
                "message": "Invalid Request - jsonrpc must be '2.0'",
            },
        }

    async def test_post_returns_invalid_request_when_version_missing(self, client):
        response = await client.post("/mcp", json={"method": "tools/list"})

        assert response.json()["error"]["code"] == -32600
        assert response.json()["id"] is None

    async def test_post_raises_when_batch_array_sent(self, client):
        with pytest.raises(AttributeError):
            await client.post("/mcp", json=[INIT_BODY])

    async def test_post_returns_method_not_found_when_unknown_method(self, client):
        response = await client.post(
            "/mcp", json={"jsonrpc": "2.0", "method": "bogus/x", "id": "a"}
        )

        assert response.status_code == 200
        assert response.json() == {
            "jsonrpc": "2.0",
            "id": "a",
            "error": {"code": -32601, "message": "Method not found: bogus/x"},
        }

    async def test_post_returns_method_not_found_when_method_absent(self, client):
        response = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 2})

        assert response.json()["error"] == {
            "code": -32601,
            "message": "Method not found: None",
        }

    async def test_post_returns_empty_result_when_initialized_notification(
        self, client
    ):
        response = await client.post(
            "/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}
        )

        assert response.status_code == 200
        assert response.json() == {"jsonrpc": "2.0", "id": None, "result": {}}

    async def test_tools_list_returns_four_tools_when_called(self, client):
        response = await client.post(
            "/mcp", json={"jsonrpc": "2.0", "method": "tools/list", "id": 3}
        )

        tools = response.json()["result"]["tools"]
        assert [t["name"] for t in tools] == [
            "discover_tools",
            "get_tool_spec",
            "execute_tool",
            "server_info",
        ]
        by_name = {t["name"]: t["inputSchema"] for t in tools}
        assert by_name["get_tool_spec"]["required"] == ["tool_name"]
        assert by_name["execute_tool"]["required"] == ["tool_name", "parameters"]
        assert by_name["server_info"] == {"type": "object", "properties": {}}
        assert by_name["discover_tools"]["properties"] == {
            "pattern": {"type": "string", "default": ""}
        }


class TestToolsCall:
    async def test_call_returns_session_required_when_header_and_default_missing(
        self, client
    ):
        response = await client.post("/mcp", json=_call("discover_tools", {}))

        assert response.status_code == 200
        assert response.json() == {
            "jsonrpc": "2.0",
            "id": 7,
            "error": {"code": -32000, "message": "MCP-Session-Id header required"},
        }

    async def test_call_uses_default_session_when_header_missing_and_default_repo(
        self, default_server, default_client
    ):
        mock = _stub(default_server, "discover_tools", return_value={"tools": []})

        response = await default_client.post("/mcp", json=_call("discover_tools", {}))

        assert response.status_code == 200
        mock.assert_awaited_once_with(session_id="default", pattern="")

    async def test_call_returns_name_required_when_name_missing(self, client):
        response = await client.post(
            "/mcp", json=_call(None), headers={"MCP-Session-Id": "s"}
        )

        assert response.json()["error"] == {
            "code": -32602,
            "message": "Invalid params - 'name' required",
        }

    async def test_call_returns_name_required_when_params_absent(self, client):
        response = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "tools/call", "id": 1},
            headers={"MCP-Session-Id": "s"},
        )

        assert response.json()["error"]["code"] == -32602

    async def test_call_returns_internal_error_when_params_not_object(self, client):
        response = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "tools/call", "params": "x", "id": 1},
            headers={"MCP-Session-Id": "s"},
        )

        error = response.json()["error"]
        assert error["code"] == -32603
        assert error["message"].startswith("Internal error: ")

    async def test_call_wraps_result_when_discover_tools(self, server, client):
        mock = _stub(server, "discover_tools", return_value={"tools": ["a"]})

        response = await client.post(
            "/mcp",
            json=_call("discover_tools", {"pattern": "git"}),
            headers={"MCP-Session-Id": "s1"},
        )

        assert response.json() == {
            "jsonrpc": "2.0",
            "id": 7,
            "result": {
                "content": [{"type": "text", "text": json.dumps({"tools": ["a"]})}]
            },
        }
        mock.assert_awaited_once_with(session_id="s1", pattern="git")

    async def test_call_dispatches_when_get_tool_spec(self, server, client):
        mock = _stub(server, "get_tool_spec", return_value={"n": 1})

        response = await client.post(
            "/mcp",
            json=_call("get_tool_spec", {"tool_name": "git_status"}),
            headers={"MCP-Session-Id": "s1"},
        )

        assert json.loads(response.json()["result"]["content"][0]["text"]) == {"n": 1}
        mock.assert_awaited_once_with(session_id="s1", tool_name="git_status")

    @pytest.mark.parametrize("name", ["get_tool_spec", "execute_tool"])
    async def test_call_returns_tool_name_required_when_target_missing(
        self, client, name
    ):
        response = await client.post(
            "/mcp", json=_call(name, {}), headers={"MCP-Session-Id": "s1"}
        )

        assert response.json()["error"] == {
            "code": -32602,
            "message": "tool_name required",
        }

    async def test_call_dispatches_when_execute_tool(self, server, client):
        mock = _stub(server, "execute_tool", return_value="done")

        response = await client.post(
            "/mcp",
            json=_call(
                "execute_tool",
                {"tool_name": "git_status", "parameters": {"repo_path": "."}},
            ),
            headers={"MCP-Session-Id": "s1"},
        )

        assert response.json()["result"]["content"][0]["text"] == '"done"'
        mock.assert_awaited_once_with(
            session_id="s1", tool_name="git_status", args={"repo_path": "."}
        )

    async def test_call_defaults_parameters_when_execute_tool_has_none(
        self, server, client
    ):
        mock = _stub(server, "execute_tool", return_value=1)

        await client.post(
            "/mcp",
            json=_call("execute_tool", {"tool_name": "t"}),
            headers={"MCP-Session-Id": "s1"},
        )

        mock.assert_awaited_once_with(session_id="s1", tool_name="t", args={})

    async def test_call_executes_directly_when_tool_name_unknown(self, server, client):
        mock = _stub(server, "execute_tool", return_value={"ok": True})

        response = await client.post(
            "/mcp",
            json=_call("git_status", {"a": 1}),
            headers={"MCP-Session-Id": "s1"},
        )

        assert response.status_code == 200
        mock.assert_awaited_once_with(
            session_id="s1", tool_name="git_status", args={"a": 1}
        )

    async def test_call_defaults_arguments_when_omitted(self, server, client):
        mock = _stub(server, "execute_tool", return_value=None)

        await client.post(
            "/mcp", json=_call("git_status"), headers={"MCP-Session-Id": "s1"}
        )

        mock.assert_awaited_once_with(session_id="s1", tool_name="git_status", args={})

    async def test_call_returns_server_info_when_session_resolves(self, server, client):
        ctx = MagicMock()
        ctx.lean_interface.tool_registry = {}
        mock = _stub(server, "get_or_create_session", return_value=ctx)

        response = await client.post(
            "/mcp",
            json=_call("server_info", {}),
            headers={"MCP-Session-Id": "s1"},
        )

        payload = json.loads(response.json()["result"]["content"][0]["text"])
        assert isinstance(payload, dict)
        assert payload
        mock.assert_awaited_once_with("s1")

    async def test_call_returns_session_not_found_when_server_info_unresolved(
        self, server, client
    ):
        _stub(server, "get_or_create_session", return_value=None)

        response = await client.post(
            "/mcp", json=_call("server_info", {}), headers={"MCP-Session-Id": "s1"}
        )

        assert response.json()["error"] == {
            "code": -32000,
            "message": "Session not found: s1",
        }

    async def test_call_returns_value_error_when_tool_raises_value_error(
        self, server, client
    ):
        _stub(server, "execute_tool", side_effect=ValueError("bad session"))

        response = await client.post(
            "/mcp", json=_call("git_status", {}), headers={"MCP-Session-Id": "s1"}
        )

        assert response.status_code == 200
        assert response.json()["error"] == {"code": -32000, "message": "bad session"}

    async def test_call_returns_internal_error_when_tool_raises(self, server, client):
        _stub(server, "execute_tool", side_effect=RuntimeError("kaboom"))

        response = await client.post(
            "/mcp", json=_call("git_status", {}), headers={"MCP-Session-Id": "s1"}
        )

        assert response.status_code == 200
        assert response.json()["error"] == {
            "code": -32603,
            "message": "Internal error: kaboom",
        }
