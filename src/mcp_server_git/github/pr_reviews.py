"""Inline PR review comments with optional filters (#355)."""

from __future__ import annotations

import logging
from typing import Any

from mcp_server_git.github.client import github_client_context

from ..utils.tool_failure import ToolFailure, fail
from ._pr_format import format_review_comment
from .pr_threads import comment_thread_map
from .projects_paging import MAX_PAGES

__all__ = ["github_get_pr_reviews"]

logger = logging.getLogger(__name__)

_PER_PAGE = 100


async def _fetch_review_comments(
    client: Any, repo_owner: str, repo_name: str, pr_number: int
) -> list[dict[str, Any]] | ToolFailure:
    """All inline comments (every REST page), or a ready failure."""
    comments: list[dict[str, Any]] = []
    for page in range(1, MAX_PAGES + 1):
        response = await client.get(
            f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}/comments",
            accept="application/vnd.github.full+json",
            params={"per_page": _PER_PAGE, "page": page},
        )
        if response.status != 200:
            error_text = await response.text()
            return fail(
                f"❌ Failed to fetch review comments: {response.status} - {error_text}"
            )
        batch = await response.json()
        comments.extend(batch)
        if len(batch) < _PER_PAGE:
            return comments
    return fail(
        f"❌ Review comments exceed {MAX_PAGES} pages; refusing to return a truncated list."
    )


async def _filter_comments(
    client: Any,
    comments: list[dict[str, Any]],
    ids: list[int] | None,
    unresolved_only: bool,
    coords: tuple[str, str, int],
) -> list[dict[str, Any]]:
    if ids is not None:
        wanted = set(ids)
        comments = [c for c in comments if c.get("id") in wanted]
    if unresolved_only and comments:
        threads = await comment_thread_map(client, *coords)
        comments = [
            c
            for c in comments
            if c.get("id") in threads and not threads[c["id"]]["isResolved"]
        ]
    return comments


async def github_get_pr_reviews(
    repo_owner: str,
    repo_name: str,
    pr_number: int,
    comment_ids: list[int] | None = None,
    unresolved_only: bool = False,
) -> str:
    """Get inline code review comments on a PR.

    ``comment_ids`` keeps only those comments; ``unresolved_only`` keeps only
    comments whose review thread is unresolved.
    """
    logger.debug(
        f"🚀 Fetching review comments for PR #{pr_number} in {repo_owner}/{repo_name}"
    )

    try:
        async with github_client_context() as client:
            fetched = await _fetch_review_comments(
                client, repo_owner, repo_name, pr_number
            )
            if isinstance(fetched, ToolFailure):
                return fetched
            comments = await _filter_comments(
                client,
                fetched,
                comment_ids,
                unresolved_only,
                (repo_owner, repo_name, pr_number),
            )

        if not comments:
            return f"No review comments on PR #{pr_number}"

        lines = [f"Review comments on PR #{pr_number} ({len(comments)} total):\n"]
        for c in comments:
            lines.extend(format_review_comment(c))

        return "\n".join(lines)

    except ValueError as auth_error:
        logger.error(f"Authentication error fetching PR review comments: {auth_error}")
        return fail(f"❌ {str(auth_error)}")
    except ConnectionError as conn_error:
        logger.error(f"Connection error fetching PR review comments: {conn_error}")
        return fail(f"❌ Network connection failed: {str(conn_error)}")
    except Exception as e:
        logger.error(
            f"Unexpected error fetching review comments for PR #{pr_number}: {e}",
            exc_info=True,
        )
        return fail(f"❌ Error fetching PR review comments: {str(e)}")
