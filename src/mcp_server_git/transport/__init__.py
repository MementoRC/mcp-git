"""
HTTP Transport for MCP Git Server.

This module provides HTTP transport support for the mcp-git server,
enabling shared server instances across multiple Claude Code sessions
while maintaining strict git repository isolation.

Architecture:
- HTTPGitServer: FastAPI-based HTTP server with MCP protocol support
- HTTPSessionManager: Session-repository binding and isolation
- Security middleware: Localhost-only restriction and API key authentication

Each HTTP session gets:
1. Dedicated MCPGitServerCore instance
2. Dedicated RepositoryBindingManager instance
3. Bound to exactly one repository at session creation
"""

from .http_server import HTTPGitServer
from .http_session_manager import HTTPSessionManager, SessionContext
from .security import APIKeyMiddleware, LocalhostOnlyMiddleware

__all__ = [
    "HTTPGitServer",
    "HTTPSessionManager",
    "SessionContext",
    "LocalhostOnlyMiddleware",
    "APIKeyMiddleware",
]
