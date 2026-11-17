"""discover_tools keyword matching (#355)."""

from unittest.mock import MagicMock

import pytest

from mcp_server_git.lean.interface import GitLeanInterface, ToolDefinition
from mcp_server_git.lean.tool_match import tool_matches


def _tool(keywords=()):
    return ToolDefinition(
        name="git_show",
        implementation=lambda: None,
        description="Shows a commit about mutation",
        schema={},
        keywords=keywords,
    )


@pytest.mark.parametrize(
    ("pattern", "keywords", "expected"),
    [
        ("show", (), True),
        ("GIT_SHOW", (), True),
        ("revision", ("revision",), True),
        ("FILE AT", ("file at commit",), True),
        ("", (), True),
        ("   ", (), True),
        ("revision", (), False),
        ("mutation", ("blob",), False),
    ],
)
def test_tool_matches_returns_expected_when_pattern_vs_name_and_keywords(
    pattern, keywords, expected
):
    assert tool_matches(pattern, _tool(keywords)) is expected


def test_tool_definition_defaults_keywords_to_empty_when_not_given():
    tool = ToolDefinition("n", lambda: None, "d", {})

    assert tool.keywords == ()


@pytest.fixture
def iface():
    return GitLeanInterface(MagicMock(), MagicMock(), MagicMock())


@pytest.mark.parametrize("pattern", ["revision", "CAT-FILE", "blob", "file at commit"])
def test_discover_tools_returns_git_show_when_pattern_is_a_keyword(iface, pattern):
    names = [t["name"] for t in iface.discover_tools(pattern)["available_tools"]]

    assert "git_show" in names


def test_discover_tools_returns_graphql_query_when_pattern_is_graphql(iface):
    names = [t["name"] for t in iface.discover_tools("graphql")["available_tools"]]

    assert "github_graphql_query" in names


def test_discover_tools_returns_thread_tools_when_pattern_is_thread_keyword(iface):
    def names(pattern):
        return [t["name"] for t in iface.discover_tools(pattern)["available_tools"]]

    assert {"github_resolve_review_thread", "github_unresolve_review_thread"} <= set(
        names("resolve")
    )
    assert "github_list_review_threads" in names("discussion")


def test_discover_tools_ignores_description_when_pattern_only_in_description(iface):
    result = iface.discover_tools("caps output")

    assert result["available_tools"] == []
