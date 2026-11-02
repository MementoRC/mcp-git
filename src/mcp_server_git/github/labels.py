"""Repository label management: list, create, update (#327).

Label names contain spaces, colons and slashes, so every name placed in a URL
path is percent-encoded with ``quote(name, safe="")``.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from mcp_server_git.utils.tool_failure import ToolFailure, fail

from .workflow_actions import run_guarded, status_failure

__all__ = [
    "github_create_label",
    "github_list_labels",
    "github_update_label",
    "normalise_color",
]

_HEX6 = re.compile(r"[0-9a-fA-F]{6}")


def normalise_color(color: str) -> str | ToolFailure:
    """Strip a leading '#' and require exactly six hex digits."""
    value = color.strip().removeprefix("#")
    if not _HEX6.fullmatch(value):
        return fail(
            f"❌ Invalid color {color!r}: use 6 hex digits such as 'fbca04' "
            "(a leading '#' is accepted)."
        )
    return value.lower()


def _label_line(label: dict) -> str:
    description = label.get("description") or ""
    return f"- {label.get('name')} (#{label.get('color')}) {description}".rstrip()


async def _list_op(
    client: Any, repo_owner: str, repo_name: str, per_page: int, page: int
) -> str:
    response = await client.get(
        f"/repos/{repo_owner}/{repo_name}/labels?per_page={per_page}&page={page}"
    )
    if response.status != 200:
        return await status_failure("list labels", response, repo_owner, repo_name)
    labels = await response.json()
    if not labels:
        return f"No labels on page {page} of {repo_owner}/{repo_name}."
    lines = "\n".join(_label_line(label) for label in labels)
    return f"Labels in {repo_owner}/{repo_name} (page {page}, {len(labels)}):\n{lines}"


async def _create_failure(response: Any, name: str, owner: str, repo: str) -> str:
    if response.status == 422:
        body = await response.text()
        if "already_exists" in body:
            return (
                f"ℹ️ Label {name!r} already exists in {owner}/{repo}; nothing changed."
            )
    return await status_failure(f"create label {name!r}", response, owner, repo)


async def _create_op(
    client: Any,
    repo_owner: str,
    repo_name: str,
    name: str,
    color: str,
    description: str | None,
) -> str:
    payload: dict[str, Any] = {"name": name, "color": color}
    if description is not None:
        payload["description"] = description
    response = await client.post(
        f"/repos/{repo_owner}/{repo_name}/labels", json=payload
    )
    if response.status != 201:
        return await _create_failure(response, name, repo_owner, repo_name)
    return f"✅ Created label {name!r} (#{color}) in {repo_owner}/{repo_name}"


async def _update_op(
    client: Any, repo_owner: str, repo_name: str, name: str, payload: dict[str, str]
) -> str:
    endpoint = f"/repos/{repo_owner}/{repo_name}/labels/{quote(name, safe='')}"
    response = await client.patch(endpoint, json=payload)
    if response.status == 404:
        return fail(f"❌ Label {name!r} not found in {repo_owner}/{repo_name} (404).")
    if response.status != 200:
        return await status_failure(
            f"update label {name!r}", response, repo_owner, repo_name
        )
    label = await response.json()
    return f"✅ Updated label: {_label_line(label)}"


async def github_list_labels(
    repo_owner: str, repo_name: str, per_page: int = 100, page: int = 1
) -> str:
    """List repository labels (GET /repos/{o}/{r}/labels)."""
    return await run_guarded(
        lambda client: _list_op(
            client, repo_owner, repo_name, max(1, min(100, per_page)), max(1, page)
        )
    )


async def github_create_label(
    repo_owner: str,
    repo_name: str,
    name: str,
    color: str,
    description: str | None = None,
) -> str:
    """Create a label (POST /repos/{o}/{r}/labels); an existing one is not an error."""
    normalised = normalise_color(color)
    if isinstance(normalised, ToolFailure):
        return normalised
    return await run_guarded(
        lambda client: _create_op(
            client, repo_owner, repo_name, name, normalised, description
        )
    )


async def github_update_label(
    repo_owner: str,
    repo_name: str,
    name: str,
    new_name: str | None = None,
    color: str | None = None,
    description: str | None = None,
) -> str:
    """Update a label (PATCH /repos/{o}/{r}/labels/{name}); only given fields are sent."""
    payload: dict[str, str] = {}
    if new_name is not None:
        payload["new_name"] = new_name
    if description is not None:
        payload["description"] = description
    if color is not None:
        normalised = normalise_color(color)
        if isinstance(normalised, ToolFailure):
            return normalised
        payload["color"] = normalised
    if not payload:
        return fail(
            "❌ Nothing to update: provide at least one of new_name, color, description."
        )
    return await run_guarded(
        lambda client: _update_op(client, repo_owner, repo_name, name, payload)
    )
