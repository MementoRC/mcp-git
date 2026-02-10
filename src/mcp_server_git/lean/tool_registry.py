"""
Tool Registry for Git Lean MCP Interface.

Registers all 77 tools across git, github, and azure domains with complete metadata.

Tool Distribution:
- Git tools (26): Core git operations
- GitHub tools (47): PR, issues, workflows, repo settings, actions, branch protection, security, releases
- Azure tools (4): Build logs and status

New in Issue #57:
- Releases: create_release, get_release, list_releases, update_release, delete_release,
           upload_release_asset, list_release_assets, delete_release_asset

New in Issue #41:
- Repository Settings: get_repo_settings, update_repo_settings
- Actions Config: get_actions_permissions, update_actions_permissions,
                  get_workflow_permissions, update_workflow_permissions
- Branch Protection: get_branch_protection, update_branch_protection, delete_branch_protection
- Security: get_vulnerability_alerts, enable/disable_vulnerability_alerts,
           get_automated_security_fixes, enable/disable_automated_security_fixes,
           get_security_analysis
"""

import logging
from typing import Any

from .interface import ToolDefinition

logger = logging.getLogger(__name__)


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

    # Register GitHub tools (22 tools)
    _register_github_tools(interface, github_service)

    # Register Azure tools (4 tools)
    _register_azure_tools(interface, azure_service)

    logger.info(f"Registered {len(interface.tool_registry)} tools total")


