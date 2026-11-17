"""PR review thread tools (issue #355); only the GraphQL boundary is faked."""

import json

import pytest

from mcp_server_git.github.client import GraphQLError
from mcp_server_git.github.review_threads import (
    github_list_review_threads,
    github_reply_review_thread,
    github_resolve_review_thread,
    github_unresolve_review_thread,
)
from mcp_server_git.utils.tool_failure import ToolFailure

from ._actions_fakes import call
from ._thread_fakes import FakeGraphQL, comment, thread, threads_response

LIST_MARKER = "reviewThreads("


async def _list(client, **kwargs):
    args = {"repo_owner": "o", "repo_name": "r", "pr_number": 7}
    return await call(github_list_review_threads, client, **(args | kwargs))


@pytest.mark.asyncio
async def test_list_review_threads_returns_summary_when_thread_has_comments():
    long_body = "x" * 300
    t = thread("T1", [comment(11, long_body), comment(12)], line=None)
    client = FakeGraphQL({LIST_MARKER: threads_response([t])})

    result = json.loads(await _list(client))

    summary = result["threads"][0]
    assert summary["thread_id"] == "T1"
    assert summary["line"] == 8
    assert summary["comment_count"] == 2
    assert summary["first_comment"]["database_id"] == 11
    assert summary["first_comment"]["body"] == "x" * 200 + "... [truncated]"


@pytest.mark.asyncio
async def test_list_review_threads_filters_resolved_when_unresolved_only():
    nodes = [
        thread("T1", [comment(1)], resolved=True),
        thread("T2", [comment(2)]),
    ]
    client = FakeGraphQL({LIST_MARKER: threads_response(nodes)})

    result = json.loads(await _list(client, unresolved_only=True))

    assert [t["thread_id"] for t in result["threads"]] == ["T2"]


@pytest.mark.asyncio
async def test_list_review_threads_follows_cursor_when_more_pages():
    pages = [
        threads_response([thread("T1", [comment(1)])], cursor="c1"),
        threads_response([thread("T2", [comment(2)])]),
    ]
    client = FakeGraphQL({LIST_MARKER: pages})

    result = json.loads(await _list(client))

    assert result["count"] == 2
    assert client.calls[1][1]["after"] == "c1"


@pytest.mark.asyncio
async def test_list_review_threads_fails_when_pull_request_missing():
    client = FakeGraphQL({LIST_MARKER: {"repository": {"pullRequest": None}}})

    result = await _list(client)

    assert isinstance(result, ToolFailure)
    assert "not found" in result


@pytest.mark.asyncio
async def test_reply_review_thread_returns_comment_when_reply_posted():
    reply = {
        "addPullRequestReviewThreadReply": {
            "comment": {"databaseId": 99, "url": "https://github.com/o/r/x"}
        }
    }
    client = FakeGraphQL({"addPullRequestReviewThreadReply": reply})

    result = await call(
        github_reply_review_thread, client, "o", "r", "T1", "Thanks, fixed"
    )

    assert json.loads(result)["database_id"] == 99
    assert client.calls[0][1] == {"id": "T1", "body": "Thanks, fixed"}


@pytest.mark.asyncio
@pytest.mark.parametrize("body", ["", "   \n"])
async def test_reply_review_thread_fails_without_network_when_body_blank(body):
    client = FakeGraphQL({})

    result = await call(github_reply_review_thread, client, "o", "r", "T1", body)

    assert isinstance(result, ToolFailure)
    assert client.calls == []


@pytest.mark.asyncio
async def test_reply_review_thread_fails_when_graphql_errors():
    errors = GraphQLError([{"message": "Could not resolve to a node"}])
    client = FakeGraphQL({"addPullRequestReviewThreadReply": errors})

    result = await call(github_reply_review_thread, client, "o", "r", "T1", "hi")

    assert isinstance(result, ToolFailure)
    assert "Could not resolve" in result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("op", "key", "resolved"),
    [
        (github_resolve_review_thread, "resolveReviewThread", True),
        (github_unresolve_review_thread, "unresolveReviewThread", False),
    ],
)
async def test_resolve_review_thread_returns_state_when_mutation_succeeds(
    op, key, resolved
):
    node = thread("T1", [], resolved=resolved)
    client = FakeGraphQL({key: {key: {"thread": node}}})

    result = json.loads(await call(op, client, "o", "r", "T1"))

    assert result["is_resolved"] is resolved
    assert result["resolved_by"] == ("alice" if resolved else None)
