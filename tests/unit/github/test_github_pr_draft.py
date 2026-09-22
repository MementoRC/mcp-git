"""
Unit tests for the draft PR toggle tools (GitHub issue #238).

A PR created via github_create_pr with draft=True could never be taken out
of draft: PATCH /pulls/{number} does not support the ``draft`` field on
GitHub's REST API. Clearing (or setting) the draft flag is GraphQL-only,
via ``markPullRequestReadyForReview`` / ``convertPullRequestToDraft``.

GraphQL's sharp edge is the one under test most carefully here: it returns
HTTP 200 even when the mutation failed, with the failure reported only in
a top-level ``errors`` array. A REST-shaped ``if status != 200`` check
would silently report success on a failed mutation.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp_server_git.github.client import GraphQLError
from src.mcp_server_git.github.pr_actions import (
    github_convert_pr_to_draft,
    github_mark_pr_ready,
)

PATCH_TARGET = "src.mcp_server_git.github.pr_actions.github_client_context"

_NODE_ID = "PR_kwDOAbC123xyz"


def _rest_response(pr_json: dict, status: int = 200) -> AsyncMock:
    response = AsyncMock()
    response.status = status
    response.json = AsyncMock(return_value=pr_json)
    response.text = AsyncMock(return_value="error")
    return response


def _pr_node_json(**overrides) -> dict:
    base = {"number": 238, "node_id": _NODE_ID}
    base.update(overrides)
    return base


def _client_with(get_response, graphql_result=None, graphql_side_effect=None):
    client = MagicMock()
    client.get = AsyncMock(return_value=get_response)
    if graphql_side_effect is not None:
        client.graphql = AsyncMock(side_effect=graphql_side_effect)
    else:
        client.graphql = AsyncMock(return_value=graphql_result)
    return client


@asynccontextmanager
async def _client_ctx(client):
    yield client


def _patch_client(client):
    return patch(PATCH_TARGET, return_value=_client_ctx(client))


class TestGitHubMarkPRReady:
    @pytest.mark.asyncio
    async def test_mark_ready_sends_node_id_from_rest_lookup_as_mutation_variable(
        self,
    ):
        """The node_id fetched via REST GET must reach the GraphQL mutation
        as the ``id`` variable — not just that some call was made."""
        client = _client_with(
            _rest_response(_pr_node_json()),
            graphql_result={
                "markPullRequestReadyForReview": {
                    "pullRequest": {
                        "number": 238,
                        "isDraft": False,
                        "url": "https://github.com/o/r/pull/238",
                    }
                }
            },
        )

        with _patch_client(client):
            await github_mark_pr_ready("o", "r", 238)

        client.graphql.assert_awaited_once()
        args, kwargs = client.graphql.call_args
        assert "markPullRequestReadyForReview" in args[0]
        assert kwargs["variables"] == {"id": _NODE_ID}

    @pytest.mark.asyncio
    async def test_mark_ready_returns_failure_when_graphql_reports_errors_with_http_200(
        self,
    ):
        """THE CRITICAL CASE: GraphQL returns HTTP 200 with a non-empty
        top-level ``errors`` array. The tool must return "❌ ", not treat
        the 200 status as success."""
        client = _client_with(
            _rest_response(_pr_node_json()),
            graphql_side_effect=GraphQLError(
                [{"message": "Pull request Merge Conflict: 238 is closed"}]
            ),
        )

        with _patch_client(client):
            result = await github_mark_pr_ready("o", "r", 238)

        assert result.startswith("❌ ")
        assert "✅" not in result

    @pytest.mark.asyncio
    async def test_mark_ready_success_returns_check_and_reflects_not_draft(self):
        client = _client_with(
            _rest_response(_pr_node_json()),
            graphql_result={
                "markPullRequestReadyForReview": {
                    "pullRequest": {
                        "number": 238,
                        "isDraft": False,
                        "url": "https://github.com/o/r/pull/238",
                    }
                }
            },
        )

        with _patch_client(client):
            result = await github_mark_pr_ready("o", "r", 238)

        assert result.startswith("✅ ")
        assert "238" in result
        assert "isDraft=False" in result

    @pytest.mark.asyncio
    async def test_mark_ready_returns_failure_naming_pr_when_node_id_lookup_fails(
        self,
    ):
        """A non-200 on the REST node_id lookup must return "❌ " naming
        the PR, and never reach the mutation."""
        client = _client_with(_rest_response({}, status=404))

        with _patch_client(client):
            result = await github_mark_pr_ready("o", "r", 238)

        assert result.startswith("❌ ")
        assert "238" in result
        client.graphql.assert_not_awaited()


class TestGitHubConvertPRToDraft:
    @pytest.mark.asyncio
    async def test_convert_to_draft_sends_mutation_and_reflects_is_draft_true(self):
        client = _client_with(
            _rest_response(_pr_node_json()),
            graphql_result={
                "convertPullRequestToDraft": {
                    "pullRequest": {
                        "number": 238,
                        "isDraft": True,
                        "url": "https://github.com/o/r/pull/238",
                    }
                }
            },
        )

        with _patch_client(client):
            result = await github_convert_pr_to_draft("o", "r", 238)

        args, kwargs = client.graphql.call_args
        assert "convertPullRequestToDraft" in args[0]
        assert kwargs["variables"] == {"id": _NODE_ID}
        assert result.startswith("✅ ")
        assert "isDraft=True" in result

    @pytest.mark.asyncio
    async def test_convert_to_draft_returns_failure_on_graphql_errors_with_http_200(
        self,
    ):
        client = _client_with(
            _rest_response(_pr_node_json()),
            graphql_side_effect=GraphQLError([{"message": "not authorized"}]),
        )

        with _patch_client(client):
            result = await github_convert_pr_to_draft("o", "r", 238)

        assert result.startswith("❌ ")
