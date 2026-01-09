"""
Main MCP Git Server Application.

This module provides the ServerApplication class that serves as the primary entry point
and orchestrator for the entire MCP Git server system. It integrates all decomposed
components into a cohesive, production-ready application.

The ServerApplication replaces the monolithic server.py approach with a clean,
component-based architecture that provides the same functionality with improved
structure, maintainability, and LLM compatibility.
"""

import asyncio
import logging
import signal
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from mcp.types import Tool
from pydantic import BaseModel, Field, field_validator

from ..frameworks.mcp_server_framework import MCPServerFramework
from ..frameworks.server_configuration import ServerConfigurationManager
from ..frameworks.server_core import MCPGitServerCore
from ..frameworks.server_github import GitHubService
from ..frameworks.server_middleware import MiddlewareChainManager
from ..frameworks.server_security import SecurityFramework
from ..operations.server_notifications import NotificationOperations
from ..protocols.debugging_protocol import DebuggableComponent
from ..services.git_service import GitService
from ..services.github_service import GitHubServiceConfig
from ..services.server_metrics import MetricsService
from ..services.server_session import SessionManager

# Azure DevOps models for tool registration
from ..azure.models import (
    AzureGetBuildLogs,
    AzureGetBuildStatus,
    AzureGetFailingJobs,
    AzureListBuilds,
)

logger = logging.getLogger(__name__)

# ===== MCP TOOL MODELS =====
# Import the tool models from the original server to maintain compatibility

from enum import Enum


class GitTools(str, Enum):
    """Git tool names."""

    STATUS = "git_status"
    DIFF_UNSTAGED = "git_diff_unstaged"
    DIFF_STAGED = "git_diff_staged"
    DIFF = "git_diff"
    COMMIT = "git_commit"
    ADD = "git_add"
    RESET = "git_reset"
    LOG = "git_log"
    CREATE_BRANCH = "git_create_branch"
    CHECKOUT = "git_checkout"
    SHOW = "git_show"
    INIT = "git_init"
    PUSH = "git_push"
    PULL = "git_pull"
    DIFF_BRANCHES = "git_diff_branches"
    REBASE = "git_rebase"
    MERGE = "git_merge"
    CHERRY_PICK = "git_cherry_pick"
    ABORT = "git_abort"
    CONTINUE = "git_continue"
    BRANCH_LIST = "git_branch_list"
    FETCH = "git_fetch"
    REMOTE_ADD = "git_remote_add"
    REMOTE_REMOVE = "git_remote_remove"
    REMOTE_LIST = "git_remote_list"
    REMOTE_GET_URL = "git_remote_get_url"


class GitStatus(BaseModel):
    repo_path: str


class GitDiffUnstaged(BaseModel):
    repo_path: str


class GitDiffStaged(BaseModel):
    repo_path: str


class GitDiff(BaseModel):
    repo_path: str
    target: str


class GitCommit(BaseModel):
    repo_path: str
    message: str
    gpg_sign: bool = False
    gpg_key_id: str | None = None


class GitAdd(BaseModel):
    repo_path: str
    files: list[str]


class GitReset(BaseModel):
    repo_path: str
    mode: str = "mixed"  # soft, mixed, hard
    target: str | None = None


class GitLog(BaseModel):
    repo_path: str
    max_count: int = 10


class GitCreateBranch(BaseModel):
    repo_path: str
    branch_name: str
    base_branch: str | None = None


class GitCheckout(BaseModel):
    repo_path: str
    branch_name: str


class GitShow(BaseModel):
    repo_path: str
    revision: str


class GitInit(BaseModel):
    repo_path: str


class GitPush(BaseModel):
    repo_path: str
    remote: str = "origin"
    branch: str | None = None
    force: bool = False


class GitPull(BaseModel):
    repo_path: str
    remote: str = "origin"
    branch: str | None = None


class GitDiffBranches(BaseModel):
    repo_path: str
    base_branch: str
    target_branch: str


class GitRebase(BaseModel):
    repo_path: str
    target_branch: str


class GitMerge(BaseModel):
    repo_path: str
    source_branch: str
    strategy: str = "merge"
    message: str | None = None


class GitCherryPick(BaseModel):
    repo_path: str
    commit_hash: str


class GitAbort(BaseModel):
    repo_path: str
    operation: Literal["rebase", "merge", "cherry-pick"] = Field(
        ..., description="The git operation to abort"
    )


class GitContinue(BaseModel):
    repo_path: str
    operation: Literal["rebase", "merge", "cherry-pick"] = Field(
        ..., description="The git operation to continue"
    )


class GitFetch(BaseModel):
    repo_path: str
    remote: str = "origin"


class GitRemoteAdd(BaseModel):
    repo_path: str
    name: str
    url: str


class GitRemoteRemove(BaseModel):
    repo_path: str
    name: str


class GitRemoteList(BaseModel):
    repo_path: str


class GitRemoteGetUrl(BaseModel):
    repo_path: str
    name: str


class GitHubTools(str, Enum):
    """GitHub tool names."""

    CREATE_ISSUE = "github_create_issue"
    LIST_ISSUES = "github_list_issues"
    UPDATE_ISSUE = "github_update_issue"
    GET_PR_CHECKS = "github_get_pr_checks"
    GET_PR_DETAILS = "github_get_pr_details"
    LIST_PULL_REQUESTS = "github_list_pull_requests"
    GET_PR_STATUS = "github_get_pr_status"
    GET_PR_FILES = "github_get_pr_files"
    EDIT_PR_DESCRIPTION = "github_edit_pr_description"
    GET_WORKFLOW_RUN = "github_get_workflow_run"
    LIST_WORKFLOW_RUNS = "github_list_workflow_runs"
    AWAIT_WORKFLOW_COMPLETION = "github_await_workflow_completion"
    CREATE_PR = "github_create_pr"
    MERGE_PR = "github_merge_pr"
    ADD_PR_COMMENT = "github_add_pr_comment"
    CLOSE_PR = "github_close_pr"
    REOPEN_PR = "github_reopen_pr"
    UPDATE_PR = "github_update_pr"
    GET_FAILING_JOBS = "github_get_failing_jobs"


class AzureTools(str, Enum):
    """Azure DevOps tool names."""

    GET_BUILD_STATUS = "azure_get_build_status"
    GET_BUILD_LOGS = "azure_get_build_logs"
    GET_FAILING_JOBS = "azure_get_failing_jobs"
    LIST_BUILDS = "azure_list_builds"


class GitHubCreateIssue(BaseModel):
    repo_owner: str
    repo_name: str
    title: str
    body: str | None = None
    labels: list[str] | None = None
    assignees: list[str] | None = None
    milestone: int | None = None


class GitHubListIssues(BaseModel):
    repo_owner: str
    repo_name: str
    state: str = "open"  # open, closed, all
    labels: str | None = None
    assignee: str | None = None
    creator: str | None = None
    mentioned: str | None = None
    milestone: str | None = None
    sort: str = "created"  # created, updated, comments
    direction: str = "desc"  # asc, desc
    since: str | None = None
    per_page: int = 30
    page: int = 1


