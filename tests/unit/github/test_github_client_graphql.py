"""
Direct unit tests for GitHubClient.graphql() (issue #238).

Every existing GraphQL-mutation test (test_github_pr_draft.py, etc.) mocks
``client.graphql`` itself to raise GraphQLError. That exercises how callers
handle the error but never exercises graphql()'s own error-detection logic.
If graphql() were rewritten to check only ``response.status`` and return
``result["data"]`` without ever inspecting the top-level ``errors`` array,
every one of those caller tests would still pass — yet that is exactly the
defect the method exists to prevent, since GitHub's GraphQL endpoint returns
HTTP 200 even for failed operations. These tests pin graphql() itself
against a fake aiohttp session so that regression cannot slip through.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.mcp_server_git.github.client import GitHubClient, GraphQLError

_VALID_TOKEN = "ghp_" + "a" * 36


def _response(
    json_body: dict, status: int = 200, text_body: str = "error"
) -> AsyncMock:
    response = AsyncMock()
    response.status = status
    response.json = AsyncMock(return_value=json_body)
    response.text = AsyncMock(return_value=text_body)
    return response


def _client_with(response: AsyncMock) -> tuple[GitHubClient, MagicMock]:
    session = MagicMock()
    session.post = AsyncMock(return_value=response)
    client = GitHubClient(token=_VALID_TOKEN, session=session)
    return client, session


class TestGitHubClientGraphql:
    @pytest.mark.asyncio
    async def test_graphql_raises_graphql_error_when_http_200_has_nonempty_errors(
        self,
    ):
        """THE CENTRAL CASE: HTTP 200 with a non-empty top-level ``errors``
        array must raise, carrying the message text so a caller can report
        why."""
        response = _response(
            {"data": None, "errors": [{"message": "Pull request is closed"}]}
        )
        client, _session = _client_with(response)

        with pytest.raises(GraphQLError) as exc_info:
            await client.graphql("mutation { foo }")

        assert "Pull request is closed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_graphql_returns_data_when_http_200_has_no_errors_key(self):
        """No ``errors`` key at all returns the ``data`` object."""
        response = _response({"data": {"foo": "bar"}})
        client, _session = _client_with(response)

        result = await client.graphql("query { foo }")

        assert result == {"foo": "bar"}

    @pytest.mark.asyncio
    async def test_graphql_returns_data_when_errors_key_present_but_empty(self):
        """An ``errors`` key present but an EMPTY array is falsy and must
        NOT raise — pins that the check is on emptiness, not key
        presence."""
        response = _response({"data": {"foo": "bar"}, "errors": []})
        client, _session = _client_with(response)

        result = await client.graphql("query { foo }")

        assert result == {"foo": "bar"}

    @pytest.mark.asyncio
    async def test_graphql_raises_graphql_error_when_http_status_is_not_200(self):
        """A non-200 response raises GraphQLError including the status
        code."""
        response = _response({}, status=500, text_body="internal error")
        client, _session = _client_with(response)

        with pytest.raises(GraphQLError) as exc_info:
            await client.graphql("query { foo }")

        assert "500" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_graphql_sends_query_and_variables_as_graphql_variables(self):
        """The request sent contains the query and, when ``variables`` is
        passed, a ``variables`` key carrying them — not interpolated into
        the query string."""
        response = _response({"data": {"ok": True}})
        client, session = _client_with(response)

        await client.graphql(
            "mutation($id: ID!) { foo(id: $id) }", variables={"id": "PR_1"}
        )

        _args, kwargs = session.post.call_args
        payload = kwargs["json"]
        assert payload["query"] == "mutation($id: ID!) { foo(id: $id) }"
        assert payload["variables"] == {"id": "PR_1"}

    @pytest.mark.asyncio
    async def test_graphql_omits_variables_key_when_variables_is_none(self):
        """``variables=None`` omits the ``variables`` key from the payload
        entirely."""
        response = _response({"data": {"ok": True}})
        client, session = _client_with(response)

        await client.graphql("query { foo }")

        _args, kwargs = session.post.call_args
        payload = kwargs["json"]
        assert "variables" not in payload
