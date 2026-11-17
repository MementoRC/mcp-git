"""GraphQL plumbing for PR review threads (#355).

Review threads (the unit that can be resolved) exist only in GraphQL. Both
pagination levels are drained, never truncated: the thread list, and the
comments of any thread with more than one page of them.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from mcp_server_git.utils.tool_failure import fail

from .client import GraphQLError
from .projects_paging import ProjectError, drain_connection
from .workflow_actions import run_guarded

__all__ = [
    "ThreadError",
    "comment_thread_map",
    "fetch_threads",
    "run_mutation",
    "threads_guarded",
]

_COMMENT_FIELDS = "databaseId url body author { login }"

_THREADS_Q = """
query($owner: String!, $name: String!, $number: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id isResolved isOutdated path line originalLine
          resolvedBy { login }
          comments(first: 100) {
            totalCount
            pageInfo { hasNextPage endCursor }
            nodes { COMMENT_FIELDS }
          }
        }
      }
    }
  }
}
""".replace("COMMENT_FIELDS", _COMMENT_FIELDS)

_COMMENTS_Q = """
query($id: ID!, $after: String) {
  node(id: $id) {
    ... on PullRequestReviewThread {
      comments(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes { COMMENT_FIELDS }
      }
    }
  }
}
""".replace("COMMENT_FIELDS", _COMMENT_FIELDS)


class ThreadError(ProjectError):
    """A user-facing review-thread failure (reported as an error envelope)."""


async def _thread_comments(client: Any, thread: dict[str, Any]) -> list[dict[str, Any]]:
    """All comments of a thread, following pagination past the first 100."""

    async def fetch_page(cursor: str) -> dict[str, Any]:
        data = await client.graphql(_COMMENTS_Q, {"id": thread["id"], "after": cursor})
        return ((data.get("node") or {}).get("comments")) or {}

    return await drain_connection(
        thread.get("comments") or {}, fetch_page, f"Comments of {thread['id']}"
    )


async def fetch_threads(
    client: Any, owner: str, name: str, number: int
) -> list[dict[str, Any]]:
    """Every review thread of a PR, with only the first page of comments each."""

    async def fetch_page(cursor: str | None) -> dict[str, Any]:
        data = await client.graphql(
            _THREADS_Q,
            {"owner": owner, "name": name, "number": number, "after": cursor},
        )
        pr = ((data.get("repository") or {}).get("pullRequest")) or None
        if pr is None:
            raise ThreadError(f"Pull request {owner}/{name}#{number} not found.")
        return pr["reviewThreads"]

    first = await fetch_page(None)
    return await drain_connection(first, fetch_page, "Review threads")


async def comment_thread_map(
    client: Any, owner: str, name: str, number: int
) -> dict[int, dict[str, Any]]:
    """Map every review comment ``databaseId`` to its (unpaginated) thread."""
    mapping: dict[int, dict[str, Any]] = {}
    for thread in await fetch_threads(client, owner, name, number):
        comments = thread["comments"]
        if (comments.get("pageInfo") or {}).get("hasNextPage"):
            nodes = await _thread_comments(client, thread)
        else:
            nodes = comments.get("nodes") or []
        for comment in nodes:
            mapping[comment["databaseId"]] = thread
    return mapping


async def run_mutation(
    client: Any, document: str, variables: dict[str, Any], key: str
) -> dict[str, Any]:
    """Run a mutation and return its ``key`` payload; raise when it is null."""
    data = await client.graphql(document, variables)
    payload = data.get(key)
    if not payload:
        raise ThreadError(f"GitHub returned no result for {key}.")
    return payload


async def threads_guarded(op: Callable[[Any], Awaitable[str]]) -> str:
    """``run_guarded`` plus thread/GraphQL errors as error envelopes."""

    async def wrapped(client: Any) -> str:
        try:
            return await op(client)
        except (ProjectError, GraphQLError) as exc:
            return fail(f"❌ {exc}")

    return await run_guarded(wrapped)
