"""
Unit tests for GitHub security functions.

Tests the GitHub security management functionality including:
- Vulnerability alerts checking and toggling (Dependabot alerts)
- Automated security fixes checking and toggling (Dependabot security updates)
- Comprehensive security analysis with graceful partial failure handling
- Authentication and connection error handling
- API error responses
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp_server_git.github.api import (
    github_disable_automated_security_fixes,
    github_disable_vulnerability_alerts,
    github_enable_automated_security_fixes,
    github_enable_vulnerability_alerts,
    github_get_automated_security_fixes,
    github_get_security_analysis,
    github_get_vulnerability_alerts,
)


class TestGitHubGetVulnerabilityAlerts:
    """Test github_get_vulnerability_alerts function."""

    @pytest.mark.asyncio
    async def test_vulnerability_alerts_enabled(self):
        """Test that enabled vulnerability alerts return 204 status."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 204
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_vulnerability_alerts(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "✅" in result
            assert "ENABLED" in result
            assert "owner/repo" in result
            assert "Dependabot" in result
            mock_client.get.assert_called_once_with(
                "/repos/owner/repo/vulnerability-alerts"
            )

    @pytest.mark.asyncio
    async def test_vulnerability_alerts_disabled(self):
        """Test that disabled vulnerability alerts return 404 status."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 404
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_vulnerability_alerts(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "❌" in result
            assert "DISABLED" in result
            assert "owner/repo" in result

    @pytest.mark.asyncio
    async def test_vulnerability_alerts_api_error(self):
        """Test that API errors are handled gracefully."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal Server Error")
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_vulnerability_alerts(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "❌" in result
            assert "Failed to check vulnerability alerts" in result
            assert "500" in result
            assert "Internal Server Error" in result

    @pytest.mark.asyncio
    async def test_vulnerability_alerts_auth_error(self):
        """Test that authentication errors are handled properly."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ValueError(
                "GitHub token not configured"
            )

            result = await github_get_vulnerability_alerts(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "❌" in result
            assert "GitHub token not configured" in result

    @pytest.mark.asyncio
    async def test_vulnerability_alerts_connection_error(self):
        """Test that connection errors are handled gracefully."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ConnectionError(
                "Network timeout"
            )

            result = await github_get_vulnerability_alerts(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "❌" in result
            assert "Network connection failed" in result
            assert "Network timeout" in result

    @pytest.mark.asyncio
    async def test_vulnerability_alerts_unexpected_error(self):
        """Test that unexpected errors are caught and reported."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = RuntimeError(
                "Unexpected error"
            )

            result = await github_get_vulnerability_alerts(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "❌" in result
            assert "Error checking vulnerability alerts" in result
            assert "Unexpected error" in result


class TestGitHubEnableVulnerabilityAlerts:
    """Test github_enable_vulnerability_alerts function."""

    @pytest.mark.asyncio
    async def test_enable_vulnerability_alerts_success(self):
        """Test successfully enabling vulnerability alerts."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 204
        mock_client.put = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_enable_vulnerability_alerts(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "✅" in result
            assert "Successfully enabled" in result
            assert "owner/repo" in result
            mock_client.put.assert_called_once_with(
                "/repos/owner/repo/vulnerability-alerts"
            )

    @pytest.mark.asyncio
    async def test_enable_vulnerability_alerts_error(self):
        """Test error handling when enabling fails."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 403
        mock_response.text = AsyncMock(return_value="Forbidden")
        mock_client.put = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_enable_vulnerability_alerts(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "❌" in result
            assert "Failed to enable" in result
            assert "403" in result
            assert "Forbidden" in result

    @pytest.mark.asyncio
    async def test_enable_vulnerability_alerts_auth_error(self):
        """Test authentication error handling."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ValueError(
                "GitHub token not configured"
            )

            result = await github_enable_vulnerability_alerts(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "❌" in result
            assert "GitHub token not configured" in result

    @pytest.mark.asyncio
    async def test_enable_vulnerability_alerts_connection_error(self):
        """Test connection error handling."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ConnectionError(
                "Network timeout"
            )

            result = await github_enable_vulnerability_alerts(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "❌" in result
            assert "Network connection failed" in result


class TestGitHubDisableVulnerabilityAlerts:
    """Test github_disable_vulnerability_alerts function."""

    @pytest.mark.asyncio
    async def test_disable_vulnerability_alerts_success(self):
        """Test successfully disabling vulnerability alerts."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 204
        mock_client.delete = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_disable_vulnerability_alerts(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "✅" in result
            assert "Successfully disabled" in result
            assert "owner/repo" in result
            mock_client.delete.assert_called_once_with(
                "/repos/owner/repo/vulnerability-alerts"
            )

    @pytest.mark.asyncio
    async def test_disable_vulnerability_alerts_error(self):
        """Test error handling when disabling fails."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 403
        mock_response.text = AsyncMock(return_value="Forbidden")
        mock_client.delete = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_disable_vulnerability_alerts(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "❌" in result
            assert "Failed to disable" in result
            assert "403" in result


class TestGitHubGetAutomatedSecurityFixes:
    """Test github_get_automated_security_fixes function."""

    @pytest.mark.asyncio
    async def test_automated_security_fixes_enabled(self):
        """Test that enabled automated security fixes are reported correctly."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "enabled": True,
                "paused": False,
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_automated_security_fixes(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "✅" in result
            assert "ENABLED" in result
            assert "owner/repo" in result
            assert "Dependabot security updates" in result
            assert "PAUSED" not in result

    @pytest.mark.asyncio
    async def test_automated_security_fixes_disabled(self):
        """Test that disabled automated security fixes are reported correctly."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "enabled": False,
                "paused": False,
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_automated_security_fixes(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "❌" in result
            assert "DISABLED" in result
            assert "owner/repo" in result

    @pytest.mark.asyncio
    async def test_automated_security_fixes_paused(self):
        """Test that paused automated security fixes are reported correctly."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "enabled": True,
                "paused": True,
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_automated_security_fixes(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "✅" in result
            assert "ENABLED" in result
            assert "PAUSED" in result
            assert "owner/repo" in result

    @pytest.mark.asyncio
    async def test_automated_security_fixes_not_available(self):
        """Test that 404 status is handled for unavailable feature."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 404
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_automated_security_fixes(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "❌" in result
            assert "not available or disabled" in result

    @pytest.mark.asyncio
    async def test_automated_security_fixes_api_error(self):
        """Test that API errors are handled gracefully."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal Server Error")
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_automated_security_fixes(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "❌" in result
            assert "Failed to check" in result
            assert "500" in result


class TestGitHubEnableAutomatedSecurityFixes:
    """Test github_enable_automated_security_fixes function."""

    @pytest.mark.asyncio
    async def test_enable_automated_security_fixes_success(self):
        """Test successfully enabling automated security fixes."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 204
        mock_client.put = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_enable_automated_security_fixes(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "✅" in result
            assert "Successfully enabled" in result
            assert "owner/repo" in result
            mock_client.put.assert_called_once_with(
                "/repos/owner/repo/automated-security-fixes"
            )

    @pytest.mark.asyncio
    async def test_enable_automated_security_fixes_error(self):
        """Test error handling when enabling fails."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 403
        mock_response.text = AsyncMock(return_value="Forbidden")
        mock_client.put = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_enable_automated_security_fixes(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "❌" in result
            assert "Failed to enable" in result
            assert "403" in result


class TestGitHubDisableAutomatedSecurityFixes:
    """Test github_disable_automated_security_fixes function."""

    @pytest.mark.asyncio
    async def test_disable_automated_security_fixes_success(self):
        """Test successfully disabling automated security fixes."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 204
        mock_client.delete = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_disable_automated_security_fixes(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "✅" in result
            assert "Successfully disabled" in result
            assert "owner/repo" in result
            mock_client.delete.assert_called_once_with(
                "/repos/owner/repo/automated-security-fixes"
            )

    @pytest.mark.asyncio
    async def test_disable_automated_security_fixes_error(self):
        """Test error handling when disabling fails."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 403
        mock_response.text = AsyncMock(return_value="Forbidden")
        mock_client.delete = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_disable_automated_security_fixes(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "❌" in result
            assert "Failed to disable" in result
            assert "403" in result


class TestGitHubGetSecurityAnalysis:
    """Test github_get_security_analysis function."""

    @pytest.mark.asyncio
    async def test_security_analysis_full_success(self):
        """Test comprehensive security analysis with all checks succeeding."""
        mock_client = MagicMock()

        # Mock vulnerability alerts response (enabled)
        vuln_response = AsyncMock()
        vuln_response.status = 204

        # Mock automated security fixes response (enabled)
        auto_response = AsyncMock()
        auto_response.status = 200
        auto_response.json = AsyncMock(
            return_value={
                "enabled": True,
                "paused": False,
            }
        )

        # Mock repository settings response with security features
        repo_response = AsyncMock()
        repo_response.status = 200
        repo_response.json = AsyncMock(
            return_value={
                "visibility": "private",
                "private": True,
                "archived": False,
                "security_and_analysis": {
                    "secret_scanning": {"status": "enabled"},
                    "secret_scanning_push_protection": {"status": "enabled"},
                    "dependabot_security_updates": {"status": "enabled"},
                },
            }
        )

        # Setup mock to return different responses for each endpoint
        async def mock_get(url):
            if "vulnerability-alerts" in url:
                return vuln_response
            elif "automated-security-fixes" in url:
                return auto_response
            else:
                return repo_response

        mock_client.get = AsyncMock(side_effect=mock_get)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_security_analysis(
                repo_owner="owner",
                repo_name="repo",
            )

            # Verify header
            assert "Security Analysis for owner/repo" in result

            # Verify vulnerability alerts check
            assert "✅ Vulnerability Alerts (Dependabot): ENABLED" in result

            # Verify automated security fixes check
            assert "✅ Automated Security Fixes: ENABLED" in result

            # Verify repository settings
            assert "📋 Repository Security Settings:" in result
            assert "Visibility: private" in result
            assert "Private: ✅" in result
            assert "Archived: ❌" in result

            # Verify security features
            assert "🔐 Security & Analysis Features:" in result
            assert "✅ Secret Scanning: ENABLED" in result
            assert "✅ Secret Scanning Push Protection: ENABLED" in result
            assert "✅ Dependabot Security Updates: ENABLED" in result

            # Verify settings URL
            assert (
                "https://github.com/owner/repo/settings/security_analysis" in result
            )

            # Should not have failure warnings
            assert "checks failed" not in result

    @pytest.mark.asyncio
    async def test_security_analysis_partial_failure_vulnerability_check(self):
        """Test that vulnerability alerts check failure doesn't prevent other checks."""
        mock_client = MagicMock()

        # Mock automated security fixes response (succeeds)
        auto_response = AsyncMock()
        auto_response.status = 200
        auto_response.json = AsyncMock(
            return_value={
                "enabled": True,
                "paused": False,
            }
        )

        # Mock repository settings response (succeeds)
        repo_response = AsyncMock()
        repo_response.status = 200
        repo_response.json = AsyncMock(
            return_value={
                "visibility": "public",
                "private": False,
                "archived": False,
                "security_and_analysis": {
                    "secret_scanning": {"status": "disabled"},
                },
            }
        )

        # Setup mock to fail vulnerability check but succeed others
        async def mock_get(url):
            if "vulnerability-alerts" in url:
                raise RuntimeError("Temporary API error")
            elif "automated-security-fixes" in url:
                return auto_response
            else:
                return repo_response

        mock_client.get = AsyncMock(side_effect=mock_get)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_security_analysis(
                repo_owner="owner",
                repo_name="repo",
            )

            # Verify the failure is reported
            assert "⚠️ Vulnerability Alerts: Check failed" in result
            assert "Temporary API error" in result

            # Verify other checks still completed
            assert "✅ Automated Security Fixes: ENABLED" in result
            assert "📋 Repository Security Settings:" in result

            # Verify failure summary
            assert "1 of 3 checks failed" in result

    @pytest.mark.asyncio
    async def test_security_analysis_partial_failure_security_fixes_check(self):
        """Test that security fixes check failure doesn't prevent other checks."""
        mock_client = MagicMock()

        # Mock vulnerability alerts response (succeeds)
        vuln_response = AsyncMock()
        vuln_response.status = 204

        # Mock repository settings response (succeeds)
        repo_response = AsyncMock()
        repo_response.status = 200
        repo_response.json = AsyncMock(
            return_value={
                "visibility": "public",
                "private": False,
                "archived": False,
            }
        )

        # Setup mock to fail security fixes check but succeed others
        async def mock_get(url):
            if "vulnerability-alerts" in url:
                return vuln_response
            elif "automated-security-fixes" in url:
                raise RuntimeError("API timeout")
            else:
                return repo_response

        mock_client.get = AsyncMock(side_effect=mock_get)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_security_analysis(
                repo_owner="owner",
                repo_name="repo",
            )

            # Verify the failure is reported
            assert "⚠️ Automated Security Fixes: Check failed" in result
            assert "API timeout" in result

            # Verify other checks still completed
            assert "✅ Vulnerability Alerts (Dependabot): ENABLED" in result
            assert "📋 Repository Security Settings:" in result

            # Verify failure summary
            assert "1 of 3 checks failed" in result

    @pytest.mark.asyncio
    async def test_security_analysis_partial_failure_repo_settings(self):
        """Test that repo settings check failure doesn't prevent other checks."""
        mock_client = MagicMock()

        # Mock vulnerability alerts response (succeeds)
        vuln_response = AsyncMock()
        vuln_response.status = 404  # Disabled

        # Mock automated security fixes response (succeeds)
        auto_response = AsyncMock()
        auto_response.status = 200
        auto_response.json = AsyncMock(
            return_value={
                "enabled": False,
                "paused": False,
            }
        )

        # Setup mock to fail repo settings check but succeed others
        async def mock_get(url):
            if "vulnerability-alerts" in url:
                return vuln_response
            elif "automated-security-fixes" in url:
                return auto_response
            else:
                raise RuntimeError("Database connection failed")

        mock_client.get = AsyncMock(side_effect=mock_get)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_security_analysis(
                repo_owner="owner",
                repo_name="repo",
            )

            # Verify the failure is reported
            assert "⚠️ Repository Settings: Check failed" in result
            assert "Database connection failed" in result

            # Verify other checks still completed
            assert "❌ Vulnerability Alerts (Dependabot): DISABLED" in result
            assert "❌ Automated Security Fixes: DISABLED" in result

            # Verify failure summary
            assert "1 of 3 checks failed" in result

    @pytest.mark.asyncio
    async def test_security_analysis_multiple_failures(self):
        """Test that multiple check failures are counted correctly."""
        mock_client = MagicMock()

        # Mock automated security fixes response (succeeds)
        auto_response = AsyncMock()
        auto_response.status = 200
        auto_response.json = AsyncMock(
            return_value={
                "enabled": True,
                "paused": False,
            }
        )

        # Setup mock to fail two checks
        async def mock_get(url):
            if "vulnerability-alerts" in url:
                raise RuntimeError("Error 1")
            elif "automated-security-fixes" in url:
                return auto_response
            else:
                raise RuntimeError("Error 2")

        mock_client.get = AsyncMock(side_effect=mock_get)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_security_analysis(
                repo_owner="owner",
                repo_name="repo",
            )

            # Verify both failures are reported
            assert "⚠️ Vulnerability Alerts: Check failed" in result
            assert "⚠️ Repository Settings: Check failed" in result

            # Verify the one success is reported
            assert "✅ Automated Security Fixes: ENABLED" in result

            # Verify failure summary
            assert "2 of 3 checks failed" in result

    @pytest.mark.asyncio
    async def test_security_analysis_all_checks_fail(self):
        """Test graceful handling when all individual checks fail."""
        mock_client = MagicMock()

        # Setup mock to fail all checks
        mock_client.get = AsyncMock(side_effect=RuntimeError("API unavailable"))

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_security_analysis(
                repo_owner="owner",
                repo_name="repo",
            )

            # Verify all failures are reported
            assert "⚠️ Vulnerability Alerts: Check failed" in result
            assert "⚠️ Automated Security Fixes: Check failed" in result
            assert "⚠️ Repository Settings: Check failed" in result

            # Verify failure summary
            assert "3 of 3 checks failed" in result

            # Should still have header and settings URL
            assert "Security Analysis for owner/repo" in result
            assert (
                "https://github.com/owner/repo/settings/security_analysis" in result
            )

    @pytest.mark.asyncio
    async def test_security_analysis_auth_error(self):
        """Test that authentication errors are handled at the top level."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ValueError(
                "GitHub token not configured"
            )

            result = await github_get_security_analysis(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "❌" in result
            assert "GitHub token not configured" in result

    @pytest.mark.asyncio
    async def test_security_analysis_connection_error(self):
        """Test that connection errors are handled at the top level."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ConnectionError(
                "Network timeout"
            )

            result = await github_get_security_analysis(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "❌" in result
            assert "Network connection failed" in result
            assert "Network timeout" in result

    @pytest.mark.asyncio
    async def test_security_analysis_unexpected_error(self):
        """Test that unexpected errors are caught and reported."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = RuntimeError(
                "Unexpected error"
            )

            result = await github_get_security_analysis(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "❌" in result
            assert "Error getting security analysis" in result
            assert "Unexpected error" in result

    @pytest.mark.asyncio
    async def test_security_analysis_disabled_features(self):
        """Test reporting when security features are disabled."""
        mock_client = MagicMock()

        # Mock vulnerability alerts response (disabled)
        vuln_response = AsyncMock()
        vuln_response.status = 404

        # Mock automated security fixes response (disabled)
        auto_response = AsyncMock()
        auto_response.status = 200
        auto_response.json = AsyncMock(
            return_value={
                "enabled": False,
                "paused": False,
            }
        )

        # Mock repository settings response with disabled features
        repo_response = AsyncMock()
        repo_response.status = 200
        repo_response.json = AsyncMock(
            return_value={
                "visibility": "public",
                "private": False,
                "archived": False,
                "security_and_analysis": {
                    "secret_scanning": {"status": "disabled"},
                    "secret_scanning_push_protection": {"status": "disabled"},
                    "dependabot_security_updates": {"status": "disabled"},
                },
            }
        )

        # Setup mock to return different responses for each endpoint
        async def mock_get(url):
            if "vulnerability-alerts" in url:
                return vuln_response
            elif "automated-security-fixes" in url:
                return auto_response
            else:
                return repo_response

        mock_client.get = AsyncMock(side_effect=mock_get)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_security_analysis(
                repo_owner="owner",
                repo_name="repo",
            )

            # Verify all features show as disabled
            assert "❌ Vulnerability Alerts (Dependabot): DISABLED" in result
            assert "❌ Automated Security Fixes: DISABLED" in result
            assert "❌ Secret Scanning: DISABLED" in result
            assert "❌ Secret Scanning Push Protection: DISABLED" in result
            assert "❌ Dependabot Security Updates: DISABLED" in result

            # Should not have failure warnings (all checks succeeded)
            assert "checks failed" not in result

    @pytest.mark.asyncio
    async def test_security_analysis_paused_security_fixes(self):
        """Test reporting when automated security fixes are paused."""
        mock_client = MagicMock()

        # Mock vulnerability alerts response (enabled)
        vuln_response = AsyncMock()
        vuln_response.status = 204

        # Mock automated security fixes response (enabled but paused)
        auto_response = AsyncMock()
        auto_response.status = 200
        auto_response.json = AsyncMock(
            return_value={
                "enabled": True,
                "paused": True,
            }
        )

        # Mock repository settings response
        repo_response = AsyncMock()
        repo_response.status = 200
        repo_response.json = AsyncMock(
            return_value={
                "visibility": "public",
                "private": False,
                "archived": False,
            }
        )

        # Setup mock to return different responses for each endpoint
        async def mock_get(url):
            if "vulnerability-alerts" in url:
                return vuln_response
            elif "automated-security-fixes" in url:
                return auto_response
            else:
                return repo_response

        mock_client.get = AsyncMock(side_effect=mock_get)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_security_analysis(
                repo_owner="owner",
                repo_name="repo",
            )

            # Verify paused status is reported
            assert "✅ Automated Security Fixes: ENABLED (PAUSED)" in result
            assert "✅ Vulnerability Alerts (Dependabot): ENABLED" in result

    @pytest.mark.asyncio
    async def test_security_analysis_minimal_repo_data(self):
        """Test handling of repository with minimal security data."""
        mock_client = MagicMock()

        # Mock vulnerability alerts response (enabled)
        vuln_response = AsyncMock()
        vuln_response.status = 204

        # Mock automated security fixes response (disabled)
        auto_response = AsyncMock()
        auto_response.status = 200
        auto_response.json = AsyncMock(
            return_value={
                "enabled": False,
            }
        )

        # Mock repository settings response without security_and_analysis
        repo_response = AsyncMock()
        repo_response.status = 200
        repo_response.json = AsyncMock(
            return_value={
                "visibility": "public",
                "private": False,
                "archived": False,
                # No security_and_analysis field
            }
        )

        # Setup mock to return different responses for each endpoint
        async def mock_get(url):
            if "vulnerability-alerts" in url:
                return vuln_response
            elif "automated-security-fixes" in url:
                return auto_response
            else:
                return repo_response

        mock_client.get = AsyncMock(side_effect=mock_get)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_security_analysis(
                repo_owner="owner",
                repo_name="repo",
            )

            # Verify basic checks completed
            assert "✅ Vulnerability Alerts (Dependabot): ENABLED" in result
            assert "❌ Automated Security Fixes: DISABLED" in result
            assert "📋 Repository Security Settings:" in result

            # Should not have security features section since data is missing
            assert "🔐 Security & Analysis Features:" not in result
