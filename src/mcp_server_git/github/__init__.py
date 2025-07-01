"""GitHub integration for MCP Git Server"""

from .api import (
    github_add_pr_comment,
    github_close_pr,
    github_create_pr,
    github_get_failing_jobs,
    github_get_pr_checks,
    github_get_pr_details,
    github_get_pr_files,
    github_get_pr_status,
    github_get_workflow_run,
    github_list_pull_requests,
    github_merge_pr,
    github_reopen_pr,
    github_update_pr,
)
from .client import GitHubClient, get_github_client
from .models import (
    GitHubGetFailingJobs,
    GitHubGetPRChecks,
    GitHubGetPRDetails,
    GitHubGetPRFiles,
    GitHubGetPRStatus,
    GitHubGetWorkflowRun,
    GitHubListPullRequests,
)

__all__ = [
    "GitHubClient",
    "get_github_client",
    # Read operations
    "github_get_pr_checks",
    "github_get_failing_jobs",
    "github_get_workflow_run",
    "github_get_pr_details",
    "github_list_pull_requests",
    "github_get_pr_status",
    "github_get_pr_files",
    # Write operations
    "github_update_pr",
    "github_create_pr",
    "github_merge_pr",
    "github_add_pr_comment",
    "github_close_pr",
    "github_reopen_pr",
    # Models
    "GitHubGetFailingJobs",
    "GitHubGetPRChecks",
    "GitHubGetPRDetails",
    "GitHubGetPRFiles",
    "GitHubGetPRStatus",
    "GitHubGetWorkflowRun",
    "GitHubListPullRequests",
]
