"""github_get_pr_reviews: rendering, pagination and filters (#355).

Only the HTTP/GraphQL boundary (``github_client_context``) is faked.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from mcp_server_git.github.pr_reviews import github_get_pr_reviews

from ._actions_fakes import FakeResponse
from ._thread_fakes import FakeGraphQL, comment, thread, threads_response

_FULL_MEDIA_TYPE = "application/vnd.github.full+json"
_REST = "/repos/owner/repo/pulls/1/comments"


class FakeReviewClient(FakeGraphQL):
    """REST pages by ``page`` param plus GraphQL routes; records REST calls."""

    def __init__(self, pages, routes=None, status=200):
        super().__init__(routes or {})
        self.pages = pages
        self.status = status
        self.gets = []

    async def get(self, endpoint, **kwargs):
        self.gets.append((endpoint, kwargs))
        if self.status != 200:
            return FakeResponse(self.status, text="boom")
        return FakeResponse(200, self.pages[kwargs["params"]["page"] - 1])


def _review_comment(**overrides) -> dict:
    base: dict = {
        "id": 1,
        "user": {"login": "bot"},
        "created_at": "2024-01-01T00:00:00Z",
        "body": "Plain comment",
        "body_text": "",
        "path": "src/foo.py",
        "line": 42,
        "in_reply_to_id": None,
        "diff_hunk": "",
    }
    base.update(overrides)
    return base


async def _run(client, **kwargs):
    with patch("mcp_server_git.github.pr_reviews.github_client_context") as ctx:
        ctx.return_value.__aenter__.return_value = client
        return await github_get_pr_reviews("owner", "repo", 1, **kwargs)


@pytest.mark.asyncio
async def test_get_pr_reviews_returns_rendered_body_text_when_body_contains_template_placeholder():
    comment_ = _review_comment(
        body="Suggestion:\n\n```yml\n${{ metadata.patch }}\n```",
        body_text="Suggestion:\n\n```yml\n- old: foo\n+ new: bar\n```",
    )

    result = await _run(FakeReviewClient([[comment_]]))

    assert "old: foo" in result
    assert "new: bar" in result
    assert "${{" not in result


@pytest.mark.asyncio
async def test_get_pr_reviews_keeps_markdown_body_when_no_template_placeholder():
    c = _review_comment(body="**Bold** comment with [link](http://x)")

    result = await _run(FakeReviewClient([[c]]))

    assert "**Bold**" in result


@pytest.mark.asyncio
async def test_get_pr_reviews_includes_diff_hunk_when_present():
    c = _review_comment(diff_hunk="@@ -1,3 +1,3 @@\n-old\n+new")

    result = await _run(FakeReviewClient([[c]]))

    assert "Diff hunk:" in result
    assert "-old" in result
    assert "+new" in result


@pytest.mark.asyncio
async def test_get_pr_reviews_omits_diff_hunk_when_empty():
    result = await _run(FakeReviewClient([[_review_comment(diff_hunk="")]]))

    assert "Diff hunk:" not in result


@pytest.mark.asyncio
async def test_get_pr_reviews_requests_full_media_type_in_a_single_call_when_one_page():
    client = FakeReviewClient([[_review_comment()]])

    await _run(client)

    assert len(client.gets) == 1
    assert client.gets[0][1]["accept"] == _FULL_MEDIA_TYPE


@pytest.mark.asyncio
async def test_get_pr_reviews_returns_no_comments_message_when_response_empty():
    result = await _run(FakeReviewClient([[]]))

    assert "No review comments" in result


@pytest.mark.asyncio
async def test_get_pr_reviews_fetches_every_page_when_first_page_full():
    full = [_review_comment(id=i) for i in range(100)]
    client = FakeReviewClient([full, [_review_comment(id=100)]])

    result = await _run(client)

    assert "(101 total)" in result
    assert [g[1]["params"]["page"] for g in client.gets] == [1, 2]


@pytest.mark.asyncio
async def test_get_pr_reviews_fails_when_http_status_not_ok():
    result = await _run(FakeReviewClient([], status=404))

    assert result.startswith("❌ Failed to fetch review comments: 404")


@pytest.mark.asyncio
async def test_get_pr_reviews_keeps_only_requested_when_comment_ids_given():
    client = FakeReviewClient([[_review_comment(id=1), _review_comment(id=2)]])

    result = await _run(client, comment_ids=[2])

    assert "(1 total)" in result
    assert client.calls == []


@pytest.mark.asyncio
async def test_get_pr_reviews_drops_resolved_threads_when_unresolved_only():
    threads = [
        thread("T1", [comment(1), comment(2)], resolved=True),
        thread("T2", [comment(3)]),
    ]
    client = FakeReviewClient(
        [[_review_comment(id=i, body=f"body-{i}") for i in (1, 2, 3)]],
        {"reviewThreads(": threads_response(threads)},
    )

    result = await _run(client, unresolved_only=True)

    assert "(1 total)" in result
    assert "body-3" in result
    assert "body-1" not in result


@pytest.mark.asyncio
async def test_get_pr_reviews_reads_extra_thread_comments_when_thread_has_many():
    big = thread("T1", [comment(1)])
    big["comments"]["pageInfo"] = {"hasNextPage": True, "endCursor": "k"}
    more = {
        "node": {
            "comments": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [comment(2)],
            }
        }
    }
    client = FakeReviewClient(
        [[_review_comment(id=2)]],
        {"reviewThreads(": threads_response([big]), "node(id": more},
    )

    result = await _run(client, unresolved_only=True)

    assert "(1 total)" in result
