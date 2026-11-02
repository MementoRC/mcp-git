"""github_add_issue_labels / github_remove_issue_label (issue #327)."""

import pytest

from mcp_server_git.github.api import (
    github_add_issue_labels,
    github_remove_issue_label,
)
from mcp_server_git.utils.tool_failure import ToolFailure

from ._label_fakes import FakeResponse, LabelClient, build_interface, call

ISSUE = "/repos/o/r/issues/5/labels"
REMOVE = f"{ISSUE}/area%3A%20ci%2Fcd"


@pytest.mark.asyncio
async def test_add_issue_labels_posts_labels_body_and_lists_result():
    resp = FakeResponse(200, [{"name": "old"}, {"name": "new"}])
    client = LabelClient({("POST", ISSUE): resp})

    result = await call(github_add_issue_labels, client, "o", "r", 5, ["new"])

    assert client.calls == [("POST", ISSUE, {"json": {"labels": ["new"]}})]
    assert "old" in result and "new" in result


@pytest.mark.asyncio
async def test_add_issue_labels_returns_failure_without_http_when_list_empty():
    client = LabelClient({})

    result = await call(github_add_issue_labels, client, "o", "r", 5, [])

    assert isinstance(result, ToolFailure)
    assert client.calls == []


@pytest.mark.asyncio
async def test_remove_issue_label_deletes_encoded_path_when_name_has_specials():
    client = LabelClient({("DELETE", REMOVE): FakeResponse(200, [{"name": "bug"}])})

    result = await call(github_remove_issue_label, client, "o", "r", 5, "area: ci/cd")

    assert client.calls == [("DELETE", REMOVE, {})]
    assert "bug" in result


@pytest.mark.asyncio
async def test_remove_issue_label_returns_non_failure_when_404_not_applied():
    client = LabelClient({("DELETE", f"{ISSUE}/bug"): FakeResponse(404, text="x")})

    result = await call(github_remove_issue_label, client, "o", "r", 5, "bug")

    assert not isinstance(result, ToolFailure)
    assert "not applied" in result


@pytest.mark.asyncio
async def test_remove_issue_label_returns_failure_when_403():
    client = LabelClient({("DELETE", f"{ISSUE}/bug"): FakeResponse(403, text="no")})

    result = await call(github_remove_issue_label, client, "o", "r", 5, "bug")

    assert isinstance(result, ToolFailure)


def test_add_issue_labels_description_states_additive_when_registered():
    tool = build_interface().tool_registry["github_add_issue_labels"]

    assert "ADDS" in tool.description and "github_update_issue" in tool.description
