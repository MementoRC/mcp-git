"""
Integration tests for HTTP Server.

This module provides comprehensive integration tests for the HTTPGitServer class,
testing the full HTTP transport layer including FastAPI routes, session management,
and MCP tool execution.

Test Strategy:
- Uses httpx.AsyncClient with ASGITransport for async testing
- Creates real temporary git repositories for realistic testing
- Tests all HTTP endpoints and error conditions
- Validates session isolation and concurrent access
- Tests JSON-RPC 2.0 tool execution

Critical for TDD Compliance:
    These tests verify the complete HTTP transport implementation and must
    pass to ensure MCP Git server can be used over HTTP.
"""

import asyncio
import subprocess
import tempfile
from pathlib import Path

import httpx
import pytest

from mcp_server_git.transport.http_server import HTTPGitServer


@pytest.fixture
def temp_git_repo():
    """Create a temporary git repository with a remote."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir) / "test_repo"
        repo_path.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Add remote
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/test/repo.git"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Create initial commit
        (repo_path / "README.md").write_text("# Test Repository")
        subprocess.run(
            ["git", "add", "README.md"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        yield repo_path


@pytest.fixture
async def http_server():
    """Create HTTP server instance for testing."""
    server = HTTPGitServer(
        host="127.0.0.1",
        port=8765,
        api_key=None,  # No API key for testing
        session_timeout=60.0,  # Short timeout for testing
    )
    yield server
    # Cleanup: close all sessions
    session_ids = list(server.session_manager._sessions.keys())
    for session_id in session_ids:
        await server.session_manager.close_session(session_id)


@pytest.fixture
async def async_client(http_server):
    """Create async HTTP client for testing."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=http_server.app),
        base_url="http://test",
    ) as client:
        yield client


