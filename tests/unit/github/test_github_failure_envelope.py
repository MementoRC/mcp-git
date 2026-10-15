"""Failing GitHub PR, issue and release ops report status "error" (issue #271).

The HTTP client is mocked at the ``github_client_context`` boundary. Each op
must return a ToolFailure so the execute_tool envelope is not "success".
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_server_git.github.api import (
    github_delete_release,
    github_get_issue,
    github_get_pr_details,
)
from mcp_server_git.github.issue_search import github_bulk_update_issues
from mcp_server_git.lean.interface import GitLeanInterface
from mcp_server_git.utils.tool_failure import ToolFailure


class _MockService:
    def __getattr__(self, name: str):
        return lambda **kwargs: {"result": f"mock_{name}", "params": kwargs}


@pytest.fixture
def interface():
    return GitLeanInterface(
        git_service=_MockService(),
        github_service=_MockService(),
        azure_service=_MockService(),
    )


@pytest.fixture
def not_found_client():
    """Patch ``github_client_context`` in every module to yield a 404 client."""
    response = AsyncMock()
    response.status = 404
    response.text = AsyncMock(return_value="Not Found")
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    client.delete = AsyncMock(return_value=response)
    targets = [
        f"mcp_server_git.github.{module}.github_client_context"
        for module in ("pr", "issues", "releases")
    ]
    patches = [patch(target) for target in targets]
    for p in patches:
        p.start().return_value.__aenter__.return_value = client
    yield client
    for p in patches:
        p.stop()


@pytest.mark.asyncio
async def test_github_get_pr_details_returns_tool_failure_when_pr_is_404(
    not_found_client,
):
    result = await github_get_pr_details("owner", "repo", 999)

    assert isinstance(result, ToolFailure)
    assert result == "❌ Failed to get PR #999: 404"


@pytest.mark.asyncio
async def test_execute_tool_direct_returns_error_when_pr_details_is_404(
    not_found_client, interface
):
    envelope = await interface.execute_tool_direct(
        "github_get_pr_details",
        {"repo_owner": "owner", "repo_name": "repo", "pr_number": 999},
    )

    assert envelope["status"] == "error"
    assert envelope["error"].startswith("❌ Failed to get PR #999")


@pytest.mark.asyncio
async def test_github_get_issue_returns_tool_failure_when_issue_is_404(
    not_found_client,
):
    result = await github_get_issue("owner", "repo", 404)

    assert isinstance(result, ToolFailure)
    assert result.startswith("❌ Issue #404 not found in owner/repo")


@pytest.mark.asyncio
async def test_execute_tool_direct_returns_error_when_issue_is_404(
    not_found_client, interface
):
    envelope = await interface.execute_tool_direct(
        "github_get_issue",
        {"repo_owner": "owner", "repo_name": "repo", "issue_number": 404},
    )

    assert envelope["status"] == "error"
    assert envelope["error"].startswith("❌ Issue #404 not found")


def _patch_response(status: int, number: int = 0) -> AsyncMock:
    response = AsyncMock()
    response.status = status
    response.text = AsyncMock(return_value="Not Found")
    response.json = AsyncMock(
        return_value={"number": number, "html_url": f"https://x/{number}"}
    )
    return response


@pytest.mark.asyncio
async def test_github_bulk_update_issues_returns_tool_failure_when_every_update_fails():
    client = MagicMock()
    client.patch = AsyncMock(return_value=_patch_response(404))
    with patch("mcp_server_git.github.issues.github_client_context") as ctx:
        ctx.return_value.__aenter__.return_value = client
        result = await github_bulk_update_issues(
            "owner", "repo", [1, 2], labels=["bug"]
        )

    assert isinstance(result, ToolFailure)
    assert "❌ Failed: 2" in result


@pytest.mark.asyncio
async def test_github_bulk_update_issues_returns_plain_str_when_some_updates_succeed():
    client = MagicMock()
    client.patch = AsyncMock(
        side_effect=[_patch_response(200, 1), _patch_response(404)]
    )
    with patch("mcp_server_git.github.issues.github_client_context") as ctx:
        ctx.return_value.__aenter__.return_value = client
        result = await github_bulk_update_issues(
            "owner", "repo", [1, 2], labels=["bug"]
        )

    assert not isinstance(result, ToolFailure)
    assert "✅ Successful: 1" in result


@pytest.mark.asyncio
async def test_github_delete_release_returns_tool_failure_when_release_is_404(
    not_found_client,
):
    result = await github_delete_release("owner", "repo", 7)

    assert isinstance(result, ToolFailure)
    assert result == "❌ Release 7 not found in owner/repo"


@pytest.mark.asyncio
async def test_execute_tool_direct_returns_error_when_release_delete_is_404(
    not_found_client, interface
):
    envelope = await interface.execute_tool_direct(
        "github_delete_release",
        {"repo_owner": "owner", "repo_name": "repo", "release_id": 7},
    )

    assert envelope["status"] == "error"
    assert envelope["error"] == "❌ Release 7 not found in owner/repo"
