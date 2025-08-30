"""GitHub operations module for MCP Git Server.

This module provides higher-level GitHub operations that build on primitive operations
to provide more complex functionality. Operations combine 2-3 primitives to create
meaningful business logic while maintaining clear boundaries and responsibilities.

Design principles:
    - Composition over inheritance: Build functionality by combining primitives
    - Clear interfaces: Well-defined inputs and outputs
    - Error propagation: Proper handling of primitive errors
    - Transaction safety: Atomic operations where needed
    - Logging: Comprehensive operation logging for debugging

Critical for TDD Compliance:
    This module implements the interface defined by test specifications.
    DO NOT modify tests to match this implementation - this implementation
    must satisfy the test requirements to prevent LLM compliance issues.
"""

import logging
from dataclasses import dataclass
from typing import Any

from ..primitives.github_primitives import (
    GitHubAPIError,
    GitHubPrimitiveError,
    check_repository_access,
    get_pull_request_info,
    get_repository_info,
    make_github_request,
)

logger = logging.getLogger(__name__)


@dataclass
class PullRequestRequest:
    """Request parameters for pull request operations."""

    title: str
    head: str
    base: str
    body: str | None = None
    maintainer_can_modify: bool = True
    draft: bool = False


@dataclass
class IssueRequest:
    """Request parameters for issue operations."""

    title: str
    body: str | None = None
    assignees: list[str] | None = None
    labels: list[str] | None = None
    milestone: int | None = None


@dataclass
class ReleaseRequest:
    """Request parameters for release operations."""

    tag_name: str
    name: str | None = None
    body: str | None = None
    draft: bool = False
    prerelease: bool = False
    target_commitish: str | None = None


class GitHubOperationError(GitHubPrimitiveError):
    """Base exception for GitHub operation errors."""

    pass


async def create_pull_request(
    repo_owner: str, repo_name: str, request: PullRequestRequest
) -> dict[str, Any]:
    """Create a new pull request in the repository.

    Args:
        repo_owner: Repository owner username
        repo_name: Repository name
        request: Pull request creation parameters

    Returns:
        Created pull request information

    Raises:
        GitHubOperationError: If PR creation fails
        GitHubAuthenticationError: If authentication fails
        GitHubAPIError: For other API errors

    Example:
        >>> pr_request = PullRequestRequest(
        ...     title="Add new feature",
        ...     head="feature-branch",
        ...     base="main",
        ...     body="This PR adds a new feature"
        ... )
        >>> pr = await create_pull_request("owner", "repo", pr_request)
        >>> print(f"Created PR #{pr['number']}: {pr['title']}")
    """
    logger.info(f"Creating pull request: {request.title} in {repo_owner}/{repo_name}")

    # Verify repository access first
    if not await check_repository_access(repo_owner, repo_name):
        raise GitHubOperationError(
            f"No access to repository {repo_owner}/{repo_name} or repository does not exist"
        )

    try:
        # Prepare pull request data
        pr_data = {
            "title": request.title,
            "head": request.head,
            "base": request.base,
            "maintainer_can_modify": request.maintainer_can_modify,
            "draft": request.draft,
        }

        if request.body is not None:
            pr_data["body"] = request.body

        # Create the pull request
        pr = await make_github_request(
            "POST", f"/repos/{repo_owner}/{repo_name}/pulls", json_data=pr_data
        )

        logger.info(f"Successfully created PR #{pr['number']}")
        return pr

    except GitHubAPIError as e:
        logger.error(f"Failed to create pull request: {e}")
        raise GitHubOperationError(f"Failed to create pull request: {e}") from e


async def update_pull_request(
    repo_owner: str, repo_name: str, pr_number: int, updates: dict[str, Any]
) -> dict[str, Any]:
    """Update an existing pull request.

    Args:
        repo_owner: Repository owner username
        repo_name: Repository name
        pr_number: Pull request number
        updates: Dictionary of fields to update

    Returns:
        Updated pull request information

    Raises:
        GitHubOperationError: If PR update fails
        GitHubAPIError: For API errors

    Example:
        >>> updates = {"title": "Updated title", "body": "Updated description"}
        >>> pr = await update_pull_request("owner", "repo", 123, updates)
        >>> print(f"Updated PR #{pr['number']}")
    """
    logger.info(f"Updating pull request #{pr_number} in {repo_owner}/{repo_name}")

    try:
        # Get current PR info to verify it exists
        await get_pull_request_info(repo_owner, repo_name, pr_number)

        # Update the pull request
        pr = await make_github_request(
            "PATCH",
            f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}",
            json_data=updates,
        )

        logger.info(f"Successfully updated PR #{pr_number}")
        return pr

    except GitHubAPIError as e:
        logger.error(f"Failed to update pull request #{pr_number}: {e}")
        raise GitHubOperationError(f"Failed to update pull request: {e}") from e