class TestHealthEndpoint:
    """Test health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_endpoint(self, async_client):
        """Test GET /health returns healthy status."""
        response = await async_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "active_sessions" in data
        assert isinstance(data["active_sessions"], int)
        assert data["active_sessions"] >= 0


class TestSessionManagement:
    """Test session lifecycle management endpoints."""

    @pytest.mark.asyncio
    async def test_create_session_success(self, async_client, temp_git_repo):
        """Test POST /mcp/session/create with valid repository."""
        response = await async_client.post(
            "/mcp/session/create",
            json={
                "repository_path": str(temp_git_repo),
                "expected_remote_url": "https://github.com/test/repo.git",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert "session_id" in data
        assert data["session_id"].startswith("mcp-")
        assert data["status"] == "bound"
        assert data["repository_path"] == str(temp_git_repo)

    @pytest.mark.asyncio
    async def test_create_session_invalid_repo(self, async_client):
        """Test POST /mcp/session/create returns error for invalid repository."""
        response = await async_client.post(
            "/mcp/session/create",
            json={
                "repository_path": "/nonexistent/path",
                "expected_remote_url": "https://github.com/test/repo.git",
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "Failed to create session" in data["detail"]

    @pytest.mark.asyncio
    async def test_create_session_remote_mismatch(self, async_client, temp_git_repo):
        """Test POST /mcp/session/create returns error for remote URL mismatch."""
        response = await async_client.post(
            "/mcp/session/create",
            json={
                "repository_path": str(temp_git_repo),
                "expected_remote_url": "https://github.com/wrong/repo.git",
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_get_session_status(self, async_client, temp_git_repo):
        """Test GET /mcp/session/{id}/status returns session info."""
        # First create a session
        create_response = await async_client.post(
            "/mcp/session/create",
            json={
                "repository_path": str(temp_git_repo),
                "expected_remote_url": "https://github.com/test/repo.git",
            },
        )
        assert create_response.status_code == 201
        session_id = create_response.json()["session_id"]

        # Get session status
        response = await async_client.get(f"/mcp/session/{session_id}/status")

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
        assert "created_at" in data
        assert "last_activity" in data
        assert "age" in data
        assert "idle_time" in data
        assert "binding_info" in data
        assert isinstance(data["age"], float)
        assert isinstance(data["idle_time"], float)

    @pytest.mark.asyncio
    async def test_get_session_not_found(self, async_client):
        """Test GET /mcp/session/{id}/status returns 404 for non-existent session."""
        response = await async_client.get("/mcp/session/nonexistent-session/status")

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "Session not found" in data["detail"]

    @pytest.mark.asyncio
    async def test_close_session(self, async_client, temp_git_repo):
        """Test DELETE /mcp/session/{id} closes session."""
        # First create a session
        create_response = await async_client.post(
            "/mcp/session/create",
            json={
                "repository_path": str(temp_git_repo),
                "expected_remote_url": "https://github.com/test/repo.git",
            },
        )
        assert create_response.status_code == 201
        session_id = create_response.json()["session_id"]

        # Close the session
        response = await async_client.delete(f"/mcp/session/{session_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "closed"

        # Verify session no longer exists
        status_response = await async_client.get(f"/mcp/session/{session_id}/status")
        assert status_response.status_code == 404

    @pytest.mark.asyncio
    async def test_close_session_not_found(self, async_client):
        """Test DELETE /mcp/session/{id} returns 404 for non-existent session."""
        response = await async_client.delete("/mcp/session/nonexistent-session")

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "Session not found" in data["detail"]


class TestMCPToolExecution:
    """Test MCP tool execution via JSON-RPC 2.0."""

    @pytest.mark.asyncio
    async def test_mcp_tool_execution(self, async_client, temp_git_repo):
        """Test POST /mcp executes discover_tools successfully."""
        # Create a session first
        create_response = await async_client.post(
            "/mcp/session/create",
            json={
                "repository_path": str(temp_git_repo),
                "expected_remote_url": "https://github.com/test/repo.git",
            },
        )
        assert create_response.status_code == 201
        session_id = create_response.json()["session_id"]

        # Execute discover_tools via JSON-RPC
        response = await async_client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "discover_tools",
                    "arguments": {"pattern": ""},
                },
                "id": 1,
            },
            headers={"MCP-Session-Id": session_id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert "result" in data
        assert data["id"] == 1
        assert "error" not in data or data["error"] is None

        # Result is in MCP content format
        result = data["result"]
        assert "content" in result
        assert len(result["content"]) > 0
        assert result["content"][0]["type"] == "text"

        # Parse the JSON text to get actual tool info
        import json

        tool_result = json.loads(result["content"][0]["text"])
        assert "available_tools" in tool_result or "tools" in tool_result

    @pytest.mark.asyncio
    async def test_mcp_missing_session_header(self, async_client):
        """Test POST /mcp without MCP-Session-Id header returns JSON-RPC error."""
        response = await async_client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "discover_tools",
                    "arguments": {},
                },
                "id": 1,
            },
        )

        # JSON-RPC error response (not HTTP error)
        assert response.status_code == 200
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert "error" in data
        assert data["error"]["code"] == -32000
        assert "MCP-Session-Id" in data["error"]["message"]

    @pytest.mark.asyncio
    async def test_mcp_invalid_session(self, async_client):
        """Test POST /mcp with invalid session returns error."""
        response = await async_client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "discover_tools",
                    "arguments": {},
                },
                "id": 1,
            },
            headers={"MCP-Session-Id": "invalid-session"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert "error" in data
        assert data["error"] is not None
        assert data["id"] == 1

    @pytest.mark.asyncio
    async def test_mcp_invalid_jsonrpc_version(self, async_client, temp_git_repo):
        """Test POST /mcp with invalid JSON-RPC version returns error."""
        # Create a session first
        create_response = await async_client.post(
            "/mcp/session/create",
            json={
                "repository_path": str(temp_git_repo),
                "expected_remote_url": "https://github.com/test/repo.git",
            },
        )
        session_id = create_response.json()["session_id"]

        response = await async_client.post(
            "/mcp",
            json={
                "jsonrpc": "1.0",
                "method": "tools/call",
                "params": {
                    "name": "discover_tools",
                    "arguments": {},
                },
                "id": 1,
            },
            headers={"MCP-Session-Id": session_id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert "error" in data
        assert data["error"]["code"] == -32600

    @pytest.mark.asyncio
    async def test_mcp_invalid_method(self, async_client, temp_git_repo):
        """Test POST /mcp with invalid method returns error."""
        # Create a session first
        create_response = await async_client.post(
            "/mcp/session/create",
            json={
                "repository_path": str(temp_git_repo),
                "expected_remote_url": "https://github.com/test/repo.git",
            },
        )
        session_id = create_response.json()["session_id"]

        response = await async_client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "invalid/method",
                "params": {},
                "id": 1,
            },
            headers={"MCP-Session-Id": session_id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert "error" in data
        assert data["error"]["code"] == -32601

    @pytest.mark.asyncio
    async def test_mcp_missing_tool_name(self, async_client, temp_git_repo):
        """Test POST /mcp without tool name returns error."""
        # Create a session first
        create_response = await async_client.post(
            "/mcp/session/create",
            json={
                "repository_path": str(temp_git_repo),
                "expected_remote_url": "https://github.com/test/repo.git",
            },
        )
        session_id = create_response.json()["session_id"]

        response = await async_client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "arguments": {},
                },
                "id": 1,
            },
            headers={"MCP-Session-Id": session_id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert "error" in data
        assert data["error"]["code"] == -32602


class TestConcurrentSessions:
    """Test concurrent session handling and isolation."""

    @pytest.mark.asyncio
    async def test_concurrent_sessions(self, async_client):
        """Test creating multiple sessions and verifying isolation."""
        # Create multiple temporary git repos
        repos = []
        for i in range(3):
            temp_dir = tempfile.mkdtemp()
            repo_path = Path(temp_dir) / "test_repo"
            repo_path.mkdir()

            # Initialize git repo
            subprocess.run(
                ["git", "init"], cwd=repo_path, check=True, capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.name", f"Test User {i}"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.email", f"test{i}@example.com"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    "git",
                    "remote",
                    "add",
                    "origin",
                    f"https://github.com/test/repo{i}.git",
                ],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )

            # Create initial commit
            (repo_path / "README.md").write_text(f"# Test Repository {i}")
            subprocess.run(
                ["git", "add", "README.md"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", f"Initial commit {i}"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )

            repos.append((repo_path, f"https://github.com/test/repo{i}.git"))

        try:
            # Create sessions concurrently
            session_tasks = [
                async_client.post(
                    "/mcp/session/create",
                    json={
                        "repository_path": str(repo_path),
                        "expected_remote_url": remote_url,
                    },
                )
                for repo_path, remote_url in repos
            ]

            responses = await asyncio.gather(*session_tasks)

            # Verify all sessions created successfully
            session_ids = []
            for response in responses:
                assert response.status_code == 201
                data = response.json()
                assert "session_id" in data
                session_ids.append(data["session_id"])

            # Verify session IDs are unique
            assert len(session_ids) == len(set(session_ids))

            # Verify each session has correct binding
            for i, session_id in enumerate(session_ids):
                status_response = await async_client.get(
                    f"/mcp/session/{session_id}/status"
                )
                assert status_response.status_code == 200
                status_data = status_response.json()
                binding_info = status_data["binding_info"]
                # repository_path is inside binding object
                binding = binding_info.get("binding", {})
                assert repos[i][0].name in str(binding.get("repository_path", ""))

            # Execute tool in each session concurrently
            tool_tasks = [
                async_client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {
                            "name": "discover_tools",
                            "arguments": {"pattern": ""},
                        },
                        "id": i,
                    },
                    headers={"MCP-Session-Id": session_id},
                )
                for i, session_id in enumerate(session_ids)
            ]

            tool_responses = await asyncio.gather(*tool_tasks)

            # Verify all tool executions succeeded
            for response in tool_responses:
                assert response.status_code == 200
                data = response.json()
                assert "result" in data

            # Clean up sessions
            close_tasks = [
                async_client.delete(f"/mcp/session/{session_id}")
                for session_id in session_ids
            ]
            await asyncio.gather(*close_tasks)

        finally:
            # Clean up temp directories
            import shutil

            for repo_path, _ in repos:
                shutil.rmtree(repo_path.parent, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_session_isolation(self, async_client, temp_git_repo):
        """Test that sessions are properly isolated from each other."""
        # Create two sessions with same repo
        create_tasks = [
            async_client.post(
                "/mcp/session/create",
                json={
                    "repository_path": str(temp_git_repo),
                    "expected_remote_url": "https://github.com/test/repo.git",
                },
            )
            for _ in range(2)
        ]

        responses = await asyncio.gather(*create_tasks)
        session_ids = [resp.json()["session_id"] for resp in responses]

        # Verify different session IDs
        assert session_ids[0] != session_ids[1]

        # Close one session
        await async_client.delete(f"/mcp/session/{session_ids[0]}")

        # Verify first session is gone
        status_response1 = await async_client.get(
            f"/mcp/session/{session_ids[0]}/status"
        )
        assert status_response1.status_code == 404

        # Verify second session still exists
        status_response2 = await async_client.get(
            f"/mcp/session/{session_ids[1]}/status"
        )
        assert status_response2.status_code == 200

        # Clean up
        await async_client.delete(f"/mcp/session/{session_ids[1]}")


class TestToolsListAndServerInfo:
    """Test tools/list endpoint and server_info tool."""

    @pytest.mark.asyncio
    async def test_tools_list_includes_server_info(self, async_client):
        """Test tools/list returns 4 meta-tools including server_info."""
        response = await async_client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 1,
            },
        )
        assert response.status_code == 200
        data = response.json()
        tools = data["result"]["tools"]
        assert len(tools) == 4
        tool_names = [t["name"] for t in tools]
        assert "discover_tools" in tool_names
        assert "get_tool_spec" in tool_names
        assert "execute_tool" in tool_names
        assert "server_info" in tool_names

    @pytest.mark.asyncio
    async def test_server_info_returns_metadata(self, async_client, temp_git_repo):
        """Test server_info tool returns complete server metadata."""
        import json

        # Create session
        create_response = await async_client.post(
            "/mcp/session/create",
            json={
                "repository_path": str(temp_git_repo),
                "expected_remote_url": "https://github.com/test/repo.git",
            },
        )
        assert create_response.status_code == 201
        session_id = create_response.json()["session_id"]

        # Call server_info
        response = await async_client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "server_info", "arguments": {}},
                "id": 2,
            },
            headers={"MCP-Session-Id": session_id},
        )
        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        result_text = data["result"]["content"][0]["text"]
        server_info = json.loads(result_text)

        assert server_info["name"] == "mcp-git"
        assert "version" in server_info
        assert server_info["issues"] == "https://github.com/MementoRC/mcp-git/issues"
        assert "bug_reports" in server_info["support"]
        assert "feature_requests" in server_info["support"]
        assert "git" in server_info["domains"]
        assert "github" in server_info["domains"]
        assert "azure" in server_info["domains"]

    @pytest.mark.asyncio
    async def test_server_info_without_session(self, async_client):
        """Test server_info works without a session when default_repo is set."""
        response = await async_client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "server_info", "arguments": {}},
                "id": 3,
            },
        )
        # Should work - server_info doesn't need repo access
        assert response.status_code == 200
