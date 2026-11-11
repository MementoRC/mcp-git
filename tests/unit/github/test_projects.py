"""GitHub Projects (v2) tools (issue #345); only the GraphQL boundary is faked."""

import json

import pytest

from mcp_server_git.github.client import GraphQLError
from mcp_server_git.github.projects import (
    github_project_add_item,
    github_project_get_fields,
    github_project_list_items,
    github_project_set_item_field,
)
from mcp_server_git.utils.tool_failure import ToolFailure

from ._actions_fakes import call

OPTIONS = [{"id": "o1", "name": "Todo"}, {"id": "o2", "name": "In progress"}]
PROJECT = {
    "id": "P1",
    "title": "Roadmap",
    "number": 3,
    "fields": {
        "nodes": [
            {"__typename": "ProjectV2Field", "id": "f0", "name": "Title"},
            {
                "__typename": "ProjectV2SingleSelectField",
                "id": "f1",
                "name": "Status",
                "dataType": "SINGLE_SELECT",
                "options": OPTIONS,
            },
            {
                "__typename": "ProjectV2Field",
                "id": "f2",
                "name": "Estimate",
                "dataType": "NUMBER",
            },
        ]
    },
}


def _item(item_id, number, status=None, repo="o/r"):
    values = []
    if status:
        values.append(
            {
                "__typename": "ProjectV2ItemFieldSingleSelectValue",
                "name": status,
                "field": {"name": "Status"},
            }
        )
    return {
        "id": item_id,
        "isArchived": False,
        "content": {
            "__typename": "Issue",
            "number": number,
            "title": f"Issue {number}",
            "state": "OPEN",
            "url": f"https://github.com/{repo}/issues/{number}",
            "repository": {"nameWithOwner": repo},
        },
        "fieldValues": {"nodes": values},
    }


def _page(nodes, cursor=None):
    return {
        "node": {
            "items": {
                "pageInfo": {"hasNextPage": cursor is not None, "endCursor": cursor},
                "nodes": nodes,
            }
        }
    }