async def get_pull_request_with_status(
    repo_owner: str, repo_name: str, pr_number: int
) -> dict[str, Any]:
    """Get pull request information including status checks and reviews.

    Args:
        repo_owner: Repository owner username
        repo_name: Repository name
        pr_number: Pull request number

    Returns:
        Enhanced pull request information with status and reviews

    Raises:
        GitHubAPIError: If PR not found

    Example:
        >>> pr_info = await get_pull_request_with_status("owner", "repo", 123)
        >>> print(f"PR #{pr_info['number']}: {pr_info['state']}")
        >>> print(f"Mergeable: {pr_info['mergeable']}")
        >>> print(f"Status checks: {len(pr_info.get('status_checks', []))}")
    """
    logger.info(f"Getting PR #{pr_number} with status from {repo_owner}/{repo_name}")

    try:
        # Get basic PR info
        pr = await get_pull_request_info(repo_owner, repo_name, pr_number)

        # Get status checks if available
        if pr.get("head", {}).get("sha"):
            try:
                status_checks = await make_github_request(
                    "GET",
                    f"/repos/{repo_owner}/{repo_name}/commits/{pr['head']['sha']}/status",
                )
                pr["status_checks"] = status_checks
            except GitHubAPIError:
                logger.debug("Could not fetch status checks")
                pr["status_checks"] = {}

        # Get reviews
        try:
            reviews = await make_github_request(
                "GET", f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}/reviews"
            )
            pr["reviews"] = reviews
        except GitHubAPIError:
            logger.debug("Could not fetch PR reviews")
            pr["reviews"] = []

        return pr

    except GitHubAPIError as e:
        logger.error(f"Failed to get PR #{pr_number} with status: {e}")
        raise


async def merge_pull_request(
    repo_owner: str,
    repo_name: str,
    pr_number: int,
    commit_title: str | None = None,
    commit_message: str | None = None,
    merge_method: str = "merge",
) -> dict[str, Any]:
    """Merge a pull request.

    Args:
        repo_owner: Repository owner username
        repo_name: Repository name
        pr_number: Pull request number
        commit_title: Title for merge commit
        commit_message: Message for merge commit
        merge_method: Merge method (merge, squash, rebase)

    Returns:
        Merge result information

    Raises:
        GitHubOperationError: If merge fails
        GitHubAPIError: For API errors

    Example:
        >>> result = await merge_pull_request(
        ...     "owner", "repo", 123,
        ...     commit_title="Merge feature branch",
        ...     merge_method="squash"
        ... )
        >>> print(f"Merged: {result['merged']}")
    """
    logger.info(f"Merging pull request #{pr_number} in {repo_owner}/{repo_name}")

    try:
        # Verify PR exists and is mergeable
        pr = await get_pull_request_info(repo_owner, repo_name, pr_number)
        if pr["state"] != "open":
            raise GitHubOperationError(f"Pull request #{pr_number} is not open")

        # Prepare merge data
        merge_data = {"merge_method": merge_method}
        if commit_title:
            merge_data["commit_title"] = commit_title
        if commit_message:
            merge_data["commit_message"] = commit_message

        # Merge the pull request
        result = await make_github_request(
            "PUT",
            f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}/merge",
            json_data=merge_data,
        )

        logger.info(f"Successfully merged PR #{pr_number}")
        return result

    except GitHubAPIError as e:
        logger.error(f"Failed to merge pull request #{pr_number}: {e}")
        raise GitHubOperationError(f"Failed to merge pull request: {e}") from e


