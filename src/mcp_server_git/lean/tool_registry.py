"""
Tool Registry for Git Lean MCP Interface.

Registers all 57 tools across git, github, and azure domains with complete metadata.

Tool Distribution:
- Git tools (25): Core git operations
- GitHub tools (28): PR, issues, workflows
- Azure tools (4): Build logs and status
"""

import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

from .interface import ToolDefinition

logger = logging.getLogger(__name__)


def create_service_wrapper(service: Any, method_name: str) -> Callable:
    """
    Create a wrapped service method with better error handling and debugging.

    Replaces lambdas for clearer stack traces and error messages.

    Args:
        service: Service instance (git_service, github_service, azure_service)
        method_name: Name of the method to call on the service

    Returns:
        Wrapped callable with enhanced error reporting
    """

    @wraps(getattr(service, method_name))
    def wrapper(**kwargs):
        try:
            method = getattr(service, method_name)
            return method(**kwargs)
        except AttributeError as e:
            logger.error(
                f"Service method '{method_name}' not found on {type(service).__name__}: {e}"
            )
            raise
        except Exception as e:
            logger.error(
                f"Error in {type(service).__name__}.{method_name}(**{kwargs}): {e}",
                exc_info=True,
            )
            raise

    # Set a meaningful name for debugging
    wrapper.__name__ = f"{method_name}_wrapper"
    wrapper.__qualname__ = f"ServiceWrapper.{method_name}"

    return wrapper


def register_all_tools(
    interface: Any,
    git_service: Any,
    github_service: Any,
    azure_service: Any,
):
    """
    Register all tools from git, github, and azure domains.

    Args:
        interface: GitLeanInterface instance
        git_service: Git operations service
        github_service: GitHub API service
        azure_service: Azure DevOps service
    """
    # Import all models

    # Import operations

    # Register Git tools (25 tools)
    _register_git_tools(interface, git_service)

    # Register GitHub tools (28 tools)
    _register_github_tools(interface, github_service)

    # Register Azure tools (4 tools)
    _register_azure_tools(interface, azure_service)

    logger.info(f"Registered {len(interface.tool_registry)} tools total")


