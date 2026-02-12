"""
FastAPI HTTP Server for MCP Git Server.

This module implements the HTTP transport layer for the MCP Git server, providing
RESTful endpoints for session management and MCP tool execution over HTTP.

Key features:
- Session management with isolated repository contexts
- JSON-RPC 2.0 tool execution
- Security middleware (localhost-only + optional API key)
- Health monitoring and session cleanup
- Automatic session timeout handling

Architecture:
    HTTP Client → FastAPI → SessionManager → Services → Git/GitHub Operations
                        ├─> Localhost-only middleware
                        └─> API Key middleware (optional)
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import uvicorn
from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from .http_session_manager import HTTPSessionManager
from .security import APIKeyMiddleware, LocalhostOnlyMiddleware

logger = logging.getLogger(__name__)

__all__ = ["HTTPGitServer"]


# Pydantic models for request/response validation


class CreateSessionRequest(BaseModel):
    """Request model for creating a new session."""

    repository_path: str = Field(
        ..., description="Absolute path to the git repository"
    )
    expected_remote_url: str = Field(
        ..., description="Expected remote URL for validation"
    )


class CreateSessionResponse(BaseModel):
    """Response model for session creation."""

    session_id: str = Field(..., description="Unique session identifier")
    status: str = Field(default="bound", description="Session status")
    repository_path: str = Field(..., description="Bound repository path")


class SessionStatusResponse(BaseModel):
    """Response model for session status."""

    session_id: str
    created_at: float
    last_activity: float
    age: float
    idle_time: float
    binding_info: dict[str, Any]


class CloseSessionResponse(BaseModel):
    """Response model for session closure."""

    status: str = Field(default="closed", description="Closure status")


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str = Field(default="healthy", description="Server health status")
    active_sessions: int = Field(..., description="Number of active sessions")


class JSONRPCRequest(BaseModel):
    """JSON-RPC 2.0 request model."""

    jsonrpc: str = Field(default="2.0", description="JSON-RPC version")
    method: str = Field(..., description="Method name (e.g., 'tools/call')")
    params: dict[str, Any] = Field(..., description="Method parameters")
    id: Optional[int | str] = Field(None, description="Request ID")


class JSONRPCResponse(BaseModel):
    """JSON-RPC 2.0 response model."""

    jsonrpc: str = Field(default="2.0", description="JSON-RPC version")
    result: Optional[dict[str, Any]] = Field(None, description="Result data")
    error: Optional[dict[str, Any]] = Field(None, description="Error data")
    id: Optional[int | str] = Field(None, description="Request ID")


class HTTPGitServer:
    """
    FastAPI HTTP server for MCP Git operations.

    Provides HTTP endpoints for:
    - Session lifecycle management (create, close, status)
    - MCP tool execution via JSON-RPC 2.0
    - Health monitoring
    - Automatic session cleanup

    Security:
    - Localhost-only access by default
    - Optional API key authentication
    - Per-session repository isolation

    Auto-session mode:
    - When default_repo is specified, creates a default session at startup
    - MCP clients can omit MCP-Session-Id header and use default session
    - Enables compatibility with standard MCP clients
    """

    DEFAULT_SESSION_ID = "default"

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        api_key: Optional[str] = None,
        session_timeout: float = 3600.0,
        default_repo: Optional[Path] = None,
    ):
        """
        Initialize HTTP Git server.

        Args:
            host: Host address to bind to (default: 127.0.0.1)
            port: Port to listen on (default: 8765)
            api_key: Optional API key for authentication
            session_timeout: Session timeout in seconds (default: 3600 = 1 hour)
            default_repo: Optional default repository for auto-session mode
        """
        self.host = host
        self.port = port
        self.api_key = api_key
        self.default_repo = default_repo
        self.session_manager = HTTPSessionManager(session_timeout=session_timeout)

        # Create FastAPI app with lifespan context manager
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            """Lifespan context manager for startup/shutdown."""
            # Startup
            logger.info(
                f"MCP Git HTTP Server starting on {self.host}:{self.port}"
            )
            if self.api_key:
                logger.info("API key authentication enabled")
            else:
                logger.info("API key authentication disabled")

            # Create default session if default_repo is specified
            if self.default_repo:
                try:
                    await self.session_manager.create_session(
                        repo_path=self.default_repo,
                        expected_remote_url=None,  # Skip URL validation for default session
                        session_id=self.DEFAULT_SESSION_ID,
                    )
                    logger.info(
                        f"Default session created for: {self.default_repo}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to create default session: {e}"
                    )

            yield

            # Shutdown
            logger.info("MCP Git HTTP Server shutting down")
            # Cleanup all sessions
            session_ids = list(self.session_manager._sessions.keys())
            for session_id in session_ids:
                await self.session_manager.close_session(session_id)
            logger.info(f"Cleaned up {len(session_ids)} sessions on shutdown")

        self.app = FastAPI(
            title="MCP Git HTTP Server",
            description="HTTP transport for MCP Git operations",
            version="1.0.0",
            lifespan=lifespan,
        )

        # Apply security middleware
        self.app.add_middleware(LocalhostOnlyMiddleware)
        if self.api_key:
            self.app.add_middleware(APIKeyMiddleware, api_key=self.api_key)

        # Register endpoints
        self._register_endpoints()

    def _register_endpoints(self):
        """Register all HTTP endpoints."""

        @self.app.post(
            "/mcp/session/create",
            response_model=CreateSessionResponse,
            status_code=status.HTTP_201_CREATED,
        )
        async def create_session(request: CreateSessionRequest):
            """
            Create a new MCP session with repository binding.

            This endpoint creates an isolated session context with its own
            service instances and binds it to a specific repository.

            Args:
                request: Session creation request with repository path and expected remote URL

            Returns:
                Session information including session_id and status

            Raises:
                HTTPException 400: If repository binding fails
                HTTPException 422: If request validation fails
            """
            try:
                session_context = await self.session_manager.create_session(
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

            except Exception as e:
                logger.error(f"Failed to create session: {e}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to create session: {str(e)}",
                )

        @self.app.delete(
            "/mcp/session/{session_id}",
            response_model=CloseSessionResponse,
        )
        async def close_session(session_id: str):
            """
            Close an existing MCP session.

            This endpoint unbinds the repository and releases all session resources.

            Args:
                session_id: The session identifier to close

            Returns:
                Closure status

            Raises:
                HTTPException 404: If session not found
            """
            success = await self.session_manager.close_session(session_id)

            if not success:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Session not found: {session_id}",
                )

            logger.info(f"Session closed: {session_id}")
            return CloseSessionResponse(status="closed")

        @self.app.get(
            "/mcp/session/{session_id}/status",
            response_model=SessionStatusResponse,
        )
        async def get_session_status(session_id: str):
            """
            Get status information for a session.

            Args:
                session_id: The session identifier

            Returns:
                Session status information including activity timestamps

            Raises:
                HTTPException 404: If session not found
            """
            session_info = await self.session_manager.get_session_info(session_id)

            if not session_info:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Session not found: {session_id}",
                )

            return SessionStatusResponse(**session_info)

        @self.app.post("/mcp", response_model=JSONRPCResponse)
        async def execute_mcp_tool(
            request: JSONRPCRequest,
            mcp_session_id: Optional[str] = Header(None, alias="MCP-Session-Id"),
        ):
            """
            Execute an MCP tool via JSON-RPC 2.0.

            This endpoint accepts JSON-RPC 2.0 formatted requests for tool execution.
            The session ID can be provided via the MCP-Session-Id header.
            If no session ID is provided and a default session exists, uses the default.

            Args:
                request: JSON-RPC 2.0 request with method and params
                mcp_session_id: Optional session identifier from header

            Returns:
                JSON-RPC 2.0 response with result or error

            Raises:
                HTTPException 400: If request is invalid
                HTTPException 404: If session not found
            """
            # Use default session if none provided
            if not mcp_session_id:
                if self.default_repo and self.DEFAULT_SESSION_ID in self.session_manager._sessions:
                    mcp_session_id = self.DEFAULT_SESSION_ID
                else:
                    return JSONRPCResponse(
                        jsonrpc="2.0",
                        error={
                            "code": -32000,
                            "message": "MCP-Session-Id header required (no default session configured)",
                        },
                        id=request.id,
                    )

            # Validate JSON-RPC version
            if request.jsonrpc != "2.0":
                return JSONRPCResponse(
                    jsonrpc="2.0",
                    error={
                        "code": -32600,
                        "message": "Invalid Request - only JSON-RPC 2.0 supported",
                    },
                    id=request.id,
                )

            # Validate method
            if request.method != "tools/call":
                return JSONRPCResponse(
                    jsonrpc="2.0",
                    error={
                        "code": -32601,
                        "message": f"Method not found: {request.method}",
                    },
                    id=request.id,
                )

            # Extract tool name and arguments
            try:
                tool_name = request.params.get("name")
                arguments = request.params.get("arguments", {})

                if not tool_name:
                    return JSONRPCResponse(
                        jsonrpc="2.0",
                        error={
                            "code": -32602,
                            "message": "Invalid params - 'name' required",
                        },
                        id=request.id,
                    )

                # Execute tool via session manager
                result = await self.session_manager.execute_tool(
                    session_id=mcp_session_id,
                    tool_name=tool_name,
                    args=arguments,
                )

                logger.debug(
                    f"Tool executed: {tool_name} for session {mcp_session_id}"
                )

                return JSONRPCResponse(
                    jsonrpc="2.0",
                    result=result,
                    id=request.id,
                )

            except ValueError as e:
                # Session not found or validation error
                logger.error(f"Tool execution error: {e}")
                return JSONRPCResponse(
                    jsonrpc="2.0",
                    error={
                        "code": -32000,
                        "message": str(e),
                    },
                    id=request.id,
                )

            except Exception as e:
                # Internal error
                logger.error(f"Tool execution failed: {e}", exc_info=True)
                return JSONRPCResponse(
                    jsonrpc="2.0",
                    error={
                        "code": -32603,
                        "message": f"Internal error: {str(e)}",
                    },
                    id=request.id,
                )

        @self.app.get("/health", response_model=HealthResponse)
        async def health_check():
            """
            Health check endpoint.

            Returns:
                Server health status and active session count
            """
            active_sessions = len(self.session_manager._sessions)

            return HealthResponse(
                status="healthy",
                active_sessions=active_sessions,
            )

    def run(self):
        """
        Run the HTTP server.

        This starts the uvicorn server with the configured host and port.
        The server will run until interrupted (e.g., Ctrl+C).
        """
        logger.info(f"Starting HTTP server on {self.host}:{self.port}")

        uvicorn.run(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info",
        )