async def create_issue(
    repo_owner: str, repo_name: str, issue: IssueRequest
) -> dict[str, Any]:
    """Create a new issue in the repository.

    Args:
        repo_owner: Repository owner username
        repo_name: Repository name
        issue: Issue creation parameters

    Returns:
        Created issue information

    Raises:
        GitHubOperationError: If issue creation fails
        GitHubAPIError: For API errors

    Example:
        >>> issue_request = IssueRequest(
        ...     title="Bug report",
        ...     body="Description of the bug",
        ...     labels=["bug", "priority-high"]
        ... )
        >>> issue = await create_issue("owner", "repo", issue_request)
        >>> print(f"Created issue #{issue['number']}: {issue['title']}")
    """
    logger.info(f"Creating issue: {issue.title} in {repo_owner}/{repo_name}")

    try:
        # Prepare issue data
        issue_data = {"title": issue.title}

        if issue.body is not None:
            issue_data["body"] = issue.body
        if issue.assignees:
            issue_data["assignees"] = issue.assignees
        if issue.labels:
            issue_data["labels"] = issue.labels
        if issue.milestone is not None:
            issue_data["milestone"] = issue.milestone

        # Create the issue
        created_issue = await make_github_request(
            "POST", f"/repos/{repo_owner}/{repo_name}/issues", json_data=issue_data
        )

        logger.info(f"Successfully created issue #{created_issue['number']}")
        return created_issue

    except GitHubAPIError as e:
        logger.error(f"Failed to create issue: {e}")
        raise GitHubOperationError(f"Failed to create issue: {e}") from e


async def update_issue(
    repo_owner: str, repo_name: str, issue_number: int, updates: dict[str, Any]
) -> dict[str, Any]:
    """Update an existing issue.

    Args:
        repo_owner: Repository owner username
        repo_name: Repository name
        issue_number: Issue number
        updates: Dictionary of fields to update

    Returns:
        Updated issue information

    Raises:
        GitHubOperationError: If issue update fails
        GitHubAPIError: For API errors

    Example:
        >>> updates = {"state": "closed", "labels": ["resolved"]}
        >>> issue = await update_issue("owner", "repo", 123, updates)
        >>> print(f"Updated issue #{issue['number']}")
    """
    logger.info(f"Updating issue #{issue_number} in {repo_owner}/{repo_name}")

    try:
        # Update the issue
        issue = await make_github_request(
            "PATCH",
            f"/repos/{repo_owner}/{repo_name}/issues/{issue_number}",
            json_data=updates,
        )

        logger.info(f"Successfully updated issue #{issue_number}")
        return issue

    except GitHubAPIError as e:
        logger.error(f"Failed to update issue #{issue_number}: {e}")
        raise GitHubOperationError(f"Failed to update issue: {e}") from e


async def create_release(
    repo_owner: str, repo_name: str, release: ReleaseRequest
) -> dict[str, Any]:
    """Create a new release in the repository.

    Args:
        repo_owner: Repository owner username
        repo_name: Repository name
        release: Release creation parameters

    Returns:
        Created release information

    Raises:
        GitHubOperationError: If release creation fails
        GitHubAPIError: For API errors

    Example:
        >>> release_request = ReleaseRequest(
        ...     tag_name="v1.0.0",
        ...     name="Version 1.0.0",
        ...     body="Release notes for v1.0.0"
        ... )
        >>> release = await create_release("owner", "repo", release_request)
        >>> print(f"Created release: {release['name']}")
    """
    logger.info(f"Creating release {release.tag_name} in {repo_owner}/{repo_name}")

    try:
        # Prepare release data
        release_data = {
            "tag_name": release.tag_name,
            "draft": release.draft,
            "prerelease": release.prerelease,
        }

        if release.name is not None:
            release_data["name"] = release.name
        if release.body is not None:
            release_data["body"] = release.body
        if release.target_commitish is not None:
            release_data["target_commitish"] = release.target_commitish

        # Create the release
        created_release = await make_github_request(
            "POST", f"/repos/{repo_owner}/{repo_name}/releases", json_data=release_data
        )

        logger.info(f"Successfully created release {release.tag_name}")
        return created_release

    except GitHubAPIError as e:
        logger.error(f"Failed to create release {release.tag_name}: {e}")
        raise GitHubOperationError(f"Failed to create release: {e}") from e


