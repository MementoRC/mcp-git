"""Nested-connection pagination for Projects (v2) tools (issue #352)."""

import json

import pytest

from mcp_server_git.github.projects import (
    github_project_get_fields,
    github_project_list_items,
    github_project_set_item_field,
)
from mcp_server_git.utils.tool_failure import ToolFailure

from ._actions_fakes import call


def _conn(nodes, cursor, size):
    start = int(cursor or 0)
    end = start + size
    return {
        "pageInfo": {
            "hasNextPage": end < len(nodes),
            "endCursor": str(end) if end < len(nodes) else None,
        },
        "nodes": nodes[start:end],
    }


def _field(n):
    return {
        "__typename": "ProjectV2Field",
        "id": f"f{n}",
        "name": f"Field{n}",
        "dataType": "NUMBER",
    }


def _value(n):
    return {
        "__typename": "ProjectV2ItemFieldNumberValue",
        "number": n,
        "field": {"name": f"Field{n}"},
    }


class PagedGraphQL:
    """Serves every connection by cursor (the cursor is a plain offset)."""

    def __init__(self, n_fields=3, n_items=1, values=None):
        self.fields = [_field(n) for n in range(n_fields)]
        self.n_items = n_items
        self.values = values or {}
        self.calls = []

    def _item(self, item_id, size, cursor=None):
        values = [_value(n) for n in range(self.values.get(item_id, 0))]
        number = int(item_id[1:])
        return {
            "id": item_id,
            "isArchived": False,
            "content": {
                "__typename": "Issue",
                "number": number,
                "title": f"Issue {number}",
                "state": "OPEN",
                "url": "u",
                "repository": {"nameWithOwner": "o/r"},
            },
            "fieldValues": _conn(values, cursor, size),
        }

    async def graphql(self, query, variables=None):
        self.calls.append(query)
        cursor = (variables or {}).get("cursor")
        if "mutation" in query:
            return {}
        if "fieldValues(first: 100, after" in query:
            item = self._item(variables["id"], 100, cursor)
            return {"node": {"fieldValues": item["fieldValues"]}}
        if "fields(first: 100, after" in query:
            return {"node": {"fields": _conn(self.fields, cursor, 100)}}
        if "items(first" in query:
            ids = [f"I{n}" for n in range(self.n_items)]
            nodes = [self._item(i, 50) for i in ids]
            return {"node": {"items": _conn(nodes, cursor, 100)}}
        if "projectV2(number" in query:
            project = {
                "id": "P1",
                "title": "T",
                "number": 3,
                "fields": _conn(self.fields, None, 100),
            }
            return {"organization": {"projectV2": project}}
        return {"node": self._item(variables["id"], 50)}


ARGS = {"owner": "o", "owner_type": "org", "project_number": 3}


@pytest.mark.asyncio
async def test_get_fields_returns_all_fields_when_more_than_100():
    client = PagedGraphQL(n_fields=250)

    result = json.loads(await call(github_project_get_fields, client, **ARGS))

    assert [f["name"] for f in result["fields"]] == [f"Field{n}" for n in range(250)]
    assert len(client.calls) == 3


@pytest.mark.asyncio
async def test_set_item_field_resolves_field_when_past_first_100():
    client = PagedGraphQL(n_fields=150, n_items=8)

    result = await call(
        github_project_set_item_field,
        client,
        **ARGS,
        field="field120",
        value="5",
        repo="r",
        issue_number=7,
    )

    assert not isinstance(result, ToolFailure)
    assert any("updateProjectV2ItemFieldValue" in q for q in client.calls)


@pytest.mark.asyncio
async def test_list_items_returns_all_values_when_item_has_over_50():
    client = PagedGraphQL(n_items=1, values={"I0": 230})

    result = json.loads(await call(github_project_list_items, client, **ARGS))

    assert result["items"][0]["fields"] == {f"Field{n}": n for n in range(230)}


@pytest.mark.asyncio
async def test_list_items_returns_all_when_items_and_values_both_paginate():
    client = PagedGraphQL(n_items=101, values={"I0": 60, "I100": 120})

    result = json.loads(await call(github_project_list_items, client, **ARGS))

    by_id = {i["number"]: i for i in result["items"]}
    assert result["count"] == 101
    assert len(by_id[0]["fields"]) == 60 and len(by_id[100]["fields"]) == 120


@pytest.mark.asyncio
async def test_list_items_makes_baseline_calls_when_nothing_has_next_page():
    client = PagedGraphQL(n_items=3, values={"I1": 10})

    await call(github_project_list_items, client, **ARGS)

    assert len(client.calls) == 2  # project + one items page


@pytest.mark.asyncio
async def test_list_items_fails_when_values_exceed_page_cap():
    client = PagedGraphQL(n_items=1, values={"I0": 50 + 100 * 50})

    result = await call(github_project_list_items, client, **ARGS)

    assert isinstance(result, ToolFailure) and "truncated" in result