class GitHubUpdateIssue(BaseModel):
    repo_owner: str
    repo_name: str
    issue_number: int
    title: str | None = None
    body: str | None = None
    state: str | None = None  # open, closed
    labels: list[str] | None = None
    assignees: list[str] | None = None
    milestone: int | None = None


class GitHubGetPrChecks(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int
    status: str | None = None
    conclusion: str | None = None


class GitHubGetPrDetails(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int
    include_files: bool = False
    include_reviews: bool = False


class GitHubListPullRequests(BaseModel):
    repo_owner: str
    repo_name: str
    state: str = "open"  # open, closed, all
    head: str | None = None
    base: str | None = None
    sort: str = "created"  # created, updated, popularity
    direction: str = "desc"  # asc, desc
    per_page: int = 30
    page: int = 1


class GitHubGetPrStatus(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int


class GitHubGetPrFiles(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int
    per_page: int = 30
    page: int = 1
    include_patch: bool = False


class GitHubEditPrDescription(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int
    description: str


class GitHubGetWorkflowRun(BaseModel):
    repo_owner: str
    repo_name: str
    run_id: int
    include_logs: bool = False


class GitHubListWorkflowRuns(BaseModel):
    repo_owner: str
    repo_name: str
    workflow_id: str | None = None
    actor: str | None = None
    branch: str | None = None
    event: str | None = None
    status: str | None = None
    conclusion: str | None = None
    per_page: int = 30
    page: int = 1
    created: str | None = None
    exclude_pull_requests: bool = False
    check_suite_id: int | None = None
    head_sha: str | None = None

    @field_validator("per_page")
    @classmethod
    def validate_per_page(cls, v: int) -> int:
        """Enforce GitHub API limits for per_page parameter."""
        return max(1, min(v, 100))

    @field_validator("page")
    @classmethod
    def validate_page(cls, v: int) -> int:
        """Ensure page number is positive."""
        return max(1, v)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        """Validate workflow run status values."""
        if v is None:
            return v
        valid_statuses = {
            "queued",
            "in_progress",
            "completed",
            "waiting",
            "requested",
            "pending",
        }
        if v not in valid_statuses:
            raise ValueError(
                f"status must be one of: {', '.join(sorted(valid_statuses))}"
            )
        return v

    @field_validator("conclusion")
    @classmethod
    def validate_conclusion(cls, v: str | None) -> str | None:
        """Validate workflow run conclusion values."""
        if v is None:
            return v
        valid_conclusions = {
            "success",
            "failure",
            "neutral",
            "cancelled",
            "timed_out",
            "action_required",
            "stale",
            "startup_failure",
        }
        if v not in valid_conclusions:
            raise ValueError(
                f"conclusion must be one of: {', '.join(sorted(valid_conclusions))}"
            )
        return v


class GitHubAwaitWorkflowCompletion(BaseModel):
    repo_owner: str
    repo_name: str
    run_id: int | None = None  # None = latest run
    timeout_minutes: int = 15
    poll_interval_seconds: int = 20

    @field_validator("timeout_minutes")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        """Ensure timeout is reasonable (1-350 minutes / 5h 50m)."""
        if v < 1 or v > 350:
            raise ValueError("timeout_minutes must be between 1 and 350")
        return v

    @field_validator("poll_interval_seconds")
    @classmethod
    def validate_poll_interval(cls, v: int) -> int:
        """Ensure poll interval is reasonable (5-120 seconds)."""
        if v < 5 or v > 120:
            raise ValueError("poll_interval_seconds must be between 5 and 120")
        return v


class GitHubCreatePr(BaseModel):
    repo_owner: str
    repo_name: str
    title: str
    head: str
    base: str
    body: str | None = None
    draft: bool = False


class GitHubMergePr(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int
    commit_title: str | None = None
    commit_message: str | None = None
    merge_method: str = "merge"


class GitHubAddPrComment(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int
    body: str


class GitHubClosePr(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int


class GitHubReopenPr(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int


class GitHubUpdatePr(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int
    title: str | None = None
    body: str | None = None
    state: str | None = None
    base: str | None = None


class GitHubGetFailingJobs(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int
    include_logs: bool = True
    include_annotations: bool = True


class ServerApplicationConfig:
    """Configuration for the server application."""

    def __init__(
        self,
        repository_path: Path | None = None,
        enable_metrics: bool = True,
        enable_security: bool = True,
        enable_notifications: bool = True,
        test_mode: bool = False,
        debug_mode: bool = False,
    ):
        """
        Initialize server application configuration.

        Args:
            repository_path: Optional path to the git repository to serve
            enable_metrics: Whether to enable metrics collection
            enable_security: Whether to enable security framework
            enable_notifications: Whether to enable notification operations
            test_mode: Whether to run in test mode
            debug_mode: Whether to enable debug mode
        """
        self.repository_path = repository_path
        self.enable_metrics = enable_metrics
        self.enable_security = enable_security
        self.enable_notifications = enable_notifications
        self.test_mode = test_mode
        self.debug_mode = debug_mode


class ServerApplication(DebuggableComponent):
    """
    Main MCP Git Server Application.

    This class orchestrates all components of the MCP Git server into a cohesive
    application. It handles initialization, startup, runtime management, and
    graceful shutdown of all subsystems.

    The application follows a component-based architecture where each major
    subsystem is represented by a dedicated component that can be independently
    configured, started, stopped, and debugged.

    Example usage:
        >>> config = ServerApplicationConfig(
        ...     repository_path=Path("/path/to/repo"),
        ...     enable_metrics=True
        ... )
        >>> app = ServerApplication(config)
        >>> await app.start()
        >>> # Server is now running
        >>> await app.stop()
    """

    def __init__(self, config: ServerApplicationConfig | None = None):
        """
        Initialize the server application.

        Args:
            config: Application configuration
        """
        self.config = config or ServerApplicationConfig()
        self._initialized = False
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._components: dict[str, Any] = {}

        # Core framework components
        self._framework: MCPServerFramework | None = None
        self._server_core: MCPGitServerCore | None = None
        self._configuration_manager: ServerConfigurationManager | None = None

        # Service components
        self._git_service: GitService | None = None
        self._github_service: GitHubService | None = None
        self._metrics_service: MetricsService | None = None
        self._session_manager: SessionManager | None = None

        # Operations components
        self._notification_operations: NotificationOperations | None = None

        # Infrastructure components
        self._middleware_manager: MiddlewareChainManager | None = None
        self._security_framework: SecurityFramework | None = None

        logger.info("ServerApplication initialized")

    async def initialize(self) -> None:
        """
        Initialize all application components.

        This method sets up all components in the correct order, ensuring
        that dependencies are satisfied and all systems are ready to start.
        """
        if self._initialized:
            logger.warning("ServerApplication already initialized")
            return

        logger.info("Initializing ServerApplication components...")

        try:
            # Phase 1: Initialize core framework
            await self._initialize_core_framework()

            # Phase 2: Initialize configuration management
            await self._initialize_configuration()

            # Phase 3: Initialize infrastructure components
            await self._initialize_infrastructure()

            # Phase 4: Initialize services
            await self._initialize_services()

            # Phase 5: Initialize operations
            await self._initialize_operations()

            # Phase 6: Register all components with framework
            await self._register_components()

            # Phase 7: Initialize the framework
            await self._framework.initialize()

            self._initialized = True
            logger.info("ServerApplication initialization complete")

        except Exception as e:
            logger.error(f"Failed to initialize ServerApplication: {e}")
            await self._cleanup_partial_initialization()
            raise

    async def _initialize_core_framework(self) -> None:
        """Initialize the core MCP framework."""
        logger.debug("Initializing core framework...")

        # Create the main framework
        self._framework = MCPServerFramework()

        # Create the server core
        self._server_core = MCPGitServerCore("mcp-git-server")

        # Initialize the MCP server within the core
        self._server_core.initialize_server(self.config.repository_path)

        # Register MCP tools with the server
        await self._register_mcp_tools()

        logger.debug("Core framework initialized")

    async def _initialize_configuration(self) -> None:
        """Initialize configuration management."""
        logger.debug("Initializing configuration management...")

        self._configuration_manager = ServerConfigurationManager()

        # Initialize with default configuration
        await self._configuration_manager.initialize()

        # Get the validated configuration
        self._configuration_manager.get_current_config()

        logger.debug("Configuration management initialized")

    async def _initialize_infrastructure(self) -> None:
        """Initialize infrastructure components."""
        logger.debug("Initializing infrastructure components...")

        # Initialize security framework
        if self.config.enable_security:
            self._security_framework = SecurityFramework()
            logger.debug("Security framework initialized")

        # Initialize middleware management with enhanced token limit middleware
        from ..frameworks.server_middleware import create_enhanced_middleware_chain

        self._middleware_manager = create_enhanced_middleware_chain(
            enable_token_limits=True
        )
        logger.debug("Enhanced middleware chain initialized with token limits")

        logger.debug("Infrastructure components initialized")

    async def _initialize_services(self) -> None:
        """Initialize service components."""
        logger.debug("Initializing service components...")

        # Get configuration for services
        server_config = self._configuration_manager.get_current_config()

        # Initialize Git service (convert server_config to GitServiceConfig)
        from ..services.git_service import GitServiceConfig

        git_config = GitServiceConfig(
            max_concurrent_operations=server_config.max_concurrent_operations,
            operation_timeout_seconds=server_config.operation_timeout_seconds,
            enable_security_validation=server_config.enable_security_validation,
        )
        self._git_service = GitService(config=git_config)

        # Initialize GitHub service
        github_config = GitHubServiceConfig(
            github_token=server_config.github_token,
        )
        self._github_service = GitHubService(github_config)

        # Initialize metrics service
        if self.config.enable_metrics:
            self._metrics_service = MetricsService(
                enable_system_metrics=True, max_metric_history=1000
            )
            logger.debug("Metrics service initialized")

        # Initialize session management
        self._session_manager = SessionManager()
        logger.debug("Session manager initialized")

        logger.debug("Service components initialized")

    async def _initialize_operations(self) -> None:
        """Initialize operations components."""
        logger.debug("Initializing operations components...")

        # Initialize notification operations - TEMPORARILY DISABLED due to abstract methods
        # TODO: Fix NotificationOperations abstract method implementations
        # if self.config.enable_notifications:
        #     server_config = self._configuration_manager.get_current_config()
        #     self._notification_operations = NotificationOperations(server_config)
        #     logger.debug("Notification operations initialized")

        logger.debug("Operations components initialized")

    async def _register_components(self) -> None:
        """Register all components with the framework."""
        logger.debug("Registering components with framework...")

        # Register core components
        if self._server_core:
            self._framework.register_component(
                name="server_core",
                component=self._server_core,
                dependencies=[],
                priority=1,
            )

        if self._configuration_manager:
            self._framework.register_component(
                name="configuration",
                component=self._configuration_manager,
                dependencies=[],
                priority=2,
            )

        # Register infrastructure components
        if self._security_framework:
            self._framework.register_component(
                name="security",
                component=self._security_framework,
                dependencies=["configuration"],
                priority=3,
            )

        if self._middleware_manager:
            self._framework.register_component(
                name="middleware",
                component=self._middleware_manager,
                dependencies=["configuration"],
                priority=4,
            )

        # Register services
        if self._git_service:
            self._framework.register_component(
                name="git_service",
                component=self._git_service,
                dependencies=["configuration", "security"],
                priority=5,
            )

        if self._github_service:
            self._framework.register_component(
                name="github_service",
                component=self._github_service,
                dependencies=["configuration", "security"],
                priority=6,
            )

        if self._metrics_service:
            self._framework.register_component(
                name="metrics",
                component=self._metrics_service,
                dependencies=["configuration"],
                priority=7,
            )

        if self._session_manager:
            self._framework.register_component(
                name="sessions",
                component=self._session_manager,
                dependencies=["configuration"],
                priority=8,
            )

        # Register operations
        if self._notification_operations:
            self._framework.register_component(
                name="notifications",
                component=self._notification_operations,
                dependencies=["configuration"],
                priority=9,
            )

        logger.debug("Component registration complete")

    async def start(self) -> None:
        """
        Start the server application.

        This method starts all components in the correct order and begins
        serving MCP requests. The method will block until the server is
        shut down.
        """
        if not self._initialized:
            await self.initialize()

        if self._running:
            logger.warning("ServerApplication already running")
            return

        logger.info("Starting ServerApplication...")

        try:
            # Start the framework (which starts all components)
            await self._framework.start()

            # Start the MCP server core
            if self._server_core:
                self._running = True
                logger.info("ServerApplication started successfully")

                # Install signal handlers for graceful shutdown
                self._install_signal_handlers()

                # Start server core - this blocks until client disconnects or shutdown signal
                await self._server_core.start_server(test_mode=self.config.test_mode)

                # If we reach here, server core completed (client disconnected)
                logger.info(
                    "🔁 Server core completed - client disconnected, shutting down"
                )

                # Set shutdown event to signal completion
                self._shutdown_event.set()

        except Exception as e:
            logger.error(f"Failed to start ServerApplication: {e}")
            await self.stop()

            # In test mode, don't re-raise exceptions - exit gracefully for CI
            if self.config.test_mode:
                logger.warning(
                    f"🧪 Test mode: Application error handled gracefully: {e}"
                )
                return
            else:
                raise

    async def stop(self) -> None:
        """
        Stop the server application gracefully.

        This method stops all components in reverse order and cleans up
        all resources.
        """
        if not self._running:
            logger.warning("ServerApplication not running")
            return

        logger.info("Stopping ServerApplication...")

        try:
            # Signal shutdown
            self._shutdown_event.set()

            # Stop the framework (which stops all components)
            if self._framework:
                await self._framework.stop()

            self._running = False
            logger.info("ServerApplication stopped successfully")

        except Exception as e:
            logger.error(f"Error during ServerApplication shutdown: {e}")
            raise

    async def restart(self) -> None:
        """
        Restart the server application.

        This method performs a graceful stop followed by a start.
        """
        logger.info("Restarting ServerApplication...")
        await self.stop()
        await self.start()

    def _install_signal_handlers(self) -> None:
        """Install signal handlers for graceful shutdown."""

        def signal_handler(signum: int, frame: Any) -> None:
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            asyncio.create_task(self.stop())

        if sys.platform != "win32":
            signal.signal(signal.SIGTERM, signal_handler)
            signal.signal(signal.SIGINT, signal_handler)

    async def _cleanup_partial_initialization(self) -> None:
        """Clean up after partial initialization failure."""
        logger.debug("Cleaning up partial initialization...")

        # Stop any components that were started
        if self._framework:
            try:
                await self._framework.stop()
            except Exception as e:
                logger.error(f"Error stopping framework during cleanup: {e}")

        # Reset initialization state
        self._initialized = False

    @asynccontextmanager
    async def _component_context(self, name: str, component: Any) -> AsyncIterator[Any]:
        """Context manager for component lifecycle."""
        logger.debug(f"Starting component: {name}")
        try:
            if hasattr(component, "start"):
                await component.start()
            yield component
        except Exception as e:
            logger.error(f"Error in component {name}: {e}")
            raise
        finally:
            logger.debug(f"Stopping component: {name}")
            if hasattr(component, "stop"):
                try:
                    await component.stop()
                except Exception as e:
                    logger.error(f"Error stopping component {name}: {e}")

    # DebuggableComponent Protocol Implementation

    def get_component_state(self) -> dict[str, Any]:
        """Get current state of the server application."""
        component_states = {}

        # Collect state from all registered components
        if self._framework:
            for name, registration in self._framework._components.items():
                component = registration.component
                if hasattr(component, "get_component_state"):
                    try:
                        component_states[name] = component.get_component_state()
                    except Exception as e:
                        component_states[name] = {"error": str(e)}
                else:
                    component_states[name] = {"status": "no_state_available"}

        return {
            "application_id": "mcp_git_server_application",
            "status": "running" if self._running else "stopped",
            "initialized": self._initialized,
            "config": {
                "repository_path": str(self.config.repository_path)
                if self.config.repository_path
                else None,
                "enable_metrics": self.config.enable_metrics,
                "enable_security": self.config.enable_security,
                "enable_notifications": self.config.enable_notifications,
                "test_mode": self.config.test_mode,
                "debug_mode": self.config.debug_mode,
            },
            "components": component_states,
            "component_count": len(component_states),
        }

    def validate_component(self) -> dict[str, Any]:
        """Validate server application configuration and state."""
        issues = []
        recommendations = []

        # Check initialization state
        if not self._initialized:
            issues.append("Application not initialized")

        # Check component availability
        if not self._framework:
            issues.append("Core framework not available")

        if not self._server_core:
            issues.append("Server core not available")

        # Check optional components
        if self.config.enable_metrics and not self._metrics_service:
            issues.append("Metrics enabled but service not available")

        if self.config.enable_security and not self._security_framework:
            issues.append("Security enabled but framework not available")

        if self.config.enable_notifications and not self._notification_operations:
            issues.append("Notifications enabled but operations not available")

        # Generate recommendations
        if not self.config.enable_metrics:
            recommendations.append(
                "Consider enabling metrics for production monitoring"
            )

        if not self.config.enable_security:
            recommendations.append(
                "Consider enabling security framework for production use"
            )

        return {
            "is_valid": len(issues) == 0,
            "issues": issues,
            "recommendations": recommendations,
        }

    def get_debug_info(self, detailed: bool = False) -> dict[str, Any]:
        """Get debug information about the server application."""
        debug_info = {
            "application_type": "MCPGitServerApplication",
            "state": self.get_component_state(),
            "validation": self.validate_component(),
        }

        if detailed:
            # Add detailed component debug information
            detailed_components = {}
            if self._framework:
                for name, registration in self._framework._components.items():
                    component = registration.component
                    if hasattr(component, "get_debug_info"):
                        try:
                            detailed_components[name] = component.get_debug_info(
                                detailed=True
                            )
                        except Exception as e:
                            detailed_components[name] = {"error": str(e)}

            debug_info["detailed_components"] = detailed_components

            # Add framework debug information
            if self._framework:
                debug_info["framework_debug"] = self._framework.get_debug_info(
                    detailed=True
                )

        return debug_info

    def inspect_state(self, path: str | None = None) -> dict[str, Any]:
        """Inspect the current state of the application or a specific component.

        Args:
            path: Optional path to inspect specific component (e.g., "framework", "git_service")

        Returns:
            State information for the application or specified component
        """
        if path is None:
            # Return overall application state
            return {
                "application_state": "running" if self._framework else "stopped",
                "components": {
                    "framework": self._framework is not None,
                    "git_service": self._git_service is not None,
                    "github_service": self._github_service is not None,
                    "security_framework": self._security_framework is not None,
                    "notifications": self._notification_operations is not None,
                },
                "configuration": {
                    "repository_path": str(self.config.repository_path)
                    if self.config.repository_path
                    else None,
                    "test_mode": self.config.test_mode,
                    "debug_mode": self.config.debug_mode,
                },
            }

        # Return specific component state
        if path == "framework" and self._framework:
            return self._framework.get_component_state()
        elif path == "git_service" and self._git_service:
            return self._git_service.get_component_state()
        elif path == "github_service" and self._github_service:
            return self._github_service.get_component_state()
        elif path == "security_framework" and self._security_framework:
            return self._security_framework.get_component_state()
        else:
            return {"error": f"Component '{path}' not found or not initialized"}

    def get_component_dependencies(self) -> list[str]:
        """Get the list of component dependencies for this application.

        Returns:
            List of component names that this application depends on
        """
        return [
            "framework",
            "git_service",
            "github_service",
            "security_framework",
            "notifications",
            "configuration_manager",
        ]

    def export_state_json(self) -> str:
        """Export the current application state as JSON string.

        Returns:
            JSON string representation of the application state
        """
        import json

        state = self.inspect_state()
        return json.dumps(state, indent=2)

    def health_check(self) -> dict[str, Any]:
        """Perform a health check on the application and all components.

        Returns:
            Health status information for the application and components
        """
        health = {
            "overall_status": "healthy",
            "timestamp": str(datetime.now()),
            "components": {},
        }

        try:
            # Check framework health
            if self._framework:
                framework_health = self._framework.health_check()
                health["components"]["framework"] = framework_health
                if not framework_health.get("healthy", False):
                    health["overall_status"] = "unhealthy"
            else:
                health["components"]["framework"] = {
                    "healthy": False,
                    "reason": "Not initialized",
                }
                health["overall_status"] = "unhealthy"

            # Check other components
            components_to_check = [
                ("git_service", self._git_service),
                ("github_service", self._github_service),
                ("security_framework", self._security_framework),
            ]

            for name, component in components_to_check:
                if component and hasattr(component, "health_check"):
                    comp_health = component.health_check()
                    health["components"][name] = comp_health
                    if not comp_health.get("healthy", False):
                        health["overall_status"] = "unhealthy"
                elif component:
                    health["components"][name] = {
                        "healthy": True,
                        "status": "operational",
                    }
                else:
                    health["components"][name] = {
                        "healthy": False,
                        "reason": "Not initialized",
                    }
                    health["overall_status"] = "unhealthy"

        except Exception as e:
            health["overall_status"] = "error"
            health["error"] = str(e)

        return health

    async def _register_mcp_tools(self) -> None:
        """Register all MCP tools with the server."""
        if not self._server_core or not self._server_core.server:
            logger.error("Cannot register tools: server not initialized")
            return

        server = self._server_core.server
        logger.info("Registering MCP tools...")

        @server.list_tools()
        async def list_tools() -> list[Tool]:
            """Return available git tools."""
            return [
                Tool(
                    name=GitTools.STATUS,
                    description="Shows the working tree status",
                    inputSchema=GitStatus.model_json_schema(),
                ),
                Tool(
                    name=GitTools.DIFF_UNSTAGED,
                    description="Shows changes in the working directory that are not yet staged",
                    inputSchema=GitDiffUnstaged.model_json_schema(),
                ),
                Tool(
                    name=GitTools.DIFF_STAGED,
                    description="Shows changes that are staged for commit",
                    inputSchema=GitDiffStaged.model_json_schema(),
                ),
                Tool(
                    name=GitTools.DIFF,
                    description="Shows differences between branches or commits",
                    inputSchema=GitDiff.model_json_schema(),
                ),
                Tool(
                    name=GitTools.COMMIT,
                    description="Records changes to the repository",
                    inputSchema=GitCommit.model_json_schema(),
                ),
                Tool(
                    name=GitTools.ADD,
                    description="Adds file contents to the staging area",
                    inputSchema=GitAdd.model_json_schema(),
                ),
                Tool(
                    name=GitTools.RESET,
                    description="Reset repository with advanced options (--soft, --mixed, --hard)",
                    inputSchema=GitReset.model_json_schema(),
                ),
                Tool(
                    name=GitTools.LOG,
                    description="Shows the commit logs",
                    inputSchema=GitLog.model_json_schema(),
                ),
                Tool(
                    name=GitTools.CREATE_BRANCH,
                    description="Creates a new branch from an optional base branch",
                    inputSchema=GitCreateBranch.model_json_schema(),
                ),
                Tool(
                    name=GitTools.CHECKOUT,
                    description="Switches branches",
                    inputSchema=GitCheckout.model_json_schema(),
                ),
                Tool(
                    name=GitTools.SHOW,
                    description="Shows the contents of a commit",
                    inputSchema=GitShow.model_json_schema(),
                ),
                Tool(
                    name=GitTools.INIT,
                    description="Initialize a new Git repository",
                    inputSchema=GitInit.model_json_schema(),
                ),
                Tool(
                    name=GitTools.PUSH,
                    description="Push commits to remote repository",
                    inputSchema=GitPush.model_json_schema(),
                ),
                Tool(
                    name=GitTools.PULL,
                    description="Pull changes from remote repository",
                    inputSchema=GitPull.model_json_schema(),
                ),
                Tool(
                    name=GitTools.DIFF_BRANCHES,
                    description="Show differences between two branches",
                    inputSchema=GitDiffBranches.model_json_schema(),
                ),
                Tool(
                    name=GitTools.REBASE,
                    description="Rebase current branch onto another branch",
                    inputSchema=GitRebase.model_json_schema(),
                ),
                Tool(
                    name=GitTools.MERGE,
                    description="Merge a branch into the current branch",
                    inputSchema=GitMerge.model_json_schema(),
                ),
                Tool(
                    name=GitTools.CHERRY_PICK,
                    description="Apply a commit from another branch to current branch",
                    inputSchema=GitCherryPick.model_json_schema(),
                ),
                Tool(
                    name=GitTools.ABORT,
                    description="Abort an in-progress git operation (rebase, merge, cherry-pick)",
                    inputSchema=GitAbort.model_json_schema(),
                ),
                Tool(
                    name=GitTools.CONTINUE,
                    description="Continue an in-progress git operation after resolving conflicts",
                    inputSchema=GitContinue.model_json_schema(),
                ),
                Tool(
                    name=GitTools.FETCH,
                    description="Fetch changes from remote repository",
                    inputSchema=GitFetch.model_json_schema(),
                ),
                Tool(
                    name=GitTools.REMOTE_ADD,
                    description="Add a remote repository",
                    inputSchema=GitRemoteAdd.model_json_schema(),
                ),
                Tool(
                    name=GitTools.REMOTE_REMOVE,
                    description="Remove a remote repository",
                    inputSchema=GitRemoteRemove.model_json_schema(),
                ),
                Tool(
                    name=GitTools.REMOTE_LIST,
                    description="List remote repositories",
                    inputSchema=GitRemoteList.model_json_schema(),
                ),
                Tool(
                    name=GitTools.REMOTE_GET_URL,
                    description="Get URL of a remote repository",
                    inputSchema=GitRemoteGetUrl.model_json_schema(),
                ),
                # GitHub Tools
                Tool(
                    name=GitHubTools.CREATE_ISSUE,
                    description="Create a new GitHub issue",
                    inputSchema=GitHubCreateIssue.model_json_schema(),
                ),
                Tool(
                    name=GitHubTools.LIST_ISSUES,
                    description="List GitHub issues with filtering options",
                    inputSchema=GitHubListIssues.model_json_schema(),
                ),
                Tool(
                    name=GitHubTools.UPDATE_ISSUE,
                    description="Update an existing GitHub issue",
                    inputSchema=GitHubUpdateIssue.model_json_schema(),
                ),
                Tool(
                    name=GitHubTools.GET_PR_CHECKS,
                    description="Get check runs for a pull request",
                    inputSchema=GitHubGetPrChecks.model_json_schema(),
                ),
                Tool(
                    name=GitHubTools.GET_PR_DETAILS,
                    description="Get detailed information about a pull request",
                    inputSchema=GitHubGetPrDetails.model_json_schema(),
                ),
                Tool(
                    name=GitHubTools.LIST_PULL_REQUESTS,
                    description="List pull requests with filtering options",
                    inputSchema=GitHubListPullRequests.model_json_schema(),
                ),
                Tool(
                    name=GitHubTools.GET_PR_STATUS,
                    description="Get the status of a pull request",
                    inputSchema=GitHubGetPrStatus.model_json_schema(),
                ),
                Tool(
                    name=GitHubTools.GET_PR_FILES,
                    description="Get files changed in a pull request",
                    inputSchema=GitHubGetPrFiles.model_json_schema(),
                ),
                Tool(
                    name=GitHubTools.EDIT_PR_DESCRIPTION,
                    description="Edit the description of a pull request",
                    inputSchema=GitHubEditPrDescription.model_json_schema(),
                ),
                Tool(
                    name=GitHubTools.GET_WORKFLOW_RUN,
                    description="Get detailed workflow run information",
                    inputSchema=GitHubGetWorkflowRun.model_json_schema(),
                ),
                Tool(
                    name=GitHubTools.LIST_WORKFLOW_RUNS,
                    description="List workflow runs for a repository with comprehensive filtering",
                    inputSchema=GitHubListWorkflowRuns.model_json_schema(),
                ),
                Tool(
                    name=GitHubTools.AWAIT_WORKFLOW_COMPLETION,
                    description="Monitor a GitHub Actions workflow run until completion. Enables automated CI response workflows by waiting for CI runs to complete and providing failure details when runs fail.",
                    inputSchema=GitHubAwaitWorkflowCompletion.model_json_schema(),
                ),
                Tool(
                    name=GitHubTools.CREATE_PR,
                    description="Create a new pull request",
                    inputSchema=GitHubCreatePr.model_json_schema(),
                ),
                Tool(
                    name=GitHubTools.MERGE_PR,
                    description="Merge a pull request",
                    inputSchema=GitHubMergePr.model_json_schema(),
                ),
                Tool(
                    name=GitHubTools.ADD_PR_COMMENT,
                    description="Add a comment to a pull request",
                    inputSchema=GitHubAddPrComment.model_json_schema(),
                ),
                Tool(
                    name=GitHubTools.CLOSE_PR,
                    description="Close a pull request",
                    inputSchema=GitHubClosePr.model_json_schema(),
                ),
                Tool(
                    name=GitHubTools.REOPEN_PR,
                    description="Reopen a closed pull request",
                    inputSchema=GitHubReopenPr.model_json_schema(),
                ),
                Tool(
                    name=GitHubTools.UPDATE_PR,
                    description="Update a pull request (title, body, state, or base)",
                    inputSchema=GitHubUpdatePr.model_json_schema(),
                ),
                Tool(
                    name=GitHubTools.GET_FAILING_JOBS,
                    description="Get detailed information about failing CI jobs for a pull request",
                    inputSchema=GitHubGetFailingJobs.model_json_schema(),
                ),
                # Azure DevOps Tools
                Tool(
                    name=AzureTools.GET_BUILD_STATUS,
                    description="Get the status of an Azure DevOps build/pipeline run",
                    inputSchema=AzureGetBuildStatus.model_json_schema(),
                ),
                Tool(
                    name=AzureTools.GET_BUILD_LOGS,
                    description="Get logs from an Azure DevOps build",
                    inputSchema=AzureGetBuildLogs.model_json_schema(),
                ),
                Tool(
                    name=AzureTools.GET_FAILING_JOBS,
                    description="Get detailed information about failing jobs in an Azure DevOps build",
                    inputSchema=AzureGetFailingJobs.model_json_schema(),
                ),
                Tool(
                    name=AzureTools.LIST_BUILDS,
                    description="List Azure DevOps builds with filtering options",
                    inputSchema=AzureListBuilds.model_json_schema(),
                ),
            ]

        @server.call_tool()
        async def call_tool(name: str, arguments: dict) -> list[dict]:
            """Handle tool calls with middleware processing."""
            logger.debug(f"[CALL_TOOL] name={name}, arguments={arguments}")

            try:
                # Execute the tool and get the result
                # Execute tool operation

                result = await self._execute_tool_operation(name, arguments)

                # Process through middleware chain for token limits and optimization
                if self._middleware_manager:
                    try:
                        # Create a proper MCP-style response that middleware can process
                        from dataclasses import dataclass

                        @dataclass
                        class TextContent:
                            text: str
                            type: str = "text"

                        @dataclass
                        class MCPResponse:
                            content: list[TextContent]

                        # Create the response structure middleware expects
                        mcp_response = MCPResponse(
                            content=[TextContent(text=str(result))]
                        )

                        # Process through middleware chain
                        processed_response = (
                            await self._middleware_manager.process_request(mcp_response)
                        )

                        # Extract the processed text and return in standard MCP format
                        if (
                            hasattr(processed_response, "content")
                            and processed_response.content
                        ):
                            processed_text = processed_response.content[0].text
                            return [{"type": "text", "text": processed_text}]
                        else:
                            # If middleware didn't return expected format, use original result
                            return [{"type": "text", "text": str(result)}]

                    except Exception as e:
                        logger.warning(
                            f"Middleware processing failed, using original result: {e}"
                        )
                        return [{"type": "text", "text": str(result)}]
                else:
                    # No middleware available, return result directly
                    return [{"type": "text", "text": str(result)}]

            except Exception as e:
                logger.error(f"[CALL_TOOL] ERROR: {e}")
                logger.error(f"Error executing tool {name}: {e}")
                return [{"type": "text", "text": f"Error: {e}"}]

        logger.info("MCP tools registered successfully")

    async def _execute_tool_operation(self, name: str, arguments: dict):
        """Execute the actual tool logic without middleware."""
        # COMPREHENSIVE INTEGRATED LOGGING
        logger.debug(f"Executing tool: {name}")

        # Import git operations (must be done here since they're not at module level)

        from ..git.operations import (
            git_abort,
            git_add,
            git_branch_list,
            git_checkout,
            git_cherry_pick,
            git_commit,
            git_continue,
            git_create_branch,
            git_diff,
            git_diff_branches,
            git_diff_staged,
            git_diff_unstaged,
            git_fetch,
            git_init,
            git_log,
            git_merge,
            git_pull,
            git_push,
            git_rebase,
            git_remote_add,
            git_remote_get_url,
            git_remote_list,
            git_remote_remove,
            git_reset,
            git_show,
            git_status,
        )
        from ..utils.git_import import Repo

        # Get repository path from arguments
        default_repo_path: str = (
            str(self.config.repository_path) if self.config.repository_path else "."
        )
        repo_path = arguments.get("repo_path", default_repo_path)

        # Route to appropriate git or GitHub operation
        # Special case: git_init doesn't need an existing repository
        if name == GitTools.INIT:
            result = git_init(repo_path)
        # Git tools that require an existing repository
        elif name in [
            GitTools.STATUS,
            GitTools.DIFF_UNSTAGED,
            GitTools.DIFF_STAGED,
            GitTools.DIFF,
            GitTools.COMMIT,
            GitTools.ADD,
            GitTools.RESET,
            GitTools.LOG,
            GitTools.CREATE_BRANCH,
            GitTools.CHECKOUT,
            GitTools.SHOW,
            GitTools.PUSH,
            GitTools.PULL,
            GitTools.DIFF_BRANCHES,
            GitTools.REBASE,
            GitTools.MERGE,
            GitTools.CHERRY_PICK,
            GitTools.ABORT,
            GitTools.CONTINUE,
            GitTools.BRANCH_LIST,
            GitTools.FETCH,
            GitTools.REMOTE_ADD,
            GitTools.REMOTE_REMOVE,
            GitTools.REMOTE_LIST,
            GitTools.REMOTE_GET_URL,
        ]:
            # Create Repo object for operations that need an existing repository
            repo = Repo(repo_path)

            if name == GitTools.STATUS:
                result = git_status(repo)
            elif name == GitTools.DIFF_UNSTAGED:
                result = git_diff_unstaged(repo)
            elif name == GitTools.DIFF_STAGED:
                result = git_diff_staged(repo)
            elif name == GitTools.DIFF:
                result = git_diff(repo, arguments["target"])
            elif name == GitTools.COMMIT:
                result = git_commit(
                    repo,
                    arguments["message"],
                    gpg_sign=arguments.get("gpg_sign", False),
                    gpg_key_id=arguments.get("gpg_key_id"),
                )
            elif name == GitTools.ADD:
                result = git_add(repo, arguments["files"])
            elif name == GitTools.RESET:
                result = git_reset(
                    repo,
                    mode=arguments.get("mode", "mixed"),
                    target=arguments.get("target"),
                )
            elif name == GitTools.LOG:
                result = git_log(repo, max_count=arguments.get("max_count", 10))
            elif name == GitTools.CREATE_BRANCH:
                base_branch_value = arguments.get("base_branch")
                if base_branch_value is not None:
                    result = git_create_branch(
                        repo, arguments["branch_name"], base_branch_value
                    )
                else:
                    result = git_create_branch(repo, arguments["branch_name"])
            elif name == GitTools.CHECKOUT:
                result = git_checkout(repo, arguments["branch_name"])
            elif name == GitTools.SHOW:
                result = git_show(repo, arguments["revision"])
            elif name == GitTools.PUSH:
                result = git_push(
                    repo,
                    remote=arguments.get("remote", "origin"),
                    branch=arguments.get("branch"),
                    force=arguments.get("force", False),
                )
            elif name == GitTools.PULL:
                result = git_pull(
                    repo,
                    remote=arguments.get("remote", "origin"),
                    branch=arguments.get("branch"),
                )
            elif name == GitTools.DIFF_BRANCHES:
                result = git_diff_branches(
                    repo, arguments["base_branch"], arguments["target_branch"]
                )
            elif name == GitTools.REBASE:
                result = git_rebase(
                    repo,
                    arguments["target_branch"],
                )
            elif name == GitTools.MERGE:
                result = git_merge(
                    repo,
                    arguments["source_branch"],
                    strategy=arguments.get("strategy", "merge"),
                    message=arguments.get("message"),
                )
            elif name == GitTools.CHERRY_PICK:
                result = git_cherry_pick(repo, arguments["commit_hash"])
            elif name == GitTools.ABORT:
                result = git_abort(repo, arguments["operation"])
            elif name == GitTools.CONTINUE:
                result = git_continue(repo, arguments["operation"])
            elif name == GitTools.BRANCH_LIST:
                result = git_branch_list(
                    repo,
                    remote=arguments.get("remote", False),
                    all=arguments.get("all", False),
                    pattern=arguments.get("pattern"),
                )
            elif name == GitTools.FETCH:
                result = git_fetch(repo, remote=arguments.get("remote", "origin"))
            elif name == GitTools.REMOTE_ADD:
                result = git_remote_add(repo, arguments["name"], arguments["url"])
            elif name == GitTools.REMOTE_REMOVE:
                result = git_remote_remove(repo, arguments["name"])
            elif name == GitTools.REMOTE_LIST:
                result = git_remote_list(repo)
            elif name == GitTools.REMOTE_GET_URL:
                result = git_remote_get_url(repo, arguments["name"])
        # GitHub Tools (don't require a Repo object)
        elif name == GitHubTools.CREATE_ISSUE:
            from ..github.api import github_create_issue

            result = await github_create_issue(
                repo_owner=arguments["repo_owner"],
                repo_name=arguments["repo_name"],
                title=arguments["title"],
                body=arguments.get("body"),
                labels=arguments.get("labels"),
                assignees=arguments.get("assignees"),
                milestone=arguments.get("milestone"),
            )
        elif name == GitHubTools.LIST_ISSUES:
            from ..github.api import github_list_issues

            result = await github_list_issues(
                repo_owner=arguments["repo_owner"],
                repo_name=arguments["repo_name"],
                state=arguments.get("state", "open"),
                labels=arguments.get("labels"),
                assignee=arguments.get("assignee"),
                creator=arguments.get("creator"),
                mentioned=arguments.get("mentioned"),
                milestone=arguments.get("milestone"),
                sort=arguments.get("sort", "created"),
                direction=arguments.get("direction", "desc"),
                since=arguments.get("since"),
                per_page=arguments.get("per_page", 30),
                page=arguments.get("page", 1),
            )
        elif name == GitHubTools.UPDATE_ISSUE:
            from ..github.api import github_update_issue

            result = await github_update_issue(
                repo_owner=arguments["repo_owner"],
                repo_name=arguments["repo_name"],
                issue_number=arguments["issue_number"],
                title=arguments.get("title"),
                body=arguments.get("body"),
                state=arguments.get("state"),
                labels=arguments.get("labels"),
                assignees=arguments.get("assignees"),
                milestone=arguments.get("milestone"),
            )
        elif name == GitHubTools.GET_PR_CHECKS:
            from ..github.api import github_get_pr_checks

            result = await github_get_pr_checks(
                repo_owner=arguments["repo_owner"],
                repo_name=arguments["repo_name"],
                pr_number=arguments["pr_number"],
                status=arguments.get("status"),
                conclusion=arguments.get("conclusion"),
            )
        elif name == GitHubTools.GET_PR_DETAILS:
            from ..github.api import github_get_pr_details

            result = await github_get_pr_details(
                repo_owner=arguments["repo_owner"],
                repo_name=arguments["repo_name"],
                pr_number=arguments["pr_number"],
                include_files=arguments.get("include_files", False),
                include_reviews=arguments.get("include_reviews", False),
            )
        elif name == GitHubTools.LIST_PULL_REQUESTS:
            from ..github.api import github_list_pull_requests

            result = await github_list_pull_requests(
                repo_owner=arguments["repo_owner"],
                repo_name=arguments["repo_name"],
                state=arguments.get("state", "open"),
                head=arguments.get("head"),
                base=arguments.get("base"),
                sort=arguments.get("sort", "created"),
                direction=arguments.get("direction", "desc"),
                per_page=arguments.get("per_page", 30),
                page=arguments.get("page", 1),
            )
        elif name == GitHubTools.GET_PR_STATUS:
            from ..github.api import github_get_pr_status

            result = await github_get_pr_status(
                repo_owner=arguments["repo_owner"],
                repo_name=arguments["repo_name"],
                pr_number=arguments["pr_number"],
            )
        elif name == GitHubTools.GET_PR_FILES:
            from ..github.api import github_get_pr_files

            result = await github_get_pr_files(
                repo_owner=arguments["repo_owner"],
                repo_name=arguments["repo_name"],
                pr_number=arguments["pr_number"],
                per_page=arguments.get("per_page", 30),
                page=arguments.get("page", 1),
                include_patch=arguments.get("include_patch", False),
            )
        elif name == GitHubTools.EDIT_PR_DESCRIPTION:
            from ..github.api import github_edit_pr_description

            result = await github_edit_pr_description(
                repo_owner=arguments["repo_owner"],
                repo_name=arguments["repo_name"],
                pr_number=arguments["pr_number"],
                description=arguments["description"],
            )
        elif name == GitHubTools.GET_WORKFLOW_RUN:
            from ..github.api import github_get_workflow_run

            result = await github_get_workflow_run(
                repo_owner=arguments["repo_owner"],
                repo_name=arguments["repo_name"],
                run_id=arguments["run_id"],
                include_logs=arguments.get("include_logs", False),
            )
        elif name == GitHubTools.LIST_WORKFLOW_RUNS:
            from ..github.api import github_list_workflow_runs

            result = await github_list_workflow_runs(
                repo_owner=arguments["repo_owner"],
                repo_name=arguments["repo_name"],
                workflow_id=arguments.get("workflow_id"),
                actor=arguments.get("actor"),
                branch=arguments.get("branch"),
                event=arguments.get("event"),
                status=arguments.get("status"),
                conclusion=arguments.get("conclusion"),
                per_page=arguments.get("per_page", 30),
                page=arguments.get("page", 1),
                created=arguments.get("created"),
                exclude_pull_requests=arguments.get("exclude_pull_requests", False),
                check_suite_id=arguments.get("check_suite_id"),
                head_sha=arguments.get("head_sha"),
            )
        elif name == GitHubTools.AWAIT_WORKFLOW_COMPLETION:
            from ..github.api import github_await_workflow_completion

            # Validate required arguments
            if "repo_owner" not in arguments or "repo_name" not in arguments:
                result = "Error: repo_owner and repo_name are required arguments"
            else:
                result = await github_await_workflow_completion(
                    repo_owner=arguments["repo_owner"],
                    repo_name=arguments["repo_name"],
                    run_id=arguments.get("run_id"),
                    timeout_minutes=arguments.get("timeout_minutes", 15),
                    poll_interval_seconds=arguments.get("poll_interval_seconds", 20),
                )
        elif name == GitHubTools.CREATE_PR:
            from ..github.api import github_create_pr

            result = await github_create_pr(
                repo_owner=arguments["repo_owner"],
                repo_name=arguments["repo_name"],
                title=arguments["title"],
                head=arguments["head"],
                base=arguments["base"],
                body=arguments.get("body"),
                draft=arguments.get("draft", False),
            )
        elif name == GitHubTools.MERGE_PR:
            from ..github.api import github_merge_pr

            result = await github_merge_pr(
                repo_owner=arguments["repo_owner"],
                repo_name=arguments["repo_name"],
                pr_number=arguments["pr_number"],
                commit_title=arguments.get("commit_title"),
                commit_message=arguments.get("commit_message"),
                merge_method=arguments.get("merge_method", "merge"),
            )
        elif name == GitHubTools.ADD_PR_COMMENT:
            from ..github.api import github_add_pr_comment

            result = await github_add_pr_comment(
                repo_owner=arguments["repo_owner"],
                repo_name=arguments["repo_name"],
                pr_number=arguments["pr_number"],
                body=arguments["body"],
            )
        elif name == GitHubTools.CLOSE_PR:
            from ..github.api import github_close_pr

            result = await github_close_pr(
                repo_owner=arguments["repo_owner"],
                repo_name=arguments["repo_name"],
                pr_number=arguments["pr_number"],
            )
        elif name == GitHubTools.REOPEN_PR:
            from ..github.api import github_reopen_pr

            result = await github_reopen_pr(
                repo_owner=arguments["repo_owner"],
                repo_name=arguments["repo_name"],
                pr_number=arguments["pr_number"],
            )
        elif name == GitHubTools.UPDATE_PR:
            from ..github.api import github_update_pr

            result = await github_update_pr(
                repo_owner=arguments["repo_owner"],
                repo_name=arguments["repo_name"],
                pr_number=arguments["pr_number"],
                title=arguments.get("title"),
                body=arguments.get("body"),
                state=arguments.get("state"),
                base=arguments.get("base"),
            )
        elif name == GitHubTools.GET_FAILING_JOBS:
            from ..github.api import github_get_failing_jobs

            result = await github_get_failing_jobs(
                repo_owner=arguments["repo_owner"],
                repo_name=arguments["repo_name"],
                pr_number=arguments["pr_number"],
                include_logs=arguments.get("include_logs", True),
                include_annotations=arguments.get("include_annotations", True),
            )
        elif name == AzureTools.GET_BUILD_STATUS:
            from ..azure.api import azure_get_build_status

            result = await azure_get_build_status(
                project=arguments["project"],
                build_id=arguments["build_id"],
            )
        elif name == AzureTools.GET_BUILD_LOGS:
            from ..azure.api import azure_get_build_logs

            result = await azure_get_build_logs(
                project=arguments["project"],
                build_id=arguments["build_id"],
                log_id=arguments.get("log_id"),
                tail_lines=arguments.get("tail_lines", 500),
            )
        elif name == AzureTools.GET_FAILING_JOBS:
            from ..azure.api import azure_get_failing_jobs

            result = await azure_get_failing_jobs(
                project=arguments["project"],
                build_id=arguments["build_id"],
                include_logs=arguments.get("include_logs", True),
                log_tail_lines=arguments.get("log_tail_lines", 500),
            )
        elif name == AzureTools.LIST_BUILDS:
            from ..azure.api import azure_list_builds

            result = await azure_list_builds(
                project=arguments["project"],
                repository_id=arguments.get("repository_id"),
                branch_name=arguments.get("branch_name"),
                status=arguments.get("status"),
                result=arguments.get("result"),
                top=arguments.get("top", 30),
                continuation_token=arguments.get("continuation_token"),
            )
        else:
            raise ValueError(f"Unknown tool: {name}")

        return result


async def main(
    repository_path: Path | None = None,
    test_mode: bool = False,
    debug_mode: bool = False,
) -> None:
    """
    Main entry point for the MCP Git Server Application.

    This function provides a simple interface for starting the server application
    with common configuration options.

    Args:
        repository_path: Optional path to the git repository to serve
        test_mode: Whether to run in test mode
        debug_mode: Whether to enable debug mode

    Example:
        >>> await main(repository_path=Path("/path/to/repo"))
    """
    # Configure logging
    log_level = logging.DEBUG if debug_mode else logging.INFO
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Create application configuration
    config = ServerApplicationConfig(
        repository_path=repository_path,
        test_mode=test_mode,
        debug_mode=debug_mode,
    )

    # Create and start the application
    app = ServerApplication(config)

    try:
        await app.start()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Application error: {e}")
        raise
    finally:
        await app.stop()


# Backward compatibility alias
serve = main


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MCP Git Server Application")
    parser.add_argument(
        "--repository", type=Path, help="Path to the git repository to serve"
    )
    parser.add_argument("--test-mode", action="store_true", help="Run in test mode")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    args = parser.parse_args()

    # Run the server application
    asyncio.run(
        main(
            repository_path=args.repository,
            test_mode=args.test_mode,
            debug_mode=args.debug,
        )
    )
