"""
Unit tests for github_get_pr_comments and github_get_pr_reviews functions.

Tests bot-template placeholder expansion via rendered body_text and diff_hunk
inclusion in review comment output.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp_server_git.github.pr_actions import (
    github_get_pr_comments,
    github_get_pr_reviews,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FULL_MEDIA_TYPE = "application/vnd.github.full+json"


def _make_client(get_return):
    client = MagicMock()
    client.get = AsyncMock(return_value=get_return)
    return client


@asynccontextmanager
async def _client_ctx(client):
    yield client


def _patch_client(client):
    return patch(
        "src.mcp_server_git.github.pr_actions.github_client_context",
        return_value=_client_ctx(client),
    )


def _make_response(data: list, status: int = 200):
    response = MagicMock()
    response.status = status
    response.json = AsyncMock(return_value=data)
    response.text = AsyncMock(return_value="error")
    return response


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


def _issue_comment(**overrides) -> dict:
    base: dict = {
        "id": 1,
        "user": {"login": "bot"},
        "created_at": "2024-01-01T00:00:00Z",
        "body": "Plain comment",
        "body_text": "",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# github_get_pr_reviews tests
# ---------------------------------------------------------------------------


class TestGitHubGetPrReviews:
    @pytest.mark.asyncio
    async def test_get_pr_reviews_returns_rendered_body_text_when_body_contains_template_placeholder(
        self,
    ):
        """body_text is used when body contains ${{ template syntax }}."""
        comment = _review_comment(
            body="Suggestion:\n\n```yml\n${{ metadata.patch }}\n```",
            body_text="Suggestion:\n\n```yml\n- old: foo\n+ new: bar\n```",
        )
        client = _make_client(_make_response([comment]))

        with _patch_client(client):
            result = await github_get_pr_reviews("owner", "repo", 1)

        assert "old: foo" in result
        assert "new: bar" in result
        assert "${{" not in result

    @pytest.mark.asyncio
    async def test_get_pr_reviews_keeps_markdown_body_when_no_template_placeholder(
        self,
    ):
        """Markdown body is preserved when no template placeholders present."""
        comment = _review_comment(body="**Bold** comment with [link](http://x)")
        client = _make_client(_make_response([comment]))

        with _patch_client(client):
            result = await github_get_pr_reviews("owner", "repo", 1)

        assert "**Bold**" in result

    @pytest.mark.asyncio
    async def test_get_pr_reviews_includes_diff_hunk_when_present(self):
        """Diff hunk block is appended to output when diff_hunk is non-empty."""
        hunk = "@@ -1,3 +1,3 @@\n-old\n+new"
        comment = _review_comment(diff_hunk=hunk)
        client = _make_client(_make_response([comment]))

        with _patch_client(client):
            result = await github_get_pr_reviews("owner", "repo", 1)

        assert "Diff hunk:" in result
        assert "-old" in result
        assert "+new" in result

    @pytest.mark.asyncio
    async def test_get_pr_reviews_omits_diff_hunk_when_empty(self):
        """Diff hunk block is absent when diff_hunk is empty."""
        comment = _review_comment(diff_hunk="")
        client = _make_client(_make_response([comment]))

        with _patch_client(client):
            result = await github_get_pr_reviews("owner", "repo", 1)

        assert "Diff hunk:" not in result

    @pytest.mark.asyncio
    async def test_get_pr_reviews_requests_full_media_type(self):
        """client.get is called with accept=application/vnd.github.full+json."""
        comment = _review_comment()
        client = _make_client(_make_response([comment]))

        with _patch_client(client):
            await github_get_pr_reviews("owner", "repo", 1)

        client.get.assert_awaited_once()
        _, kwargs = client.get.call_args
        assert kwargs.get("accept") == _FULL_MEDIA_TYPE

    @pytest.mark.asyncio
    async def test_get_pr_reviews_handles_empty_response_returns_no_comments_message(
        self,
    ):
        """Empty list from API returns a 'no review comments' message."""
        client = _make_client(_make_response([]))

        with _patch_client(client):
            result = await github_get_pr_reviews("owner", "repo", 1)

        assert "No review comments" in result


# ---------------------------------------------------------------------------
# github_get_pr_comments tests
# ---------------------------------------------------------------------------


class TestGitHubGetPrComments:
    @pytest.mark.asyncio
    async def test_get_pr_comments_returns_rendered_body_text_when_body_contains_template_placeholder(
        self,
    ):
        """body_text is used when body contains ${{ template syntax }}."""
        comment = _issue_comment(
            body="Suggestion:\n\n```yml\n${{ metadata.patch }}\n```",
            body_text="Suggestion:\n\n```yml\n- old: foo\n+ new: bar\n```",
        )
        client = _make_client(_make_response([comment]))

        with _patch_client(client):
            result = await github_get_pr_comments("owner", "repo", 1)

        assert "old: foo" in result
        assert "new: bar" in result
        assert "${{" not in result

    @pytest.mark.asyncio
    async def test_get_pr_comments_requests_full_media_type(self):
        """client.get is called with accept=application/vnd.github.full+json."""
        comment = _issue_comment()
        client = _make_client(_make_response([comment]))

        with _patch_client(client):
            await github_get_pr_comments("owner", "repo", 1)

        client.get.assert_awaited_once()
        _, kwargs = client.get.call_args
        assert kwargs.get("accept") == _FULL_MEDIA_TYPE
