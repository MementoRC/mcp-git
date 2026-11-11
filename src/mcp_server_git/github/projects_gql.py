"""GraphQL plumbing for GitHub Projects (v2) tools (#345).

Queries, pagination, flattening of field values and item lookup. Projects
belong to a user or an organization, so the owner root differs by
``owner_type``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from mcp_server_git.utils.tool_failure import fail

from .client import GraphQLError
from .workflow_actions import run_guarded

__all__ = [
    "ProjectError",
    "fetch_item",
    "fetch_items",
    "fetch_project",
    "find_field",
    "flatten_item",
    "project_guarded",
    "repo_matches",
    "resolve_item",
]

_ROOTS = {"user": "user", "org": "organization"}


class ProjectError(Exception):
    """A user-facing Projects failure (reported as an error envelope)."""


_PROJECT_Q = """
query($login: String!, $number: Int!) {
  ROOT(login: $login) {
    projectV2(number: $number) {
      id title number
      fields(first: 100) {
        nodes {
          __typename
          ... on ProjectV2FieldCommon { id name dataType }
          ... on ProjectV2SingleSelectField { options { id name } }
          ... on ProjectV2IterationField {
            configuration {
              iterations { id title startDate duration }
              completedIterations { id title startDate duration }
            }
          }
        }
      }
    }
  }
}
"""

_FIELD = "field { ... on ProjectV2FieldCommon { name } }"
_ITEM = """
id isArchived
content {
  __typename
  ... on Issue { number title state url repository { nameWithOwner } }
  ... on PullRequest { number title state url repository { nameWithOwner } }
  ... on DraftIssue { title }
}
fieldValues(first: 50) {
  nodes {
    __typename
    ... on ProjectV2ItemFieldTextValue { text FIELD }
    ... on ProjectV2ItemFieldNumberValue { number FIELD }
    ... on ProjectV2ItemFieldDateValue { date FIELD }
    ... on ProjectV2ItemFieldSingleSelectValue { name FIELD }
    ... on ProjectV2ItemFieldIterationValue { title FIELD }
    ... on ProjectV2ItemFieldLabelValue { labels(first: 20) { nodes { name } } FIELD }
    ... on ProjectV2ItemFieldMilestoneValue { milestone { title } FIELD }
    ... on ProjectV2ItemFieldUserValue { users(first: 20) { nodes { login } } FIELD }
    ... on ProjectV2ItemFieldRepositoryValue { repository { nameWithOwner } FIELD }
  }
}
""".replace("FIELD", _FIELD)

_ITEMS_Q = """
query($id: ID!, $cursor: String) {
  node(id: $id) {
    ... on ProjectV2 {
      items(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes { ITEM }
      }
    }
  }
}
""".replace("ITEM", _ITEM)

_ITEM_Q = """
query($id: ID!) { node(id: $id) { ... on ProjectV2Item { ITEM } } }
""".replace("ITEM", _ITEM)


async def fetch_project(
    client: Any, owner: str, owner_type: str, number: int
) -> dict[str, Any]:
    """The project (id, title, fields) or ``ProjectError`` when not visible."""
    root = _ROOTS.get(owner_type)
    if root is None:
        raise ProjectError(f"owner_type must be 'user' or 'org', got {owner_type!r}")
    data = await client.graphql(
        _PROJECT_Q.replace("ROOT", root), {"login": owner, "number": number}
    )
    project = (data.get(root) or {}).get("projectV2")
    if not project:
        raise ProjectError(
            f"Project #{number} not found for {owner_type} '{owner}', or the "
            "token cannot see it (needs the 'read:project' scope)."
        )
    return project


def find_field(project: dict[str, Any], name: str) -> dict[str, Any]:
    """Field by case-insensitive name; the error lists the valid names."""
    fields = [f for f in project["fields"]["nodes"] if f.get("name")]
    for f in fields:
        if f["name"].lower() == name.strip().lower():
            return f
    valid = ", ".join(sorted(f["name"] for f in fields))
    raise ProjectError(f"Unknown field '{name}'. Valid fields: {valid}")


_VALUE_READERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "ProjectV2ItemFieldTextValue": lambda n: n["text"],
    "ProjectV2ItemFieldNumberValue": lambda n: n["number"],
    "ProjectV2ItemFieldDateValue": lambda n: n["date"],
    "ProjectV2ItemFieldSingleSelectValue": lambda n: n["name"],
    "ProjectV2ItemFieldIterationValue": lambda n: n["title"],
    "ProjectV2ItemFieldLabelValue": lambda n: [x["name"] for x in n["labels"]["nodes"]],
    "ProjectV2ItemFieldMilestoneValue": lambda n: (n["milestone"] or {}).get("title"),
    "ProjectV2ItemFieldUserValue": lambda n: [x["login"] for x in n["users"]["nodes"]],
    "ProjectV2ItemFieldRepositoryValue": lambda n: (n["repository"] or {}).get(
        "nameWithOwner"
    ),
}


def _flatten_values(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for node in nodes:
        reader = _VALUE_READERS.get(node.get("__typename", ""))
        name = (node.get("field") or {}).get("name")
        if reader and name:
            values[name] = reader(node)
    return values


def flatten_item(node: dict[str, Any]) -> dict[str, Any]:
    """Item with content summary and field values keyed by field name."""
    content = node.get("content") or {}
    repo = (content.get("repository") or {}).get("nameWithOwner")
    return {
        "item_id": node["id"],
        "archived": node.get("isArchived", False),
        "type": content.get("__typename", "REDACTED"),
        "repo": repo,
        "number": content.get("number"),
        "title": content.get("title"),
        "state": content.get("state"),
        "url": content.get("url"),
        "fields": _flatten_values(node["fieldValues"]["nodes"]),
    }


async def fetch_items(client: Any, project_id: str) -> list[dict[str, Any]]:
    """Every item of the project, paginating past 100."""
    items: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        data = await client.graphql(_ITEMS_Q, {"id": project_id, "cursor": cursor})
        page = data["node"]["items"]
        items.extend(flatten_item(n) for n in page["nodes"])
        info = page["pageInfo"]
        cursor = info.get("endCursor")
        if not info.get("hasNextPage") or not cursor:
            return items


async def fetch_item(client: Any, item_id: str) -> dict[str, Any]:
    """One flattened item by node id."""
    data = await client.graphql(_ITEM_Q, {"id": item_id})
    node = data.get("node")
    if not node or "id" not in node:
        raise ProjectError(f"Project item '{item_id}' not found.")
    return flatten_item(node)


def repo_matches(item_repo: str | None, repo: str) -> bool:
    """Exact, case-insensitive: ``owner/name``, or a bare ``name`` segment."""
    if not item_repo:
        return False
    wanted, actual = repo.strip().lower(), item_repo.lower()
    return actual == wanted or actual.endswith("/" + wanted)


async def resolve_item(
    client: Any,
    project_id: str,
    repo: str | None,
    issue_number: int | None,
    item_id: str | None,
) -> dict[str, Any]:
    """Select an item by ``item_id`` or by ``repo`` + ``issue_number``."""
    if item_id:
        return await fetch_item(client, item_id)
    if not repo or issue_number is None:
        raise ProjectError("Provide item_id, or both repo and issue_number.")
    matches = [
        i
        for i in await fetch_items(client, project_id)
        if i["number"] == issue_number and repo_matches(i["repo"], repo)
    ]
    if not matches:
        raise ProjectError(f"No item for {repo}#{issue_number} in this project.")
    return matches[0]


async def project_guarded(op: Callable[[Any], Awaitable[str]]) -> str:
    """``run_guarded`` plus Projects errors and a missing-scope hint (#199)."""

    async def wrapped(client: Any) -> str:
        try:
            return await op(client)
        except ProjectError as exc:
            return fail(f"❌ {exc}")
        except GraphQLError as exc:
            text = str(exc)
            if "scope" in text.lower() or any(
                e.get("type") == "INSUFFICIENT_SCOPES" for e in exc.errors
            ):
                text += (
                    " -- the token needs the 'project' scope "
                    "('read:project' for read-only tools)."
                )
            return fail(f"❌ {text}")

    return await run_guarded(wrapped)
