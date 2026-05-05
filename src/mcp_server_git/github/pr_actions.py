"""GitHub Pull Request action operations — create, update, merge, comments."""
from __future__ import annotations

import logging
from typing import Any

from mcp_server_git.github.client import github_client_context

logger = logging.getLogger(__name__)

_BOT_TEMPLATE_MARKER = "${{"


def _select_rendered_body(comment: dict[str, Any]) -> str:
    """Pick the most useful body field from a GitHub comment object.

    GitHub renders bot template placeholders (e.g. ``${{ metadata.patch }}``)
    server-side only when the response includes ``body_html`` / ``body_text``
    (requested via ``application/vnd.github.full+json``). When the markdown
    ``body`` contains template syntax we fall back to the rendered ``body_text``;
    otherwise we keep the markdown ``body`` to preserve links and formatting.
    """
    body = (comment.get("body") or "").strip()
    if _BOT_TEMPLATE_MARKER in body:
        body_text = (comment.get("body_text") or "").strip()
        if body_text:
            return body_text
    return body


async def github_update_pr(
    repo_owner: str,
    repo_name: str,
    pr_number: int,
    title: str | None = None,
    body: str | None = None,
    state: str | None = None,
    base: str | None = None,
) -> str:
    """Update a pull request's title, body, state, or base branch."""
    logger.debug(f"🚀 Updating PR #{pr_number} in {repo_owner}/{repo_name}")

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
            if base is not None:
                payload["base"] = base

            if not payload:
                return "⚠️ No update parameters provided. Please specify title, body, state, or base."

            response = await client.patch(
                f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}", json=payload
            )

            if response.status != 200:
                error_text = await response.text()
                return f"❌ Failed to update PR #{pr_number}: {response.status} - {error_text}"

            result = await response.json()
            logger.info(f"✅ Successfully updated PR #{pr_number}")
            return (
                f"✅ Successfully updated PR #{result['number']}: {result['html_url']}"
            )

    except ValueError as auth_error:
        logger.error(f"Authentication error updating PR: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error updating PR: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error updating PR #{pr_number}: {e}", exc_info=True)
        return f"❌ Error updating PR: {str(e)}"


async def github_create_pr(
    repo_owner: str,
    repo_name: str,
    title: str,
    head: str,
    base: str,
    body: str | None = None,
    draft: bool = False,
) -> str:
    """Create a new pull request."""
    logger.debug(f"🚀 Creating PR in {repo_owner}/{repo_name} from {head} to {base}")

    try:
        async with github_client_context() as client:
            payload = {"title": title, "head": head, "base": base, "draft": draft}
            if body is not None:
                payload["body"] = body

            response = await client.post(
                f"/repos/{repo_owner}/{repo_name}/pulls", json=payload
            )

            if response.status != 201:
                error_text = await response.text()
                # Provide more helpful error for common cases
                if (
                    "No commits between" in error_text
                    or "A pull request already exists" in error_text
                ):
                    return f"❌ Could not create PR. Reason: {error_text}"
                return f"❌ Failed to create PR: {response.status} - {error_text}"

            result = await response.json()
            logger.info(f"✅ Successfully created PR #{result['number']}")
            return (
                f"✅ Successfully created PR #{result['number']}: {result['html_url']}"
            )

    except ValueError as auth_error:
        logger.error(f"Authentication error creating PR: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error creating PR: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error creating PR: {e}", exc_info=True)
        return f"❌ Error creating PR: {str(e)}"