async def list_workflows(repo_owner: str, repo_name: str) -> list[dict[str, Any]]:
    """List all workflows in the repository.

    Args:
        repo_owner: Repository owner username
        repo_name: Repository name

    Returns:
        List of workflow information

    Raises:
        GitHubAPIError: For API errors

    Example:
        >>> workflows = await list_workflows("owner", "repo")
        >>> for workflow in workflows:
        ...     print(f"Workflow: {workflow['name']} ({workflow['state']})")
    """
    logger.info(f"Listing workflows in {repo_owner}/{repo_name}")

    try:
        result = await make_github_request(
            "GET", f"/repos/{repo_owner}/{repo_name}/actions/workflows"
        )
        return result.get("workflows", [])

    except GitHubAPIError as e:
        logger.error(f"Failed to list workflows: {e}")
        raise


async def trigger_workflow(
    repo_owner: str,
    repo_name: str,
    workflow_id: str | int,
    ref: str = "main",
    inputs: dict[str, Any] | None = None,
) -> bool:
    """Trigger a workflow dispatch event.

    Args:
        repo_owner: Repository owner username
        repo_name: Repository name
        workflow_id: Workflow ID or filename
        ref: Git reference to run workflow on
        inputs: Workflow inputs

    Returns:
        True if workflow was triggered successfully

    Raises:
        GitHubOperationError: If workflow trigger fails
        GitHubAPIError: For API errors

    Example:
        >>> success = await trigger_workflow(
        ...     "owner", "repo", "deploy.yml",
        ...     ref="main",
        ...     inputs={"environment": "production"}
        ... )
        >>> print(f"Workflow triggered: {success}")
    """
    logger.info(f"Triggering workflow {workflow_id} in {repo_owner}/{repo_name}")

    try:
        # Prepare dispatch data
        dispatch_data = {"ref": ref}
        if inputs:
            dispatch_data["inputs"] = inputs

        # Trigger the workflow
        await make_github_request(
            "POST",
            f"/repos/{repo_owner}/{repo_name}/actions/workflows/{workflow_id}/dispatches",
            json_data=dispatch_data,
        )

        logger.info(f"Successfully triggered workflow {workflow_id}")
        return True

    except GitHubAPIError as e:
        logger.error(f"Failed to trigger workflow {workflow_id}: {e}")
        raise GitHubOperationError(f"Failed to trigger workflow: {e}") from e


async def get_repository_with_details(
    repo_owner: str, repo_name: str
) -> dict[str, Any]:
    """Get comprehensive repository information including branches and contributors.

    Args:
        repo_owner: Repository owner username
        repo_name: Repository name

    Returns:
        Enhanced repository information

    Raises:
        GitHubAPIError: If repository not found

    Example:
        >>> repo_info = await get_repository_with_details("owner", "repo")
        >>> print(f"Repository: {repo_info['full_name']}")
        >>> print(f"Branches: {len(repo_info.get('branches', []))}")
        >>> print(f"Contributors: {len(repo_info.get('contributors', []))}")
    """
    logger.info(f"Getting detailed repository info for {repo_owner}/{repo_name}")

    try:
        # Get basic repository info
        repo = await get_repository_info(repo_owner, repo_name)

        # Get branches (first page)
        try:
            branches = await make_github_request(
                "GET",
                f"/repos/{repo_owner}/{repo_name}/branches",
                params={"per_page": 30},
            )
            repo["branches"] = branches
        except GitHubAPIError:
            logger.debug("Could not fetch branches")
            repo["branches"] = []

        # Get contributors (first page)
        try:
            contributors = await make_github_request(
                "GET",
                f"/repos/{repo_owner}/{repo_name}/contributors",
                params={"per_page": 30},
            )
            repo["contributors"] = contributors
        except GitHubAPIError:
            logger.debug("Could not fetch contributors")
            repo["contributors"] = []

        # Get latest release
        try:
            latest_release = await make_github_request(
                "GET", f"/repos/{repo_owner}/{repo_name}/releases/latest"
            )
            repo["latest_release"] = latest_release
        except GitHubAPIError:
            logger.debug("Could not fetch latest release")
            repo["latest_release"] = None

        return repo

    except GitHubAPIError as e:
        logger.error(f"Failed to get repository details: {e}")
        raise
