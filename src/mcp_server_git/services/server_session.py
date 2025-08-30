"""Session service for MCP Git Server.

This module provides a service layer for session management functionality,
extracting session-related logic from the monolithic server.py file and
providing a clean interface for session lifecycle management.

The SessionService class integrates with the existing session management
infrastructure while providing service-level validation, error handling,
and debugging capabilities.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server.session import ServerSession
from mcp.types import ClientCapabilities, ListRootsResult, RootsCapability

from ..protocols.debugging_protocol import (
    ComponentState,
    DebuggableComponent,
    DebugInfo,
    ValidationResult,
)
from ..session import Session, SessionManager

logger = logging.getLogger(__name__)


@dataclass
class SessionServiceState:
    """Implementation of ComponentState for the session service."""

    component_id: str
    component_type: str
    state_data: dict[str, Any]
    last_updated: datetime = field(default_factory=datetime.now)


@dataclass
class SessionServiceValidationResult:
    """Implementation of ValidationResult for the session service."""

    is_valid: bool
    validation_errors: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)
    validation_timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class SessionServiceDebugInfo:
    """Implementation of DebugInfo for the session service."""

    debug_level: str
    debug_data: dict[str, Any]
    stack_trace: list[str] | None = None
    performance_metrics: dict[str, int | float] = field(default_factory=dict)


class SessionService(DebuggableComponent):
    """Service layer for session management in MCP Git Server.

    This service provides a high-level interface for session management,
    integrating with the existing session infrastructure while adding
    service-level validation, error handling, and debugging capabilities.

    The service acts as a bridge between the server components and the
    underlying session management, providing operations for:
    - Session lifecycle management
    - Server session validation
    - Client capability checking
    - Repository access validation
    - State inspection and debugging
    """

    def __init__(
        self,
        idle_timeout: float = 900.0,
        heartbeat_timeout: float = 60.0,
        service_id: str = "session_service",
    ):
        """Initialize the session service.

        Args:
            idle_timeout: Default idle timeout for sessions (seconds)
            heartbeat_timeout: Default heartbeat timeout for sessions (seconds)
            service_id: Unique identifier for this service instance
        """
        self.service_id = service_id
        self.session_manager = SessionManager(idle_timeout, heartbeat_timeout)
        self.is_running = False
        self.start_time: datetime | None = None
        self.error_count = 0
        self.last_error: str | None = None
        self.operation_count = 0

        # State tracking for debugging
        self._state_history: list[ComponentState] = []
        self._max_state_history = 100

        logger.info(f"SessionService initialized with ID: {service_id}")

    async def start(self) -> None:
        """Start the session service."""
        if self.is_running:
            logger.warning(f"SessionService {self.service_id} is already running")
            return

        self.is_running = True
        self.start_time = datetime.now()

        # Initialize heartbeat manager if needed
        if not self.session_manager.heartbeat_manager:
            from ..session import HeartbeatManager

            self.session_manager.heartbeat_manager = HeartbeatManager(
                self.session_manager
            )
            await self.session_manager.heartbeat_manager.start()

        # Restore any persisted sessions
        await self.session_manager.restore_sessions()

        logger.info(f"SessionService {self.service_id} started")

    async def stop(self) -> None:
        """Stop the session service."""
        if not self.is_running:
            logger.warning(f"SessionService {self.service_id} is not running")
            return

        # Gracefully shutdown session manager
        await self.session_manager.shutdown()

        self.is_running = False
        logger.info(f"SessionService {self.service_id} stopped")

    async def create_session(
        self,
        session_id: str,
        user: str | None = None,
        repository: Path | None = None,
    ) -> Session:
        """Create a new session with validation.

        Args:
            session_id: Unique identifier for the session
            user: Optional user identifier
            repository: Optional repository path

        Returns:
            Created session instance

        Raises:
            RuntimeError: If service is not running or session creation fails
        """
        if not self.is_running:
            raise RuntimeError("SessionService is not running")

        try:
            self.operation_count += 1
            session = await self.session_manager.create_session(
                session_id, user, repository
            )

            logger.info(f"SessionService created session {session_id} for user {user}")
            return session

        except Exception as e:
            self.error_count += 1
            self.last_error = str(e)
            logger.error(f"Failed to create session {session_id}: {e}")
            raise

    async def get_session(self, session_id: str) -> Session | None:
        """Get an existing session by ID."""
        if not self.is_running:
            raise RuntimeError("SessionService is not running")

        return await self.session_manager.get_session(session_id)

    async def close_session(self, session_id: str) -> None:
        """Close a session by ID."""
        if not self.is_running:
            raise RuntimeError("SessionService is not running")

        try:
            await self.session_manager.close_session(session_id)
            logger.info(f"SessionService closed session {session_id}")

        except Exception as e:
            self.error_count += 1
            self.last_error = str(e)
            logger.error(f"Failed to close session {session_id}: {e}")
            raise

    async def validate_server_session(
        self, server_session: ServerSession | None
    ) -> bool:
        """Validate a server session instance.

        This method extracts the server session validation logic from server.py,
        providing a centralized place for session validation.

        Args:
            server_session: The server session to validate

        Returns:
            True if session is valid, False otherwise
        """
        if not isinstance(server_session, ServerSession):
            logger.warning(
                f"Invalid server session type: {type(server_session)}, "
                "expected ServerSession"
            )
            return False

        return True

    async def check_client_capability(
        self, server_session: ServerSession, capability_type: str = "roots"
    ) -> bool:
        """Check if client has specific capabilities.

        This method extracts client capability checking from server.py.

        Args:
            server_session: The server session to check
            capability_type: Type of capability to check

        Returns:
            True if client has capability, False otherwise
        """
        try:
            if capability_type == "roots":
                return server_session.check_client_capability(
                    ClientCapabilities(roots=RootsCapability())
                )

            # Add other capability types as needed
            logger.warning(f"Unknown capability type: {capability_type}")
            return False

        except Exception as e:
            logger.error(f"Error checking client capability {capability_type}: {e}")
            return False

    async def list_repository_roots(self, server_session: ServerSession) -> list[str]:
        """List repository roots from client capabilities.

        This method extracts the repository listing logic from server.py.

        Args:
            server_session: The server session to query

        Returns:
            List of repository paths
        """
        try:
            # Validate session and capabilities
            if not await self.validate_server_session(server_session):
                return []

            if not await self.check_client_capability(server_session, "roots"):
                return []

            # Get roots from client
            roots_result: ListRootsResult = await server_session.list_roots()
            logger.debug(f"Roots result: {roots_result}")

            # Extract and validate repository paths
            repo_paths = []
            for root in roots_result.roots:
                path = root.uri.path
                try:
                    # Validate that path is a git repository
                    import git

                    git.Repo(path)
                    repo_paths.append(str(path))
                except git.InvalidGitRepositoryError:
                    logger.debug(f"Skipping non-git path: {path}")
                    pass

            return repo_paths

        except Exception as e:
            self.error_count += 1
            self.last_error = str(e)
            logger.error(f"Error listing repository roots: {e}")
            return []

    async def get_session_metrics(self) -> dict[str, Any]:
        """Get comprehensive session metrics."""
        if not self.is_running:
            raise RuntimeError("SessionService is not running")

        session_metrics = await self.session_manager.get_metrics()

        return {
            "service_id": self.service_id,
            "service_running": self.is_running,
            "service_uptime": (
                (datetime.now() - self.start_time).total_seconds()
                if self.start_time
                else 0
            ),
            "operation_count": self.operation_count,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "session_count": len(session_metrics),
            "session_metrics": session_metrics,
        }

    async def cleanup_idle_sessions(self) -> None:
        """Clean up idle sessions."""
        if not self.is_running:
            raise RuntimeError("SessionService is not running")

        await self.session_manager.cleanup_idle_sessions()

    # DebuggableComponent implementation

    def get_component_state(self) -> ComponentState:
        """Get current component state for debugging."""
        state_data = {
            "service_id": self.service_id,
            "is_running": self.is_running,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "operation_count": self.operation_count,
            "error_count": self.error_count,
            "last_error": self.last_error,
        }

        state = SessionServiceState(
            component_id=self.service_id,
            component_type="SessionService",
            state_data=state_data,
        )

        # Add to state history
        self._state_history.append(state)
        if len(self._state_history) > self._max_state_history:
            self._state_history = self._state_history[-self._max_state_history :]

        return state

    def validate_component(self) -> ValidationResult:
        """Validate component state and configuration."""
        errors = []
        warnings = []

        # Check if service is in valid state
        if not self.session_manager:
            errors.append("SessionManager is not initialized")

        if self.is_running and not self.start_time:
            warnings.append("Service is running but start_time is not set")

        if self.error_count > 10:
            warnings.append(f"High error count: {self.error_count}")

        return SessionServiceValidationResult(
            is_valid=len(errors) == 0,
            validation_errors=errors,
            validation_warnings=warnings,
        )

    def get_debug_info(self) -> DebugInfo:
        """Get detailed debug information."""
        debug_data = {
            "service_id": self.service_id,
            "is_running": self.is_running,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "operation_count": self.operation_count,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "state_history_size": len(self._state_history),
        }

        performance_metrics = {
            "uptime_seconds": (
                (datetime.now() - self.start_time).total_seconds()
                if self.start_time
                else 0
            ),
            "operations_per_second": (
                self.operation_count
                / (datetime.now() - self.start_time).total_seconds()
                if self.start_time and self.operation_count > 0
                else 0
            ),
            "error_rate": (
                self.error_count / self.operation_count
                if self.operation_count > 0
                else 0
            ),
        }

        return SessionServiceDebugInfo(
            debug_level="detailed",
            debug_data=debug_data,
            performance_metrics=performance_metrics,
        )

    def inspect_state(self, path: str | None = None) -> dict[str, Any]:
        """Inspect specific component state by path."""
        if path is None:
            # Return full state
            return {
                "component_state": self.get_component_state(),
                "validation_result": self.validate_component(),
                "debug_info": self.get_debug_info(),
            }

        # Handle specific path inspection
        parts = path.split(".")

        if parts[0] == "state":
            return self.get_component_state().state_data
        if parts[0] == "validation":
            validation = self.validate_component()
            return {
                "is_valid": validation.is_valid,
                "errors": validation.validation_errors,
                "warnings": validation.validation_warnings,
            }
        if parts[0] == "debug":
            return self.get_debug_info().debug_data
        if parts[0] == "metrics":
            return self.get_debug_info().performance_metrics
        return {"error": f"Unknown inspection path: {path}"}

    def get_component_dependencies(self) -> list[str]:
        """Get list of component dependencies."""
        return [
            "session.SessionManager",
            "session.HeartbeatManager",
            "mcp.server.session.ServerSession",
            "protocols.debugging_protocol.DebuggableComponent",
        ]

    def export_state_json(self) -> str:
        """Export component state as JSON."""
        import json

        state_data = {
            "component_state": {
                "component_id": self.service_id,
                "component_type": "SessionService",
                "state_data": self.get_component_state().state_data,
                "last_updated": datetime.now().isoformat(),
            },
            "validation_result": {
                "is_valid": self.validate_component().is_valid,
                "validation_errors": self.validate_component().validation_errors,
                "validation_warnings": self.validate_component().validation_warnings,
                "validation_timestamp": datetime.now().isoformat(),
            },
            "debug_info": {
                "debug_level": "detailed",
                "debug_data": self.get_debug_info().debug_data,
                "performance_metrics": self.get_debug_info().performance_metrics,
            },
        }

        return json.dumps(state_data, indent=2, default=str)

    def health_check(self) -> dict[str, Any]:
        """Perform health check on the service."""
        validation = self.validate_component()

        health_status = "healthy"
        if not validation.is_valid:
            health_status = "unhealthy"
        elif validation.validation_warnings:
            health_status = "degraded"

        return {
            "service_id": self.service_id,
            "status": health_status,
            "is_running": self.is_running,
            "uptime_seconds": (
                (datetime.now() - self.start_time).total_seconds()
                if self.start_time
                else 0
            ),
            "operation_count": self.operation_count,
            "error_count": self.error_count,
            "error_rate": (
                self.error_count / self.operation_count
                if self.operation_count > 0
                else 0
            ),
            "validation_errors": validation.validation_errors,
            "validation_warnings": validation.validation_warnings,
            "last_error": self.last_error,
        }
