"""Compact PR review listing: one row per review, no bodies (#357)."""

from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Any

from mcp_server_git.github.client import github_client_context

from ..utils.tool_failure import ToolFailure, fail
from .projects_paging import MAX_PAGES

__all__ = ["github_list_pr_reviews"]

logger = logging.getLogger(__name__)

_PER_PAGE = 100
_MIN_SHA_LEN = 7
_MAX_ERROR_CHARS = 500


async def _fetch_pages(
    client: Any, endpoint: str, what: str
) -> list[dict[str, Any]] | ToolFailure:
    """Every REST page of *endpoint*, or a ready failure."""
    items: list[dict[str, Any]] = []
    # One probe page past the cap: an endpoint holding exactly the cap is complete.
    for page in range(1, MAX_PAGES + 2):
        response = await client.get(
            endpoint, params={"per_page": _PER_PAGE, "page": page}
        )
        if response.status != 200:
            error_text = await response.text()
            if len(error_text) > _MAX_ERROR_CHARS:
                error_text = error_text[:_MAX_ERROR_CHARS] + "…"
            return fail(f"❌ Failed to fetch {what}: {response.status} - {error_text}")
        batch = await response.json()
        if not isinstance(batch, list):
            return fail(f"❌ Unexpected response shape from {endpoint}: expected list")
        if page > MAX_PAGES:
            if not batch:
                return items
            break
        items.extend(batch)
        if len(batch) < _PER_PAGE:
            return items
    return fail(
        f"❌ {what.capitalize()} exceed {MAX_PAGES} pages; refusing to truncate."
    )


def _row(review: dict[str, Any]) -> dict[str, Any]:
    user = review.get("user") or {}
    return {
        "id": review.get("id"),
        "author": user.get("login") or "ghost",
        "author_type": user.get("type"),
        "state": review.get("state"),
        "commit_id": review.get("commit_id"),
        "submitted_at": review.get("submitted_at"),
    }


def _keep(
    row: dict[str, Any], authors: list[str] | None, commit_id: str | None
) -> bool:
    needles = [a.strip().lower() for a in authors or [] if a and a.strip()]
    if needles:
        login = row["author"].lower()
        if not any(a in login for a in needles):
            return False
    if not commit_id:
        return True
    return (row["commit_id"] or "").lower().startswith(commit_id.lower())


async def github_list_pr_reviews(
    repo_owner: str,
    repo_name: str,
    pr_number: int,
    authors: list[str] | None = None,
    commit_id: str | None = None,
    include_inline_counts: bool = False,
) -> str:
    """List PR reviews as compact JSON rows (no bodies, all pages).

    ``authors`` are case-insensitive login substrings; bot logins keep their
    ``[bot]`` suffix. ``commit_id`` may be a full or short (>=7) SHA.
    """
    if commit_id is not None and len(commit_id) < _MIN_SHA_LEN:
        return fail(f"❌ commit_id must be at least {_MIN_SHA_LEN} characters")
    base = f"/repos/{repo_owner}/{repo_name}/pulls/{pr_number}"
    try:
        async with github_client_context() as client:
            reviews = await _fetch_pages(client, f"{base}/reviews", "reviews")
            if isinstance(reviews, ToolFailure):
                return reviews
            counts: Counter[int] | None = None
            if include_inline_counts:
                comments = await _fetch_pages(
                    client, f"{base}/comments", "review comments"
                )
                if isinstance(comments, ToolFailure):
                    return comments
                counts = Counter(
                    c["pull_request_review_id"]
                    for c in comments
                    if c.get("pull_request_review_id") is not None
                )
    except ValueError as auth_error:
        return fail(f"❌ {auth_error}")
    except ConnectionError as conn_error:
        return fail(f"❌ Network connection failed: {conn_error}")
    except Exception as e:
        logger.error(f"Error listing reviews for PR #{pr_number}: {e}", exc_info=True)
        return fail(f"❌ Error listing PR reviews: {e}")

    rows = [_row(r) for r in reviews]
    kept = [r for r in rows if _keep(r, authors, commit_id)]
    if counts is not None:
        for row in kept:
            row["inline_comment_count"] = counts.get(row["id"], 0)
    payload = {
        "pr": pr_number,
        "total": len(rows),
        "returned": len(kept),
        "reviews": kept,
    }
    return json.dumps(payload, separators=(",", ":"))
