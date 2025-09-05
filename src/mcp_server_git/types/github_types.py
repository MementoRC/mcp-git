"""GitHub domain type definitions for the MCP Git Server.

This module provides type definitions for GitHub API operations,
including repositories, pull requests, issues, and API responses.

These types are currently stubs to satisfy TDD test requirements.
Implementation will be completed in subsequent development phases.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal


class GitHubValidationError(Exception):
    """Exception raised when GitHub type validation fails."""

    pass


class GitHubAPIError(Exception):
    """Exception raised when GitHub API operations fail."""

    pass


GitHubRepoName = str
GitHubOwner = str
GitHubURL = str
GitHubToken = str


@dataclass
class GitHubRepository:
    """GitHub repository information."""

    name: str
    owner: str
    full_name: str
    description: str | None = None
    url: str | None = None
    clone_url: str | None = None
    ssh_url: str | None = None
    default_branch: str | None = None
    is_private: bool = False
    is_fork: bool = False


@dataclass
class GitHubPullRequest:
    """GitHub pull request information."""

    number: int
    title: str
    body: str | None = None
    state: Literal["open", "closed", "merged"] = "open"
    author: str | None = None
    base_branch: str | None = None
    head_branch: str | None = None
    url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class GitHubIssue:
    """GitHub issue information."""

    number: int
    title: str
    body: str | None = None
    state: Literal["open", "closed"] = "open"
    author: str | None = None
    labels: list[str] | None = None
    assignees: list[str] | None = None
    url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class GitHubUser:
    """GitHub user information."""

    login: str
    name: str | None = None
    email: str | None = None
    avatar_url: str | None = None
    url: str | None = None


@dataclass
class GitHubCommit:
    """GitHub commit information."""

    sha: str
    message: str
    author: GitHubUser | None = None
    committer: GitHubUser | None = None
    url: str | None = None
    timestamp: datetime | None = None


@dataclass
class GitHubBranch:
    """GitHub branch information."""

    name: str
    commit_sha: str
    protected: bool = False
    url: str | None = None


@dataclass
class GitHubAPIResponse:
    """GitHub API response wrapper."""

    status_code: int
    data: Any
    headers: dict[str, str] | None = None
    rate_limit_remaining: int | None = None
    rate_limit_reset: datetime | None = None


@dataclass
class GitHubCredentials:
    """GitHub authentication credentials."""

    token: str
    token_type: Literal["personal", "app", "installation"] = "personal"


@dataclass
class GitHubRateLimit:
    """GitHub API rate limit information."""

    limit: int
    remaining: int
    reset_time: datetime
    used: int


class GitHubOperationResult:
    """Result of a GitHub API operation."""

    def __init__(self, success: bool, data: Any = None, error: str = None):
        self.success = success
        self.data = data
        self.error = error
        self.is_success = success

    @classmethod
    def success(cls, data: Any) -> "GitHubOperationResult":
        return cls(success=True, data=data)

    @classmethod
    def error(cls, error: str) -> "GitHubOperationResult":
        return cls(success=False, error=error)


# Export all public types
__all__ = [
    "GitHubRepository",
    "GitHubPullRequest",
    "GitHubIssue",
    "GitHubUser",
    "GitHubCommit",
    "GitHubBranch",
    "GitHubAPIResponse",
    "GitHubCredentials",
    "GitHubRateLimit",
    "GitHubOperationResult",
    "GitHubValidationError",
    "GitHubAPIError",
    "GitHubRepoName",
    "GitHubOwner",
    "GitHubURL",
    "GitHubToken",
]