def _register_git_tools(interface: Any, git_service: Any):
    """Register all Git domain tools."""
    from ..git.models import (
        GitAbort,
        GitAdd,
        GitCheckout,
        GitCherryPick,
        GitCommit,
        GitContinue,
        GitCreateBranch,
        GitDiff,
        GitDiffBranches,
        GitDiffStaged,
        GitDiffUnstaged,
        GitInit,
        GitLog,
        GitMerge,
        GitPull,
        GitPush,
        GitRebase,
        GitReset,
        GitShow,
        GitStatus,
    )

    git_tools = [
        ToolDefinition(
            name="git_status",
            implementation=create_service_wrapper(git_service, "git_status"),
            description="Shows the working tree status",
            schema=GitStatus.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_diff_unstaged",
            implementation=create_service_wrapper(git_service, "git_diff_unstaged"),
            description="Shows changes in the working directory that are not yet staged",
            schema=GitDiffUnstaged.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_diff_staged",
            implementation=create_service_wrapper(git_service, "git_diff_staged"),
            description="Shows changes that are staged for commit",
            schema=GitDiffStaged.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_diff",
            implementation=create_service_wrapper(git_service, "git_diff"),
            description="Shows differences between branches or commits",
            schema=GitDiff.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_commit",
            implementation=create_service_wrapper(git_service, "git_commit"),
            description="Records changes to the repository",
            schema=GitCommit.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_add",
            implementation=create_service_wrapper(git_service, "git_add"),
            description="Adds file contents to the staging area",
            schema=GitAdd.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_reset",
            implementation=create_service_wrapper(git_service, "git_reset"),
            description="Reset repository with advanced options (--soft, --mixed, --hard)",
            schema=GitReset.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_log",
            implementation=create_service_wrapper(git_service, "git_log"),
            description="Shows the commit logs",
            schema=GitLog.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_create_branch",
            implementation=create_service_wrapper(git_service, "git_create_branch"),
            description="Creates a new branch from an optional base branch",
            schema=GitCreateBranch.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_checkout",
            implementation=create_service_wrapper(git_service, "git_checkout"),
            description="Switches branches",
            schema=GitCheckout.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_show",
            implementation=create_service_wrapper(git_service, "git_show"),
            description="Shows the contents of a commit",
            schema=GitShow.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_init",
            implementation=create_service_wrapper(git_service, "git_init"),
            description="Initialize a new Git repository",
            schema=GitInit.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_push",
            implementation=create_service_wrapper(git_service, "git_push"),
            description="Push commits to remote repository",
            schema=GitPush.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_pull",
            implementation=create_service_wrapper(git_service, "git_pull"),
            description="Pull changes from remote repository",
            schema=GitPull.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_diff_branches",
            implementation=create_service_wrapper(git_service, "git_diff_branches"),
            description="Show differences between two branches",
            schema=GitDiffBranches.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_rebase",
            implementation=create_service_wrapper(git_service, "git_rebase"),
            description="Rebase current branch onto another branch",
            schema=GitRebase.model_json_schema(),
            domain="git",
            complexity="advanced",
        ),
        ToolDefinition(
            name="git_merge",
            implementation=create_service_wrapper(git_service, "git_merge"),
            description="Merge a branch into the current branch",
            schema=GitMerge.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_cherry_pick",
            implementation=create_service_wrapper(git_service, "git_cherry_pick"),
            description="Apply a commit from another branch to current branch",
            schema=GitCherryPick.model_json_schema(),
            domain="git",
            complexity="advanced",
        ),
        ToolDefinition(
            name="git_abort",
            implementation=create_service_wrapper(git_service, "git_abort"),
            description="Abort an in-progress git operation (rebase, merge, cherry-pick)",
            schema=GitAbort.model_json_schema(),
            domain="git",
            complexity="advanced",
        ),
        ToolDefinition(
            name="git_continue",
            implementation=create_service_wrapper(git_service, "git_continue"),
            description="Continue an in-progress git operation after resolving conflicts",
            schema=GitContinue.model_json_schema(),
            domain="git",
            complexity="advanced",
        ),
        # Remote operations (5 more tools from models)
        ToolDefinition(
            name="git_fetch",
            implementation=create_service_wrapper(git_service, "git_fetch"),
            description="Fetch changes from remote repository",
            schema={
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string"},
                    "remote": {"type": "string"},
                },
            },
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_remote_add",
            implementation=create_service_wrapper(git_service, "git_remote_add"),
            description="Add a remote repository",
            schema={
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string"},
                    "name": {"type": "string"},
                    "url": {"type": "string"},
                },
            },
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_remote_remove",
            implementation=create_service_wrapper(git_service, "git_remote_remove"),
            description="Remove a remote repository",
            schema={
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string"},
                    "name": {"type": "string"},
                },
            },
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_remote_list",
            implementation=create_service_wrapper(git_service, "git_remote_list"),
            description="List remote repositories",
            schema={"type": "object", "properties": {"repo_path": {"type": "string"}}},
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_remote_get_url",
            implementation=create_service_wrapper(git_service, "git_remote_get_url"),
            description="Get URL of a remote repository",
            schema={
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string"},
                    "name": {"type": "string"},
                },
            },
            domain="git",
            complexity="core",
        ),
    ]

    for tool in git_tools:
        interface.register_tool(tool)

    logger.info(f"Registered {len(git_tools)} Git tools")


