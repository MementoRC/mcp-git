"""HTTP route registration for the MCP Git HTTP server."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import Header, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from .http_jsonrpc import MCPRequestHandler
from .http_models import (
    CloseSessionResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    HealthResponse,
    SessionStatusResponse,
)
from .http_sse import build_sse_response

if TYPE_CHECKING:
    from .http_server import HTTPGitServer

logger = logging.getLogger(__name__)


def register_endpoints(server: "HTTPGitServer") -> None:
    """Register all HTTP endpoints on ``server.app``."""
    _register_session_routes(server)
    _register_mcp_routes(server)
    _register_health_route(server)


def _register_session_routes(server: "HTTPGitServer") -> None:
    @server.app.post(
        "/mcp/session/create",
        response_model=CreateSessionResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_session(request: CreateSessionRequest):
        """
        Create a new MCP session with repository binding.

        Raises:
            HTTPException 400: If repository binding fails
            HTTPException 409: If the session id is a duplicate
            HTTPException 422: If request validation fails
        """
        try:
            session_context = await server.session_manager.create_session(
                repo_path=Path(request.repository_path),
                expected_remote_url=request.expected_remote_url,
            )

            logger.info(f"Session created: {session_context.session_id}")

            return CreateSessionResponse(
                session_id=session_context.session_id,
                status="bound",
                repository_path=str(
                    session_context.repository_binding.repository_path
                    if session_context.repository_binding
                    else request.repository_path
                ),
            )

        except ValueError as e:
            # Duplicate session_id
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(e),
            ) from e
        except Exception as e:
            logger.error(f"Failed to create session: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to create session: {str(e)}",
            ) from e

    @server.app.delete(
        "/mcp/session/{session_id}",
        response_model=CloseSessionResponse,
    )
    async def close_session(session_id: str):
        """
        Close an existing MCP session.

        Raises:
            HTTPException 404: If session not found
        """
        success = await server.session_manager.close_session(session_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session not found: {session_id}",
            )

        logger.info(f"Session closed: {session_id}")
        return CloseSessionResponse(status="closed")

    @server.app.get(
        "/mcp/session/{session_id}/status",
        response_model=SessionStatusResponse,
    )
    async def get_session_status(session_id: str):
        """
        Get status information for a session.

        Raises:
            HTTPException 404: If session not found
        """
        session_info = await server.session_manager.get_session_info(session_id)

        if not session_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session not found: {session_id}",
            )

        return SessionStatusResponse(**session_info)


def _register_mcp_routes(server: "HTTPGitServer") -> None:
    handler = MCPRequestHandler(server)

    @server.app.post("/mcp")
    async def handle_mcp_request(
        request: Request,
        mcp_session_id: str | None = Header(None, alias="MCP-Session-Id"),
    ) -> JSONResponse:
        """Handle MCP JSON-RPC 2.0 requests."""
        return await handler.handle(request, mcp_session_id)

    @server.app.get("/mcp")
    async def handle_mcp_sse(
        mcp_session_id: str | None = Header(None, alias="MCP-Session-Id"),
    ) -> StreamingResponse:
        """
        Server-Sent Events endpoint for MCP notifications.

        SSE transport requires both POST /mcp (client-to-server requests) and
        GET /mcp (server-to-client notifications, this endpoint).
        """
        return build_sse_response()


def _register_health_route(server: "HTTPGitServer") -> None:
    @server.app.get("/health", response_model=HealthResponse)
    async def health_check():
        """Health check endpoint: server status and active session count."""
        return HealthResponse(
            status="healthy",
            active_sessions=server.session_manager.get_session_count(),
        )
