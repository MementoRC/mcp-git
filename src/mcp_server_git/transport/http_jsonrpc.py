"""JSON-RPC 2.0 dispatch for POST /mcp.

Follows the session-intelligence reference implementation pattern:
- Raw JSON parsing (no Pydantic validation)
- Session created on initialize, validated thereafter
- 3-meta-tool pattern for tool execution
"""

import logging
import secrets
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from fastapi import Request
from fastapi.responses import JSONResponse

from ..repository_binding import RemoteContaminationError, RepositoryBindingError
from .http_rpc_responses import rpc_error, rpc_result
from .http_tool_call import ToolCallHandler
from .http_tool_catalog import PROTOCOL_VERSION, TOOLS_LIST

if TYPE_CHECKING:
    from .http_server import HTTPGitServer

logger = logging.getLogger(__name__)

_Method = Callable[[Any, Any, str | None], Awaitable[JSONResponse]]


def _creation_error(req_id: Any, exc: Exception, repo: Any) -> JSONResponse:
    """Map a session-creation failure during initialize to a JSON-RPC error."""
    if isinstance(exc, FileNotFoundError):
        logger.error(f"Repository path not found: {repo}: {exc}")
        message, error_type = f"Invalid repository path: {repo}", "path_not_found"
    elif isinstance(exc, RemoteContaminationError):
        logger.error(f"Remote URL mismatch: {exc}")
        message, error_type = f"Remote URL validation failed: {exc}", "remote_mismatch"
    elif isinstance(exc, RepositoryBindingError):
        logger.error(f"Repository binding failed: {exc}")
        message, error_type = f"Repository binding failed: {exc}", "binding_error"
    elif isinstance(exc, ValueError):
        # Duplicate session_id (rare race condition)
        logger.warning(f"Session conflict: {exc}")
        message, error_type = str(exc), "session_conflict"
    else:
        logger.error(f"Session creation failed for {repo}: {exc}")
        return rpc_error(
            req_id,
            -32603,
            f"Internal error during session initialization: {exc}",
            data={"error_type": "internal_error"},
            status_code=500,
        )
    return rpc_error(req_id, -32602, message, data={"error_type": error_type})


class MCPRequestHandler:
    """Parse, validate and dispatch MCP JSON-RPC requests."""

    def __init__(self, server: "HTTPGitServer") -> None:
        self._server = server
        self._tool_calls = ToolCallHandler(server)
        self._methods: dict[str, _Method] = {
            "initialize": self._initialize,
            "notifications/initialized": self._initialized,
            "tools/list": self._tools_list,
            "tools/call": self._tool_calls.handle,
        }

    async def handle(self, request: Request, session_id: str | None) -> JSONResponse:
        """Handle one POST /mcp request."""
        try:
            body = await request.json()
        except Exception:
            return rpc_error(None, -32700, "Parse error", status_code=400)

        method = body.get("method")
        params = body.get("params", {})
        req_id = body.get("id")

        if body.get("jsonrpc") != "2.0":
            return rpc_error(req_id, -32600, "Invalid Request - jsonrpc must be '2.0'")

        handler = self._methods.get(method) if isinstance(method, str) else None
        if handler is None:
            return rpc_error(req_id, -32601, f"Method not found: {method}")
        return await handler(req_id, params, session_id)

    async def _initialize(
        self, req_id: Any, params: Any, session_id: str | None
    ) -> JSONResponse:
        new_session_id = f"mcp-{secrets.token_urlsafe(8)}"
        repo = self._server.default_repo
        if repo:
            try:
                await self._server.session_manager.create_session(
                    repo_path=repo,
                    expected_remote_url=None,
                    session_id=new_session_id,
                )
            except Exception as e:
                return _creation_error(req_id, e, repo)

        response = rpc_result(
            req_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": True}},
                "serverInfo": {"name": "mcp-git", "version": "1.0.0"},
            },
        )
        response.headers["MCP-Session-Id"] = new_session_id
        response.headers["MCP-Protocol-Version"] = PROTOCOL_VERSION
        return response

    async def _initialized(
        self, req_id: Any, params: Any, session_id: str | None
    ) -> JSONResponse:
        return rpc_result(req_id, {})

    async def _tools_list(
        self, req_id: Any, params: Any, session_id: str | None
    ) -> JSONResponse:
        return rpc_result(req_id, {"tools": TOOLS_LIST})
