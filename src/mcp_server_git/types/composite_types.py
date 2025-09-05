"""Composite type definitions for the MCP Git Server.

This module provides complex type definitions that combine Git, GitHub, and MCP types
for advanced operations and integrations.

These types are currently stubs to satisfy TDD test requirements.
Implementation will be completed in subsequent development phases.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Union

# Import base types (these should be available)
from .git_types import (
    GitBranch,
    GitCommitInfo,
    GitOperationResult,
    GitRepositoryPath,
    GitStatusResult,
)
from .github_types import (
    GitHubOperationResult,
    GitHubPullRequest,
    GitHubRepository,
)
from .mcp_types import MCPRequest, MCPResponse, MCPTool
from .validation_types import ValidationResult


class CompositeOperationError(Exception):
    """Exception raised when composite operations fail."""

    pass


@dataclass
class GitHubIntegration:
    """Integration between Git repository and GitHub."""

    repository_path: GitRepositoryPath
    github_repo: GitHubRepository
    credentials: dict[str, str] | None = None

    def is_connected(self) -> bool:
        """Check if Git repo is connected to GitHub."""
        return self.github_repo is not None

    def sync_status(self) -> ValidationResult:
        """Check sync status between local and remote."""
        # Stub implementation
        return ValidationResult(is_valid=True, errors=[], warnings=[])


@dataclass
class MCPGitOperation:
    """MCP operation that involves Git commands."""

    request: MCPRequest
    git_commands: list[str]
    repository_path: GitRepositoryPath
    result: GitOperationResult | None = None

    def execute(self) -> MCPResponse:
        """Execute the Git operation and return MCP response."""
        # Stub implementation
        return MCPResponse(jsonrpc="2.0", id=self.request.id, result={})


@dataclass
class PullRequestContext:
    """Complete context for pull request operations."""

    pr: GitHubPullRequest
    local_repo: GitRepositoryPath
    base_branch: GitBranch
    head_branch: GitBranch
    commits: list[GitCommitInfo]
    status: GitStatusResult

    def can_merge(self) -> bool:
        """Check if PR can be merged safely."""
        return self.status.is_clean

    def get_diff_summary(self) -> dict[str, Any]:
        """Get summary of changes in the PR."""
        return {
            "commits": len(self.commits),
            "base_branch": str(self.base_branch),
            "head_branch": str(self.head_branch),
            "clean_status": self.status.is_clean,
        }


@dataclass
class RepositorySnapshot:
    """Complete snapshot of repository state."""

    repository_path: GitRepositoryPath
    current_branch: GitBranch
    status: GitStatusResult
    recent_commits: list[GitCommitInfo]
    github_info: GitHubRepository | None = None
    open_prs: list[GitHubPullRequest] | None = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

    def is_healthy(self) -> bool:
        """Check if repository is in a healthy state."""
        return self.status.is_clean and self.current_branch is not None

    def summary(self) -> dict[str, Any]:
        """Get repository summary."""
        return {
            "path": str(self.repository_path),
            "branch": str(self.current_branch),
            "clean": self.status.is_clean,
            "commits": len(self.recent_commits),
            "has_github": self.github_info is not None,
            "open_prs": len(self.open_prs) if self.open_prs else 0,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class WorkflowResult:
    """Result of a complex workflow operation."""

    success: bool
    steps: list[dict[str, Any]]
    git_operations: list[GitOperationResult]
    github_operations: list[GitHubOperationResult]
    final_state: RepositorySnapshot | None = None
    error_message: str | None = None

    @property
    def total_operations(self) -> int:
        """Get total number of operations performed."""
        return len(self.git_operations) + len(self.github_operations)

    @property
    def failed_operations(self) -> list[GitOperationResult | GitHubOperationResult]:
        """Get list of failed operations."""
        failed = []
        failed.extend([op for op in self.git_operations if not op.is_success])
        failed.extend([op for op in self.github_operations if not op.is_success])
        return failed

    def summary(self) -> dict[str, Any]:
        """Get workflow result summary."""
        return {
            "success": self.success,
            "total_steps": len(self.steps),
            "total_operations": self.total_operations,
            "failed_operations": len(self.failed_operations),
            "has_final_state": self.final_state is not None,
            "error": self.error_message,
        }


@dataclass
class MCPToolContext:
    """Context for executing MCP tools with Git/GitHub integration."""

    tool: MCPTool
    repository: GitRepositoryPath | None = None
    github_integration: GitHubIntegration | None = None
    user_context: dict[str, Any] | None = None

    def has_git_access(self) -> bool:
        """Check if tool has access to Git repository."""
        return self.repository is not None and self.repository.is_valid()

    def has_github_access(self) -> bool:
        """Check if tool has access to GitHub integration."""
        return (
            self.github_integration is not None
            and self.github_integration.is_connected()
        )

    def validate_permissions(self) -> ValidationResult:
        """Validate that tool has required permissions."""
        errors = []
        warnings = []

        if self.tool.name.startswith("git_") and not self.has_git_access():
            errors.append("Git tool requires repository access")

        if self.tool.name.startswith("github_") and not self.has_github_access():
            errors.append("GitHub tool requires GitHub integration")

        return ValidationResult(
            is_valid=len(errors) == 0, errors=errors, warnings=warnings
        )


class CompositeOperationBuilder:
    """Builder for complex composite operations."""

    def __init__(self):
        self._steps: list[dict[str, Any]] = []
        self._context: dict[str, Any] = {}

    def add_git_operation(
        self, operation: str, **kwargs
    ) -> "CompositeOperationBuilder":
        """Add a Git operation to the workflow."""
        self._steps.append({"type": "git", "operation": operation, "params": kwargs})
        return self

    def add_github_operation(
        self, operation: str, **kwargs
    ) -> "CompositeOperationBuilder":
        """Add a GitHub operation to the workflow."""
        self._steps.append({"type": "github", "operation": operation, "params": kwargs})
        return self

    def set_context(self, key: str, value: Any) -> "CompositeOperationBuilder":
        """Set context variable."""
        self._context[key] = value
        return self

    def build(self) -> dict[str, Any]:
        """Build the composite operation."""
        return {
            "steps": self._steps,
            "context": self._context,
            "total_steps": len(self._steps),
        }


# Type aliases for complex operations
GitHubWorkflow = list[tuple[str, dict[str, Any]]]
MCPOperationChain = list[tuple[MCPRequest, MCPResponse]]
RepositoryOperation = Union[GitOperationResult, GitHubOperationResult]


# Export all public types
__all__ = [
    "CompositeOperationError",
    "GitHubIntegration",
    "MCPGitOperation",
    "PullRequestContext",
    "RepositorySnapshot",
    "WorkflowResult",
    "MCPToolContext",
    "CompositeOperationBuilder",
    "GitHubWorkflow",
    "MCPOperationChain",
    "RepositoryOperation",
]
