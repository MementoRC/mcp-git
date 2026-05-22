"""
Unit tests for GitHub required signatures functions.

Tests the three required-signatures management functions:
- github_get_required_signatures
- github_enable_required_signatures
- github_disable_required_signatures
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp_server_git.github.api import (
    github_disable_required_signatures,
    github_enable_required_signatures,
    github_get_required_signatures,
)

_URL = "/repos/foo/bar/branches/main/protection/required_signatures"


class TestGithubRequiredSignatures:
    """Test github_*_required_signatures functions."""

    # ------------------------------------------------------------------
    # github_get_required_signatures
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_returns_enabled_when_status_200_and_enabled_true(self):
        """GET 200 with enabled=True returns an enabled confirmation."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"enabled": True, "url": _URL})
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.security.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_required_signatures(
                repo_owner="foo",
                repo_name="bar",
                branch="main",
            )

            assert "✅" in result
            assert "enabled" in result
            assert "foo/bar#main" in result
            mock_client.get.assert_called_once_with(_URL)

    @pytest.mark.asyncio
    async def test_get_returns_disabled_when_status_200_and_enabled_false(self):
        """GET 200 with enabled=False returns a disabled indication."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"enabled": False, "url": _URL})
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.security.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_required_signatures(
                repo_owner="foo",
                repo_name="bar",
                branch="main",
            )

            assert "❌" in result
            assert "disabled" in result
            assert "foo/bar#main" in result
            mock_client.get.assert_called_once_with(_URL)

    @pytest.mark.asyncio
    async def test_get_returns_not_found_when_status_404(self):
        """GET 404 reports that branch protection or branch was not found."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 404
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.security.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_required_signatures(
                repo_owner="foo",
                repo_name="bar",
                branch="main",
            )

            assert "❌" in result
            assert "Branch protection or branch not found" in result
            assert "foo/bar#main" in result
            mock_client.get.assert_called_once_with(_URL)

    # ------------------------------------------------------------------
    # github_enable_required_signatures
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_enable_returns_success_when_status_200(self):
        """PUT 200 returns a success confirmation."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_client.put = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.security.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_enable_required_signatures(
                repo_owner="foo",
                repo_name="bar",
                branch="main",
            )

            assert "✅" in result
            assert "Enabled required signatures" in result
            assert "foo/bar#main" in result
            mock_client.put.assert_called_once_with(_URL)

    @pytest.mark.asyncio
    async def test_enable_returns_error_when_status_404(self):
        """PUT non-200 (e.g. branch not protected) returns a failure message."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 404
        mock_response.text = AsyncMock(return_value="Not Found")
        mock_client.put = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.security.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_enable_required_signatures(
                repo_owner="foo",
                repo_name="bar",
                branch="main",
            )

            assert "❌" in result
            assert "Failed to enable required signatures" in result
            assert "404" in result
            mock_client.put.assert_called_once_with(_URL)

    # ------------------------------------------------------------------
    # github_disable_required_signatures
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_disable_returns_success_when_status_204(self):
        """DELETE 204 returns a success confirmation."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 204
        mock_client.delete = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.security.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_disable_required_signatures(
                repo_owner="foo",
                repo_name="bar",
                branch="main",
            )

            assert "✅" in result
            assert "Disabled required signatures" in result
            assert "foo/bar#main" in result
            mock_client.delete.assert_called_once_with(_URL)

    @pytest.mark.asyncio
    async def test_disable_returns_error_when_status_404(self):
        """DELETE non-204 returns a failure message."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 404
        mock_response.text = AsyncMock(return_value="Not Found")
        mock_client.delete = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.security.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_disable_required_signatures(
                repo_owner="foo",
                repo_name="bar",
                branch="main",
            )

            assert "❌" in result
            assert "Failed to disable required signatures" in result
            assert "404" in result
            mock_client.delete.assert_called_once_with(_URL)
