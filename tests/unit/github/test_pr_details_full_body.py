"""full_body option and head SHA on github_get_pr_details (issue #320)."""

from unittest.mock import patch

import pytest

from mcp_server_git.github.models import GitHubGetPRDetails
from mcp_server_git.github.pr import github_get_pr_details

PR_CTX = "mcp_server_git.github.pr.github_client_context"
LONG_BODY = "line\n" * 200  # 1000 chars, well past the preview cut


class _Response:
    status = 200

    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


class _Client:
    def __init__(self, payload):
        self._payload = payload

    async def get(self, endpoint, **kwargs):
        return _Response(self._payload)


class _Context:
    def __init__(self, payload):
        self._client = _Client(payload)

    async def __aenter__(self):
        return self._client

    async def __aexit__(self, *args):
        return None


async def _details(payload, **kwargs):
    with patch(PR_CTX, return_value=_Context(payload)):
        return await github_get_pr_details("o", "r", 5, **kwargs)


@pytest.mark.asyncio
async def test_get_pr_details_returns_whole_body_when_full_body_set():
    result = await _details({"body": LONG_BODY}, full_body=True)
    assert result.endswith(f"\nDescription:\n{LONG_BODY}")
    assert "..." not in result


@pytest.mark.asyncio
async def test_get_pr_details_truncates_body_when_full_body_not_set():
    result = await _details({"body": LONG_BODY})
    assert LONG_BODY not in result
    assert result.endswith("...")


@pytest.mark.asyncio
async def test_get_pr_details_returns_head_sha_when_head_has_sha():
    result = await _details({"head": {"ref": "feat", "sha": "abc123def"}})
    assert "Head: feat\nHead SHA: abc123def\n" in result


@pytest.mark.asyncio
async def test_get_pr_details_omits_head_sha_when_head_missing():
    result = await _details({})
    assert "Head SHA" not in result


def test_pr_details_schema_advertises_full_body_when_model_serialized():
    prop = GitHubGetPRDetails.model_json_schema()["properties"]["full_body"]
    assert prop["default"] is False
    assert prop["type"] == "boolean"
