"""GitHub Issue operations."""

from __future__ import annotations

import logging
from typing import Any

from mcp_server_git.github._issue_format import (
    format_issue_detail,
    format_issue_list,
)
from mcp_server_git.github._paging import clamp_paging, invalid_choice
from mcp_server_git.github.client import github_client_context

logger = logging.getLogger(__name__)


_LIST_STATES = ("open", "closed", "all")
_LIST_SORTS = ("created", "updated", "comments")
_LIST_DIRECTIONS = ("asc", "desc")


def _list_choice_error(state: str, sort: str, direction: str) -> str | None:
    """First invalid state/sort/direction message, or None when all are valid."""
    return (
        invalid_choice("state", state, _LIST_STATES)
        or invalid_choice("sort", sort, _LIST_SORTS)
        or invalid_choice("direction", direction, _LIST_DIRECTIONS)
    )


def _list_params(
    state: str,
    labels: list[str] | None,
    assignee: str | None,
    creator: str | None,
    mentioned: str | None,
    milestone: str | None,
    sort: str,
    direction: str,
    since: str | None,
    per_page: int,
    page: int,
) -> dict[str, Any]:
    """Build list_issues query params; falsy optional filters are dropped."""
    params: dict[str, Any] = {
        "state": state,
        "sort": sort,
        "direction": direction,
        "per_page": per_page,
        "page": page,
    }
    if labels:
        params["labels"] = ",".join(labels)
    optional = {
        "assignee": assignee,
        "creator": creator,
        "mentioned": mentioned,
        "milestone": milestone,
        "since": since,
    }
    params.update({key: value for key, value in optional.items() if value})
    return params


def _update_payload(
    title: str | None,
    body: str | None,
    state: str | None,
    labels: list[str] | None,
    assignees: list[str] | None,
    milestone: int | None,
) -> dict[str, Any]:
    """Build the update payload from every field that is not None."""
    fields = {
        "title": title,
        "body": body,
        "state": state,
        "labels": labels,
        "assignees": assignees,
        "milestone": milestone,
    }
    return {key: value for key, value in fields.items() if value is not None}


async def github_create_issue(
    repo_owner: str,
    repo_name: str,
    title: str,
    body: str | None = None,
    labels: list[str] | None = None,
    assignees: list[str] | None = None,
    milestone: int | None = None,
) -> str:
    """Create a new GitHub issue."""
    logger.debug(f"🚀 Creating issue in {repo_owner}/{repo_name}: {title}")

    try:
        async with github_client_context() as client:
            payload: dict[str, Any] = {"title": title}
            if body is not None:
                payload["body"] = body
            if labels is not None:
                payload["labels"] = labels
            if assignees is not None:
                payload["assignees"] = assignees
            if milestone is not None:
                payload["milestone"] = milestone

            response = await client.post(
                f"/repos/{repo_owner}/{repo_name}/issues", json=payload
            )

            if response.status != 201:
                error_text = await response.text()
                return f"❌ Failed to create issue: {response.status} - {error_text}"

            result = await response.json()
            logger.info(f"✅ Successfully created issue #{result['number']}")
            return f"✅ Successfully created issue #{result['number']}: {result['html_url']}"

    except ValueError as auth_error:
        logger.error(f"Authentication error creating issue: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error creating issue: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error creating issue: {e}", exc_info=True)
        return f"❌ Error creating issue: {str(e)}"


async def github_list_issues(
    repo_owner: str,
    repo_name: str,
    state: str = "open",
    labels: list[str] | None = None,
    assignee: str | None = None,
    creator: str | None = None,
    mentioned: str | None = None,
    milestone: str | None = None,
    sort: str = "created",
    direction: str = "desc",
    since: str | None = None,
    per_page: int = 30,
    page: int = 1,
) -> str:
    """List issues for a repository."""
    logger.debug(f"🔍 Listing issues for {repo_owner}/{repo_name}")

    choice_error = _list_choice_error(state, sort, direction)
    if choice_error:
        return choice_error
    per_page, page = clamp_paging(per_page, page)

    try:
        async with github_client_context() as client:
            params = _list_params(
                state,
                labels,
                assignee,
                creator,
                mentioned,
                milestone,
                sort,
                direction,
                since,
                per_page,
                page,
            )

            response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/issues", params=params
            )

            if response.status != 200:
                error_text = await response.text()
                return f"❌ Failed to list issues: {response.status} - {error_text}"

            issues = await response.json()

            if not issues:
                return f"No {state} issues found"

            return format_issue_list(state, repo_owner, repo_name, issues)

    except ValueError as auth_error:
        logger.error(f"Authentication error listing issues: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error listing issues: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error listing issues: {e}", exc_info=True)
        return f"❌ Error listing issues: {str(e)}"


async def github_get_issue(
    repo_owner: str,
    repo_name: str,
    issue_number: int,
    max_body_chars: int | None = None,
) -> str:
    """Get a single GitHub issue by number.

    Returns full issue details including title, body, state, labels,
    assignees, milestone, comments count, and timestamps.

    The body is returned in full by default (issue #201). Previously it was
    silently cut at a hardcoded 2000 characters, which hid requirements from
    callers with no way to opt out. Pass ``max_body_chars`` to opt in to
    truncation; when it triggers, the marker reports the real body size so the
    caller knows something was withheld.

    Args:
        max_body_chars: Optional cap on body length. ``None`` (the default)
            means no truncation. Values <= 0 are treated as no truncation.
    """
    logger.debug(f"🔍 Getting issue #{issue_number} for {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/issues/{issue_number}"
            )

            if response.status == 404:
                return f"❌ Issue #{issue_number} not found in {repo_owner}/{repo_name}. Check issue number and repository access."

            if response.status != 200:
                error_text = await response.text()
                return f"❌ Failed to get issue: {response.status} - {error_text}"

            issue = await response.json()

            # Check if this is a pull request (issues API returns PRs too)
            if issue.get("pull_request"):
                return f"❌ #{issue_number} is a pull request, not an issue"

            return format_issue_detail(issue, max_body_chars)

    except ValueError as auth_error:
        logger.error(f"Authentication error getting issue: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error getting issue: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error getting issue: {e}", exc_info=True)
        return f"❌ Error getting issue: {str(e)}"


async def github_update_issue(
    repo_owner: str,
    repo_name: str,
    issue_number: int,
    title: str | None = None,
    body: str | None = None,
    state: str | None = None,
    labels: list[str] | None = None,
    assignees: list[str] | None = None,
    milestone: int | None = None,
) -> str:
    """Update a GitHub issue."""
    logger.debug(f"🚀 Updating issue #{issue_number} in {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            if state is not None and state not in ["open", "closed"]:
                return "❌ State must be 'open' or 'closed'"
            payload = _update_payload(title, body, state, labels, assignees, milestone)

            if not payload:
                return "⚠️ No update parameters provided. Please specify title, body, state, labels, assignees, or milestone."

            response = await client.patch(
                f"/repos/{repo_owner}/{repo_name}/issues/{issue_number}", json=payload
            )

            if response.status != 200:
                error_text = await response.text()
                return f"❌ Failed to update issue #{issue_number}: {response.status} - {error_text}"

            result = await response.json()
            logger.info(f"✅ Successfully updated issue #{issue_number}")
            return f"✅ Successfully updated issue #{result['number']}: {result['html_url']}"

    except ValueError as auth_error:
        logger.error(f"Authentication error updating issue: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error updating issue: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error updating issue #{issue_number}: {e}", exc_info=True
        )
        return f"❌ Error updating issue: {str(e)}"


from .issue_search import *  # noqa: F401,F403
