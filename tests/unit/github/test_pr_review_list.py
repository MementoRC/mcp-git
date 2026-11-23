"""github_list_pr_reviews: compact rows, paging, filters, counts (#357).

Only the HTTP boundary (``github_client_context``) is faked.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from mcp_server_git.github.pr_review_list import github_list_pr_reviews
from mcp_server_git.lean.response_offloader import (
    NEVER_OFFLOAD_TOOLS,
    ResponseOffloader,
)
from mcp_server_git.lean.token_limiter import MCPTokenLimiter
from mcp_server_git.utils.tool_failure import ToolFailure

from ._actions_fakes import FakeResponse

_REVIEWS = "/repos/owner/repo/pulls/1/reviews"
_COMMENTS = "/repos/owner/repo/pulls/1/comments"
_SHA = "a1b2c3d4e5f6a7b8c9d0a1b2c3d4e5f6a7b8c9d0"


class FakeClient:
    """Serves REST items per endpoint, sliced by the ``page`` param."""

    def __init__(
        self, items, status=200, always_full=False, error_text="boom", body=None
    ):
        self.items = items
        self.status = status
        self.always_full = always_full
        self.error_text = error_text
        self.body = body
        self.endpoints = []

    async def get(self, endpoint, **kwargs):
        self.endpoints.append(endpoint)
        if self.status != 200:
            return FakeResponse(self.status, text=self.error_text)
        if self.body is not None:
            return FakeResponse(200, self.body)
        if self.always_full:
            return FakeResponse(200, [{"id": 1}] * 100)
        page = kwargs["params"]["page"]
        return FakeResponse(
            200, self.items.get(endpoint, [])[(page - 1) * 100 : page * 100]
        )


def _review(rid=1, login="alice", utype="User", commit=_SHA, state="COMMENTED"):
    return {
        "id": rid,
        "user": {"login": login, "type": utype} if login else None,
        "state": state,
        "commit_id": commit,
        "submitted_at": "2024-01-01T00:00:00Z",
        "body": "long body",
        "html_url": "https://x",
    }


async def _run(client, **kwargs):
    with patch("mcp_server_git.github.pr_review_list.github_client_context") as ctx:
        ctx.return_value.__aenter__.return_value = client
        return await github_list_pr_reviews("owner", "repo", 1, **kwargs)


@pytest.mark.asyncio
async def test_list_pr_reviews_returns_all_rows_when_reviews_span_pages():
    client = FakeClient({_REVIEWS: [_review(i) for i in range(230)]})

    raw = await _run(client)
    data = json.loads(raw)

    assert (data["pr"], data["total"], data["returned"]) == (1, 230, 230)
    assert len(client.endpoints) == 3
    assert ", " not in raw


@pytest.mark.asyncio
async def test_list_pr_reviews_returns_compact_row_when_review_has_body():
    client = FakeClient({_REVIEWS: [_review(7)]})

    row = json.loads(await _run(client))["reviews"][0]

    assert row == {
        "id": 7,
        "author": "alice",
        "author_type": "User",
        "state": "COMMENTED",
        "commit_id": _SHA,
        "submitted_at": "2024-01-01T00:00:00Z",
    }


@pytest.mark.asyncio
async def test_list_pr_reviews_matches_bot_login_when_authors_substring_differs_in_case():
    bot = _review(2, "copilot-pull-request-reviewer[bot]", "Bot")
    client = FakeClient({_REVIEWS: [_review(1), bot]})

    data = json.loads(await _run(client, authors=["COPILOT"]))

    assert data["total"] == 2
    assert data["returned"] == 1
    assert data["reviews"][0]["author"] == "copilot-pull-request-reviewer[bot]"
    assert data["reviews"][0]["author_type"] == "Bot"


@pytest.mark.asyncio
async def test_list_pr_reviews_returns_ghost_when_user_is_null():
    client = FakeClient({_REVIEWS: [_review(3, login=None)]})

    row = json.loads(await _run(client))["reviews"][0]

    assert (row["author"], row["author_type"]) == ("ghost", None)


@pytest.mark.asyncio
@pytest.mark.parametrize("commit", [_SHA, _SHA[:7], _SHA[:12]])
async def test_list_pr_reviews_filters_by_commit_when_commit_id_full_or_short(commit):
    other = _review(2, commit="f" * 40)
    client = FakeClient({_REVIEWS: [_review(1), other]})

    data = json.loads(await _run(client, commit_id=commit))

    assert [r["id"] for r in data["reviews"]] == [1]


@pytest.mark.asyncio
async def test_list_pr_reviews_fails_when_commit_id_shorter_than_seven():
    client = FakeClient({_REVIEWS: [_review(1)]})

    result = await _run(client, commit_id="abc123")

    assert isinstance(result, ToolFailure)
    assert client.endpoints == []


@pytest.mark.asyncio
async def test_list_pr_reviews_adds_counts_when_include_inline_counts():
    comments = [{"pull_request_review_id": 1}] * 2 + [{"pull_request_review_id": 9}]
    client = FakeClient({_REVIEWS: [_review(1), _review(2)], _COMMENTS: comments})

    rows = json.loads(await _run(client, include_inline_counts=True))["reviews"]

    assert [r["inline_comment_count"] for r in rows] == [2, 0]
    assert client.endpoints == [_REVIEWS, _COMMENTS]


@pytest.mark.asyncio
async def test_list_pr_reviews_skips_comments_call_when_counts_not_requested():
    client = FakeClient({_REVIEWS: [_review(1)]})

    row = json.loads(await _run(client))["reviews"][0]

    assert client.endpoints == [_REVIEWS]
    assert "inline_comment_count" not in row


@pytest.mark.asyncio
async def test_list_pr_reviews_fails_when_pages_exceed_max_pages():
    result = await _run(FakeClient({}, always_full=True))

    assert isinstance(result, ToolFailure)
    assert "refusing to truncate" in result


@pytest.mark.asyncio
async def test_list_pr_reviews_fails_when_api_returns_error():
    result = await _run(FakeClient({}, status=404))

    assert isinstance(result, ToolFailure)
    assert "404" in result


@pytest.mark.asyncio
async def test_list_pr_reviews_returns_ghost_when_login_is_null_and_authors_set():
    review = _review(4)
    review["user"] = {"login": None, "type": "User"}
    client = FakeClient({_REVIEWS: [review, _review(5)]})

    data = json.loads(await _run(client, authors=["ghost"]))

    assert [(r["id"], r["author"]) for r in data["reviews"]] == [(4, "ghost")]


@pytest.mark.asyncio
async def test_list_pr_reviews_counts_per_review_when_comments_span_two_pages():
    comments = [{"pull_request_review_id": 1}] * 70 + [
        {"pull_request_review_id": 2}
    ] * 50
    client = FakeClient({_REVIEWS: [_review(1), _review(2)], _COMMENTS: comments})

    rows = json.loads(await _run(client, include_inline_counts=True))["reviews"]

    assert [r["inline_comment_count"] for r in rows] == [70, 50]
    assert client.endpoints == [_REVIEWS, _COMMENTS, _COMMENTS]


@pytest.mark.asyncio
async def test_list_pr_reviews_fails_when_response_body_is_not_a_list():
    result = await _run(FakeClient({}, body={"message": "oops"}))

    assert isinstance(result, ToolFailure)
    assert "expected list" in result
    assert _REVIEWS in result


@pytest.mark.asyncio
async def test_list_pr_reviews_truncates_error_when_body_is_long():
    result = await _run(FakeClient({}, status=500, error_text="x" * 5000))

    assert isinstance(result, ToolFailure)
    assert "500" in result
    assert result.count("x") == 500
    assert result.endswith("…")


@pytest.mark.asyncio
async def test_list_pr_reviews_matches_commit_when_sha_prefix_is_uppercase():
    client = FakeClient({_REVIEWS: [_review(1), _review(2, commit="f" * 40)]})

    data = json.loads(await _run(client, commit_id=_SHA[:10].upper()))

    assert [r["id"] for r in data["reviews"]] == [1]


@pytest.mark.asyncio
async def test_list_pr_reviews_returns_all_rows_when_authors_blank():
    client = FakeClient({_REVIEWS: [_review(1), _review(2, "bob")]})

    data = json.loads(await _run(client, authors=["", "  "]))

    assert data["returned"] == 2


def test_never_offload_tools_is_only_list_pr_reviews():
    assert NEVER_OFFLOAD_TOOLS == frozenset({"github_list_pr_reviews"})


def test_should_offload_returns_false_when_tool_is_never_offload_and_result_large():
    limiter = MCPTokenLimiter(default_limit=100)
    offloader = ResponseOffloader(limiter)
    big = json.dumps({"reviews": [_review(i) for i in range(150)]})

    assert not offloader.should_offload(big, "github_list_pr_reviews")
    assert offloader.should_offload(big, "github_list_issues")


def test_process_result_returns_inline_when_never_offload_tool_is_large():
    from unittest.mock import MagicMock

    from mcp_server_git.lean.interface import GitLeanInterface

    iface = GitLeanInterface(MagicMock(), MagicMock(), MagicMock())
    iface.token_limiter.default_limit = 100
    big = json.dumps({"reviews": [_review(i) for i in range(150)]})

    assert iface._process_result(big, "github_list_pr_reviews") == big
    assert iface._process_result(big, "github_list_issues") != big
