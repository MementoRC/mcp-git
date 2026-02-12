"""
HTTP Session Manager for MCP Git Server.

This module implements HTTP session management with repository isolation to prevent
cross-session contamination. Each HTTP session gets its own isolated context with
dedicated service instances and repository binding.

Key features:
- Isolated session contexts with unique session IDs
- Per-session GitService and GitHubService instances
- Repository binding with remote URL validation
- Session timeout and automatic cleanup
- Thread-safe session management with asyncio locks
- Remote contamination detection during tool execution

Architecture:
    HTTP Request → SessionManager → SessionContext → Services → Git/GitHub Operations
                                   └─> RepositoryBinding (validation)
"""

import asyncio
import logging
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..lean.interface import GitLeanInterface
from ..repository_binding import (
    RepositoryBinding,
    RepositoryBindingManager,
)
from ..services.git_service import GitService
from ..services.github_service import GitHubService

logger = logging.getLogger(__name__)

__all__ = [
    "SessionContext",
    "HTTPSessionManager",
]


@dataclass
class SessionContext:
    """
    Isolated session context for HTTP sessions.

    Each session gets its own service instances and repository binding to prevent
    cross-session contamination.
    """

    session_id: str
    binding_manager: RepositoryBindingManager
    repository_binding: RepositoryBinding | None
    created_at: float
    last_activity: float
    git_service: GitService
    github_service: GitHubService
    lean_interface: GitLeanInterface = field(init=False)

    def __post_init__(self):
        """Initialize the lean interface for this session."""
        # Create lean interface with session's service instances
        # Note: azure_service is optional and can be None for now
        self.lean_interface = GitLeanInterface(
            git_service=self.git_service,
            github_service=self.github_service,
            azure_service=None,  # Azure service not required for basic operations
            app_name=f"mcp-git-session-{self.session_id}",
        )