async def github_merge_pr(
    repo_owner: str,
    repo_name: str,
    pr_number: int,
    commit_title: str | None = None,
    commit_message: str | None = None,
    merge_method: str = "merge",
) -> str:
    """Merge a pull request."""
    logger.debug(
        f"🚀 Merging PR #{pr_number} in {repo_owner}/{repo_name} using '{merge_method}' method"
    )

    try:
        async with github_client_context() as client:
            if merge_method not in ["merge", "squash", "rebase"]:
                return "❌ merge_method must be one of 'merge', 'squash', or 'rebase'"

            payload = {"merge_method": merge_method}
            if commit_title:
                payload["commit_title"] = commit_title
            if commit_message:
                payload["commit_message"] = commit_message

            response = await client.put(
                f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}/merge", json=payload
            )

            if response.status != 200:
                error_text = await response.text()
                if response.status in [405, 409]:
                    return f"❌ Could not merge PR. Reason: {error_text}. This may be due to merge conflicts or failing status checks."
                return f"❌ Failed to merge PR: {response.status} - {error_text}"

            result = await response.json()
            if result.get("merged"):
                logger.info(f"✅ Successfully merged PR #{pr_number}")
                return f"✅ {result['message']}"
            else:
                logger.warning(
                    f"⚠️ Merge attempt for PR #{pr_number} returned 200 OK but 'merged' is false: {result.get('message')}"
                )
                return f"⚠️ {result.get('message', 'Merge was not successful but API returned 200 OK. Check PR status.')}"

    except ValueError as auth_error:
        logger.error(f"Authentication error merging PR: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error merging PR: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(f"Unexpected error merging PR #{pr_number}: {e}", exc_info=True)
        return f"❌ Error merging PR: {str(e)}"


async def github_add_pr_comment(
    repo_owner: str, repo_name: str, pr_number: int, body: str
) -> str:
    """Add a comment to a pull request."""
    logger.debug(f"🚀 Adding comment to PR #{pr_number} in {repo_owner}/{repo_name}")

    try:
        async with github_client_context() as client:
            # Comments are added to the corresponding issue
            payload = {"body": body}

            response = await client.post(
                f"/repos/{repo_owner}/{repo_name}/issues/{pr_number}/comments",
                json=payload,
            )

            if response.status != 201:
                error_text = await response.text()
                return f"❌ Failed to add comment: {response.status} - {error_text}"

            result = await response.json()
            logger.info(f"✅ Successfully added comment to PR #{pr_number}")
            return f"✅ Successfully added comment: {result['html_url']}"

    except ValueError as auth_error:
        logger.error(f"Authentication error adding PR comment: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error adding PR comment: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error adding comment to PR #{pr_number}: {e}", exc_info=True
        )
        return f"❌ Error adding comment: {str(e)}"


async def github_get_pr_comments(
    repo_owner: str, repo_name: str, pr_number: int
) -> str:
    """Get top-level conversation comments on a PR."""
    logger.debug(
        f"🚀 Fetching comments for PR #{pr_number} in {repo_owner}/{repo_name}"
    )

    try:
        async with github_client_context() as client:
            response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/issues/{pr_number}/comments",
                accept="application/vnd.github.full+json",
                params={"per_page": 100},
            )

            if response.status != 200:
                error_text = await response.text()
                return f"❌ Failed to fetch comments: {response.status} - {error_text}"

            comments = await response.json()

        if not comments:
            return f"No comments on PR #{pr_number}"

        lines = [f"Comments on PR #{pr_number} ({len(comments)} total):\n"]
        for c in comments:
            author = c.get("user", {}).get("login", "unknown")
            created = c.get("created_at", "")
            body = _select_rendered_body(c)
            comment_id = c.get("id", "")
            lines.append(f"  #{comment_id} by {author} ({created}):")
            lines.append(f"    {body}\n")

        return "\n".join(lines)

    except ValueError as auth_error:
        logger.error(f"Authentication error fetching PR comments: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error fetching PR comments: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error fetching comments for PR #{pr_number}: {e}",
            exc_info=True,
        )
        return f"❌ Error fetching PR comments: {str(e)}"