def _register_git_tools(interface: Any, git_service: Any):
    """Register all Git domain tools."""
    # Import models for schema generation
    # Import operations and Repo for path conversion
    from ..git import operations as git_ops
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
        GitMergeBase,
        GitPull,
        GitPush,
        GitRebase,
        GitReset,
        GitShow,
        GitStatus,
    )
    from ..utils.git_import import Repo

    # Create wrapper functions that convert repo_path to Repo object
    # The underlying operations expect Repo objects, not path strings
    def wrap_repo_op(op_func):
        """Wrap a git operation that takes Repo as first argument."""

        def wrapper(repo_path: str, **kwargs):
            repo = Repo(repo_path)
            return op_func(repo, **kwargs)

        return wrapper

    git_tools = [
        ToolDefinition(
            name="git_status",
            implementation=wrap_repo_op(git_ops.git_status),
            description="Shows the working tree status",
            schema=GitStatus.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_diff_unstaged",
            implementation=wrap_repo_op(git_ops.git_diff_unstaged),
            description="Shows changes in the working directory that are not yet staged",
            schema=GitDiffUnstaged.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_diff_staged",
            implementation=wrap_repo_op(git_ops.git_diff_staged),
            description="Shows changes that are staged for commit",
            schema=GitDiffStaged.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_diff",
            implementation=wrap_repo_op(git_ops.git_diff),
            description="Shows differences between branches or commits",
            schema=GitDiff.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_commit",
            implementation=wrap_repo_op(git_ops.git_commit),
            description="Records changes to the repository",
            schema=GitCommit.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_add",
            implementation=wrap_repo_op(git_ops.git_add),
            description="Adds file contents to the staging area",
            schema=GitAdd.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_reset",
            implementation=wrap_repo_op(git_ops.git_reset),
            description="Reset repository with advanced options (--soft, --mixed, --hard)",
            schema=GitReset.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_log",
            implementation=wrap_repo_op(git_ops.git_log),
            description="Shows the commit logs",
            schema=GitLog.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_create_branch",
            implementation=wrap_repo_op(git_ops.git_create_branch),
            description="Creates a new branch from an optional base branch",
            schema=GitCreateBranch.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_checkout",
            implementation=wrap_repo_op(git_ops.git_checkout),
            description="Switches branches",
            schema=GitCheckout.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_show",
            implementation=wrap_repo_op(git_ops.git_show),
            description="Shows the contents of a commit",
            schema=GitShow.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_init",
            implementation=git_ops.git_init,  # git_init takes path directly, not Repo
            description="Initialize a new Git repository",
            schema=GitInit.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_push",
            implementation=wrap_repo_op(git_ops.git_push),
            description="Push commits to remote repository",
            schema=GitPush.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_pull",
            implementation=wrap_repo_op(git_ops.git_pull),
            description="Pull changes from remote repository",
            schema=GitPull.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_diff_branches",
            implementation=wrap_repo_op(git_ops.git_diff_branches),
            description="Show differences between two branches",
            schema=GitDiffBranches.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_rebase",
            implementation=wrap_repo_op(git_ops.git_rebase),
            description="Rebase current branch onto another branch",
            schema=GitRebase.model_json_schema(),
            domain="git",
            complexity="advanced",
        ),
        ToolDefinition(
            name="git_merge",
            implementation=wrap_repo_op(git_ops.git_merge),
            description="Merge a branch into the current branch",
            schema=GitMerge.model_json_schema(),
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_cherry_pick",
            implementation=wrap_repo_op(git_ops.git_cherry_pick),
            description="Apply a commit from another branch to current branch",
            schema=GitCherryPick.model_json_schema(),
            domain="git",
            complexity="advanced",
        ),
        ToolDefinition(
            name="git_abort",
            implementation=wrap_repo_op(git_ops.git_abort),
            description="Abort an in-progress git operation (rebase, merge, cherry-pick)",
            schema=GitAbort.model_json_schema(),
            domain="git",
            complexity="advanced",
        ),
        ToolDefinition(
            name="git_continue",
            implementation=wrap_repo_op(git_ops.git_continue),
            description="Continue an in-progress git operation after resolving conflicts",
            schema=GitContinue.model_json_schema(),
            domain="git",
            complexity="advanced",
        ),
        # Remote operations
        ToolDefinition(
            name="git_fetch",
            implementation=wrap_repo_op(git_ops.git_fetch),
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
            implementation=wrap_repo_op(git_ops.git_remote_add),
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
            implementation=wrap_repo_op(git_ops.git_remote_remove),
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
            implementation=wrap_repo_op(git_ops.git_remote_list),
            description="List remote repositories",
            schema={"type": "object", "properties": {"repo_path": {"type": "string"}}},
            domain="git",
            complexity="core",
        ),
        ToolDefinition(
            name="git_remote_get_url",
            implementation=wrap_repo_op(git_ops.git_remote_get_url),
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
        ToolDefinition(
            name="git_merge_base",
            implementation=wrap_repo_op(git_ops.git_merge_base),
            description="Find the common ancestor (merge-base) of two references",
            schema=GitMergeBase.model_json_schema(),
            domain="git",
            complexity="core",
        ),
    ]

    for tool in git_tools:
        interface.register_tool(tool)

    logger.info(f"Registered {len(git_tools)} Git tools")


def _register_github_tools(interface: Any, github_service: Any):
    """Register all GitHub domain tools."""
    from ..github import api as github_ops
    from ..github.models import (
        GitHubBulkUpdateIssues,
        GitHubCreateIssue,
        GitHubCreateIssueFromTemplate,
        GitHubCreateRelease,
        GitHubDeleteBranchProtection,
        GitHubDeleteRelease,
        GitHubDeleteReleaseAsset,
        GitHubDisableAutomatedSecurityFixes,
        GitHubDisableVulnerabilityAlerts,
        GitHubEditPRDescription,
        GitHubEnableAutomatedSecurityFixes,
        GitHubEnableVulnerabilityAlerts,
        GitHubGetActionsPermissions,
        GitHubGetAutomatedSecurityFixes,
        GitHubGetBranchProtection,
        GitHubGetFailingJobs,
        GitHubGetIssue,
        GitHubGetPRChecks,
        GitHubGetPRDetails,
        GitHubGetPRFiles,
        GitHubGetPRStatus,
        GitHubGetRelease,
        GitHubGetRepoSettings,
        GitHubGetSecurityAnalysis,
        GitHubGetVulnerabilityAlerts,
        GitHubGetWorkflowPermissions,
        GitHubGetWorkflowRun,
        GitHubListIssues,
        GitHubListPullRequests,
        GitHubListReleaseAssets,
        GitHubListReleases,
        GitHubListWorkflowRuns,
        GitHubSearchIssues,
        GitHubUpdateActionsPermissions,
        GitHubUpdateBranchProtection,
        GitHubUpdateIssue,
        GitHubUpdateRelease,
        GitHubUpdateRepoSettings,
        GitHubUpdateWorkflowPermissions,
        GitHubUploadReleaseAsset,
    )

    github_tools = [
        # PR Tools
        ToolDefinition(
            name="github_get_pr_checks",
            implementation=github_ops.github_get_pr_checks,
            description="Get check runs for a pull request",
            schema=GitHubGetPRChecks.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_get_failing_jobs",
            implementation=github_ops.github_get_failing_jobs,
            description="Get detailed information about failing CI jobs for a pull request",
            schema=GitHubGetFailingJobs.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_get_pr_details",
            implementation=github_ops.github_get_pr_details,
            description="Get detailed information about a pull request",
            schema=GitHubGetPRDetails.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_list_pull_requests",
            implementation=github_ops.github_list_pull_requests,
            description="List pull requests with filtering options",
            schema=GitHubListPullRequests.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_get_pr_status",
            implementation=github_ops.github_get_pr_status,
            description="Get the status of a pull request",
            schema=GitHubGetPRStatus.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_get_pr_files",
            implementation=github_ops.github_get_pr_files,
            description="Get files changed in a pull request",
            schema=GitHubGetPRFiles.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_edit_pr_description",
            implementation=github_ops.github_edit_pr_description,
            description="Edit the description of a pull request",
            schema=GitHubEditPRDescription.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        # Workflow Tools
        ToolDefinition(
            name="github_get_workflow_run",
            implementation=github_ops.github_get_workflow_run,
            description="Get detailed workflow run information",
            schema=GitHubGetWorkflowRun.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_list_workflow_runs",
            implementation=github_ops.github_list_workflow_runs,
            description="List workflow runs for a repository with comprehensive filtering",
            schema=GitHubListWorkflowRuns.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        # Issue Tools
        ToolDefinition(
            name="github_create_issue",
            implementation=github_ops.github_create_issue,
            description="Create a new GitHub issue",
            schema=GitHubCreateIssue.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_list_issues",
            implementation=github_ops.github_list_issues,
            description="List GitHub issues with filtering options",
            schema=GitHubListIssues.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_get_issue",
            implementation=github_ops.github_get_issue,
            description="Get a single GitHub issue by number with full details",
            schema=GitHubGetIssue.model_json_schema(),
            domain="github",
            complexity="core",
        ),
        ToolDefinition(
            name="github_update_issue",
            implementation=github_ops.github_update_issue,
            description="Update an existing GitHub issue",
            schema=GitHubUpdateIssue.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_search_issues",
            implementation=github_ops.github_search_issues,
            description="Search GitHub issues with advanced query capabilities",
            schema=GitHubSearchIssues.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_create_issue_from_template",
            implementation=github_ops.github_create_issue_from_template,
            description="Create issue from template",
            schema=GitHubCreateIssueFromTemplate.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_bulk_update_issues",
            implementation=github_ops.github_bulk_update_issues,
            description="Bulk update multiple issues",
            schema=GitHubBulkUpdateIssues.model_json_schema(),
            domain="github",
            complexity="comprehensive",
        ),
        # Additional GitHub tools from CLI (7 more to reach 22 total)
        ToolDefinition(
            name="github_create_pr",
            implementation=github_ops.github_create_pr,
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
            implementation=github_ops.github_merge_pr,
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
            implementation=github_ops.github_add_pr_comment,
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
            implementation=github_ops.github_close_pr,
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
            implementation=github_ops.github_reopen_pr,
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
            implementation=github_ops.github_update_pr,
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
            implementation=github_ops.github_await_workflow_completion,
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
        # Repository Settings Management (Issue #41)
        ToolDefinition(
            name="github_get_repo_settings",
            implementation=github_ops.github_get_repo_settings,
            description="Get repository settings including features, merge options, and security settings",
            schema=GitHubGetRepoSettings.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_update_repo_settings",
            implementation=github_ops.github_update_repo_settings,
            description="Update repository settings (merge strategies, features, security)",
            schema=GitHubUpdateRepoSettings.model_json_schema(),
            domain="github",
            complexity="comprehensive",
        ),
        # GitHub Actions Configuration (Issue #41)
        ToolDefinition(
            name="github_get_actions_permissions",
            implementation=github_ops.github_get_actions_permissions,
            description="Get GitHub Actions permissions for a repository",
            schema=GitHubGetActionsPermissions.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_update_actions_permissions",
            implementation=github_ops.github_update_actions_permissions,
            description="Update GitHub Actions permissions (enable/disable, allowed actions)",
            schema=GitHubUpdateActionsPermissions.model_json_schema(),
            domain="github",
            complexity="comprehensive",
        ),
        ToolDefinition(
            name="github_get_workflow_permissions",
            implementation=github_ops.github_get_workflow_permissions,
            description="Get default workflow permissions (GITHUB_TOKEN permissions)",
            schema=GitHubGetWorkflowPermissions.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_update_workflow_permissions",
            implementation=github_ops.github_update_workflow_permissions,
            description="Update default workflow permissions and PR approval settings",
            schema=GitHubUpdateWorkflowPermissions.model_json_schema(),
            domain="github",
            complexity="comprehensive",
        ),
        # Branch Protection Rules (Issue #41)
        ToolDefinition(
            name="github_get_branch_protection",
            implementation=github_ops.github_get_branch_protection,
            description="Get branch protection rules for a specific branch",
            schema=GitHubGetBranchProtection.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_update_branch_protection",
            implementation=github_ops.github_update_branch_protection,
            description="Create or update branch protection rules (status checks, reviews, restrictions)",
            schema=GitHubUpdateBranchProtection.model_json_schema(),
            domain="github",
            complexity="comprehensive",
        ),
        ToolDefinition(
            name="github_delete_branch_protection",
            implementation=github_ops.github_delete_branch_protection,
            description="Delete branch protection rules",
            schema=GitHubDeleteBranchProtection.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        # Security & Compliance (Issue #41)
        ToolDefinition(
            name="github_get_vulnerability_alerts",
            implementation=github_ops.github_get_vulnerability_alerts,
            description="Check if vulnerability alerts (Dependabot alerts) are enabled",
            schema=GitHubGetVulnerabilityAlerts.model_json_schema(),
            domain="github",
            complexity="core",
        ),
        ToolDefinition(
            name="github_enable_vulnerability_alerts",
            implementation=github_ops.github_enable_vulnerability_alerts,
            description="Enable vulnerability alerts (Dependabot alerts) for a repository",
            schema=GitHubEnableVulnerabilityAlerts.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_disable_vulnerability_alerts",
            implementation=github_ops.github_disable_vulnerability_alerts,
            description="Disable vulnerability alerts (Dependabot alerts) for a repository",
            schema=GitHubDisableVulnerabilityAlerts.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_get_automated_security_fixes",
            implementation=github_ops.github_get_automated_security_fixes,
            description="Check if automated security fixes (Dependabot security updates) are enabled",
            schema=GitHubGetAutomatedSecurityFixes.model_json_schema(),
            domain="github",
            complexity="core",
        ),
        ToolDefinition(
            name="github_enable_automated_security_fixes",
            implementation=github_ops.github_enable_automated_security_fixes,
            description="Enable automated security fixes (Dependabot security updates)",
            schema=GitHubEnableAutomatedSecurityFixes.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_disable_automated_security_fixes",
            implementation=github_ops.github_disable_automated_security_fixes,
            description="Disable automated security fixes (Dependabot security updates)",
            schema=GitHubDisableAutomatedSecurityFixes.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_get_security_analysis",
            implementation=github_ops.github_get_security_analysis,
            description="Get comprehensive security analysis status (vulnerability alerts, security fixes, secret scanning)",
            schema=GitHubGetSecurityAnalysis.model_json_schema(),
            domain="github",
            complexity="comprehensive",
        ),
        # Release Management Tools
        ToolDefinition(
            name="github_create_release",
            implementation=github_ops.github_create_release,
            description="Create a new GitHub release with tag, title, and notes",
            schema=GitHubCreateRelease.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_get_release",
            implementation=github_ops.github_get_release,
            description="Get release information by ID or tag name",
            schema=GitHubGetRelease.model_json_schema(),
            domain="github",
            complexity="core",
        ),
        ToolDefinition(
            name="github_list_releases",
            implementation=github_ops.github_list_releases,
            description="List releases for a repository with pagination",
            schema=GitHubListReleases.model_json_schema(),
            domain="github",
            complexity="core",
        ),
        ToolDefinition(
            name="github_update_release",
            implementation=github_ops.github_update_release,
            description="Update an existing release's properties",
            schema=GitHubUpdateRelease.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_delete_release",
            implementation=github_ops.github_delete_release,
            description="Delete a GitHub release (does not delete the git tag)",
            schema=GitHubDeleteRelease.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
        ToolDefinition(
            name="github_upload_release_asset",
            implementation=github_ops.github_upload_release_asset,
            description="Upload a file as an asset to a GitHub release",
            schema=GitHubUploadReleaseAsset.model_json_schema(),
            domain="github",
            complexity="advanced",
        ),
        ToolDefinition(
            name="github_list_release_assets",
            implementation=github_ops.github_list_release_assets,
            description="List assets attached to a release",
            schema=GitHubListReleaseAssets.model_json_schema(),
            domain="github",
            complexity="core",
        ),
        ToolDefinition(
            name="github_delete_release_asset",
            implementation=github_ops.github_delete_release_asset,
            description="Delete an asset from a release",
            schema=GitHubDeleteReleaseAsset.model_json_schema(),
            domain="github",
            complexity="focused",
        ),
    ]

    for tool in github_tools:
        interface.register_tool(tool)

    logger.info(f"Registered {len(github_tools)} GitHub tools")


def _register_azure_tools(interface: Any, azure_service: Any):
    """Register all Azure DevOps domain tools."""
    from ..azure import api as azure_ops
    from ..azure.models import (
        AzureGetBuildLogs,
        AzureGetBuildStatus,
        AzureGetFailingJobs,
        AzureListBuilds,
    )

    azure_tools = [
        ToolDefinition(
            name="azure_get_build_status",
            implementation=azure_ops.azure_get_build_status,
            description="Get the status of an Azure DevOps build/pipeline run",
            schema=AzureGetBuildStatus.model_json_schema(),
            domain="azure",
            complexity="focused",
        ),
        ToolDefinition(
            name="azure_get_build_logs",
            implementation=azure_ops.azure_get_build_logs,
            description="Get logs from an Azure DevOps build",
            schema=AzureGetBuildLogs.model_json_schema(),
            domain="azure",
            complexity="focused",
        ),
        ToolDefinition(
            name="azure_get_failing_jobs",
            implementation=azure_ops.azure_get_failing_jobs,
            description="Get detailed information about failing jobs in an Azure DevOps build",
            schema=AzureGetFailingJobs.model_json_schema(),
            domain="azure",
            complexity="focused",
        ),
        ToolDefinition(
            name="azure_list_builds",
            implementation=azure_ops.azure_list_builds,
            description="List Azure DevOps builds with filtering options",
            schema=AzureListBuilds.model_json_schema(),
            domain="azure",
            complexity="focused",
        ),
    ]

    for tool in azure_tools:
        interface.register_tool(tool)

    logger.info(f"Registered {len(azure_tools)} Azure tools")
