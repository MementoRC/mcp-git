"""Add and list issue / PR conversation comments (#326).

``issue_number`` also addresses a pull request's conversation thread. The list
tool returns every comment body in full so callers can run idempotency checks
(for example "is my hidden HTML marker already there?").
"""

from __future__ import annotations

from typing import Any

from mcp_server_git.utils.tool_failure import ToolFailure, fail

from ._failures import http_failure
from .workflow_actions import run_guarded

__all__ = ["github_add_issue_comment", "github_list_issue_comments"]


async def _failure(
    action: str, response: Any, repo_owner: str, repo_name: str, issue_number: int
) -> ToolFailure:
    if response.status == 404:
        text = await response.text()
        return fail(
            f"❌ Issue not found: #{issue_number} in {repo_owner}/{repo_name} "
            f"(404), or the token cannot see it. GitHub said: {text}"
        )
    return await http_failure(action, response)


async def _add_op(
    client: Any, repo_owner: str, repo_name: str, issue_number: int, body: str
) -> str:
    response = await client.post(
        f"/repos/{repo_owner}/{repo_name}/issues/{issue_number}/comments",
        json={"body": body},
    )
    if response.status != 201:
        return await _failure(
            "add comment", response, repo_owner, repo_name, issue_number
        )
    result = await response.json()
    return (
        f"✅ Successfully added comment {result['id']} to "
        f"#{issue_number}: {result['html_url']}"
    )


async def github_add_issue_comment(
    repo_owner: str, repo_name: str, issue_number: int, body: str
) -> str:
    """Add a comment to an issue or PR conversation (POST /issues/{n}/comments)."""
    if not body or not body.strip():
        return fail("❌ Comment body must not be empty or whitespace-only.")
    return await run_guarded(
        lambda client: _add_op(client, repo_owner, repo_name, issue_number, body)
    )


def _format_comment(comment: dict) -> str:
    author = (comment.get("user") or {}).get("login", "unknown")
    return (
        f"Comment {comment.get('id')} by {author} at {comment.get('created_at')}\n"
        f"URL: {comment.get('html_url')}\n"
        f"Body:\n{comment.get('body') or ''}"
    )


async def _list_op(
    client: Any,
    repo_owner: str,
    repo_name: str,
    issue_number: int,
    per_page: int,
    page: int,
) -> str:
    response = await client.get(
        f"/repos/{repo_owner}/{repo_name}/issues/{issue_number}/comments",
        params={"per_page": per_page, "page": page},
    )
    if response.status != 200:
        return await _failure(
            "list comments", response, repo_owner, repo_name, issue_number
        )
    comments = await response.json()
    if not comments:
        return (
            f"No comments on #{issue_number} in {repo_owner}/{repo_name} (page {page})."
        )
    header = f"{len(comments)} comment(s) on #{issue_number} (page {page}):"
    return "\n\n".join([header, *(_format_comment(c) for c in comments)])


async def github_list_issue_comments(
    repo_owner: str,
    repo_name: str,
    issue_number: int,
    per_page: int = 30,
    page: int = 1,
) -> str:
    """List an issue or PR conversation's comments with full bodies."""
    return await run_guarded(
        lambda client: _list_op(
            client, repo_owner, repo_name, issue_number, per_page, page
        )
    )
