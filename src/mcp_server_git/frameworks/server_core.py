"""
Core server logic for the MCP Git Server with Repository Binding.

This module contains the core server initialization, event loop, and request
processing logic extracted from the monolithic server.py file. It implements
the DebuggableComponent protocol for state inspection and debugging.

Enhanced with repository binding architecture to prevent cross-session contamination
as documented in CRITICAL_INCIDENT_REPORT.md.

As specified in the PRD, this module focuses on:
- Server initialization and lifecycle management
- Core request/response processing
- Event loop management
- State inspection capabilities
- Repository binding and remote protection
"""

import asyncio
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import ClientCapabilities

from ..utils.repository_resolver import RepositoryResolver

from ..protocols.debugging_protocol import (
    ComponentState,
    DebuggableComponent,
    DebugInfo,
    ValidationResult,
)
from ..repository_binding import (
    RepositoryBindingManager,
    RepositoryBindingError,
    RemoteContaminationError,
)
from ..protected_git_operations import ProtectedGitOperations

logger = logging.getLogger(__name__)


@dataclass
class ServerComponentState:
    """Implementation of ComponentState for the server core."""

    component_id: str
    component_type: str
    state_data: dict[str, Any]
    last_updated: datetime = field(default_factory=datetime.now)


@dataclass
class ServerValidationResult:
    """Implementation of ValidationResult for the server core."""

    is_valid: bool
    validation_errors: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)
    validation_timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ServerDebugInfo:
    """Implementation of DebugInfo for the server core."""

    debug_level: str
    debug_data: dict[str, Any]
    stack_trace: list[str] | None = None
    performance_metrics: dict[str, int | float] = field(default_factory=dict)


