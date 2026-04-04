"""GitHub Issue operations."""

from __future__ import annotations

import logging
from typing import Any

from mcp_server_git.github.client import github_client_context

logger = logging.getLogger(__name__)


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

    try:
        async with github_client_context() as client:
            params = {
                "state": state,
                "sort": sort,
                "direction": direction,
                "per_page": per_page,
                "page": page,
            }

            if labels:
                params["labels"] = ",".join(labels)
            if assignee:
                params["assignee"] = assignee
            if creator:
                params["creator"] = creator
            if mentioned:
                params["mentioned"] = mentioned
            if milestone:
                params["milestone"] = milestone
            if since:
                params["since"] = since

            response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/issues", params=params
            )

            if response.status != 200:
                error_text = await response.text()
                return f"❌ Failed to list issues: {response.status} - {error_text}"

            issues = await response.json()

            if not issues:
                return f"No {state} issues found"

            output = [f"{state.title()} Issues for {repo_owner}/{repo_name}:\n"]

            for issue in issues:
                # Skip pull requests (they appear in issues API but have 'pull_request' key)
                if issue.get("pull_request"):
                    continue

                state_emoji = {"open": "🟢", "closed": "🔴"}.get(
                    issue.get("state"), "❓"
                )
                output.append(f"{state_emoji} #{issue['number']}: {issue['title']}")
                output.append(f"   Author: {issue.get('user', {}).get('login', 'N/A')}")

                # Show labels if any
                if issue.get("labels"):
                    label_names = [label["name"] for label in issue["labels"]]
                    output.append(f"   Labels: {', '.join(label_names)}")

                # Show assignees if any
                if issue.get("assignees"):
                    assignee_names = [
                        assignee["login"] for assignee in issue["assignees"]
                    ]
                    output.append(f"   Assignees: {', '.join(assignee_names)}")

                output.append(f"   Created: {issue.get('created_at', 'N/A')}")
                output.append("")

            return "\n".join(output)

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
) -> str:
    """Get a single GitHub issue by number.

    Returns full issue details including title, body, state, labels,
    assignees, milestone, comments count, and timestamps.
    """
    BODY_TRUNCATION_LIMIT = 2000
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

            # Format the issue details
            state_emoji = {"open": "🟢", "closed": "🔴"}.get(issue.get("state"), "❓")

            output = [
                f"Issue #{issue['number']}: {issue['title']}",
                f"State: {state_emoji} {issue.get('state', 'unknown')}",
                f"Author: {(issue.get('user') or {}).get('login', 'N/A')}",
                f"Created: {issue.get('created_at', 'N/A')}",
                f"Updated: {issue.get('updated_at', 'N/A')}",
            ]

            # Add closed_at if closed
            if issue.get("closed_at"):
                output.append(f"Closed: {issue['closed_at']}")

            # Add labels
            if issue.get("labels"):
                label_names = [label["name"] for label in issue["labels"]]
                output.append(f"Labels: {', '.join(label_names)}")

            # Add assignees
            if issue.get("assignees"):
                assignee_names = [a["login"] for a in issue["assignees"]]
                output.append(f"Assignees: {', '.join(assignee_names)}")

            # Add milestone
            if issue.get("milestone"):
                output.append(f"Milestone: {issue['milestone'].get('title', 'N/A')}")

            # Add comments count
            output.append(f"Comments: {issue.get('comments', 0)}")

            # Add URL
            output.append(f"URL: {issue.get('html_url', 'N/A')}")

            # Add body (with truncation for very long bodies)
            body = issue.get("body") or "(No description provided)"
            output.append("")
            output.append("Description:")
            output.append("-" * 40)
            # Truncate very long bodies
            if len(body) > BODY_TRUNCATION_LIMIT:
                output.append(body[:BODY_TRUNCATION_LIMIT] + "\n\n... (truncated)")
            else:
                output.append(body)

            return "\n".join(output)

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
            payload: dict[str, Any] = {}
            if title is not None:
                payload["title"] = title
            if body is not None:
                payload["body"] = body
            if state is not None:
                if state not in ["open", "closed"]:
                    return "❌ State must be 'open' or 'closed'"
                payload["state"] = state
            if labels is not None:
                payload["labels"] = labels
            if assignees is not None:
                payload["assignees"] = assignees
            if milestone is not None:
                payload["milestone"] = milestone

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
