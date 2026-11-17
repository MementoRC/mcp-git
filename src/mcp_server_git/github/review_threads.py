"""PR review thread tools: list, reply, resolve, unresolve (#355).

Thread mutations are addressed by node id and need no owner/repo; the tools
still take them so the identity mapping can pick the right token.
"""

from __future__ import annotations

import json
from typing import Any

from mcp_server_git.utils.tool_failure import fail

from .pr_threads import fetch_threads, run_mutation, threads_guarded

__all__ = [
    "github_list_review_threads",
    "github_reply_review_thread",
    "github_resolve_review_thread",
    "github_unresolve_review_thread",
]

_BODY_CHARS = 200

_REPLY_M = """
mutation($id: ID!, $body: String!) {
  addPullRequestReviewThreadReply(
    input: {pullRequestReviewThreadId: $id, body: $body}
  ) {
    comment { databaseId url }
  }
}
"""

_RESOLVE_M = """
mutation($id: ID!) {
  resolveReviewThread(input: {threadId: $id}) {
    thread { id isResolved resolvedBy { login } }
  }
}
"""

_UNRESOLVE_M = """
mutation($id: ID!) {
  unresolveReviewThread(input: {threadId: $id}) {
    thread { id isResolved resolvedBy { login } }
  }
}
"""


def _dump(payload: Any) -> str:
    return json.dumps(payload, indent=2, default=str)


def _truncate(body: str) -> str:
    return body if len(body) <= _BODY_CHARS else body[:_BODY_CHARS] + "... [truncated]"


def _first_comment(thread: dict[str, Any]) -> dict[str, Any] | None:
    nodes = (thread.get("comments") or {}).get("nodes") or []
    if not nodes:
        return None
    first = nodes[0]
    return {
        "database_id": first.get("databaseId"),
        "author": (first.get("author") or {}).get("login"),
        "url": first.get("url"),
        "body": _truncate(first.get("body") or ""),
    }


def _summarize(thread: dict[str, Any]) -> dict[str, Any]:
    line = thread.get("line")
    return {
        "thread_id": thread["id"],
        "is_resolved": thread["isResolved"],
        "is_outdated": thread["isOutdated"],
        "resolved_by": (thread.get("resolvedBy") or {}).get("login"),
        "path": thread.get("path"),
        "line": line if line is not None else thread.get("originalLine"),
        "comment_count": (thread.get("comments") or {}).get("totalCount", 0),
        "first_comment": _first_comment(thread),
    }


def _thread_state(thread: dict[str, Any]) -> dict[str, Any]:
    return {
        "thread_id": thread["id"],
        "is_resolved": thread["isResolved"],
        "resolved_by": (thread.get("resolvedBy") or {}).get("login"),
    }


async def github_list_review_threads(
    repo_owner: str, repo_name: str, pr_number: int, unresolved_only: bool = False
) -> str:
    """List a PR's review threads (resolution state, location, first comment)."""

    async def op(client: Any) -> str:
        threads = await fetch_threads(client, repo_owner, repo_name, pr_number)
        if unresolved_only:
            threads = [t for t in threads if not t["isResolved"]]
        return _dump(
            {
                "pr_number": pr_number,
                "count": len(threads),
                "threads": [_summarize(t) for t in threads],
            }
        )

    return await threads_guarded(op)


async def github_reply_review_thread(
    repo_owner: str, repo_name: str, thread_id: str, body: str
) -> str:
    """Reply to a review thread; returns the new comment's url and id."""
    if not body or not body.strip():
        return fail("❌ Error: reply body cannot be empty")

    async def op(client: Any) -> str:
        payload = await run_mutation(
            client,
            _REPLY_M,
            {"id": thread_id, "body": body},
            "addPullRequestReviewThreadReply",
        )
        comment = payload.get("comment") or {}
        return _dump(
            {
                "thread_id": thread_id,
                "url": comment.get("url"),
                "database_id": comment.get("databaseId"),
            }
        )

    return await threads_guarded(op)


async def _set_resolved(client: Any, thread_id: str, mutation: str, key: str) -> str:
    payload = await run_mutation(client, mutation, {"id": thread_id}, key)
    return _dump(_thread_state(payload["thread"]))


async def github_resolve_review_thread(
    repo_owner: str, repo_name: str, thread_id: str
) -> str:
    """Mark a review thread resolved."""
    return await threads_guarded(
        lambda client: _set_resolved(
            client, thread_id, _RESOLVE_M, "resolveReviewThread"
        )
    )


async def github_unresolve_review_thread(
    repo_owner: str, repo_name: str, thread_id: str
) -> str:
    """Reopen a resolved review thread."""
    return await threads_guarded(
        lambda client: _set_resolved(
            client, thread_id, _UNRESOLVE_M, "unresolveReviewThread"
        )
    )
