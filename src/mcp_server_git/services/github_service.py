"""GitHub service implementation for MCP Git Server.

This module provides a comprehensive GitHub service that orchestrates GitHub operations
and primitives to deliver complete GitHub repository management capabilities.
The service provides high-level interfaces, handles authentication, rate limiting,
webhook processing, and state management.

Design principles:
    - Complete functionality: End-to-end GitHub repository management
    - State management: Maintains operational state and configuration
    - Rate limiting: Intelligent API rate limiting with backoff
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
from threading import Lock
from typing import Any

from ..operations.github_operations import (
    PullRequestRequest,
    create_pull_request,
    get_pull_request_with_status,
    get_repository_with_details,
    merge_pull_request,
)
from ..primitives.github_primitives import (
    GitHubAuthenticationError,
    GitHubPrimitiveError,
    get_authenticated_user,
    get_github_token,
    validate_github_token,
)
from ..protocols.debugging_protocol import DebuggableComponent

logger = logging.getLogger(__name__)


@dataclass
class GitHubServiceConfig:
    """Configuration for GitHub service."""

    # Authentication settings
    github_token: str | None = None
    auto_refresh_token: bool = True

    # Rate limiting settings
    enable_rate_limiting: bool = True
    rate_limit_buffer: int = 10  # Keep this many requests in reserve
    rate_limit_backoff: float = 60.0  # Seconds to wait when rate limited

    # Webhook settings
    webhook_secret: str | None = None
    webhook_events: list[str] = field(default_factory=lambda: ["push", "pull_request"])

    # Service settings
    max_concurrent_operations: int = 5
    operation_timeout: int = 300  # 5 minutes
    cache_ttl: int = 300  # 5 minutes

    # GitHub API settings
    api_base_url: str = "https://api.github.com"
    user_agent: str = "MCP-Git-Server/1.1.0"


@dataclass
class GitHubServiceState:
    """Internal state of GitHub service."""

    # Service status
    is_running: bool = False
    started_at: datetime | None = None
    last_activity: datetime | None = None

    # Authentication state
    is_authenticated: bool = False
    authenticated_user: dict[str, Any] | None = None
    token_validated_at: datetime | None = None

    # Rate limiting state
    rate_limit_remaining: int | None = None
    rate_limit_reset_at: datetime | None = None
    rate_limit_used: int = 0

    # Operation tracking
    active_operations: set[str] = field(default_factory=set)
    completed_operations: int = 0
    failed_operations: int = 0
    operation_history: list[dict[str, Any]] = field(default_factory=list)

    # Error tracking
    last_error: Exception | None = None
    error_count: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class GitHubOperationResult:
    """Result of a GitHub service operation."""

    success: bool
    data: dict[str, Any] | None = None
    error: Exception | None = None
    duration: float = 0.0
    rate_limit_used: int = 0
    timestamp: datetime = field(default_factory=datetime.now)


class GitHubService(DebuggableComponent):
    """Comprehensive GitHub service providing high-level GitHub functionality.

    This service orchestrates GitHub operations, handles authentication,
    rate limiting, webhook processing, and provides comprehensive state
    management and debugging capabilities.
    """

    def __init__(self, config: GitHubServiceConfig | None = None):
        """Initialize GitHub service.

        Args:
            config: Service configuration, defaults to GitHubServiceConfig()

        Example:
            >>> service = GitHubService()
            >>> await service.start()
        """
        self.config = config or GitHubServiceConfig()
        self.state = GitHubServiceState()
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=self.config.max_concurrent_operations
        )

        # Initialize GitHub token from config or environment
        if self.config.github_token is None:
            self.config.github_token = get_github_token()

        logger.info("GitHub service initialized")

    async def start(self) -> None:
        """Start the GitHub service.

        Raises:
            GitHubServiceError: If service fails to start
            GitHubAuthenticationError: If authentication fails

        Example:
            >>> service = GitHubService()
            >>> await service.start()
            >>> print(f"Service authenticated: {service.is_authenticated()}")
        """
        if self.state.is_running:
            logger.warning("GitHub service already running")
            return

        logger.info("Starting GitHub service...")

        try:
            # Authenticate if token is available
            if self.config.github_token:
                await self.authenticate(self.config.github_token)

            # Update service state
            with self._lock:
                self.state.is_running = True
                self.state.started_at = datetime.now()
                self.state.last_activity = datetime.now()

            logger.info("GitHub service started successfully")

        except Exception as e:
            logger.error(f"Failed to start GitHub service: {e}")
            raise GitHubServiceError(f"Service startup failed: {e}") from e

    async def stop(self) -> None:
        """Stop the GitHub service.

        Example:
            >>> await service.stop()
        """
        if not self.state.is_running:
            return

        logger.info("Stopping GitHub service...")

        # Wait for active operations to complete
        max_wait = 30  # seconds
        wait_start = time.time()

        while self.state.active_operations and (time.time() - wait_start) < max_wait:
            logger.info(
                f"Waiting for {len(self.state.active_operations)} active operations to complete..."
            )
            await asyncio.sleep(1)

        # Force shutdown if operations are still active
        if self.state.active_operations:
            logger.warning(
                f"Force stopping with {len(self.state.active_operations)} active operations"
            )

        # Shutdown executor
        self._executor.shutdown(wait=True)

        # Update service state
        with self._lock:
            self.state.is_running = False
            self.state.active_operations.clear()

        logger.info("GitHub service stopped")

    async def authenticate(self, token: str | None = None) -> bool:
        """Authenticate with GitHub API.

        Args:
            token: GitHub token to use, if None uses configured token

        Returns:
            True if authentication successful

        Raises:
            GitHubAuthenticationError: If authentication fails

        Example:
            >>> success = await service.authenticate("ghp_token123")
            >>> print(f"Authentication successful: {success}")
        """
        auth_token = token or self.config.github_token
        if not auth_token:
            raise GitHubAuthenticationError("No GitHub token provided")

        logger.info("Authenticating with GitHub API...")

        try:
            # Validate token format
            if not validate_github_token(auth_token):
                raise GitHubAuthenticationError("Invalid GitHub token format")

            # Test authentication by getting user info
            user_info = await get_authenticated_user()

            # Update service state
            with self._lock:
                self.state.is_authenticated = True
                self.state.authenticated_user = user_info
                self.state.token_validated_at = datetime.now()
                self.config.github_token = auth_token

            logger.info(
                f"Successfully authenticated as {user_info.get('login', 'unknown')}"
            )
            return True

        except GitHubAuthenticationError:
            logger.error("GitHub authentication failed")
            with self._lock:
                self.state.is_authenticated = False
                self.state.authenticated_user = None
            raise
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            raise GitHubAuthenticationError(f"Authentication failed: {e}") from e

    def is_authenticated(self) -> bool:
        """Check if service is authenticated with GitHub."""
        return self.state.is_authenticated

    async def create_pull_request_workflow(
        self,
        repo_owner: str,
        repo_name: str,
        pr_request: PullRequestRequest,
        auto_merge: bool = False,
        wait_for_checks: bool = True,
    ) -> GitHubOperationResult:
        """Complete pull request workflow with optional auto-merge.

        Args:
            repo_owner: Repository owner
            repo_name: Repository name
            pr_request: Pull request creation parameters
            auto_merge: Whether to auto-merge if checks pass
            wait_for_checks: Whether to wait for status checks

        Returns:
            GitHubOperationResult with PR information

        Example:
            >>> pr_req = PullRequestRequest(
            ...     title="Feature: New API",
            ...     head="feature-branch",
            ...     base="main"
            ... )
            >>> result = await service.create_pull_request_workflow(
            ...     "owner", "repo", pr_req, auto_merge=True
            ... )
            >>> print(f"PR #{result.data['number']} created")
        """
        operation_id = f"pr_workflow_{repo_owner}_{repo_name}_{int(time.time())}"

        try:
            await self._start_operation(operation_id)
            start_time = time.time()

            # Create the pull request
            logger.info(f"Creating PR: {pr_request.title} in {repo_owner}/{repo_name}")
            pr = await create_pull_request(repo_owner, repo_name, pr_request)
            pr_number = pr["number"]

            result_data = {"pull_request": pr}

            # Wait for status checks if requested
            if wait_for_checks:
                logger.info(f"Waiting for status checks on PR #{pr_number}")
                pr_with_status = await self._wait_for_pr_checks(
                    repo_owner, repo_name, pr_number
                )
                result_data["status_checks"] = pr_with_status.get("status_checks", {})

            # Auto-merge if requested and checks pass
            if auto_merge and self._pr_checks_passed(
                result_data.get("status_checks", {})
            ):
                logger.info(f"Auto-merging PR #{pr_number}")
                merge_result = await merge_pull_request(
                    repo_owner,
                    repo_name,
                    pr_number,
                    commit_title=f"Merge PR #{pr_number}: {pr_request.title}",
                )
                result_data["merge_result"] = merge_result

            duration = time.time() - start_time
            return GitHubOperationResult(
                success=True, data=result_data, duration=duration
            )

        except Exception as e:
            logger.error(f"Pull request workflow failed: {e}")
            await self._record_error(e)
            return GitHubOperationResult(
                success=False, error=e, duration=time.time() - start_time
            )
        finally:
            await self._finish_operation(operation_id)

    async def handle_webhook_event(
        self, event_type: str, event_data: dict[str, Any]
    ) -> GitHubOperationResult:
        """Process GitHub webhook events.

        Args:
            event_type: Type of webhook event (push, pull_request, etc.)
            event_data: Webhook payload data

        Returns:
            GitHubOperationResult with processing result

        Example:
            >>> webhook_data = {"action": "opened", "pull_request": {...}}
            >>> result = await service.handle_webhook_event("pull_request", webhook_data)
            >>> print(f"Webhook processed: {result.success}")
        """
        operation_id = f"webhook_{event_type}_{int(time.time())}"

        try:
            await self._start_operation(operation_id)
            start_time = time.time()

            logger.info(f"Processing webhook event: {event_type}")

            # Process different event types
            result_data = {}

            if event_type == "pull_request":
                result_data = await self._handle_pr_webhook(event_data)
            elif event_type == "push":
                result_data = await self._handle_push_webhook(event_data)
            elif event_type == "issues":
                result_data = await self._handle_issue_webhook(event_data)
            else:
                logger.warning(f"Unhandled webhook event type: {event_type}")
                result_data = {"message": f"Event type {event_type} not handled"}

            return GitHubOperationResult(
                success=True, data=result_data, duration=time.time() - start_time
            )

        except Exception as e:
            logger.error(f"Webhook processing failed: {e}")
            await self._record_error(e)
            return GitHubOperationResult(
                success=False, error=e, duration=time.time() - start_time
            )
        finally:
            await self._finish_operation(operation_id)

    def get_rate_limit_status(self) -> dict[str, Any]:
        """Get current GitHub API rate limit status.

        Returns:
            Dictionary with rate limit information

        Example:
            >>> status = service.get_rate_limit_status()
            >>> print(f"Remaining requests: {status['remaining']}")
        """
        return {
            "remaining": self.state.rate_limit_remaining,
            "reset_at": self.state.rate_limit_reset_at.isoformat()
            if self.state.rate_limit_reset_at
            else None,
            "used": self.state.rate_limit_used,
            "buffer": self.config.rate_limit_buffer,
            "approaching_limit": self._is_approaching_rate_limit(),
        }

    async def get_repository_insights(
        self, repo_owner: str, repo_name: str
    ) -> GitHubOperationResult:
        """Get comprehensive repository insights and analytics.

        Args:
            repo_owner: Repository owner
            repo_name: Repository name

        Returns:
            GitHubOperationResult with repository insights

        Example:
            >>> insights = await service.get_repository_insights("owner", "repo")
            >>> print(f"Repository health score: {insights.data['health_score']}")
        """
        operation_id = f"insights_{repo_owner}_{repo_name}"

        try:
            await self._start_operation(operation_id)
            start_time = time.time()

            # Get detailed repository information
            repo_details = await get_repository_with_details(repo_owner, repo_name)

            # Calculate insights
            insights = {
                "repository": repo_details,
                "health_score": self._calculate_health_score(repo_details),
                "activity_level": self._calculate_activity_level(repo_details),
                "maintenance_status": self._assess_maintenance_status(repo_details),
                "insights_generated_at": datetime.now().isoformat(),
            }

            return GitHubOperationResult(
                success=True, data=insights, duration=time.time() - start_time
            )

        except Exception as e:
            logger.error(f"Failed to get repository insights: {e}")
            return GitHubOperationResult(
                success=False, error=e, duration=time.time() - start_time
            )
        finally:
            await self._finish_operation(operation_id)

    # DebuggableComponent Protocol Implementation

    def get_component_state(self) -> "GitHubServiceComponentState":
        """Get current state of the GitHub service."""
        return GitHubServiceComponentState(
            component_id="github_service",
            component_type="GitHubService",
            state_data={
                "config": self.config.__dict__,
                "state": self.state.__dict__,
                "rate_limit_status": self.get_rate_limit_status(),
            },
            last_updated=self.state.last_activity or datetime.now(),
        )

    def validate_component(self) -> "GitHubServiceValidationResult":
        """Validate the GitHub service configuration and state."""
        errors = []
        warnings = []

        # Check authentication
        if not self.state.is_authenticated:
            errors.append("GitHub service not authenticated")

        # Check token validity
        if not self.config.github_token:
            errors.append("No GitHub token configured")
        elif not validate_github_token(self.config.github_token):
            errors.append("Invalid GitHub token format")

        # Check rate limiting
        if self._is_approaching_rate_limit():
            warnings.append("Approaching GitHub API rate limit")

        # Check service status
        if not self.state.is_running:
            warnings.append("GitHub service not running")

        return GitHubServiceValidationResult(
            is_valid=len(errors) == 0,
            validation_errors=errors,
            validation_warnings=warnings,
            validation_timestamp=datetime.now(),
        )

    def get_debug_info(self, debug_level: str = "INFO") -> "GitHubServiceDebugInfo":
        """Get debug information for the GitHub service."""
        debug_data = {
            "service_uptime": (datetime.now() - self.state.started_at).total_seconds()
            if self.state.started_at
            else 0,
            "operations": {
                "active": len(self.state.active_operations),
                "completed": self.state.completed_operations,
                "failed": self.state.failed_operations,
            },
            "authentication": {
                "is_authenticated": self.state.is_authenticated,
                "user": self.state.authenticated_user.get("login")
                if self.state.authenticated_user
                else None,
            },
        }

        if debug_level == "DEBUG":
            debug_data.update(
                {
                    "active_operations_list": list(self.state.active_operations),
                    "recent_operations": self.state.operation_history[-10:],
                    "recent_errors": [
                        {"error": str(e["error"]), "timestamp": e["timestamp"]}
                        for e in self.state.errors[-5:]
                    ],
                }
            )

        return GitHubServiceDebugInfo(
            debug_level=debug_level,
            debug_data=debug_data,
            stack_trace=None,
            performance_metrics={
                "operations_per_minute": self._calculate_operations_per_minute(),
                "average_operation_duration": self._calculate_average_operation_duration(),
                "error_rate": self._calculate_error_rate(),
            },
        )

    def inspect_state(self, path: str | None = None) -> dict[str, Any]:
        """Inspect specific parts of the GitHub service state."""
        full_state = {
            "config": self.config.__dict__,
            "state": self.state.__dict__,
            "rate_limit": self.get_rate_limit_status(),
        }

        if path is None:
            return full_state

        # Navigate to specific path using dot notation
        current = full_state
        for part in path.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return {}

        return {path: current}

    def get_component_dependencies(self) -> list[str]:
        """Get list of component dependencies."""
        return [
            "github_primitives",
            "github_operations",
            "network_connection",
            "github_api",
        ]

    def export_state_json(self) -> str:
        """Export component state as JSON."""
        state = self.get_component_state()
        return json.dumps(
            {
                "component_id": state.component_id,
                "component_type": state.component_type,
                "state_data": state.state_data,
                "last_updated": state.last_updated.isoformat(),
                "exported_at": datetime.now().isoformat(),
            },
            indent=2,
        )

    def health_check(self) -> dict[str, bool | str | int | float | None]:
        """Perform health check on the GitHub service."""
        return {
            "healthy": self.state.is_running and self.state.is_authenticated,
            "status": self._get_health_status(),
            "uptime": (datetime.now() - self.state.started_at).total_seconds()
            if self.state.started_at
            else 0,
            "last_error": str(self.state.last_error) if self.state.last_error else None,
            "error_count": self.state.error_count,
        }

    # Private helper methods

    async def _start_operation(self, operation_id: str) -> None:
        """Start tracking a new operation."""
        with self._lock:
            self.state.active_operations.add(operation_id)
            self.state.last_activity = datetime.now()

    async def _finish_operation(self, operation_id: str, success: bool = True) -> None:
        """Finish tracking an operation."""
        with self._lock:
            self.state.active_operations.discard(operation_id)
            if success:
                self.state.completed_operations += 1
            else:
                self.state.failed_operations += 1

            # Record operation in history
            self.state.operation_history.append(
                {
                    "operation_id": operation_id,
                    "success": success,
                    "timestamp": datetime.now().isoformat(),
                }
            )

            # Keep only recent history
            if len(self.state.operation_history) > 100:
                del self.state.operation_history[:-50]  # More memory efficient

    async def _record_error(self, error: Exception) -> None:
        """Record an error in service state."""
        with self._lock:
            self.state.last_error = error
            self.state.error_count += 1
            self.state.errors.append(
                {"error": error, "timestamp": datetime.now().isoformat()}
            )

            # Keep only recent errors
            if len(self.state.errors) > 50:
                del self.state.errors[:-25]  # More memory efficient

    def _is_approaching_rate_limit(self) -> bool:
        """Check if approaching GitHub API rate limit."""
        if self.state.rate_limit_remaining is None:
            return False
        return self.state.rate_limit_remaining <= self.config.rate_limit_buffer

    async def _wait_for_pr_checks(
        self, repo_owner: str, repo_name: str, pr_number: int, timeout: int = 300
    ) -> dict[str, Any]:
        """Wait for PR status checks to complete."""
        start_time = time.time()
        while (time.time() - start_time) < timeout:
            pr_status = await get_pull_request_with_status(
                repo_owner, repo_name, pr_number
            )

            status_checks = pr_status.get("status_checks", {})
            if self._pr_checks_complete(status_checks):
                return pr_status

            await asyncio.sleep(30)  # Wait 30 seconds between checks

        logger.warning(f"Timeout waiting for PR #{pr_number} checks")
        return await get_pull_request_with_status(repo_owner, repo_name, pr_number)

    def _pr_checks_complete(self, status_checks: dict[str, Any]) -> bool:
        """Check if PR status checks are complete."""
        if not status_checks:
            return True

        state = status_checks.get("state", "pending")
        return state in ["success", "failure", "error"]

    def _pr_checks_passed(self, status_checks: dict[str, Any]) -> bool:
        """Check if PR status checks passed."""
        if not status_checks:
            return True

        return status_checks.get("state") == "success"

    async def _handle_pr_webhook(self, event_data: dict[str, Any]) -> dict[str, Any]:
        """Handle pull request webhook events."""
        action = event_data.get("action", "unknown")
        pr = event_data.get("pull_request", {})

        logger.info(
            f"Processing PR webhook: {action} for PR #{pr.get('number', 'unknown')}"
        )

        return {
            "event_type": "pull_request",
            "action": action,
            "pr_number": pr.get("number"),
            "pr_title": pr.get("title"),
            "processed_at": datetime.now().isoformat(),
        }

    async def _handle_push_webhook(self, event_data: dict[str, Any]) -> dict[str, Any]:
        """Handle push webhook events."""
        ref = event_data.get("ref", "unknown")
        commits = event_data.get("commits", [])

        logger.info(f"Processing push webhook: {len(commits)} commits to {ref}")

        return {
            "event_type": "push",
            "ref": ref,
            "commit_count": len(commits),
            "processed_at": datetime.now().isoformat(),
        }

    async def _handle_issue_webhook(self, event_data: dict[str, Any]) -> dict[str, Any]:
        """Handle issue webhook events."""
        action = event_data.get("action", "unknown")
        issue = event_data.get("issue", {})

        logger.info(
            f"Processing issue webhook: {action} for issue #{issue.get('number', 'unknown')}"
        )

        return {
            "event_type": "issues",
            "action": action,
            "issue_number": issue.get("number"),
            "issue_title": issue.get("title"),
            "processed_at": datetime.now().isoformat(),
        }

    def _calculate_health_score(self, repo_data: dict[str, Any]) -> float:
        """Calculate repository health score."""
        # Simple health score based on activity and maintenance
        score = 0.0

        # Factor in recent activity
        if repo_data.get("pushed_at"):
            # Add scoring logic based on recent pushes
            score += 30.0

        # Factor in documentation
        if repo_data.get("has_wiki") or "README" in str(
            repo_data.get("description", "")
        ):
            score += 20.0

        # Factor in community
        if repo_data.get("stargazers_count", 0) > 0:
            score += min(25.0, repo_data["stargazers_count"] / 10)

        # Factor in issues management
        open_issues = repo_data.get("open_issues_count", 0)
        if open_issues == 0:
            score += 25.0
        elif open_issues < 10:
            score += 15.0

        return min(100.0, score)

    def _calculate_activity_level(self, repo_data: dict[str, Any]) -> str:
        """Calculate repository activity level."""
        # Simple activity assessment
        pushed_at = repo_data.get("pushed_at")
        if not pushed_at:
            return "dormant"

        # This would need proper date parsing in real implementation
        return "active"  # Simplified for now

    def _assess_maintenance_status(self, repo_data: dict[str, Any]) -> str:
        """Assess repository maintenance status."""
        # Simple maintenance assessment
        if repo_data.get("archived"):
            return "archived"
        if repo_data.get("disabled"):
            return "disabled"
        return "maintained"

    def _get_health_status(self) -> str:
        """Get overall service health status."""
        if not self.state.is_running:
            return "stopped"
        if not self.state.is_authenticated:
            return "unauthenticated"
        if self._is_approaching_rate_limit():
            return "degraded"
        return "healthy"

    def _calculate_operations_per_minute(self) -> float:
        """Calculate operations per minute metric."""
        if not self.state.started_at:
            return 0.0

        uptime_minutes = (datetime.now() - self.state.started_at).total_seconds() / 60
        if uptime_minutes == 0:
            return 0.0

        total_operations = (
            self.state.completed_operations + self.state.failed_operations
        )
        return total_operations / uptime_minutes

    def _calculate_average_operation_duration(self) -> float:
        """Calculate average operation duration."""
        # This would require tracking operation durations
        return 0.0  # Placeholder

    def _calculate_error_rate(self) -> float:
        """Calculate error rate percentage."""
        total_operations = (
            self.state.completed_operations + self.state.failed_operations
        )
        if total_operations == 0:
            return 0.0

        return (self.state.failed_operations / total_operations) * 100


class GitHubServiceError(GitHubPrimitiveError):
    """Base exception for GitHub service errors."""

    pass


# Protocol implementations for DebuggableComponent


@dataclass
class GitHubServiceComponentState:
    """GitHub service component state implementation."""

    component_id: str
    component_type: str
    state_data: dict[str, Any]
    last_updated: datetime


@dataclass
class GitHubServiceValidationResult:
    """GitHub service validation result implementation."""

    is_valid: bool
    validation_errors: list[str]
    validation_warnings: list[str]
    validation_timestamp: datetime


@dataclass
class GitHubServiceDebugInfo:
    """GitHub service debug info implementation."""

    debug_level: str
    debug_data: dict[str, Any]
    stack_trace: list[str] | None
    performance_metrics: dict[str, int | float]
