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

import asyncio
import logging
import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .http_session_manager import HTTPSessionManager
from .security import APIKeyMiddleware, LocalhostOnlyMiddleware

logger = logging.getLogger(__name__)

__all__ = ["HTTPGitServer"]


# Pydantic models for request/response validation


class CreateSessionRequest(BaseModel):
    """Request model for creating a new session."""

    repository_path: str = Field(..., description="Absolute path to the git repository")
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
    params: Optional[dict[str, Any]] = Field(
        default=None, description="Method parameters"
    )
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
            logger.info(f"MCP Git HTTP Server starting on {self.host}:{self.port}")
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
                    logger.info(f"Default session created for: {self.default_repo}")
                except Exception as e:
                    logger.warning(f"Failed to create default session: {e}")

            yield

            # Shutdown
            logger.info("MCP Git HTTP Server shutting down")
            # Cleanup all sessions via encapsulated method
            count = await self.session_manager.close_all_sessions()
            logger.info(f"Cleaned up {count} sessions on shutdown")

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

        @self.app.post("/mcp")
        async def handle_mcp_request(
            request: Request,
            mcp_session_id: Optional[str] = Header(None, alias="MCP-Session-Id"),
        ):
            """
            Handle MCP JSON-RPC 2.0 requests.

            Follows session-intelligence reference implementation pattern:
            - Raw JSON parsing (no Pydantic validation)
            - Session created on initialize, validated thereafter
            - 3-meta-tool pattern for tool execution
            """
            # Parse raw JSON (session-intelligence pattern)
            try:
                body = await request.json()
            except Exception:
                return JSONResponse(
                    status_code=400,
                    content={
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32700, "message": "Parse error"},
                    },
                )

            method = body.get("method")
            params = body.get("params", {})
            req_id = body.get("id")

            # Handle initialize - creates new MCP session
            if method == "initialize":
                new_session_id = f"mcp-{secrets.token_urlsafe(8)}"
                # Create session with default repo if configured
                if self.default_repo:
                    try:
                        await self.session_manager.create_session(
                            repo_path=self.default_repo,
                            expected_remote_url=None,
                            session_id=new_session_id,
                        )
                    except Exception as e:
                        logger.error(
                            f"Session creation failed for {self.default_repo}: {e}"
                        )
                        return JSONResponse(
                            status_code=500,
                            content={
                                "jsonrpc": "2.0",
                                "id": req_id,
                                "error": {
                                    "code": -32603,
                                    "message": f"Failed to initialize session: {e}",
                                },
                            },
                        )

                response = JSONResponse(
                    content={
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {
                                "tools": {"listChanged": True},
                            },
                            "serverInfo": {"name": "mcp-git", "version": "1.0.0"},
                        },
                    }
                )
                response.headers["MCP-Session-Id"] = new_session_id
                response.headers["MCP-Protocol-Version"] = "2024-11-05"
                return response

            # Handle notifications/initialized - just acknowledge
            if method == "notifications/initialized":
                return JSONResponse(
                    content={
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {},
                    }
                )

            # Handle tools/list - return the 3 meta-tools
            if method == "tools/list":
                return JSONResponse(
                    content={
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "tools": [
                                {
                                    "name": "discover_tools",
                                    "description": "Discover available Git, GitHub, and Azure DevOps tools. USE WHEN: finding tools by pattern",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {
                                            "pattern": {"type": "string", "default": ""}
                                        },
                                    },
                                },
                                {
                                    "name": "get_tool_spec",
                                    "description": "Get full specification for specific tool including schema and examples.",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {"tool_name": {"type": "string"}},
                                        "required": ["tool_name"],
                                    },
                                },
                                {
                                    "name": "execute_tool",
                                    "description": "Execute Git, GitHub, or Azure DevOps operation.",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {
                                            "tool_name": {"type": "string"},
                                            "parameters": {"type": "object"},
                                        },
                                        "required": ["tool_name", "parameters"],
                                    },
                                },
                            ]
                        },
                    }
                )

            # For tools/call, we need a session
            if method == "tools/call":
                # Use default session if none provided
                if not mcp_session_id:
                    if (
                        self.default_repo
                        and self.DEFAULT_SESSION_ID in self.session_manager._sessions
                    ):
                        mcp_session_id = self.DEFAULT_SESSION_ID
                    else:
                        return JSONResponse(
                            content={
                                "jsonrpc": "2.0",
                                "id": req_id,
                                "error": {
                                    "code": -32000,
                                    "message": "MCP-Session-Id header required",
                                },
                            }
                        )

                # Extract tool name and arguments
                try:
                    call_params = params or {}
                    tool_name = call_params.get("name")
                    arguments = call_params.get("arguments", {})

                    if not tool_name:
                        return JSONResponse(
                            content={
                                "jsonrpc": "2.0",
                                "id": req_id,
                                "error": {
                                    "code": -32602,
                                    "message": "Invalid params - 'name' required",
                                },
                            }
                        )

                    # Handle 3-meta-tool pattern
                    if tool_name == "discover_tools":
                        pattern = arguments.get("pattern", "")
                        result = await self.session_manager.discover_tools(
                            session_id=mcp_session_id,
                            pattern=pattern,
                        )
                    elif tool_name == "get_tool_spec":
                        target_tool = arguments.get("tool_name")
                        if not target_tool:
                            return JSONResponse(
                                content={
                                    "jsonrpc": "2.0",
                                    "id": req_id,
                                    "error": {
                                        "code": -32602,
                                        "message": "tool_name required",
                                    },
                                }
                            )
                        result = await self.session_manager.get_tool_spec(
                            session_id=mcp_session_id,
                            tool_name=target_tool,
                        )
                    elif tool_name == "execute_tool":
                        target_tool = arguments.get("tool_name")
                        tool_params = arguments.get("parameters", {})
                        if not target_tool:
                            return JSONResponse(
                                content={
                                    "jsonrpc": "2.0",
                                    "id": req_id,
                                    "error": {
                                        "code": -32602,
                                        "message": "tool_name required",
                                    },
                                }
                            )
                        result = await self.session_manager.execute_tool(
                            session_id=mcp_session_id,
                            tool_name=target_tool,
                            args=tool_params,
                        )
                    else:
                        # Direct tool execution (legacy/fallback)
                        result = await self.session_manager.execute_tool(
                            session_id=mcp_session_id,
                            tool_name=tool_name,
                            args=arguments,
                        )

                    logger.debug(
                        f"Tool executed: {tool_name} for session {mcp_session_id}"
                    )

                    return JSONResponse(
                        content={
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "result": {
                                "content": [{"type": "text", "text": str(result)}]
                            },
                        }
                    )

                except ValueError as e:
                    logger.error(f"Tool execution error: {e}")
                    return JSONResponse(
                        content={
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "error": {"code": -32000, "message": str(e)},
                        }
                    )

                except Exception as e:
                    logger.error(f"Tool execution failed: {e}", exc_info=True)
                    return JSONResponse(
                        content={
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "error": {
                                "code": -32603,
                                "message": f"Internal error: {str(e)}",
                            },
                        }
                    )

            # Unknown method
            return JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
            )

        @self.app.get("/mcp")
        async def handle_mcp_sse(
            mcp_session_id: Optional[str] = Header(None, alias="MCP-Session-Id"),
        ) -> StreamingResponse:
            """
            Server-Sent Events endpoint for MCP notifications.

            SSE transport requires both:
            - POST /mcp for client-to-server requests
            - GET /mcp for server-to-client notifications (this endpoint)

            Returns:
                StreamingResponse with text/event-stream content type
            """

            async def event_generator() -> AsyncGenerator[str, None]:
                """Generate SSE events."""
                try:
                    # Keep connection alive with periodic heartbeats
                    while True:
                        # Send heartbeat comment every 30 seconds
                        yield ": heartbeat\n\n"
                        await asyncio.sleep(30)
                except asyncio.CancelledError:
                    pass

            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
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
