"""
Unit tests for GitHub GHAS forensics functions (Issue #186).

Covers 7 read-only tools:
  Rulesets:       github_list_rulesets, github_get_ruleset, github_get_branch_rules
  Code scanning:  github_list_code_scanning_alerts, github_list_code_scanning_analyses,
                  github_get_code_scanning_default_setup
  Secret scanning: github_list_secret_scanning_alerts
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp_server_git.github.api import (
    github_get_branch_rules,
    github_get_code_scanning_default_setup,
    github_get_ruleset,
    github_list_code_scanning_alerts,
    github_list_code_scanning_analyses,
    github_list_rulesets,
    github_list_secret_scanning_alerts,
)

_OWNER = "myorg"
_REPO = "myrepo"

_PATCH_CTX = "src.mcp_server_git.github.scanning.github_client_context"


def _mock_client(method: str, status: int, json_body=None, text_body: str = ""):
    """Create a mock HTTP client returning the given status and body."""
    mock_response = AsyncMock()
    mock_response.status = status
    if json_body is not None:
        mock_response.json = AsyncMock(return_value=json_body)
    mock_response.text = AsyncMock(return_value=text_body)

    mock_client = MagicMock()
    setattr(mock_client, method, AsyncMock(return_value=mock_response))
    return mock_client, mock_response


# ===========================================================================
# github_list_rulesets
# ===========================================================================


class TestGithubListRulesets:
    """Tests for github_list_rulesets."""

    @pytest.mark.asyncio
    async def test_list_rulesets_returns_list_when_status_200(self):
        """GET 200 returns the JSON list of rulesets."""
        rulesets = [{"id": 1, "name": "default"}]
        mock_client, _ = _mock_client("get", 200, json_body=rulesets)

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            result = await github_list_rulesets(
                repo_owner=_OWNER, repo_name=_REPO
            )

        assert result == rulesets
        mock_client.get.assert_called_once_with(
            f"/repos/{_OWNER}/{_REPO}/rulesets",
            params=None,
        )

    @pytest.mark.asyncio
    async def test_list_rulesets_returns_not_found_when_status_404(self):
        """GET 404 returns a structured not-found string."""
        mock_client, _ = _mock_client("get", 404, text_body="Not Found")

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            result = await github_list_rulesets(
                repo_owner=_OWNER, repo_name=_REPO
            )

        assert "❌" in result
        assert "not found" in result.lower()
        assert f"{_OWNER}/{_REPO}" in result

    @pytest.mark.asyncio
    async def test_list_rulesets_forwards_pagination_params(self):
        """per_page and page are forwarded as query params when set."""
        mock_client, _ = _mock_client("get", 200, json_body=[])

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            await github_list_rulesets(
                repo_owner=_OWNER, repo_name=_REPO, per_page=50, page=2
            )

        params = mock_client.get.call_args.kwargs["params"]
        assert params["per_page"] == "50"
        assert params["page"] == "2"

    @pytest.mark.asyncio
    async def test_list_rulesets_omits_none_pagination(self):
        """None per_page/page must not appear in params."""
        mock_client, _ = _mock_client("get", 200, json_body=[])

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            await github_list_rulesets(
                repo_owner=_OWNER, repo_name=_REPO, per_page=None, page=None
            )

        params = mock_client.get.call_args.kwargs["params"]
        assert params is None

    @pytest.mark.asyncio
    async def test_list_rulesets_returns_error_when_status_403(self):
        """GET 403 (insufficient security_events scope) returns an error string."""
        mock_client, _ = _mock_client("get", 403, text_body="Forbidden")

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            result = await github_list_rulesets(repo_owner=_OWNER, repo_name=_REPO)

        assert "❌" in result
        assert "403" in result

    @pytest.mark.asyncio
    async def test_list_rulesets_returns_error_on_connection_exception(self):
        """A ConnectionError raised by the client returns a network-error string."""
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=ConnectionError("timeout"))

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            result = await github_list_rulesets(repo_owner=_OWNER, repo_name=_REPO)

        assert "❌" in result
        assert "Network connection failed" in result


# ===========================================================================
# github_get_ruleset
# ===========================================================================


class TestGithubGetRuleset:
    """Tests for github_get_ruleset."""

    @pytest.mark.asyncio
    async def test_get_ruleset_returns_dict_when_status_200(self):
        """GET 200 returns the full ruleset dict."""
        ruleset = {"id": 42, "name": "ci-required", "rules": []}
        mock_client, _ = _mock_client("get", 200, json_body=ruleset)

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            result = await github_get_ruleset(
                repo_owner=_OWNER, repo_name=_REPO, ruleset_id=42
            )

        assert result == ruleset
        mock_client.get.assert_called_once_with(
            f"/repos/{_OWNER}/{_REPO}/rulesets/42"
        )

    @pytest.mark.asyncio
    async def test_get_ruleset_returns_not_found_when_status_404(self):
        """GET 404 returns a structured not-found string containing the ruleset ID."""
        mock_client, _ = _mock_client("get", 404, text_body="Not Found")

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            result = await github_get_ruleset(
                repo_owner=_OWNER, repo_name=_REPO, ruleset_id=42
            )

        assert "❌" in result
        assert "42" in result
        assert f"{_OWNER}/{_REPO}" in result

    @pytest.mark.asyncio
    async def test_get_ruleset_returns_error_when_status_403(self):
        """GET 403 (insufficient security_events scope) returns an error string."""
        mock_client, _ = _mock_client("get", 403, text_body="Forbidden")

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            result = await github_get_ruleset(
                repo_owner=_OWNER, repo_name=_REPO, ruleset_id=42
            )

        assert "❌" in result
        assert "403" in result

    @pytest.mark.asyncio
    async def test_get_ruleset_returns_error_on_value_error(self):
        """A ValueError raised by the client returns an error string."""
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=ValueError("Auth error"))

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            result = await github_get_ruleset(
                repo_owner=_OWNER, repo_name=_REPO, ruleset_id=1
            )

        assert "❌" in result

    @pytest.mark.asyncio
    async def test_get_ruleset_returns_error_on_connection_error(self):
        """A ConnectionError raised by the client returns a network-error string."""
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=ConnectionError("Network error"))

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            result = await github_get_ruleset(
                repo_owner=_OWNER, repo_name=_REPO, ruleset_id=1
            )

        assert "❌" in result


# ===========================================================================
# github_get_branch_rules
# ===========================================================================


class TestGithubGetBranchRules:
    """Tests for github_get_branch_rules."""

    @pytest.mark.asyncio
    async def test_get_branch_rules_returns_list_when_status_200(self):
        """GET 200 returns the list of rules for the branch."""
        rules = [{"type": "required_signatures"}, {"type": "code_scanning"}]
        mock_client, _ = _mock_client("get", 200, json_body=rules)

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            result = await github_get_branch_rules(
                repo_owner=_OWNER, repo_name=_REPO, branch="main"
            )

        assert result == rules
        mock_client.get.assert_called_once_with(
            f"/repos/{_OWNER}/{_REPO}/rules/branches/main"
        )

    @pytest.mark.asyncio
    async def test_get_branch_rules_returns_not_found_when_status_404(self):
        """GET 404 returns a not-found string mentioning branch and repo."""
        mock_client, _ = _mock_client("get", 404, text_body="Not Found")

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            result = await github_get_branch_rules(
                repo_owner=_OWNER, repo_name=_REPO, branch="main"
            )

        assert "❌" in result
        assert f"{_OWNER}/{_REPO}#main" in result

    @pytest.mark.asyncio
    async def test_get_branch_rules_returns_error_when_status_403(self):
        """GET 403 (insufficient security_events scope) returns an error string."""
        mock_client, _ = _mock_client("get", 403, text_body="Forbidden")

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            result = await github_get_branch_rules(
                repo_owner=_OWNER, repo_name=_REPO, branch="main"
            )

        assert "❌" in result
        assert "403" in result

    @pytest.mark.asyncio
    async def test_get_branch_rules_returns_error_on_value_error(self):
        """A ValueError raised by the client returns an error string."""
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=ValueError("Auth error"))

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            result = await github_get_branch_rules(
                repo_owner=_OWNER, repo_name=_REPO, branch="main"
            )

        assert "❌" in result

    @pytest.mark.asyncio
    async def test_get_branch_rules_returns_error_on_connection_error(self):
        """A ConnectionError raised by the client returns a network-error string."""
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=ConnectionError("Network error"))

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            result = await github_get_branch_rules(
                repo_owner=_OWNER, repo_name=_REPO, branch="main"
            )

        assert "❌" in result


# ===========================================================================
# github_list_code_scanning_alerts
# ===========================================================================


class TestGithubListCodeScanningAlerts:
    """Tests for github_list_code_scanning_alerts."""

    @pytest.mark.asyncio
    async def test_list_alerts_returns_list_when_status_200(self):
        """GET 200 returns the alert list."""
        alerts = [{"number": 1, "state": "open", "rule": {"severity": "critical"}}]
        mock_client, _ = _mock_client("get", 200, json_body=alerts)

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            result = await github_list_code_scanning_alerts(
                repo_owner=_OWNER, repo_name=_REPO
            )

        assert result == alerts
        mock_client.get.assert_called_once_with(
            f"/repos/{_OWNER}/{_REPO}/code-scanning/alerts",
            params=None,
        )

    @pytest.mark.asyncio
    async def test_list_alerts_passes_filters_as_query_params(self):
        """Provided filter args are forwarded as query params; None args are omitted."""
        mock_client, _ = _mock_client("get", 200, json_body=[])

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            await github_list_code_scanning_alerts(
                repo_owner=_OWNER,
                repo_name=_REPO,
                state="open",
                severity="critical",
                tool_name="CodeQL",
                ref="refs/pull/207/head",
            )

        params = mock_client.get.call_args.kwargs["params"]
        assert params["state"] == "open"
        assert params["severity"] == "critical"
        assert params["tool_name"] == "CodeQL"
        assert params["ref"] == "refs/pull/207/head"

    @pytest.mark.asyncio
    async def test_list_alerts_omits_none_filters(self):
        """None filter args must NOT appear in query params."""
        mock_client, _ = _mock_client("get", 200, json_body=[])

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            await github_list_code_scanning_alerts(
                repo_owner=_OWNER,
                repo_name=_REPO,
                state="open",
                severity=None,
                tool_name=None,
                ref=None,
            )

        params = mock_client.get.call_args.kwargs["params"]
        assert "severity" not in params
        assert "tool_name" not in params
        assert "ref" not in params

    @pytest.mark.asyncio
    async def test_list_alerts_returns_not_found_when_status_404(self):
        """GET 404 returns a not-found/not-enabled string."""
        mock_client, _ = _mock_client("get", 404, text_body="Not Found")

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            result = await github_list_code_scanning_alerts(
                repo_owner=_OWNER, repo_name=_REPO
            )

        assert "❌" in result
        assert f"{_OWNER}/{_REPO}" in result

    @pytest.mark.asyncio
    async def test_list_alerts_forwards_pagination_params(self):
        """per_page and page are forwarded as query params when set."""
        mock_client, _ = _mock_client("get", 200, json_body=[])

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            await github_list_code_scanning_alerts(
                repo_owner=_OWNER, repo_name=_REPO, per_page=100, page=3
            )

        params = mock_client.get.call_args.kwargs["params"]
        assert params["per_page"] == "100"
        assert params["page"] == "3"

    @pytest.mark.asyncio
    async def test_list_alerts_returns_error_when_status_403(self):
        """GET 403 (insufficient security_events scope) returns an error string."""
        mock_client, _ = _mock_client("get", 403, text_body="Forbidden")

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            result = await github_list_code_scanning_alerts(
                repo_owner=_OWNER, repo_name=_REPO
            )

        assert "❌" in result
        assert "403" in result

    @pytest.mark.asyncio
    async def test_list_alerts_returns_error_on_exception(self):
        """An unexpected exception raised by the client returns an error string."""
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=RuntimeError("unexpected"))

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            result = await github_list_code_scanning_alerts(
                repo_owner=_OWNER, repo_name=_REPO
            )

        assert "❌" in result
        assert "Error listing code scanning alerts" in result


# ===========================================================================
# github_list_code_scanning_analyses
# ===========================================================================


class TestGithubListCodeScanningAnalyses:
    """Tests for github_list_code_scanning_analyses."""

    @pytest.mark.asyncio
    async def test_list_analyses_returns_list_when_status_200(self):
        """GET 200 returns the analysis list."""
        analyses = [{"id": 1, "ref": "refs/heads/main", "tool": {"name": "CodeQL"}}]
        mock_client, _ = _mock_client("get", 200, json_body=analyses)

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            result = await github_list_code_scanning_analyses(
                repo_owner=_OWNER, repo_name=_REPO
            )

        assert result == analyses
        mock_client.get.assert_called_once_with(
            f"/repos/{_OWNER}/{_REPO}/code-scanning/analyses",
            params=None,
        )

    @pytest.mark.asyncio
    async def test_list_analyses_passes_filters_as_query_params(self):
        """ref and tool_name are forwarded; None values omitted."""
        mock_client, _ = _mock_client("get", 200, json_body=[])

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            await github_list_code_scanning_analyses(
                repo_owner=_OWNER,
                repo_name=_REPO,
                ref="refs/pull/207/head",
                tool_name="CodeQL",
            )

        params = mock_client.get.call_args.kwargs["params"]
        assert params["ref"] == "refs/pull/207/head"
        assert params["tool_name"] == "CodeQL"

    @pytest.mark.asyncio
    async def test_list_analyses_omits_none_filters(self):
        """None ref and tool_name must not appear in params."""
        mock_client, _ = _mock_client("get", 200, json_body=[])

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            await github_list_code_scanning_analyses(
                repo_owner=_OWNER,
                repo_name=_REPO,
                ref=None,
                tool_name=None,
            )

        params = mock_client.get.call_args.kwargs["params"]
        assert params is None

    @pytest.mark.asyncio
    async def test_list_analyses_returns_not_found_when_status_404(self):
        """GET 404 returns a not-found/not-enabled string."""
        mock_client, _ = _mock_client("get", 404, text_body="Not Found")

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            result = await github_list_code_scanning_analyses(
                repo_owner=_OWNER, repo_name=_REPO
            )

        assert "❌" in result
        assert f"{_OWNER}/{_REPO}" in result

    @pytest.mark.asyncio
    async def test_list_analyses_forwards_pagination_params(self):
        """per_page and page are forwarded as query params when set."""
        mock_client, _ = _mock_client("get", 200, json_body=[])

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            await github_list_code_scanning_analyses(
                repo_owner=_OWNER, repo_name=_REPO, per_page=30, page=2
            )

        params = mock_client.get.call_args.kwargs["params"]
        assert params["per_page"] == "30"
        assert params["page"] == "2"

    @pytest.mark.asyncio
    async def test_list_analyses_returns_error_when_status_403(self):
        """GET 403 (insufficient security_events scope) returns an error string."""
        mock_client, _ = _mock_client("get", 403, text_body="Forbidden")

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            result = await github_list_code_scanning_analyses(
                repo_owner=_OWNER, repo_name=_REPO
            )

        assert "❌" in result
        assert "403" in result


# ===========================================================================
# github_get_code_scanning_default_setup
# ===========================================================================


class TestGithubGetCodeScanningDefaultSetup:
    """Tests for github_get_code_scanning_default_setup."""

    @pytest.mark.asyncio
    async def test_get_default_setup_returns_dict_when_status_200(self):
        """GET 200 returns the default-setup configuration."""
        config = {"state": "configured", "languages": ["python"], "query_suite": "default"}
        mock_client, _ = _mock_client("get", 200, json_body=config)

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            result = await github_get_code_scanning_default_setup(
                repo_owner=_OWNER, repo_name=_REPO
            )

        assert result == config
        mock_client.get.assert_called_once_with(
            f"/repos/{_OWNER}/{_REPO}/code-scanning/default-setup"
        )

    @pytest.mark.asyncio
    async def test_get_default_setup_returns_not_found_when_status_404(self):
        """GET 404 returns a not-found/not-available string."""
        mock_client, _ = _mock_client("get", 404, text_body="Not Found")

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            result = await github_get_code_scanning_default_setup(
                repo_owner=_OWNER, repo_name=_REPO
            )

        assert "❌" in result
        assert f"{_OWNER}/{_REPO}" in result

    @pytest.mark.asyncio
    async def test_get_default_setup_returns_error_when_status_403(self):
        """GET 403 (insufficient security_events scope) returns an error string."""
        mock_client, _ = _mock_client("get", 403, text_body="Forbidden")

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            result = await github_get_code_scanning_default_setup(
                repo_owner=_OWNER, repo_name=_REPO
            )

        assert "❌" in result
        assert "403" in result

    @pytest.mark.asyncio
    async def test_get_default_setup_returns_error_on_exception(self):
        """An unexpected exception raised by the client returns an error string."""
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=ConnectionError("refused"))

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            result = await github_get_code_scanning_default_setup(
                repo_owner=_OWNER, repo_name=_REPO
            )

        assert "❌" in result
        assert "Network connection failed" in result


# ===========================================================================
# github_list_secret_scanning_alerts
# ===========================================================================


class TestGithubListSecretScanningAlerts:
    """Tests for github_list_secret_scanning_alerts."""

    @pytest.mark.asyncio
    async def test_list_secret_alerts_returns_list_when_status_200(self):
        """GET 200 returns the alert list."""
        alerts = [{"number": 1, "state": "open", "secret_type": "github_personal_access_token"}]
        mock_client, _ = _mock_client("get", 200, json_body=alerts)

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            result = await github_list_secret_scanning_alerts(
                repo_owner=_OWNER, repo_name=_REPO
            )

        assert result == alerts
        mock_client.get.assert_called_once_with(
            f"/repos/{_OWNER}/{_REPO}/secret-scanning/alerts",
            params=None,
        )

    @pytest.mark.asyncio
    async def test_list_secret_alerts_passes_state_filter(self):
        """Provided state is forwarded as a query param."""
        mock_client, _ = _mock_client("get", 200, json_body=[])

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            await github_list_secret_scanning_alerts(
                repo_owner=_OWNER, repo_name=_REPO, state="open"
            )

        params = mock_client.get.call_args.kwargs["params"]
        assert params["state"] == "open"

    @pytest.mark.asyncio
    async def test_list_secret_alerts_omits_none_state(self):
        """None state must not appear in params."""
        mock_client, _ = _mock_client("get", 200, json_body=[])

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            await github_list_secret_scanning_alerts(
                repo_owner=_OWNER, repo_name=_REPO, state=None
            )

        params = mock_client.get.call_args.kwargs["params"]
        assert params is None

    @pytest.mark.asyncio
    async def test_list_secret_alerts_returns_not_found_when_status_404(self):
        """GET 404 returns a not-found/not-enabled string."""
        mock_client, _ = _mock_client("get", 404, text_body="Not Found")

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            result = await github_list_secret_scanning_alerts(
                repo_owner=_OWNER, repo_name=_REPO
            )

        assert "❌" in result
        assert f"{_OWNER}/{_REPO}" in result

    @pytest.mark.asyncio
    async def test_list_secret_alerts_forwards_pagination_params(self):
        """per_page and page are forwarded as query params when set."""
        mock_client, _ = _mock_client("get", 200, json_body=[])

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            await github_list_secret_scanning_alerts(
                repo_owner=_OWNER, repo_name=_REPO, per_page=100, page=1
            )

        params = mock_client.get.call_args.kwargs["params"]
        assert params["per_page"] == "100"
        assert params["page"] == "1"

    @pytest.mark.asyncio
    async def test_list_secret_alerts_returns_error_when_status_403(self):
        """GET 403 (insufficient security_events scope) returns an error string."""
        mock_client, _ = _mock_client("get", 403, text_body="Forbidden")

        with patch(_PATCH_CTX) as mock_ctx:
            mock_ctx.return_value.__aenter__.return_value = mock_client

            result = await github_list_secret_scanning_alerts(
                repo_owner=_OWNER, repo_name=_REPO
            )

        assert "❌" in result
        assert "403" in result
