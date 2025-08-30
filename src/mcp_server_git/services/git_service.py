"""Git service implementation for MCP Git Server.

This module provides a comprehensive Git service that orchestrates Git operations
and primitives to deliver complete Git repository management capabilities.
The service provides high-level interfaces, handles authentication, validation,
error recovery, and state management.

Design principles:
    - Complete functionality: End-to-end Git repository management
    - State management: Maintains operational state and configuration
    - Error recovery: Robust error handling and graceful degradation
    - Observability: Comprehensive metrics and debugging support
    - Testability: Extensive test coverage and mocking support

Critical for TDD Compliance:
    This service implements the interface defined by test specifications.
    DO NOT modify tests to match this implementation - this implementation
    must satisfy the test requirements to prevent LLM compliance issues.
"""

import asyncio
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any

from ..operations.git_operations import (
    BranchRequest,
    CommitRequest,
    MergeRequest,
    commit_changes_with_validation,
    create_branch_with_checkout,
    merge_branches_with_conflict_detection,
    push_with_validation,
)
from ..primitives.git_primitives import (
    GitValidationError,
    get_repository_status,
)
from ..protocols.debugging_protocol import DebuggableComponent

logger = logging.getLogger(__name__)


@dataclass
class GitServiceConfig:
    """Configuration for GitService."""

    max_concurrent_operations: int = 10
    operation_timeout_seconds: int = 300
    enable_security_validation: bool = True
    enable_performance_monitoring: bool = True
    enable_state_history: bool = True
    max_state_history_entries: int = 100
    default_remote: str = "origin"
    auto_push_after_commit: bool = False
    gpg_signing_enabled: bool = False
    gpg_key_id: str | None = None


@dataclass
class GitOperationResult:
    """Result of a Git service operation."""

    success: bool
    operation_type: str
    repository_path: str
    result_data: dict[str, Any] | None = None
    error_message: str | None = None
    duration_seconds: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class GitServiceState:
    """Internal state of GitService."""

    service_id: str
    started_at: datetime
    operation_count: int = 0
    error_count: int = 0
    last_operation: GitOperationResult | None = None
    active_operations: int = 0
    configuration: GitServiceConfig = field(default_factory=GitServiceConfig)
    performance_metrics: dict[str, int | float] = field(default_factory=dict)