class HTTPSessionManager:
    """
    Manages HTTP sessions with repository isolation.

    Provides session lifecycle management including:
    - Session creation with isolated service instances
    - Repository binding with remote validation
    - Tool execution with contamination detection
    - Session cleanup and timeout handling
    """

    def __init__(self, session_timeout: float = 3600.0):
        """
        Initialize HTTP session manager.

        Args:
            session_timeout: Session timeout in seconds (default: 1 hour)
        """
        self.session_timeout = session_timeout
        self._sessions: dict[str, SessionContext] = {}
        self._lock = asyncio.Lock()
        logger.info(
            f"HTTPSessionManager initialized with {session_timeout}s timeout"
        )

    async def create_session(
        self,
        repo_path: Path,
        expected_remote_url: str | None = None,
        session_id: str | None = None,
    ) -> SessionContext:
        """
        Create a new HTTP session with isolated context.

        Each session gets:
        - Unique session ID with "mcp-" prefix (or custom ID if provided)
        - New GitService instance
        - New GitHubService instance
        - New RepositoryBindingManager
        - Repository binding with optional remote validation

        Args:
            repo_path: Path to git repository
            expected_remote_url: Expected remote URL for validation (optional for default sessions)
            session_id: Custom session ID (optional, auto-generated if not provided)

        Returns:
            SessionContext with bound repository

        Raises:
            RepositoryBindingError: If repository binding fails
            RemoteContaminationError: If remote URL doesn't match
        """
        async with self._lock:
            # Use provided session ID or generate a unique one
            if session_id is None:
                session_id = f"mcp-{secrets.token_urlsafe(16)}"

            # Create isolated service instances
            git_service = GitService()
            github_service = GitHubService()

            # Create binding manager for this session
            binding_manager = RepositoryBindingManager(
                server_name=f"http-session-{session_id}"
            )

            # Bind repository with optional remote validation
            repository_binding = await binding_manager.bind_repository(
                repository_path=repo_path,
                expected_remote_url=expected_remote_url,
                verify_remote=expected_remote_url is not None,
            )

            # Create session context
            current_time = time.time()
            session_context = SessionContext(
                session_id=session_id,
                binding_manager=binding_manager,
                repository_binding=repository_binding,
                created_at=current_time,
                last_activity=current_time,
                git_service=git_service,
                github_service=github_service,
            )

            # Store session
            self._sessions[session_id] = session_context

            remote_info = f"with remote {expected_remote_url}" if expected_remote_url else "(no remote validation)"
            logger.info(
                f"Session created: {session_id} for repository {repo_path} "
                f"{remote_info}"
            )

            return session_context

    async def get_session(self, session_id: str) -> SessionContext | None:
        """
        Get session context by ID.

        Updates last activity timestamp if session exists.

        Args:
            session_id: Session identifier

        Returns:
            SessionContext if found, None otherwise
        """
        async with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.last_activity = time.time()
                logger.debug(f"Session accessed: {session_id}")
            else:
                logger.warning(f"Session not found: {session_id}")
            return session

    async def close_session(self, session_id: str) -> bool:
        """
        Close session and unbind repository.

        Args:
            session_id: Session identifier

        Returns:
            True if session was closed, False if not found
        """
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                logger.warning(f"Cannot close non-existent session: {session_id}")
                return False

            # Unbind repository
            await session.binding_manager.unbind_repository()

            # Remove from sessions
            del self._sessions[session_id]

            logger.info(f"Session closed: {session_id}")
            return True

    async def execute_tool(
        self,
        session_id: str,
        tool_name: str,
        args: dict,
    ) -> dict:
        """
        Execute tool with session context and contamination detection.

        Validates:
        1. Session exists
        2. Repository binding integrity
        3. Remote URL hasn't been contaminated

        Args:
            session_id: Session identifier
            tool_name: Tool name to execute
            args: Tool arguments

        Returns:
            Tool execution result

        Raises:
            ValueError: If session not found
            RemoteContaminationError: If remote contamination detected
            RepositoryBindingError: If binding validation fails
        """
        # Get session (updates last_activity)
        session = await self.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        # Validate repository binding integrity
        if session.repository_binding:
            if not session.repository_binding.verify_integrity():
                logger.error(
                    f"Binding integrity check failed for session {session_id}"
                )
                raise ValueError(
                    "Repository binding corrupted - potential tampering detected"
                )

        # Check for remote contamination
        await session.binding_manager.validate_remote_integrity()

        # Validate operation path if provided in args
        if "repo_path" in args:
            operation_path = Path(args["repo_path"])
            session.binding_manager.validate_operation_path(operation_path)

        # Execute tool via session's lean interface
        logger.debug(
            f"Executing tool {tool_name} for session {session_id} with args: {args}"
        )

        # Use the lean interface's execute_tool_direct method
        # This will route to the appropriate handler based on tool name
        result = await session.lean_interface.execute_tool_direct(tool_name, args)

        return result

    async def cleanup_expired_sessions(self) -> int:
        """
        Remove sessions older than timeout.

        Returns:
            Number of sessions cleaned up
        """
        async with self._lock:
            current_time = time.time()
            expired_sessions = []

            for session_id, session in self._sessions.items():
                age = current_time - session.last_activity
                if age > self.session_timeout:
                    expired_sessions.append(session_id)

            # Clean up expired sessions
            for session_id in expired_sessions:
                session = self._sessions[session_id]
                await session.binding_manager.unbind_repository(force=True)
                del self._sessions[session_id]
                logger.info(
                    f"Expired session cleaned up: {session_id} "
                    f"(age: {current_time - session.created_at:.1f}s)"
                )

            if expired_sessions:
                logger.info(
                    f"Cleanup completed: {len(expired_sessions)} sessions removed"
                )

            return len(expired_sessions)

    async def get_session_info(self, session_id: str) -> dict | None:
        """
        Get session information.

        Args:
            session_id: Session identifier

        Returns:
            Session info dictionary or None if not found
        """
        session = await self.get_session(session_id)
        if not session:
            return None

        current_time = time.time()
        return {
            "session_id": session.session_id,
            "created_at": session.created_at,
            "last_activity": session.last_activity,
            "age": current_time - session.created_at,
            "idle_time": current_time - session.last_activity,
            "binding_info": session.binding_manager.get_binding_info(),
        }

    async def get_all_sessions_info(self) -> list[dict]:
        """
        Get information for all active sessions.

        Returns:
            List of session info dictionaries
        """
        async with self._lock:
            session_infos = []
            current_time = time.time()

            for session in self._sessions.values():
                session_infos.append({
                    "session_id": session.session_id,
                    "created_at": session.created_at,
                    "last_activity": session.last_activity,
                    "age": current_time - session.created_at,
                    "idle_time": current_time - session.last_activity,
                    "binding_info": session.binding_manager.get_binding_info(),
                })

            return session_infos
