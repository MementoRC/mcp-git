"""Additive issue labelling: add and remove labels on one issue (#327)."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from mcp_server_git.utils.tool_failure import fail

from .workflow_actions import run_guarded, status_failure

__all__ = ["github_add_issue_labels", "github_remove_issue_label"]


async def _add_op(
    client: Any, repo_owner: str, repo_name: str, issue_number: int, labels: list[str]
) -> str:
    endpoint = f"/repos/{repo_owner}/{repo_name}/issues/{issue_number}/labels"
    response = await client.post(endpoint, json={"labels": labels})
    if response.status != 200:
        return await status_failure(
            f"add labels to #{issue_number}", response, repo_owner, repo_name
        )
    names = [label.get("name") for label in await response.json()]
    return (
        f"✅ Issue #{issue_number} labels now: {', '.join(map(str, names)) or '(none)'}"
    )


async def _remove_op(
    client: Any, repo_owner: str, repo_name: str, issue_number: int, label: str
) -> str:
    endpoint = (
        f"/repos/{repo_owner}/{repo_name}/issues/{issue_number}"
        f"/labels/{quote(label, safe='')}"
    )
    response = await client.delete(endpoint)
    if response.status == 404:
        return f"ℹ️ Label {label!r} is not applied to #{issue_number}; nothing changed."
    if response.status != 200:
        return await status_failure(
            f"remove label {label!r} from #{issue_number}",
            response,
            repo_owner,
            repo_name,
        )
    names = [item.get("name") for item in await response.json()]
    return (
        f"✅ Removed {label!r} from #{issue_number}; labels now: "
        f"{', '.join(map(str, names)) or '(none)'}"
    )


async def github_add_issue_labels(
    repo_owner: str, repo_name: str, issue_number: int, labels: list[str]
) -> str:
    """Add labels to an issue without replacing existing ones (POST .../labels)."""
    if not labels:
        return fail("❌ labels must be a non-empty list of label names.")
    return await run_guarded(
        lambda client: _add_op(client, repo_owner, repo_name, issue_number, labels)
    )


async def github_remove_issue_label(
    repo_owner: str, repo_name: str, issue_number: int, label: str
) -> str:
    """Remove one label from an issue (DELETE .../labels/{label})."""
    return await run_guarded(
        lambda client: _remove_op(client, repo_owner, repo_name, issue_number, label)
    )
