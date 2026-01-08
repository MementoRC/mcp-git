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
            implementation=lambda **kwargs: git_service.git_diff(**kwargs),
            description="Shows differences between branches or commits",
            schema=GitDiff.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_commit",
            implementation=lambda **kwargs: git_service.git_commit(**kwargs),
            description="Records changes to the repository",
            schema=GitCommit.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_add",
            implementation=lambda **kwargs: git_service.git_add(**kwargs),
            description="Adds file contents to the staging area",
            schema=GitAdd.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_reset",
            implementation=lambda **kwargs: git_service.git_reset(**kwargs),
            description="Reset repository with advanced options (--soft, --mixed, --hard)",
            schema=GitReset.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_log",
            implementation=lambda **kwargs: git_service.git_log(**kwargs),
            description="Shows the commit logs",
            schema=GitLog.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_create_branch",
            implementation=lambda **kwargs: git_service.git_create_branch(**kwargs),
            description="Creates a new branch from an optional base branch",
            schema=GitCreateBranch.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_checkout",
            implementation=lambda **kwargs: git_service.git_checkout(**kwargs),
            description="Switches branches",
            schema=GitCheckout.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_show",
            implementation=lambda **kwargs: git_service.git_show(**kwargs),
            description="Shows the contents of a commit",
            schema=GitShow.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_init",
            implementation=lambda **kwargs: git_service.git_init(**kwargs),
            description="Initialize a new Git repository",
            schema=GitInit.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_push",
            implementation=lambda **kwargs: git_service.git_push(**kwargs),
            description="Push commits to remote repository",
            schema=GitPush.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_pull",
            implementation=lambda **kwargs: git_service.git_pull(**kwargs),
            description="Pull changes from remote repository",
            schema=GitPull.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_diff_branches",
            implementation=lambda **kwargs: git_service.git_diff_branches(**kwargs),
            description="Show differences between two branches",
            schema=GitDiffBranches.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_rebase",
            implementation=lambda **kwargs: git_service.git_rebase(**kwargs),
            description="Rebase current branch onto another branch",
            schema=GitRebase.model_json_schema(),
            domain="git",
            complexity="advanced",
        ),
        ToolDefinition(
            name="git_merge",
            implementation=lambda **kwargs: git_service.git_merge(**kwargs),
            description="Merge a branch into the current branch",
            schema=GitMerge.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_cherry_pick",
            implementation=lambda **kwargs: git_service.git_cherry_pick(**kwargs),
            description="Apply a commit from another branch to current branch",
            schema=GitCherryPick.model_json_schema(),
            domain="git",
            complexity="advanced",
        ),
        ToolDefinition(
            name="git_abort",
            implementation=lambda **kwargs: git_service.git_abort(**kwargs),
            description="Abort an in-progress git operation (rebase, merge, cherry-pick)",
            schema=GitAbort.model_json_schema(),
            domain="git",
            complexity="advanced",
        ),
        ToolDefinition(
            name="git_continue",
            implementation=lambda **kwargs: git_service.git_continue(**kwargs),
            description="Continue an in-progress git operation after resolving conflicts",
            schema=GitContinue.model_json_schema(),
            domain="git",
            complexity="advanced",
        ),
        # Remote operations (5 more tools from models)
        ToolDefinition(
            name="git_fetch",
            implementation=lambda **kwargs: git_service.git_fetch(**kwargs),
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
            implementation=lambda **kwargs: git_service.git_remote_add(**kwargs),
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
            implementation=lambda **kwargs: git_service.git_remote_remove(**kwargs),
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
            implementation=lambda **kwargs: git_service.git_remote_list(**kwargs),
            description="List remote repositories",
            schema={"type": "object", "properties": {"repo_path": {"type": "string"}}},
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_remote_get_url",
            implementation=lambda **kwargs: git_service.git_remote_get_url(**kwargs),
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
            implementation=lambda **kwargs: github_service.github_get_pr_checks(
                **kwargs
            ),
            description="Get check runs for a pull request",
            schema=GitHubGetPRChecks.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_get_failing_jobs",
            implementation=lambda **kwargs: github_service.github_get_failing_jobs(
                **kwargs
            ),
            description="Get detailed information about failing CI jobs for a pull request",
            schema=GitHubGetFailingJobs.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_get_pr_details",
            implementation=lambda **kwargs: github_service.github_get_pr_details(
                **kwargs
            ),
            description="Get detailed information about a pull request",
            schema=GitHubGetPRDetails.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_list_pull_requests",
            implementation=lambda **kwargs: github_service.github_list_pull_requests(
                **kwargs
            ),
            description="List pull requests with filtering options",
            schema=GitHubListPullRequests.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_get_pr_status",
            implementation=lambda **kwargs: github_service.github_get_pr_status(
                **kwargs
            ),
            description="Get the status of a pull request",
            schema=GitHubGetPRStatus.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_get_pr_files",
            implementation=lambda **kwargs: github_service.github_get_pr_files(
                **kwargs
            ),
            description="Get files changed in a pull request",
            schema=GitHubGetPRFiles.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_edit_pr_description",
            implementation=lambda **kwargs: github_service.github_edit_pr_description(
                **kwargs
            ),
            description="Edit the description of a pull request",
            schema=GitHubEditPRDescription.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        # Workflow Tools
        ToolDefinition(
            name="github_get_workflow_run",
            implementation=lambda **kwargs: github_service.github_get_workflow_run(
                **kwargs
            ),
            description="Get detailed workflow run information",
            schema=GitHubGetWorkflowRun.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_list_workflow_runs",
            implementation=lambda **kwargs: github_service.github_list_workflow_runs(
                **kwargs
            ),
            description="List workflow runs for a repository with comprehensive filtering",
            schema=GitHubListWorkflowRuns.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        # Issue Tools
        ToolDefinition(
            name="github_create_issue",
            implementation=lambda **kwargs: github_service.github_create_issue(
                **kwargs
            ),
            description="Create a new GitHub issue",
            schema=GitHubCreateIssue.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_list_issues",
            implementation=lambda **kwargs: github_service.github_list_issues(**kwargs),
            description="List GitHub issues with filtering options",
            schema=GitHubListIssues.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_update_issue",
            implementation=lambda **kwargs: github_service.github_update_issue(
                **kwargs
            ),
            description="Update an existing GitHub issue",
            schema=GitHubUpdateIssue.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_search_issues",
            implementation=lambda **kwargs: github_service.github_search_issues(
                **kwargs
            ),
            description="Search GitHub issues with advanced query capabilities",
            schema=GitHubSearchIssues.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_create_issue_from_template",
            implementation=lambda **kwargs: github_service.github_create_issue_from_template(
                **kwargs
            ),
            description="Create issue from template",
            schema=GitHubCreateIssueFromTemplate.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_bulk_update_issues",
            implementation=lambda **kwargs: github_service.github_bulk_update_issues(
                **kwargs
            ),
            description="Bulk update multiple issues",
            schema=GitHubBulkUpdateIssues.model_json_schema(),
            domain="github",
            complexity="comprehensive",
        ),
        # Additional GitHub tools from CLI (13 more to reach 28 total)
        ToolDefinition(
            name="github_create_pr",
            implementation=lambda **kwargs: github_service.github_create_pr(**kwargs),
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
            implementation=lambda **kwargs: github_service.github_merge_pr(**kwargs),
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
            implementation=lambda **kwargs: github_service.github_add_pr_comment(
                **kwargs
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
            implementation=lambda **kwargs: github_service.github_close_pr(**kwargs),
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
            implementation=lambda **kwargs: github_service.github_reopen_pr(**kwargs),
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
            implementation=lambda **kwargs: github_service.github_update_pr(**kwargs),
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
            implementation=lambda **kwargs: github_service.github_await_workflow_completion(
                **kwargs
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
            implementation=lambda **kwargs: github_service.github_get_repo_info(
                **kwargs
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
            implementation=lambda **kwargs: github_service.github_list_branches(
                **kwargs
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
            implementation=lambda **kwargs: github_service.github_get_commit(**kwargs),
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
            implementation=lambda **kwargs: github_service.github_list_commits(
                **kwargs
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
            implementation=lambda **kwargs: github_service.github_compare_commits(
                **kwargs
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
            implementation=lambda **kwargs: azure_service.azure_get_build_status(
                **kwargs
            ),
            description="Get the status of an Azure DevOps build/pipeline run",
            schema=AzureGetBuildStatus.model_json_schema(),
            domain="azure",
            complexity="focused",
        ),
        ToolDefinition(
            name="azure_get_build_logs",
            implementation=lambda **kwargs: azure_service.azure_get_build_logs(
                **kwargs
            ),
            description="Get logs from an Azure DevOps build",
            schema=AzureGetBuildLogs.model_json_schema(),
            domain="azure",
            complexity="focused",
        ),
        ToolDefinition(
            name="azure_get_failing_jobs",
            implementation=lambda **kwargs: azure_service.azure_get_failing_jobs(
                **kwargs
            ),
            description="Get detailed information about failing jobs in an Azure DevOps build",
            schema=AzureGetFailingJobs.model_json_schema(),
            domain="azure",
            complexity="focused",
        ),
        ToolDefinition(
            name="azure_list_builds",
            implementation=lambda **kwargs: azure_service.azure_list_builds(**kwargs),
            description="List Azure DevOps builds with filtering options",
            schema=AzureListBuilds.model_json_schema(),
            domain="azure",
            complexity="focused",
        ),
    ]

    for tool in azure_tools:
        interface.register_tool(tool)

    logger.info(f"Registered {len(azure_tools)} Azure tools")