class GitService(DebuggableComponent):
    """Comprehensive Git service providing high-level Git repository management.

    This service orchestrates Git operations and primitives to provide complete
    Git functionality including repository management, branch operations,
    commit management, and remote synchronization.

    Features:
        - Asynchronous operation support
        - Concurrent operation management
        - Comprehensive error handling and recovery
        - State management and inspection
        - Performance monitoring and metrics
        - Security validation and authentication
        - Debugging and introspection capabilities

    Example:
        >>> config = GitServiceConfig(
        ...     max_concurrent_operations=5,
        ...     enable_security_validation=True
        ... )
        >>> service = GitService(config)
        >>> await service.start()
        >>>
        >>> result = await service.commit_changes(
        ...     "/path/to/repo",
        ...     "feat: add new feature",
        ...     files=["src/feature.py"]
        ... )
        >>> print(result.success)
        True
    """

    def __init__(self, config: GitServiceConfig | None = None):
        """Initialize GitService with configuration.

        Args:
            config: Service configuration, defaults to GitServiceConfig()
        """
        self._config = config or GitServiceConfig()
        self._service_id = f"git_service_{int(time.time())}"
        self._state = GitServiceState(
            service_id=self._service_id,
            started_at=datetime.now(),
            configuration=self._config,
        )
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, self._config.max_concurrent_operations)
        )
        self._operation_lock = Lock()
        self._state_history: list[GitServiceState] = []
        self._is_started = False
        self._total_duration: float = 0.0

        logger.info(f"GitService initialized with ID: {self._service_id}")

    async def start(self) -> None:
        """Start the Git service.

        Initializes the service, validates configuration, and prepares
        for operation execution.

        Raises:
            GitValidationError: If service configuration is invalid
        """
        if self._is_started:
            logger.warning("GitService already started")
            return

        logger.info(f"Starting GitService {self._service_id}")

        # Validate configuration
        self._validate_configuration()

        # Initialize performance metrics
        self._state.performance_metrics = {
            "operations_per_second": 0.0,
            "average_operation_duration": 0.0,
            "success_rate": 1.0,
            "concurrent_operations_peak": 0,
        }

        # Save initial state
        if self._config.enable_state_history:
            self._save_state_snapshot()

        self._is_started = True
        logger.info(f"GitService {self._service_id} started successfully")

    async def stop(self) -> None:
        """Stop the Git service gracefully.

        Waits for active operations to complete and shuts down the service.
        """
        if not self._is_started:
            logger.warning("GitService not started")
            return

        logger.info(f"Stopping GitService {self._service_id}")

        # Wait for active operations to complete
        while self._state.active_operations > 0:
            logger.info(
                f"Waiting for {self._state.active_operations} active operations to complete"
            )
            await asyncio.sleep(0.1)

        # Shutdown executor
        self._executor.shutdown(wait=True)

        self._is_started = False
        logger.info(f"GitService {self._service_id} stopped")

    async def commit_changes(
        self,
        repository_path: str | Path,
        message: str,
        files: list[str] | None = None,
        author: str | None = None,
        email: str | None = None,
        auto_push: bool | None = None,
    ) -> GitOperationResult:
        """Commit changes to a Git repository.

        Args:
            repository_path: Path to the Git repository
            message: Commit message
            files: Optional list of files to commit
            author: Optional commit author name
            email: Optional commit author email
            auto_push: Optional flag to push after commit

        Returns:
            GitOperationResult with operation details and result

        Example:
            >>> result = await service.commit_changes(
            ...     "/path/to/repo",
            ...     "feat: add new feature",
            ...     files=["src/feature.py"],
            ...     author="Developer",
            ...     email="dev@example.com"
            ... )
            >>> print(result.success)
            True
        """
        start_time = time.time()
        operation_type = "commit_changes"

        try:
            self._ensure_started()
            await self._acquire_operation_slot()

            logger.info(f"Starting commit operation for repository: {repository_path}")

            # Create commit request
            commit_request = CommitRequest(
                message=message,
                files=files,
                author=author,
                email=email,
                gpg_sign=self._config.gpg_signing_enabled,
                gpg_key_id=self._config.gpg_key_id,
            )

            # Execute commit operation
            loop = asyncio.get_event_loop()
            commit_result = await loop.run_in_executor(
                self._executor,
                commit_changes_with_validation,
                repository_path,
                commit_request,
            )

            # Handle auto-push if enabled
            if (
                auto_push or self._config.auto_push_after_commit
            ) and commit_result.success:
                logger.info("Auto-push enabled, pushing changes")
                push_result = await self._push_changes(repository_path)
                if not push_result["success"]:
                    logger.warning(f"Auto-push failed: {push_result['error']}")

            # Create operation result
            result = GitOperationResult(
                success=commit_result.success,
                operation_type=operation_type,
                repository_path=str(repository_path),
                result_data={
                    "commit_hash": commit_result.commit_hash,
                    "files_committed": commit_result.files_committed,
                    "message": commit_result.message,
                },
                error_message=commit_result.error,
                duration_seconds=time.time() - start_time,
            )

            await self._record_operation_result(result)
            return result

        except Exception as e:
            logger.error(f"Commit operation failed: {e}")
            result = GitOperationResult(
                success=False,
                operation_type=operation_type,
                repository_path=str(repository_path),
                error_message=str(e),
                duration_seconds=time.time() - start_time,
            )
            await self._record_operation_result(result)
            return result
        finally:
            await self._release_operation_slot()

    async def create_branch(
        self,
        repository_path: str | Path,
        branch_name: str,
        base_branch: str | None = None,
        checkout: bool = True,
        force: bool = False,
    ) -> GitOperationResult:
        """Create a new Git branch.

        Args:
            repository_path: Path to the Git repository
            branch_name: Name of the new branch
            base_branch: Base branch for new branch (default: current branch)
            checkout: Whether to checkout the new branch
            force: Whether to force branch creation

        Returns:
            GitOperationResult with operation details and result
        """
        start_time = time.time()
        operation_type = "create_branch"

        try:
            self._ensure_started()
            await self._acquire_operation_slot()

            logger.info(
                f"Creating branch '{branch_name}' in repository: {repository_path}"
            )

            # Create branch request
            branch_request = BranchRequest(
                name=branch_name,
                base_branch=base_branch,
                checkout=checkout,
                force=force,
            )

            # Execute branch creation
            loop = asyncio.get_event_loop()
            branch_result = await loop.run_in_executor(
                self._executor,
                create_branch_with_checkout,
                repository_path,
                branch_request,
            )

            # Create operation result
            result = GitOperationResult(
                success=branch_result.success,
                operation_type=operation_type,
                repository_path=str(repository_path),
                result_data={
                    "branch_name": branch_result.branch_name,
                    "previous_branch": branch_result.previous_branch,
                    "message": branch_result.message,
                },
                error_message=branch_result.error,
                duration_seconds=time.time() - start_time,
            )

            await self._record_operation_result(result)
            return result

        except Exception as e:
            logger.error(f"Branch creation failed: {e}")
            result = GitOperationResult(
                success=False,
                operation_type=operation_type,
                repository_path=str(repository_path),
                error_message=str(e),
                duration_seconds=time.time() - start_time,
            )
            await self._record_operation_result(result)
            return result
        finally:
            await self._release_operation_slot()

    async def merge_branches(
        self,
        repository_path: str | Path,
        source_branch: str,
        target_branch: str | None = None,
        message: str | None = None,
        no_fast_forward: bool = False,
        squash: bool = False,
    ) -> GitOperationResult:
        """Merge Git branches.

        Args:
            repository_path: Path to the Git repository
            source_branch: Source branch to merge from
            target_branch: Target branch to merge into (default: current branch)
            message: Optional merge commit message
            no_fast_forward: Whether to create merge commit even for fast-forward
            squash: Whether to squash commits during merge

        Returns:
            GitOperationResult with operation details and result
        """
        start_time = time.time()
        operation_type = "merge_branches"

        try:
            self._ensure_started()
            await self._acquire_operation_slot()

            logger.info(f"Merging '{source_branch}' in repository: {repository_path}")

            # Create merge request
            merge_request = MergeRequest(
                source_branch=source_branch,
                target_branch=target_branch,
                message=message,
                no_fast_forward=no_fast_forward,
                squash=squash,
            )

            # Execute merge operation
            loop = asyncio.get_event_loop()
            merge_result = await loop.run_in_executor(
                self._executor,
                merge_branches_with_conflict_detection,
                repository_path,
                merge_request,
            )

            # Create operation result
            result = GitOperationResult(
                success=merge_result.success,
                operation_type=operation_type,
                repository_path=str(repository_path),
                result_data={
                    "merge_commit_hash": merge_result.merge_commit_hash,
                    "conflicts": merge_result.conflicts,
                    "message": merge_result.message,
                },
                error_message=merge_result.error,
                duration_seconds=time.time() - start_time,
            )

            await self._record_operation_result(result)
            return result

        except Exception as e:
            logger.error(f"Merge operation failed: {e}")
            result = GitOperationResult(
                success=False,
                operation_type=operation_type,
                repository_path=str(repository_path),
                error_message=str(e),
                duration_seconds=time.time() - start_time,
            )
            await self._record_operation_result(result)
            return result
        finally:
            await self._release_operation_slot()

    async def get_repository_status(
        self, repository_path: str | Path
    ) -> GitOperationResult:
        """Get comprehensive repository status.

        Args:
            repository_path: Path to the Git repository

        Returns:
            GitOperationResult with repository status information
        """
        start_time = time.time()
        operation_type = "get_repository_status"

        try:
            self._ensure_started()
            await self._acquire_operation_slot()

            logger.debug(f"Getting status for repository: {repository_path}")

            # Execute status operation
            loop = asyncio.get_event_loop()
            status_result = await loop.run_in_executor(
                self._executor, get_repository_status, str(repository_path)
            )

            # Create operation result
            result = GitOperationResult(
                success=True,
                operation_type=operation_type,
                repository_path=str(repository_path),
                result_data={"status": status_result},
                duration_seconds=time.time() - start_time,
            )

            await self._record_operation_result(result)
            return result

        except Exception as e:
            logger.error(f"Status operation failed: {e}")
            result = GitOperationResult(
                success=False,
                operation_type=operation_type,
                repository_path=str(repository_path),
                error_message=str(e),
                duration_seconds=time.time() - start_time,
            )
            await self._record_operation_result(result)
            return result
        finally:
            await self._release_operation_slot()

    # DebuggableComponent protocol implementation
    def get_component_state(self):
        """Get the current state of the GitService component."""
        from dataclasses import asdict

        class GitServiceComponentState:
            def __init__(self, state: GitServiceState):
                self._state = state

            @property
            def component_id(self) -> str:
                return self._state.service_id

            @property
            def component_type(self) -> str:
                return "GitService"

            @property
            def state_data(self) -> dict[str, Any]:
                return asdict(self._state)

            @property
            def last_updated(self) -> datetime:
                return datetime.now()

        return GitServiceComponentState(self._state)

    def validate_component(self):
        """Validate the current state and configuration of the GitService."""

        class GitServiceValidationResult:
            def __init__(self, is_valid: bool, errors: list[str], warnings: list[str]):
                self._is_valid = is_valid
                self._errors = errors
                self._warnings = warnings
                self._timestamp = datetime.now()

            @property
            def is_valid(self) -> bool:
                return self._is_valid

            @property
            def validation_errors(self) -> list[str]:
                return self._errors

            @property
            def validation_warnings(self) -> list[str]:
                return self._warnings

            @property
            def validation_timestamp(self) -> datetime:
                return self._timestamp

        errors = []
        warnings = []

        # Validate configuration
        if self._config.max_concurrent_operations <= 0:
            errors.append("max_concurrent_operations must be positive")

        if self._config.operation_timeout_seconds <= 0:
            errors.append("operation_timeout_seconds must be positive")

        # Validate service state
        if not self._is_started and self._state.active_operations > 0:
            warnings.append("Service not started but has active operations")

        if self._state.error_count > self._state.operation_count * 0.5:
            warnings.append("High error rate detected")

        return GitServiceValidationResult(len(errors) == 0, errors, warnings)

    def get_debug_info(self, debug_level: str = "INFO"):
        """Get debug information for the GitService."""

        class GitServiceDebugInfo:
            def __init__(
                self, debug_level: str, state: GitServiceState, is_started: bool
            ):
                self._debug_level = debug_level
                self._state = state
                self._is_started = is_started

            @property
            def debug_level(self) -> str:
                return self._debug_level

            @property
            def debug_data(self) -> dict[str, Any]:
                return {
                    "service_id": self._state.service_id,
                    "is_started": self._is_started,
                    "configuration": self._state.configuration.__dict__,
                    "operation_statistics": {
                        "total_operations": self._state.operation_count,
                        "error_count": self._state.error_count,
                        "active_operations": self._state.active_operations,
                    },
                }

            @property
            def stack_trace(self) -> list[str] | None:
                return None  # No stack trace for normal operation

            @property
            def performance_metrics(self) -> dict[str, int | float]:
                return self._state.performance_metrics.copy()

        return GitServiceDebugInfo(debug_level, self._state, self._is_started)

    def inspect_state(self, path: str | None = None) -> dict[str, Any]:
        """Inspect specific parts of the GitService state."""
        state_dict = {
            "service_id": self._state.service_id,
            "started_at": self._state.started_at.isoformat(),
            "is_started": self._is_started,
            "operation_count": self._state.operation_count,
            "error_count": self._state.error_count,
            "active_operations": self._state.active_operations,
            "configuration": self._state.configuration.__dict__,
            "performance_metrics": self._state.performance_metrics,
            "last_operation": (
                self._state.last_operation.__dict__
                if self._state.last_operation
                else None
            ),
        }

        if path is None:
            return state_dict

        # Navigate to specific path
        keys = path.split(".")
        current: Any = state_dict
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return {"error": f"Path '{path}' not found"}

        # Ensure we return the expected format
        if not isinstance(current, dict):
            current = {"value": current}

        return {path: current}

    def get_component_dependencies(self) -> list[str]:
        """Get list of GitService dependencies."""
        return [
            "git_operations",
            "git_primitives",
            "thread_pool_executor",
            "asyncio_event_loop",
        ]

    def export_state_json(self) -> str:
        """Export GitService state as JSON."""
        state_data = self.inspect_state()
        # Convert datetime objects to ISO format for JSON serialization
        if "started_at" in state_data:
            state_data["started_at"] = self._state.started_at.isoformat()
        if (
            "last_operation" in state_data
            and state_data["last_operation"]
            and self._state.last_operation
        ):
            state_data["last_operation"]["timestamp"] = (
                self._state.last_operation.timestamp.isoformat()
            )

        return json.dumps(state_data, indent=2, default=str)

    def health_check(self) -> dict[str, bool | str | int | float]:
        """Perform a health check on the GitService."""
        uptime = (datetime.now() - self._state.started_at).total_seconds()
        error_rate = self._state.error_count / max(self._state.operation_count, 1) * 100

        healthy = (
            self._is_started
            and self._state.active_operations < self._config.max_concurrent_operations
            and error_rate < 50.0
        )

        status = "healthy" if healthy else "unhealthy"
        if not self._is_started:
            status = "not_started"
        elif error_rate >= 50.0:
            status = "high_error_rate"

        return {
            "healthy": healthy,
            "status": status,
            "uptime": uptime,
            "last_error": (
                self._state.last_operation.error_message
                if self._state.last_operation
                and self._state.last_operation.error_message
                else ""
            ),
            "error_count": self._state.error_count,
            "error_rate": error_rate,
            "active_operations": self._state.active_operations,
        }

    # Private helper methods
    def _ensure_started(self) -> None:
        """Ensure the service is started."""
        if not self._is_started:
            raise GitValidationError("GitService not started")

    async def _acquire_operation_slot(self) -> None:
        """Acquire a slot for operation execution."""
        while self._state.active_operations >= self._config.max_concurrent_operations:
            await asyncio.sleep(0.01)

        with self._operation_lock:
            self._state.active_operations += 1
            self._state.performance_metrics["concurrent_operations_peak"] = max(
                self._state.performance_metrics.get("concurrent_operations_peak", 0),
                self._state.active_operations,
            )

    async def _release_operation_slot(self) -> None:
        """Release an operation slot."""
        with self._operation_lock:
            self._state.active_operations = max(0, self._state.active_operations - 1)

    async def _record_operation_result(self, result: GitOperationResult) -> None:
        """Record the result of an operation."""
        with self._operation_lock:
            self._state.operation_count += 1
            if not result.success:
                self._state.error_count += 1

            self._state.last_operation = result

            # Update performance metrics
            if self._config.enable_performance_monitoring:
                self._update_performance_metrics(result)

            # Save state snapshot
            if self._config.enable_state_history:
                self._save_state_snapshot()

    def _update_performance_metrics(self, result: GitOperationResult) -> None:
        """Update performance metrics based on operation result."""
        # Calculate operations per second
        uptime = (datetime.now() - self._state.started_at).total_seconds()
        ops_per_second = self._state.operation_count / max(uptime, 1)

        # Calculate average operation duration
        if hasattr(self, "_total_duration"):
            self._total_duration += result.duration_seconds
        else:
            self._total_duration = result.duration_seconds

        avg_duration = self._total_duration / self._state.operation_count

        # Calculate success rate
        success_rate = (
            (self._state.operation_count - self._state.error_count)
            / self._state.operation_count
            * 100
        )

        self._state.performance_metrics.update(
            {
                "operations_per_second": ops_per_second,
                "average_operation_duration": avg_duration,
                "success_rate": success_rate,
            }
        )

    def _save_state_snapshot(self) -> None:
        """Save a snapshot of the current state."""
        if len(self._state_history) >= self._config.max_state_history_entries:
            self._state_history.pop(0)

        # Create a copy of current state
        snapshot = GitServiceState(
            service_id=self._state.service_id,
            started_at=self._state.started_at,
            operation_count=self._state.operation_count,
            error_count=self._state.error_count,
            last_operation=self._state.last_operation,
            active_operations=self._state.active_operations,
            configuration=self._state.configuration,
            performance_metrics=self._state.performance_metrics.copy(),
        )
        self._state_history.append(snapshot)

    def _validate_configuration(self) -> None:
        """Validate service configuration."""
        if self._config.max_concurrent_operations <= 0:
            raise GitValidationError("max_concurrent_operations must be positive")

        if self._config.operation_timeout_seconds <= 0:
            raise GitValidationError("operation_timeout_seconds must be positive")

        if self._config.gpg_signing_enabled and not self._config.gpg_key_id:
            logger.warning("GPG signing enabled but no GPG key ID provided")

    async def _push_changes(self, repository_path: str | Path) -> dict[str, Any]:
        """Internal helper to push changes."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            push_with_validation,
            repository_path,
            self._config.default_remote,
        )
