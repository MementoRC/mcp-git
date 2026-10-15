"""Failing GitHub security, permissions and scanning ops report status "error" (issue #271).

The HTTP client is mocked at the ``github_client_context`` boundary. An op that
fails returns a ToolFailure; a report that ran and lists ❌ status lines stays
a plain str.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_server_git.github._failures import http_failure
from mcp_server_git.github.check_markers import enabled_line
from mcp_server_git.github.permissions import (
    github_get_actions_permissions,
    github_get_branch_protection,
    github_update_actions_permissions,
)
from mcp_server_git.github.scanning import (
    github_get_ruleset,
    github_list_rulesets,
)
from mcp_server_git.github.security import (
    github_get_required_signatures,
    github_get_security_analysis,
    github_get_vulnerability_alerts,
)
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


def _response(status: int, body: object = None, text: str = "Not Found") -> AsyncMock:
    response = AsyncMock()
    response.status = status
    response.text = AsyncMock(return_value=text)
    response.json = AsyncMock(return_value=body if body is not None else {})
    return response


@pytest.fixture
def github_client():
    """Patch ``github_client_context`` in the part-4 modules to yield one client."""
    client = MagicMock()
    client.get = AsyncMock(return_value=_response(404))
    patches = [
        patch(f"mcp_server_git.github.{module}.github_client_context")
        for module in ("security", "permissions", "scanning")
    ]
    for p in patches:
        p.start().return_value.__aenter__.return_value = client
    yield client
    for p in patches:
        p.stop()


# --- security -------------------------------------------------------------


@pytest.mark.asyncio
async def test_github_get_required_signatures_returns_tool_failure_when_branch_is_404(
    github_client,
):
    result = await github_get_required_signatures("owner", "repo", "main")

    assert isinstance(result, ToolFailure)
    assert result == "❌ Branch protection or branch not found: owner/repo#main"


@pytest.mark.asyncio
async def test_github_get_vulnerability_alerts_returns_tool_failure_when_server_errors(
    github_client,
):
    github_client.get.return_value = _response(500, text="boom")

    result = await github_get_vulnerability_alerts("owner", "repo")

    assert isinstance(result, ToolFailure)
    assert result == "❌ Failed to check vulnerability alerts: 500 - boom"


@pytest.mark.asyncio
async def test_github_get_vulnerability_alerts_returns_plain_str_when_alerts_disabled(
    github_client,
):
    result = await github_get_vulnerability_alerts("owner", "repo")

    assert not isinstance(result, ToolFailure)
    assert result == "❌ Vulnerability alerts (Dependabot) are DISABLED for owner/repo"


@pytest.mark.asyncio
async def test_github_get_security_analysis_returns_plain_str_when_features_disabled(
    github_client,
):
    github_client.get.side_effect = [
        _response(404),
        _response(404),
        _response(200, {"visibility": "public", "security_and_analysis": {"x": {}}}),
    ]

    result = await github_get_security_analysis("owner", "repo")

    assert not isinstance(result, ToolFailure)
    assert "❌ Vulnerability Alerts (Dependabot): DISABLED" in result
    assert "   ❌ Secret Scanning: DISABLED" in result


@pytest.mark.asyncio
async def test_execute_tool_direct_returns_error_when_required_signatures_is_404(
    github_client, interface
):
    envelope = await interface.execute_tool_direct(
        "github_get_required_signatures",
        {"repo_owner": "owner", "repo_name": "repo", "branch": "main"},
    )

    assert envelope["status"] == "error"
    assert envelope["error"].startswith("❌ Branch protection or branch not found")


@pytest.mark.asyncio
async def test_execute_tool_direct_returns_success_when_vulnerability_alerts_disabled(
    github_client, interface
):
    envelope = await interface.execute_tool_direct(
        "github_get_vulnerability_alerts",
        {"repo_owner": "owner", "repo_name": "repo"},
    )

    assert envelope["status"] == "success"


# --- permissions ----------------------------------------------------------


@pytest.mark.asyncio
async def test_github_get_actions_permissions_returns_tool_failure_when_repo_is_404(
    github_client,
):
    result = await github_get_actions_permissions("owner", "repo")

    assert isinstance(result, ToolFailure)
    assert result == "❌ Repository owner/repo not found or Actions not enabled"


@pytest.mark.asyncio
async def test_github_update_actions_permissions_returns_tool_failure_when_input_invalid(
    github_client,
):
    result = await github_update_actions_permissions(
        "owner", "repo", allowed_actions="nope"
    )

    assert isinstance(result, ToolFailure)
    assert result.startswith("❌ allowed_actions must be")


@pytest.mark.asyncio
async def test_github_get_branch_protection_returns_tool_failure_when_branch_is_404(
    github_client,
):
    result = await github_get_branch_protection("owner", "repo", "main")

    assert isinstance(result, ToolFailure)
    assert result.startswith("❌ Branch protection not found for main.")


@pytest.mark.asyncio
async def test_github_get_branch_protection_returns_plain_str_when_rules_unconfigured(
    github_client,
):
    github_client.get.return_value = _response(200, {})

    result = await github_get_branch_protection("owner", "repo", "main")

    assert not isinstance(result, ToolFailure)
    assert "❌ Required Status Checks: Not configured" in result
    assert "\n❌ Required Pull Request Reviews: Not configured" in result


@pytest.mark.asyncio
async def test_execute_tool_direct_returns_error_when_branch_protection_is_404(
    github_client, interface
):
    envelope = await interface.execute_tool_direct(
        "github_get_branch_protection",
        {"repo_owner": "owner", "repo_name": "repo", "branch": "main"},
    )

    assert envelope["status"] == "error"
    assert envelope["error"].startswith("❌ Branch protection not found for main")


# --- scanning -------------------------------------------------------------


@pytest.mark.asyncio
async def test_github_list_rulesets_returns_tool_failure_when_repo_is_404(
    github_client,
):
    result = await github_list_rulesets("owner", "repo")

    assert isinstance(result, ToolFailure)
    assert result == "❌ Repository not found: owner/repo"


@pytest.mark.asyncio
async def test_github_get_ruleset_returns_tool_failure_when_access_is_forbidden(
    github_client,
):
    github_client.get.return_value = _response(403, text="Forbidden")

    result = await github_get_ruleset("owner", "repo", 7)

    assert isinstance(result, ToolFailure)
    assert result == "❌ Failed to get ruleset: 403 - Forbidden"


@pytest.mark.asyncio
async def test_github_list_rulesets_returns_payload_when_repo_has_rulesets(
    github_client,
):
    github_client.get.return_value = _response(200, [{"id": 1}])

    result = await github_list_rulesets("owner", "repo")

    assert result == [{"id": 1}]


@pytest.mark.asyncio
async def test_execute_tool_direct_returns_error_when_ruleset_access_is_forbidden(
    github_client, interface
):
    github_client.get.return_value = _response(403, text="Forbidden")

    envelope = await interface.execute_tool_direct(
        "github_get_ruleset",
        {"repo_owner": "owner", "repo_name": "repo", "ruleset_id": 7},
    )

    assert envelope["status"] == "error"
    assert envelope["error"] == "❌ Failed to get ruleset: 403 - Forbidden"


# --- shared helpers -------------------------------------------------------


@pytest.mark.asyncio
async def test_http_failure_returns_tool_failure_when_response_has_body():
    result = await http_failure("do thing", _response(502, text="bad gateway"))

    assert isinstance(result, ToolFailure)
    assert result == "❌ Failed to do thing: 502 - bad gateway"


@pytest.mark.parametrize(
    ("enabled", "expected"),
    [(True, "   ✅ Feature: ENABLED"), (False, "   ❌ Feature: DISABLED")],
)
def test_enabled_line_returns_marker_and_state_when_flag_given(enabled, expected):
    assert enabled_line("Feature", enabled, "   ") == expected