class MCPGitServerCore(DebuggableComponent):
    """
    Enhanced MCP Git Server Core with Repository Binding.

    This class encapsulates the core server logic including initialization,
    lifecycle management, and request processing. Enhanced with repository binding
    architecture to prevent cross-session contamination.

    Key features:
    - Repository binding with remote protection
    - Protected git operations
    - Cross-session contamination prevention
    - Explicit remote change operations
    """

    def __init__(self, server_name: str = "mcp-git"):
        """
        Initialize the server core with repository binding.

        Args:
            server_name: Name identifier for the server
        """
        self.server_name = server_name
        self.server: Server | None = None
        self.repository_path: Path | None = None
        self.is_running = False
        self.start_time: datetime | None = None
        self.error_count = 0
        self.last_error: str | None = None
        self.request_count = 0
        self.client_capabilities: ClientCapabilities | None = None

        # Repository binding components
        self.binding_manager = RepositoryBindingManager(server_name)
        self.repository_resolver: Optional[RepositoryResolver] = None
        self.protected_ops: Optional[ProtectedGitOperations] = None
        
        # Binding failure tracking for user feedback
        self.binding_failed = False
        self.binding_failure_reason: str | None = None

        # State tracking
        self._state_history: list[ComponentState] = []
        self._max_state_history = 100

        logger.info(f"Initialized MCPGitServerCore with repository binding: {server_name}")

    def initialize_server(self, repository_path: Path | None = None) -> Server:
        """
        Initialize the MCP server instance.

        Args:
            repository_path: Optional path to the Git repository

        Returns:
            Initialized Server instance
        """
        if self.server is not None:
            logger.warning("Server already initialized, returning existing instance")
            return self.server

        self.repository_path = repository_path
        self.server = Server(self.server_name)
        self.start_time = datetime.now()

        # Initialize protected operations
        self.protected_ops = ProtectedGitOperations(self.binding_manager)

        logger.info(
            f"Server initialized: {self.server_name} "
            f"(repository: {repository_path or 'None'})"
        )

        # Update state history
        self._update_state_history()

        return self.server

    async def initialize_with_binding(
        self, 
        repository_path: Path, 
        expected_remote_url: str,
        auto_bind: bool = True
    ) -> Server:
        """
        Initialize server with repository binding.
        
        Args:
            repository_path: Path to git repository
            expected_remote_url: Expected remote URL
            auto_bind: Automatically bind to repository
            
        Returns:
            Initialized Server instance
        """
        # Initialize the basic server first
        server = self.initialize_server(repository_path)
        
        if auto_bind:
            try:
                await self.binding_manager.bind_repository(
                    repository_path, 
                    expected_remote_url,
                    verify_remote=True
                )
                
                logger.info(
                    f"Server {self.server_name} initialized and bound to {repository_path}"
                )
            except (RepositoryBindingError, RemoteContaminationError) as e:
                logger.error(f"Failed to bind repository: {e}")
                # Don't fail server initialization, but log the issue and store failure info
                logger.warning("Server initialized without repository binding")
                
                # Store binding failure info for user feedback
                self.binding_failure_reason = str(e)
                self.binding_failed = True
        
        return server

    async def start_server(self, test_mode: bool = False) -> None:
        """
        Start the server and run the main event loop.

        Args:
            test_mode: Whether to run in test mode (exits after brief period)
        """
        if self.server is None:
            raise RuntimeError(
                "Server not initialized. Call initialize_server() first."
            )

        self.is_running = True
        logger.info(f"Starting server in {'test' if test_mode else 'normal'} mode...")

        try:
            # Always run the server with stdio transport (test mode or normal mode)
            # Test mode simply has different timeout/exit behavior
            async with stdio_server() as (read_stream, write_stream):
                logger.info(
                    "🔗 STDIO server connected, starting main loop with enhanced error handling..."
                )

                # Create initialization options with proper configuration
                options = self.server.create_initialization_options()

                try:
                    if test_mode:
                        # Test mode: run server with timeout for E2E testing
                        print("✅ MCP server started successfully", file=sys.stderr)
                        logger.info("🧪 Test mode: MCP server ready for E2E testing")
                        
                        # Create timeout for test mode (longer timeout for E2E tests)
                        timeout_task = asyncio.create_task(asyncio.sleep(60))  # 1 minute for E2E tests
                        server_task = asyncio.create_task(
                            self.server.run(read_stream, write_stream, options, raise_exceptions=False)
                        )
                        
                        # Wait for either server completion or timeout
                        done, pending = await asyncio.wait(
                            {server_task, timeout_task}, return_when=asyncio.FIRST_COMPLETED
                        )
                        
                        # Cancel remaining task
                        for task in pending:
                            task.cancel()
                            try:
                                await task
                            except asyncio.CancelledError:
                                pass
                        
                        # Check which task completed
                        if timeout_task in done:
                            logger.info("🧪 Test mode: Timeout reached, stopping server")
                        else:
                            logger.info("🧪 Test mode: Client disconnected, stopping server")
                    else:
                        # Normal mode: run server until client disconnects
                        await self.server.run(
                            read_stream, write_stream, options, raise_exceptions=False
                        )
                    
                    # If server.run() exits normally, client has disconnected
                    logger.info("🔌 Client disconnected - MCP server run loop completed normally")
                    
                except asyncio.CancelledError:
                    logger.info("🛑 Server cancelled during client session")
                    raise
                except Exception as e:
                    # Log the error but continue to cleanup
                    self.error_count += 1
                    self.last_error = str(e)
                    logger.error(f"💥 Error during MCP server run: {e}")
                    
            # After exiting stdio context, client is definitely disconnected
            logger.info("📡 STDIO transport closed - client session ended")

        except KeyboardInterrupt:
            logger.info("⌨️ Server interrupted by user")
            raise
        except Exception as e:
            self.error_count += 1
            self.last_error = str(e)
            error_msg = str(e).lower()

            # Enhanced error categorization
            if "transport" in error_msg and "closed" in error_msg:
                logger.error(f"🔌 Transport error: {e}")
                logger.info(
                    "🔌 This is often due to client disconnection or tool execution failure - server recovering gracefully"
                )
            elif "gpg" in error_msg:
                logger.error(f"🔒 GPG-related server error: {e}")
                logger.info(
                    "🔒 GPG configuration issue detected - server remains operational"
                )
            elif "notification" in error_msg and "validation" in error_msg:
                logger.warning(f"🔔 Notification validation error: {e}")
                logger.info("🔔 Client notification issue - server continues normally")
            else:
                logger.error(f"💥 Server error: {e}", exc_info=True)
                logger.info("💥 Unexpected server error - attempting graceful recovery")

            # Don't re-raise - let server shutdown gracefully
        finally:
            self.is_running = False
            self._update_state_history()

    def get_server_instance(self) -> Server | None:
        """
        Get the current server instance.

        Returns:
            The Server instance if initialized, None otherwise
        """
        return self.server

    def increment_request_count(self) -> None:
        """Increment the request counter."""
        self.request_count += 1
        self._update_state_history()

    def set_client_capabilities(self, capabilities: ClientCapabilities) -> None:
        """
        Set the client capabilities.

        Args:
            capabilities: Client capabilities from the MCP handshake
        """
        self.client_capabilities = capabilities
        self._update_state_history()

    # Repository Binding Methods

    async def bind_repository(
        self, 
        repository_path: Path, 
        expected_remote_url: str,
        verify_remote: bool = True,
        force: bool = False
    ) -> dict:
        """
        Bind server to repository with remote protection.
        
        Args:
            repository_path: Path to git repository
            expected_remote_url: Expected remote URL for validation
            verify_remote: Verify remote URL matches expectation
            force: Force binding even if already bound
            
        Returns:
            Binding status information
        """
        try:
            await self.binding_manager.bind_repository(
                repository_path, expected_remote_url, verify_remote, force
            )
            self._update_state_history()
            return {
                "status": "bound", 
                "binding": self.binding_manager.get_binding_info()
            }
        except (RepositoryBindingError, RemoteContaminationError) as e:
            self.error_count += 1
            self.last_error = str(e)
            raise

    async def unbind_repository(self, force: bool = False) -> dict:
        """
        Unbind server from repository.
        
        Args:
            force: Force unbind even if operations are in progress
            
        Returns:
            Unbinding status
        """
        try:
            await self.binding_manager.unbind_repository(force)
            self._update_state_history()
            return {"status": "unbound"}
        except RepositoryBindingError as e:
            self.error_count += 1
            self.last_error = str(e)
            raise

    def get_repository_status(self) -> dict:
        """
        Get repository binding status.
        
        Returns:
            Current binding information
        """
        return self.binding_manager.get_binding_info()

    def get_protected_operations(self) -> Optional[ProtectedGitOperations]:
        """
        Get protected git operations instance.
        
        Returns:
            ProtectedGitOperations instance if available
        """
        return self.protected_ops

    def get_binding_status(self) -> dict[str, Any]:
        """
        Get binding status with user-friendly feedback.
        
        Returns:
            Dictionary with binding status and failure information
        """
        binding_info = self.binding_manager.get_binding_info()
        
        result = {
            "bound": binding_info.get("bound", False),
            "binding_failed": self.binding_failed,
            "status": "bound" if binding_info.get("bound", False) else ("failed" if self.binding_failed else "unbound")
        }
        
        if self.binding_failed and self.binding_failure_reason:
            result["failure_reason"] = self.binding_failure_reason
            result["user_message"] = f"Repository binding failed: {self.binding_failure_reason}"
        elif binding_info.get("bound", False):
            result["user_message"] = f"Successfully bound to repository: {binding_info.get('repository_path', 'unknown')}"
        else:
            result["user_message"] = "Repository not bound"
            
        return result

    # DebuggableComponent implementation

    def get_component_state(self) -> ComponentState:
        """Get the current state of the server core with repository binding info."""
        state_data = {
            "server_name": self.server_name,
            "repository_path": str(self.repository_path)
            if self.repository_path
            else None,
            "is_running": self.is_running,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "request_count": self.request_count,
            "client_capabilities": (
                self.client_capabilities.model_dump()
                if self.client_capabilities
                else None
            ),
            "server_initialized": self.server is not None,
            "repository_binding": self.binding_manager.get_binding_info(),
            "protected_operations_available": self.protected_ops is not None,
        }

        return ServerComponentState(
            component_id=f"server-core-{self.server_name}",
            component_type="MCPGitServerCore",
            state_data=state_data,
            last_updated=datetime.now(),
        )

    def validate_component(self) -> ValidationResult:
        """Validate the current state and configuration of the server core."""
        errors = []
        warnings = []

        # Check server initialization
        if self.server is None:
            errors.append("Server not initialized")

        # Check repository path if specified
        if self.repository_path and not self.repository_path.exists():
            errors.append(f"Repository path does not exist: {self.repository_path}")

        # Check repository binding validation
        binding_info = self.binding_manager.get_binding_info()
        if binding_info["state"] == "corrupted":
            errors.append("Repository binding corrupted - potential tampering detected")
        elif binding_info["state"] == "unbound" and self.repository_path:
            warnings.append("Repository specified but not bound - operations may be unprotected")

        # Check protected operations availability
        if self.protected_ops is None and binding_info["state"] == "bound":
            errors.append("Repository bound but protected operations not available")

        # Check error rate
        if self.error_count > 100:
            warnings.append(f"High error count: {self.error_count}")

        # Check if server is stuck
        if self.is_running and self.request_count == 0 and self.start_time:
            uptime = (datetime.now() - self.start_time).total_seconds()
            if uptime > 300:  # 5 minutes
                warnings.append("Server running but no requests processed")

        return ServerValidationResult(
            is_valid=len(errors) == 0,
            validation_errors=errors,
            validation_warnings=warnings,
            validation_timestamp=datetime.now(),
        )

    def get_debug_info(self, debug_level: str = "INFO") -> DebugInfo:
        """Get debug information for the server core."""
        debug_data = {
            "server_state": self.get_component_state().state_data,
            "state_history_size": len(self._state_history),
            "python_version": sys.version,
            "platform": sys.platform,
        }

        performance_metrics = {
            "request_count": self.request_count,
            "error_count": self.error_count,
            "uptime_seconds": (
                (datetime.now() - self.start_time).total_seconds()
                if self.start_time
                else 0
            ),
            "requests_per_minute": (
                self.request_count
                / max(1, (datetime.now() - self.start_time).total_seconds() / 60)
                if self.start_time
                else 0
            ),
        }

        return ServerDebugInfo(
            debug_level=debug_level,
            debug_data=debug_data,
            stack_trace=None,
            performance_metrics=performance_metrics,
        )

    def inspect_state(self, path: str | None = None) -> dict[str, Any]:
        """Inspect specific parts of the component state."""
        state = self.get_component_state().state_data

        if path is None:
            return state

        # Navigate the state using dot notation
        parts = path.split(".")
        current = state

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                raise KeyError(f"Path '{path}' not found in state")

        return {path: current}

    def get_component_dependencies(self) -> list[str]:
        """Get list of component dependencies."""
        return ["mcp.server", "mcp.server.stdio", "logging", "asyncio"]

    def export_state_json(self) -> str:
        """Export component state as JSON for external analysis."""
        state = self.get_component_state()
        export_data = {
            "component_id": state.component_id,
            "component_type": state.component_type,
            "state_data": state.state_data,
            "last_updated": state.last_updated.isoformat(),
            "validation": self.validate_component().__dict__,
            "debug_info": self.get_debug_info().__dict__,
        }

        # Convert datetime objects
        def datetime_handler(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        return json.dumps(export_data, indent=2, default=datetime_handler)

    def health_check(self) -> dict[str, bool | str | int | float]:
        """Perform a health check on the server core."""
        validation = self.validate_component()
        uptime = (
            (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        )

        health_status = {
            "healthy": validation.is_valid and self.is_running,
            "status": (
                "running"
                if self.is_running
                else "stopped"
                if self.server is not None
                else "not_initialized"
            ),
            "uptime": uptime,
            "last_error": self.last_error or "none",
            "error_count": self.error_count,
            "request_count": self.request_count,
            "validation_errors": len(validation.validation_errors),
            "validation_warnings": len(validation.validation_warnings),
        }

        return health_status

    # Private methods

    def _update_state_history(self) -> None:
        """Update the state history with current state."""
        current_state = self.get_component_state()
        self._state_history.append(current_state)

        # Trim history if needed
        if len(self._state_history) > self._max_state_history:
            self._state_history = self._state_history[-self._max_state_history :]

    def get_state_history(self, limit: int = 10) -> list[ComponentState]:
        """
        Get historical state information.

        Args:
            limit: Maximum number of historical states to return

        Returns:
            List of historical ComponentState objects, newest first
        """
        return list(reversed(self._state_history[-limit:]))
