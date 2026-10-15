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

Endpoint handlers live in ``http_routes``, JSON-RPC dispatch in ``http_jsonrpc``
and ``http_tool_call``, SSE in ``http_sse``, and models in ``http_models``.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from .http_routes import register_endpoints
from .http_session_manager import HTTPSessionManager
from .security import APIKeyMiddleware, LocalhostOnlyMiddleware

logger = logging.getLogger(__name__)

__all__ = ["HTTPGitServer"]

# Open SSE streams never end on their own; cap how long uvicorn waits for them.
GRACEFUL_SHUTDOWN_TIMEOUT_S = 5


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
        api_key: str | None = None,
        session_timeout: float = 3600.0,
        default_repo: Path | None = None,
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
        self.session_manager = HTTPSessionManager(
            session_timeout=session_timeout,
            default_repo=default_repo,
        )

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

        register_endpoints(self)

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
            timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_TIMEOUT_S,
        )
