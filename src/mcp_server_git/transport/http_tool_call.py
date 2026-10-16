"""``tools/call`` handling for the MCP HTTP transport (3-meta-tool pattern)."""

import json
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from fastapi.responses import JSONResponse

from ..server_metadata import build_server_info
from .http_rpc_responses import rpc_error, rpc_result

if TYPE_CHECKING:
    from .http_server import HTTPGitServer

logger = logging.getLogger(__name__)


class _RpcError(Exception):
    """Raised inside a tool runner to short-circuit with a JSON-RPC error."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ToolCallHandler:
    """Resolve the session and run a ``tools/call`` request."""

    def __init__(self, server: "HTTPGitServer") -> None:
        self._server = server
        self._runners: dict[str, Callable[[str, dict], Awaitable[Any]]] = {
            "discover_tools": self._discover_tools,
            "get_tool_spec": self._get_tool_spec,
            "execute_tool": self._execute_tool,
            "server_info": self._server_info,
        }

    async def handle(
        self, req_id: Any, params: Any, session_id: str | None
    ) -> JSONResponse:
        """Handle a ``tools/call`` JSON-RPC request."""
        if not session_id:
            if not self._server.default_repo:
                return rpc_error(req_id, -32000, "MCP-Session-Id header required")
            # get_or_create_session resurrects the default session if it has
            # expired or been lost due to a server restart
            session_id = self._server.DEFAULT_SESSION_ID

        try:
            text = json.dumps(await self._run(session_id, params))
        except _RpcError as e:
            return rpc_error(req_id, e.code, e.message)
        except ValueError as e:
            logger.error(f"Tool execution error: {e}")
            return rpc_error(req_id, -32000, str(e))
        except Exception as e:
            logger.error(f"Tool execution failed: {e}", exc_info=True)
            return rpc_error(req_id, -32603, f"Internal error: {str(e)}")

        return rpc_result(req_id, {"content": [{"type": "text", "text": text}]})

    async def _run(self, session_id: str, params: Any) -> Any:
        call_params = params or {}
        tool_name = call_params.get("name")
        arguments = call_params.get("arguments", {})

        if not tool_name:
            raise _RpcError(-32602, "Invalid params - 'name' required")

        runner = self._runners.get(tool_name) if isinstance(tool_name, str) else None
        if runner is not None:
            result = await runner(session_id, arguments)
        else:
            # Direct tool execution (legacy/fallback)
            result = await self._server.session_manager.execute_tool(
                session_id=session_id,
                tool_name=tool_name,
                args=arguments,
            )

        logger.debug(f"Tool executed: {tool_name} for session {session_id}")
        return result

    async def _discover_tools(self, session_id: str, arguments: dict) -> Any:
        return await self._server.session_manager.discover_tools(
            session_id=session_id,
            pattern=arguments.get("pattern", ""),
        )

    async def _get_tool_spec(self, session_id: str, arguments: dict) -> Any:
        target_tool = arguments.get("tool_name")
        if not target_tool:
            raise _RpcError(-32602, "tool_name required")
        return await self._server.session_manager.get_tool_spec(
            session_id=session_id,
            tool_name=target_tool,
        )

    async def _execute_tool(self, session_id: str, arguments: dict) -> Any:
        target_tool = arguments.get("tool_name")
        tool_params = arguments.get("parameters", {})
        if not target_tool:
            raise _RpcError(-32602, "tool_name required")
        return await self._server.session_manager.execute_tool(
            session_id=session_id,
            tool_name=target_tool,
            args=tool_params,
        )

    async def _server_info(self, session_id: str, arguments: dict) -> Any:
        session_context = await self._server.session_manager.get_or_create_session(
            session_id
        )
        if session_context is None:
            raise _RpcError(-32000, f"Session not found: {session_id}")
        return build_server_info(
            session_context.lean_interface.tool_registry,
            "HTTP (SSE)",
        )
