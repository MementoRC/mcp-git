"""
Unit tests for the github_get_pr_comments function.

Tests bot-template placeholder expansion via rendered body_text.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_server_git.github.pr_actions import github_get_pr_comments

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
        "mcp_server_git.github.pr_actions.github_client_context",
        return_value=_client_ctx(client),
    )


def _make_response(data: list, status: int = 200):
    response = MagicMock()
    response.status = status
    response.json = AsyncMock(return_value=data)
    response.text = AsyncMock(return_value="error")
    return response


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