async def github_get_pr_reviews(repo_owner: str, repo_name: str, pr_number: int) -> str:
    """Get inline code review comments on a PR."""
    logger.debug(
        f"🚀 Fetching review comments for PR #{pr_number} in {repo_owner}/{repo_name}"
    )

    try:
        async with github_client_context() as client:
            response = await client.get(
                f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}/comments",
                accept="application/vnd.github.full+json",
                params={"per_page": 100},
            )

            if response.status != 200:
                error_text = await response.text()
                return f"❌ Failed to fetch review comments: {response.status} - {error_text}"

            comments = await response.json()

        if not comments:
            return f"No review comments on PR #{pr_number}"

        lines = [f"Review comments on PR #{pr_number} ({len(comments)} total):\n"]
        for c in comments:
            author = c.get("user", {}).get("login", "unknown")
            created = c.get("created_at", "")
            body = _select_rendered_body(c)
            path = c.get("path", "")
            line = c.get("line") or c.get("original_line", "")
            comment_id = c.get("id", "")
            in_reply_to = c.get("in_reply_to_id", "")
            reply_info = f" (reply to #{in_reply_to})" if in_reply_to else ""
            diff_hunk = (c.get("diff_hunk") or "").strip()

            lines.append(f"  #{comment_id} by {author} ({created}){reply_info}:")
            lines.append(f"    File: {path}:{line}")
            lines.append(f"    {body}")
            if diff_hunk:
                lines.append("    Diff hunk:")
                lines.append("    ```diff")
                lines.append(diff_hunk)
                lines.append("    ```")
            lines.append("")

        return "\n".join(lines)

    except ValueError as auth_error:
        logger.error(f"Authentication error fetching PR review comments: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error fetching PR review comments: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error fetching review comments for PR #{pr_number}: {e}",
            exc_info=True,
        )
        return f"❌ Error fetching PR review comments: {str(e)}"


async def github_reply_to_pr_comment(
    repo_owner: str, repo_name: str, pr_number: int, comment_id: int, body: str
) -> str:
    """Reply to a specific review comment thread."""
    if not body or not body.strip():
        return "❌ Error: reply body cannot be empty"
    if len(body) > 65536:
        return "❌ Error: reply body exceeds GitHub's 65536 character limit"

    logger.debug(
        f"🚀 Replying to comment #{comment_id} on PR #{pr_number} in {repo_owner}/{repo_name}"
    )

    try:
        async with github_client_context() as client:
            response = await client.post(
                f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}/comments/{comment_id}/replies",
                json={"body": body},
            )

            if response.status != 201:
                error_text = await response.text()
                return f"❌ Failed to post reply: {response.status} - {error_text}"

            result = await response.json()
            reply_id = result.get("id", "unknown")
            logger.info(
                f"✅ Successfully replied to comment #{comment_id} on PR #{pr_number}"
            )
            return f"✅ Reply #{reply_id} posted to comment #{comment_id} on PR #{pr_number}"

    except ValueError as auth_error:
        logger.error(f"Authentication error replying to PR comment: {auth_error}")
        return f"❌ {str(auth_error)}"
    except ConnectionError as conn_error:
        logger.error(f"Connection error replying to PR comment: {conn_error}")
        return f"❌ Network connection failed: {str(conn_error)}"
    except Exception as e:
        logger.error(
            f"Unexpected error replying to comment #{comment_id} on PR #{pr_number}: {e}",
            exc_info=True,
        )
        return f"❌ Error replying to comment: {str(e)}"


async def github_close_pr(repo_owner: str, repo_name: str, pr_number: int) -> str:
    """Close a pull request."""
    logger.debug(f"🚀 Closing PR #{pr_number} in {repo_owner}/{repo_name}")
    return await github_update_pr(repo_owner, repo_name, pr_number, state="closed")


async def github_reopen_pr(repo_owner: str, repo_name: str, pr_number: int) -> str:
    """Reopen a closed pull request."""
    logger.debug(f"🚀 Reopening PR #{pr_number} in {repo_owner}/{repo_name}")
    return await github_update_pr(repo_owner, repo_name, pr_number, state="open")


async def github_edit_pr_description(
    repo_owner: str,
    repo_name: str,
    pr_number: int,
    description: str,
) -> str:
    """Edit a pull request's description/body."""
    logger.debug(f"🚀 Updating PR #{pr_number} description in {repo_owner}/{repo_name}")

    # Use the existing github_update_pr function to update just the body
    return await github_update_pr(
        repo_owner=repo_owner,
        repo_name=repo_name,
        pr_number=pr_number,
        body=description,
    )