class FakeGraphQL:
    """Routes a query by marker substring; list values are consumed in order."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    async def graphql(self, query, variables=None):
        self.calls.append((query, variables))
        for marker, value in self.routes.items():
            if marker in query:
                result = value.pop(0) if isinstance(value, list) else value
                if isinstance(result, Exception):
                    raise result
                return result
        raise AssertionError(f"unrouted query: {query[:60]}")

    def with_marker(self, marker):
        return [v for q, v in self.calls if marker in q]


def _project_route(root="organization"):
    return {"projectV2(number": {root: {"projectV2": PROJECT}}}


async def _list(client, **kwargs):
    args = {"owner": "o", "owner_type": "org", "project_number": 3}
    return await call(github_project_list_items, client, **(args | kwargs))


async def _set(client, **kwargs):
    args = {
        "owner": "o",
        "owner_type": "org",
        "project_number": 3,
        "field": "status",
        "value": "in progress",
        "repo": "r",
        "issue_number": 7,
    }
    return await call(github_project_set_item_field, client, **(args | kwargs))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("owner_type", "root"), [("org", "organization"), ("user", "user")]
)
async def test_get_fields_queries_owner_root_when_owner_type_given(owner_type, root):
    client = FakeGraphQL(_project_route(root))

    result = await call(
        github_project_get_fields,
        client,
        owner="o",
        owner_type=owner_type,
        project_number=3,
    )

    query, variables = client.calls[0]
    assert f"{root}(login: $login)" in query
    assert variables == {"login": "o", "number": 3}
    status = next(f for f in json.loads(result)["fields"] if f["name"] == "Status")
    assert status["options"] == OPTIONS and status["type"] == "SINGLE_SELECT"


@pytest.mark.asyncio
async def test_list_items_paginates_when_more_than_100_items():
    first = [_item(f"i{n}", n, "Todo") for n in range(100)]
    client = FakeGraphQL(
        {
            **_project_route(),
            "items(first": [_page(first, "c1"), _page([_item("i100", 100)])],
        }
    )

    result = json.loads(await _list(client))

    assert result["count"] == 101
    pages = client.with_marker("items(first")
    assert [v["cursor"] for v in pages] == [None, "c1"]
    assert result["items"][0]["fields"] == {"Status": "Todo"}
    assert result["items"][0]["repo"] == "o/r"


@pytest.mark.asyncio
async def test_list_items_filters_by_field_value_when_requested():
    nodes = [_item("a", 1, "Todo"), _item("b", 2, "In progress"), _item("c", 3)]
    client = FakeGraphQL({**_project_route(), "items(first": _page(nodes)})

    result = json.loads(await _list(client, field="status", value="in progress"))

    assert [i["number"] for i in result["items"]] == [2]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("repo", "expected"),
    [("foo", [1]), ("o/foo", [1]), ("O/FOO", [1]), ("oo", []), ("x/foo", [])],
)
async def test_list_items_matches_repo_exactly_when_repo_filter_given(repo, expected):
    nodes = [_item("a", 1, repo="o/foo"), _item("b", 2, repo="o/xfoo")]
    client = FakeGraphQL({**_project_route(), "items(first": _page(nodes)})

    result = json.loads(await _list(client, repo=repo))

    assert [i["number"] for i in result["items"]] == expected


@pytest.mark.asyncio
async def test_add_item_reports_item_added_when_initial_field_fails():
    client = FakeGraphQL(
        {
            **_project_route(),
            "issueOrPullRequest": {
                "repository": {
                    "issueOrPullRequest": {"__typename": "Issue", "id": "C9"}
                }
            },
            "addProjectV2ItemById": {"addProjectV2ItemById": {"item": {"id": "I9"}}},
            "updateProjectV2ItemFieldValue": [
                {},
                GraphQLError([{"message": "boom"}]),
            ],
        }
    )

    result = await call(
        github_project_add_item,
        client,
        owner="o",
        owner_type="org",
        project_number=3,
        repo="r",
        number=12,
        fields={"Status": "todo", "Estimate": "2"},
    )

    assert isinstance(result, ToolFailure)
    assert "WAS added" in result and "I9" in result
    assert "set: Status" in result and "failed: Estimate" in result
    assert "boom" in result


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["nan", "inf", "-inf", "Infinity"])
async def test_set_item_field_fails_when_number_not_finite(raw):
    client = FakeGraphQL(_project_route())

    result = await _set(client, field="Estimate", value=raw, item_id="I1")

    assert isinstance(result, ToolFailure) and "finite" in result
    assert not client.with_marker("updateProjectV2")


@pytest.mark.asyncio
async def test_set_item_field_sets_option_by_name_when_single_select():
    client = FakeGraphQL(
        {
            **_project_route(),
            "items(first": _page([_item("I1", 7, "Todo"), _item("I2", 8)]),
            "updateProjectV2ItemFieldValue": {},
            "ProjectV2Item {": {"node": _item("I1", 7, "In progress")},
        }
    )

    result = json.loads(await _set(client))

    ((_, variables),) = [c for c in client.calls if "updateProjectV2" in c[0]]
    assert variables == {
        "p": "P1",
        "i": "I1",
        "f": "f1",
        "v": {"singleSelectOptionId": "o2"},
    }
    assert (result["before"], result["after"]) == ("Todo", "In progress")


@pytest.mark.asyncio
async def test_set_item_field_fails_listing_options_when_option_unknown():
    client = FakeGraphQL(_project_route())

    result = await _set(client, value="Done")

    assert isinstance(result, ToolFailure)
    assert "Unknown option 'Done'" in result
    assert "Todo, In progress" in result
    assert not client.with_marker("updateProjectV2")


@pytest.mark.asyncio
async def test_set_item_field_sends_number_value_when_number_field():
    client = FakeGraphQL(
        {
            **_project_route(),
            "updateProjectV2ItemFieldValue": {},
            "ProjectV2Item {": {"node": _item("I1", 7)},
        }
    )

    await _set(client, field="Estimate", value="3.5", item_id="I1")

    ((_, variables),) = [c for c in client.calls if "updateProjectV2" in c[0]]
    assert variables["v"] == {"number": 3.5}


@pytest.mark.asyncio
async def test_list_items_returns_scope_error_when_token_lacks_project_scope():
    err = GraphQLError(
        [{"type": "INSUFFICIENT_SCOPES", "message": "Your token has not been granted"}]
    )
    client = FakeGraphQL({"projectV2(number": err})

    result = await _list(client)

    assert isinstance(result, ToolFailure)
    assert "'project' scope" in result


@pytest.mark.asyncio
async def test_list_items_fails_when_project_not_found():
    client = FakeGraphQL({"projectV2(number": {"organization": {"projectV2": None}}})

    result = await _list(client)

    assert isinstance(result, ToolFailure) and "not found" in result


@pytest.mark.asyncio
async def test_add_item_adds_by_url_and_sets_initial_field_when_fields_given():
    client = FakeGraphQL(
        {
            **_project_route(),
            "issueOrPullRequest": {
                "repository": {
                    "issueOrPullRequest": {"__typename": "Issue", "id": "C9"}
                }
            },
            "addProjectV2ItemById": {"addProjectV2ItemById": {"item": {"id": "I9"}}},
            "updateProjectV2ItemFieldValue": {},
            "ProjectV2Item {": {"node": _item("I9", 12, "Todo")},
        }
    )

    result = json.loads(
        await call(
            github_project_add_item,
            client,
            owner="o",
            owner_type="org",
            project_number=3,
            url="https://github.com/o/r/issues/12",
            fields={"Status": "todo"},
        )
    )

    assert client.with_marker("addProjectV2ItemById")[0] == {"p": "P1", "c": "C9"}
    assert result["item"]["fields"] == {"Status": "Todo"}
    assert result["added"] == "o/r#12"
