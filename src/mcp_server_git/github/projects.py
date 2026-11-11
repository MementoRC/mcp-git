"""GitHub Projects (v2) tools over GraphQL (#345).

Every tool takes ``owner``, ``owner_type`` ('user'|'org') and
``project_number``; field and option ids are resolved internally from names.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .projects_gql import (
    ProjectError,
    fetch_item,
    fetch_items,
    fetch_project,
    find_field,
    project_guarded,
    repo_matches,
    resolve_item,
)
from .projects_values import build_value

__all__ = [
    "github_project_add_item",
    "github_project_archive_item",
    "github_project_clear_item_field",
    "github_project_get_fields",
    "github_project_list_items",
    "github_project_set_item_field",
]

_URL = re.compile(r"github\.com/([^/]+)/([^/]+)/(?:issues|pull)/(\d+)")

_SET = """
mutation($p: ID!, $i: ID!, $f: ID!, $v: ProjectV2FieldValue!) {
  updateProjectV2ItemFieldValue(
    input: {projectId: $p, itemId: $i, fieldId: $f, value: $v}
  ) { projectV2Item { id } }
}
"""
_CLEAR = """
mutation($p: ID!, $i: ID!, $f: ID!) {
  clearProjectV2ItemFieldValue(input: {projectId: $p, itemId: $i, fieldId: $f}) {
    projectV2Item { id }
  }
}
"""
_ARCHIVE = """
mutation($p: ID!, $i: ID!) {
  archiveProjectV2Item(input: {projectId: $p, itemId: $i}) { item { id } }
}
"""
_ADD = """
mutation($p: ID!, $c: ID!) {
  addProjectV2ItemById(input: {projectId: $p, contentId: $c}) { item { id } }
}
"""
_CONTENT = """
query($o: String!, $n: String!, $num: Int!) {
  repository(owner: $o, name: $n) {
    issueOrPullRequest(number: $num) {
      __typename
      ... on Issue { id }
      ... on PullRequest { id }
    }
  }
}
"""


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, default=str)


def _matches_filters(
    item: dict[str, Any],
    repo: str | None,
    numbers: list[int] | None,
    field: str | None,
    value: str | None,
) -> bool:
    if repo and not repo_matches(item["repo"], repo):
        return False
    if numbers is not None and item["number"] not in numbers:
        return False
    return field is None or _field_equals(item, field, value)


def _field_equals(item: dict[str, Any], field: str, value: str | None) -> bool:
    actual = next(
        (v for k, v in item["fields"].items() if k.lower() == field.lower()), None
    )
    wanted = (value or "").strip().lower()
    if isinstance(actual, list):
        return wanted in [str(a).lower() for a in actual]
    return actual is not None and str(actual).lower() == wanted


async def github_project_list_items(
    owner: str,
    owner_type: str,
    project_number: int,
    repo: str | None = None,
    numbers: list[int] | None = None,
    field: str | None = None,
    value: str | None = None,
) -> str:
    """List project items with content and all field values, by field name."""
    if (field is None) != (value is None):
        return await project_guarded(_raise("Provide field and value together."))

    async def op(client: Any) -> str:
        project = await fetch_project(client, owner, owner_type, project_number)
        items = [
            i
            for i in await fetch_items(client, project["id"])
            if _matches_filters(i, repo, numbers, field, value)
        ]
        return _dump({"project": project["title"], "count": len(items), "items": items})

    return await project_guarded(op)


def _raise(message: str) -> Any:
    async def op(_client: Any) -> str:
        raise ProjectError(message)

    return op


def _describe_field(field: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": field["id"],
        "name": field["name"],
        "type": field.get("dataType"),
    }
    if "options" in field:
        out["options"] = field["options"]
    if "configuration" in field:
        config = field["configuration"] or {}
        out["iterations"] = [
            *config.get("iterations", []),
            *config.get("completedIterations", []),
        ]
    return out


async def github_project_get_fields(
    owner: str, owner_type: str, project_number: int
) -> str:
    """List project fields with ids, types and single-select option ids."""

    async def op(client: Any) -> str:
        project = await fetch_project(client, owner, owner_type, project_number)
        fields = [
            _describe_field(f) for f in project["fields"]["nodes"] if f.get("name")
        ]
        return _dump(
            {"project": project["title"], "id": project["id"], "fields": fields}
        )

    return await project_guarded(op)


async def github_project_set_item_field(
    owner: str,
    owner_type: str,
    project_number: int,
    field: str,
    value: str,
    repo: str | None = None,
    issue_number: int | None = None,
    item_id: str | None = None,
) -> str:
    """Set a field on a project item by names; returns before and after."""

    async def op(client: Any) -> str:
        project = await fetch_project(client, owner, owner_type, project_number)
        target = find_field(project, field)
        value_input = build_value(target, value)
        item = await resolve_item(client, project["id"], repo, issue_number, item_id)
        await client.graphql(
            _SET,
            {
                "p": project["id"],
                "i": item["item_id"],
                "f": target["id"],
                "v": value_input,
            },
        )
        after = await fetch_item(client, item["item_id"])
        return _dump(
            {
                "item_id": item["item_id"],
                "field": target["name"],
                "before": item["fields"].get(target["name"]),
                "after": after["fields"].get(target["name"]),
            }
        )

    return await project_guarded(op)


async def github_project_clear_item_field(
    owner: str,
    owner_type: str,
    project_number: int,
    field: str,
    repo: str | None = None,
    issue_number: int | None = None,
    item_id: str | None = None,
) -> str:
    """Clear a field value on a project item; returns before and after."""

    async def op(client: Any) -> str:
        project = await fetch_project(client, owner, owner_type, project_number)
        target = find_field(project, field)
        item = await resolve_item(client, project["id"], repo, issue_number, item_id)
        await client.graphql(
            _CLEAR, {"p": project["id"], "i": item["item_id"], "f": target["id"]}
        )
        after = await fetch_item(client, item["item_id"])
        return _dump(
            {
                "item_id": item["item_id"],
                "field": target["name"],
                "before": item["fields"].get(target["name"]),
                "after": after["fields"].get(target["name"]),
            }
        )

    return await project_guarded(op)


async def github_project_archive_item(
    owner: str,
    owner_type: str,
    project_number: int,
    repo: str | None = None,
    issue_number: int | None = None,
    item_id: str | None = None,
) -> str:
    """Archive a project item."""

    async def op(client: Any) -> str:
        project = await fetch_project(client, owner, owner_type, project_number)
        item = await resolve_item(client, project["id"], repo, issue_number, item_id)
        await client.graphql(_ARCHIVE, {"p": project["id"], "i": item["item_id"]})
        return _dump({"item_id": item["item_id"], "archived": True})

    return await project_guarded(op)


def _parse_target(
    owner: str, url: str | None, repo: str | None, number: int | None
) -> tuple[str, str, int]:
    if url:
        match = _URL.search(url)
        if not match:
            raise ProjectError(f"Not an issue/PR URL: {url}")
        return match[1], match[2], int(match[3])
    if not repo or number is None:
        raise ProjectError("Provide url, or both repo and number.")
    repo_owner, _, name = repo.rpartition("/")
    return repo_owner or owner, name, number


async def _set_initial_fields(
    client: Any,
    project_id: str,
    item_id: str,
    planned: list[tuple[dict[str, Any], dict[str, Any]]],
) -> None:
    """Set each planned field; a failure says the item WAS already added."""
    done: list[str] = []
    for target, value_input in planned:
        try:
            await client.graphql(
                _SET,
                {"p": project_id, "i": item_id, "f": target["id"], "v": value_input},
            )
        except Exception as exc:
            raise ProjectError(
                f"Item WAS added (item_id: {item_id}) but setting an initial "
                f"field failed. set: {', '.join(done) or 'none'}; "
                f"failed: {target['name']} ({exc})"
            ) from exc
        done.append(target["name"])


async def github_project_add_item(
    owner: str,
    owner_type: str,
    project_number: int,
    url: str | None = None,
    repo: str | None = None,
    number: int | None = None,
    fields: dict[str, str] | None = None,
) -> str:
    """Add an issue or PR to a project, optionally setting fields by name.

    The content lookup and the add both run under the project owner's identity,
    so that token must be able to read the content repo (even when it differs
    from the project owner).
    """

    async def op(client: Any) -> str:
        r_owner, r_name, num = _parse_target(owner, url, repo, number)
        project = await fetch_project(client, owner, owner_type, project_number)
        planned = [
            (t := find_field(project, name), build_value(t, val))
            for name, val in (fields or {}).items()
        ]
        data = await client.graphql(_CONTENT, {"o": r_owner, "n": r_name, "num": num})
        content = (data.get("repository") or {}).get("issueOrPullRequest")
        if not content:
            raise ProjectError(f"{r_owner}/{r_name}#{num} not found.")
        added = await client.graphql(_ADD, {"p": project["id"], "c": content["id"]})
        item_id = added["addProjectV2ItemById"]["item"]["id"]
        await _set_initial_fields(client, project["id"], item_id, planned)
        item = await fetch_item(client, item_id)
        return _dump({"added": f"{r_owner}/{r_name}#{num}", "item": item})

    return await project_guarded(op)