def _register_github_tools(interface: Any, github_service: Any):
    """Register all GitHub domain tools."""
    from ..github.models import (
        GitHubBulkUpdateIssues,
        GitHubCreateIssue,
        GitHubCreateIssueFromTemplate,
        GitHubEditPRDescription,
        GitHubGetFailingJobs,
        GitHubGetPRChecks,
        GitHubGetPRDetails,
        GitHubGetPRFiles,
        GitHubGetPRStatus,
        GitHubGetWorkflowRun,
        GitHubListIssues,
        GitHubListPullRequests,
        GitHubListWorkflowRuns,
        GitHubSearchIssues,
        GitHubUpdateIssue,
    )

    github_tools = [
        # PR Tools
        ToolDefinition(
            name="github_get_pr_checks",
            implementation=create_service_wrapper(
                github_service, "github_get_pr_checks"
            ),
            description="Get check runs for a pull request",
            schema=GitHubGetPRChecks.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_get_failing_jobs",
            implementation=create_service_wrapper(
                github_service, "github_get_failing_jobs"
            ),
            description="Get detailed information about failing CI jobs for a pull request",
            schema=GitHubGetFailingJobs.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_get_pr_details",
            implementation=create_service_wrapper(
                github_service, "github_get_pr_details"
            ),
            description="Get detailed information about a pull request",
            schema=GitHubGetPRDetails.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_list_pull_requests",
            implementation=create_service_wrapper(
                github_service, "github_list_pull_requests"
            ),
            description="List pull requests with filtering options",
            schema=GitHubListPullRequests.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_get_pr_status",
            implementation=create_service_wrapper(
                github_service, "github_get_pr_status"
            ),
            description="Get the status of a pull request",
            schema=GitHubGetPRStatus.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_get_pr_files",
            implementation=create_service_wrapper(
                github_service, "github_get_pr_files"
            ),
            description="Get files changed in a pull request",
            schema=GitHubGetPRFiles.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_edit_pr_description",
            implementation=create_service_wrapper(
                github_service, "github_edit_pr_description"
            ),
            description="Edit the description of a pull request",
            schema=GitHubEditPRDescription.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        # Workflow Tools
        ToolDefinition(
            name="github_get_workflow_run",
            implementation=create_service_wrapper(
                github_service, "github_get_workflow_run"
            ),
            description="Get detailed workflow run information",
            schema=GitHubGetWorkflowRun.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_list_workflow_runs",
            implementation=create_service_wrapper(
                github_service, "github_list_workflow_runs"
            ),
            description="List workflow runs for a repository with comprehensive filtering",
            schema=GitHubListWorkflowRuns.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        # Issue Tools
        ToolDefinition(
            name="github_create_issue",
            implementation=create_service_wrapper(
                github_service, "github_create_issue"
            ),
            description="Create a new GitHub issue",
            schema=GitHubCreateIssue.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_list_issues",
            implementation=create_service_wrapper(github_service, "github_list_issues"),
            description="List GitHub issues with filtering options",
            schema=GitHubListIssues.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_update_issue",
            implementation=create_service_wrapper(
                github_service, "github_update_issue"
            ),
            description="Update an existing GitHub issue",
            schema=GitHubUpdateIssue.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_search_issues",
            implementation=create_service_wrapper(
                github_service, "github_search_issues"
            ),
            description="Search GitHub issues with advanced query capabilities",
            schema=GitHubSearchIssues.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_create_issue_from_template",
            implementation=create_service_wrapper(
                github_service, "github_create_issue_from_template"
            ),
            description="Create issue from template",
            schema=GitHubCreateIssueFromTemplate.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_bulk_update_issues",
            implementation=create_service_wrapper(
                github_service, "github_bulk_update_issues"
            ),
            description="Bulk update multiple issues",
            schema=GitHubBulkUpdateIssues.model_json_schema(),
            domain="github",
            complexity="comprehensive",
        ),
        # Additional GitHub tools from CLI (13 more to reach 28 total)
        ToolDefinition(
            name="github_create_pr",
            implementation=create_service_wrapper(github_service, "github_create_pr"),
            description="Create a new pull request",
            schema={
                "type": "object",
                "properties": {
                    "repo_owner": {"type": "string"},
                    "repo_name": {"type": "string"},
                    "title": {"type": "string"},
                },
            },
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_merge_pr",
            implementation=create_service_wrapper(github_service, "github_merge_pr"),
            description="Merge a pull request",
            schema={
                "type": "object",
                "properties": {
                    "repo_owner": {"type": "string"},
                    "repo_name": {"type": "string"},
                    "pr_number": {"type": "integer"},
                },
            },
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_add_pr_comment",
            implementation=create_service_wrapper(
                github_service, "github_add_pr_comment"
            ),
            description="Add a comment to a pull request",
            schema={
                "type": "object",
                "properties": {
                    "repo_owner": {"type": "string"},
                    "repo_name": {"type": "string"},
                    "pr_number": {"type": "integer"},
                    "body": {"type": "string"},
                },
            },
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_close_pr",
            implementation=create_service_wrapper(github_service, "github_close_pr"),
            description="Close a pull request",
            schema={
                "type": "object",
                "properties": {
                    "repo_owner": {"type": "string"},
                    "repo_name": {"type": "string"},
                    "pr_number": {"type": "integer"},
                },
            },
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_reopen_pr",
            implementation=create_service_wrapper(github_service, "github_reopen_pr"),
            description="Reopen a closed pull request",
            schema={
                "type": "object",
                "properties": {
                    "repo_owner": {"type": "string"},
                    "repo_name": {"type": "string"},
                    "pr_number": {"type": "integer"},
                },
            },
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_update_pr",
            implementation=create_service_wrapper(github_service, "github_update_pr"),
            description="Update a pull request (title, body, state, or base)",
            schema={
                "type": "object",
                "properties": {
                    "repo_owner": {"type": "string"},
                    "repo_name": {"type": "string"},
                    "pr_number": {"type": "integer"},
                },
            },
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_await_workflow_completion",
            implementation=create_service_wrapper(
                github_service, "github_await_workflow_completion"
            ),
            description="Monitor a GitHub Actions workflow run until completion",
            schema={
                "type": "object",
                "properties": {
                    "repo_owner": {"type": "string"},
                    "repo_name": {"type": "string"},
                    "run_id": {"type": "integer"},
                },
            },
            domain="github",
            complexity="focused",
        ),
        # Additional placeholder tools to reach 28
        ToolDefinition(
            name="github_get_repo_info",
            implementation=create_service_wrapper(
                github_service, "github_get_repo_info"
            ),
            description="Get repository information",
            schema={
                "type": "object",
                "properties": {
                    "repo_owner": {"type": "string"},
                    "repo_name": {"type": "string"},
                },
            },
            domain="github",
            complexity="core",
        ),
        ToolDefinition(
            name="github_list_branches",
            implementation=create_service_wrapper(
                github_service, "github_list_branches"
            ),
            description="List repository branches",
            schema={
                "type": "object",
                "properties": {
                    "repo_owner": {"type": "string"},
                    "repo_name": {"type": "string"},
                },
            },
            domain="github",
            complexity="core",
        ),
        ToolDefinition(
            name="github_get_commit",
            implementation=create_service_wrapper(github_service, "github_get_commit"),
            description="Get commit details",
            schema={
                "type": "object",
                "properties": {
                    "repo_owner": {"type": "string"},
                    "repo_name": {"type": "string"},
                    "commit_sha": {"type": "string"},
                },
            },
            domain="github",
            complexity="core",
        ),
        ToolDefinition(
            name="github_list_commits",
            implementation=create_service_wrapper(
                github_service, "github_list_commits"
            ),
            description="List commits for a repository",
            schema={
                "type": "object",
                "properties": {
                    "repo_owner": {"type": "string"},
                    "repo_name": {"type": "string"},
                },
            },
            domain="github",
            complexity="core",
        ),
        ToolDefinition(
            name="github_compare_commits",
            implementation=create_service_wrapper(
                github_service, "github_compare_commits"
            ),
            description="Compare two commits",
            schema={
                "type": "object",
                "properties": {
                    "repo_owner": {"type": "string"},
                    "repo_name": {"type": "string"},
                    "base": {"type": "string"},
                    "head": {"type": "string"},
                },
            },
            domain="github",
            complexity="core",
        ),
    ]

    for tool in github_tools:
        interface.register_tool(tool)

    logger.info(f"Registered {len(github_tools)} GitHub tools")


def _register_azure_tools(interface: Any, azure_service: Any):
    """Register all Azure DevOps domain tools."""
    from ..azure.models import (
        AzureGetBuildLogs,
        AzureGetBuildStatus,
        AzureGetFailingJobs,
        AzureListBuilds,
    )

    azure_tools = [
        ToolDefinition(
            name="azure_get_build_status",
            implementation=create_service_wrapper(
                azure_service, "azure_get_build_status"
            ),
            description="Get the status of an Azure DevOps build/pipeline run",
            schema=AzureGetBuildStatus.model_json_schema(),
            domain="azure",
            complexity="focused",
        ),
        ToolDefinition(
            name="azure_get_build_logs",
            implementation=create_service_wrapper(
                azure_service, "azure_get_build_logs"
            ),
            description="Get logs from an Azure DevOps build",
            schema=AzureGetBuildLogs.model_json_schema(),
            domain="azure",
            complexity="focused",
        ),
        ToolDefinition(
            name="azure_get_failing_jobs",
            implementation=create_service_wrapper(
                azure_service, "azure_get_failing_jobs"
            ),
            description="Get detailed information about failing jobs in an Azure DevOps build",
            schema=AzureGetFailingJobs.model_json_schema(),
            domain="azure",
            complexity="focused",
        ),
        ToolDefinition(
            name="azure_list_builds",
            implementation=create_service_wrapper(azure_service, "azure_list_builds"),
            description="List Azure DevOps builds with filtering options",
            schema=AzureListBuilds.model_json_schema(),
            domain="azure",
            complexity="focused",
        ),
    ]

    for tool in azure_tools:
        interface.register_tool(tool)

    logger.info(f"Registered {len(azure_tools)} Azure tools")
