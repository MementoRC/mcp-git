"""Tests for collapsing per-field GraphQL errors (#349)."""

from mcp_server_git.github import projects_gql
from mcp_server_git.github.client import GraphQLError
from mcp_server_git.github.graphql_errors import summarize_graphql_errors
from mcp_server_git.github.projects_gql import project_guarded

SCOPE_MSG = (
    "Your token has not been granted the required scopes to execute this "
    "query. The '{}' field requires one of the following scopes: "
    "['read:project'], but your token has only been granted the: ['repo'] "
    "scopes. Please modify your token's scopes at: "
    "https://github.com/settings/tokens."
)


def _scope_errors(fields: list[str]) -> list[dict]:
    return [{"message": SCOPE_MSG.format(f)} for f in fields]


def test_summarize_returns_one_group_when_14_fields_share_scope_failure():
    names = ["projectV2", "id", "title"] * 4 + ["a", "b"]
    out = summarize_graphql_errors(_scope_errors(names))
    assert out.count("requires one of the following scopes") == 1
    assert "(14 fields: projectV2, id, title, a, b)" in out
    assert "; " not in out


def test_summarize_returns_both_when_errors_differ():
    out = summarize_graphql_errors(
        [{"message": "Could not resolve to a User"}, *_scope_errors(["x"])]
    )
    assert "Could not resolve to a User" in out
    assert "'x' field requires" in out


def test_summarize_returns_unchanged_when_singleton():
    msg = SCOPE_MSG.format("only")
    assert summarize_graphql_errors([{"message": msg}]) == msg


def test_summarize_deduplicates_field_names_when_fields_repeat():
    out = summarize_graphql_errors(_scope_errors(["id", "id", "title"]))
    assert "(3 fields: id, title)" in out


def test_summarize_caps_field_names_when_more_than_five():
    out = summarize_graphql_errors(_scope_errors([f"f{i}" for i in range(8)]))
    assert "(8 fields: f0, f1, f2, f3, f4, +3 more)" in out


def test_summarize_caps_groups_when_more_than_five_distinct():
    errors = [{"message": f"error {i}"} for i in range(8)]
    out = summarize_graphql_errors(errors)
    assert out == "; ".join(f"error {i}" for i in range(5)) + "; +3 more errors"


def test_graphql_error_keeps_structured_errors_when_messages_collapse():
    errors = _scope_errors(["a", "b"])
    exc = GraphQLError(errors)
    assert exc.errors == errors
    assert str(exc).count("requires one of") == 1


async def test_project_guarded_appends_hint_once_when_scope_failure(monkeypatch):
    async def fake_run_guarded(wrapped):
        return await wrapped(None)

    async def op(_client):
        raise GraphQLError(_scope_errors(["a", "b", "c"]))

    monkeypatch.setattr(projects_gql, "run_guarded", fake_run_guarded)
    out = await project_guarded(op)
    assert out.count("scopes to execute") == 1
    assert out.count("the token needs the 'project' scope") == 1
