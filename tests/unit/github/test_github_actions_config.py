"""
Unit tests for GitHub Actions configuration functions.

Tests the GitHub Actions permissions and workflow configuration functionality including:
- github_get_actions_permissions: successful retrieval, 404 error, auth error
- github_update_actions_permissions: successful update, invalid allowed_actions validation
- github_get_workflow_permissions: successful retrieval, error cases
- github_update_workflow_permissions: successful update, invalid permissions validation
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp_server_git.github.api import (
    github_get_actions_permissions,
    github_get_workflow_permissions,
    github_update_actions_permissions,
    github_update_workflow_permissions,
)


class TestGitHubGetActionsPermissions:
    """Test github_get_actions_permissions function."""

    @pytest.mark.asyncio
    async def test_successful_retrieval_all_enabled(self):
        """Test retrieving Actions permissions when enabled with all actions allowed."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "enabled": True,
                "allowed_actions": "all",
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_actions_permissions(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "GitHub Actions Permissions for owner/repo:" in result
            assert "Enabled: ✅" in result
            assert "Allowed Actions: all" in result

    @pytest.mark.asyncio
    async def test_successful_retrieval_local_only(self):
        """Test retrieving Actions permissions with local_only restriction."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "enabled": True,
                "allowed_actions": "local_only",
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_actions_permissions(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "Enabled: ✅" in result
            assert "Allowed Actions: local_only" in result

    @pytest.mark.asyncio
    async def test_successful_retrieval_selected_actions(self):
        """Test retrieving Actions permissions with selected actions."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "enabled": True,
                "allowed_actions": "selected",
                "selected_actions_url": "https://api.github.com/repos/owner/repo/actions/permissions/selected-actions",
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_actions_permissions(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "Enabled: ✅" in result
            assert "Allowed Actions: selected" in result
            assert "Selected Actions URL:" in result
            assert "selected-actions" in result

    @pytest.mark.asyncio
    async def test_successful_retrieval_disabled(self):
        """Test retrieving Actions permissions when disabled."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "enabled": False,
                "allowed_actions": "all",
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_actions_permissions(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "Enabled: ❌" in result
            assert "Allowed Actions: all" in result

    @pytest.mark.asyncio
    async def test_repository_not_found_404(self):
        """Test that 404 error is handled with helpful message."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 404
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_actions_permissions(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "❌" in result
            assert "Repository owner/repo not found" in result
            assert "Actions not enabled" in result

    @pytest.mark.asyncio
    async def test_authentication_error(self):
        """Test that authentication errors are handled properly."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ValueError(
                "GitHub token not configured"
            )

            result = await github_get_actions_permissions(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "❌" in result
            assert "GitHub token not configured" in result

    @pytest.mark.asyncio
    async def test_connection_error(self):
        """Test that connection errors are handled gracefully."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ConnectionError(
                "Network timeout"
            )

            result = await github_get_actions_permissions(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "❌" in result
            assert "Network connection failed" in result
            assert "Network timeout" in result

    @pytest.mark.asyncio
    async def test_generic_api_error(self):
        """Test that other API errors are reported properly."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal Server Error")
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_actions_permissions(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "❌" in result
            assert "Failed to get Actions permissions" in result
            assert "500" in result
            assert "Internal Server Error" in result

    @pytest.mark.asyncio
    async def test_unexpected_error_handling(self):
        """Test that unexpected errors are caught and reported."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = RuntimeError(
                "Unexpected error"
            )

            result = await github_get_actions_permissions(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "❌" in result
            assert "Error getting Actions permissions" in result
            assert "Unexpected error" in result


class TestGitHubUpdateActionsPermissions:
    """Test github_update_actions_permissions function."""

    @pytest.mark.asyncio
    async def test_successful_enable_actions(self):
        """Test successfully enabling GitHub Actions."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_client.put = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_actions_permissions(
                repo_owner="owner",
                repo_name="repo",
                enabled=True,
            )

            assert "✅" in result
            assert "Successfully updated GitHub Actions permissions" in result
            assert "owner/repo" in result

    @pytest.mark.asyncio
    async def test_successful_disable_actions(self):
        """Test successfully disabling GitHub Actions."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 204
        mock_client.put = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_actions_permissions(
                repo_owner="owner",
                repo_name="repo",
                enabled=False,
            )

            assert "✅" in result
            assert "Successfully updated GitHub Actions permissions" in result

    @pytest.mark.asyncio
    async def test_successful_update_allowed_actions_all(self):
        """Test successfully setting allowed_actions to 'all'."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_client.put = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_actions_permissions(
                repo_owner="owner",
                repo_name="repo",
                allowed_actions="all",
            )

            assert "✅" in result
            assert "Successfully updated GitHub Actions permissions" in result

    @pytest.mark.asyncio
    async def test_successful_update_allowed_actions_local_only(self):
        """Test successfully setting allowed_actions to 'local_only'."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_client.put = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_actions_permissions(
                repo_owner="owner",
                repo_name="repo",
                allowed_actions="local_only",
            )

            assert "✅" in result

    @pytest.mark.asyncio
    async def test_successful_update_allowed_actions_selected(self):
        """Test successfully setting allowed_actions to 'selected'."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_client.put = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_actions_permissions(
                repo_owner="owner",
                repo_name="repo",
                allowed_actions="selected",
            )

            assert "✅" in result

    @pytest.mark.asyncio
    async def test_successful_update_both_parameters(self):
        """Test successfully updating both enabled and allowed_actions."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_client.put = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_actions_permissions(
                repo_owner="owner",
                repo_name="repo",
                enabled=True,
                allowed_actions="local_only",
            )

            assert "✅" in result
            assert "Successfully updated GitHub Actions permissions" in result

    @pytest.mark.asyncio
    async def test_invalid_allowed_actions_value(self):
        """Test that invalid allowed_actions value is rejected."""
        # Mock the client context to prevent authentication errors
        mock_client = MagicMock()

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_actions_permissions(
                repo_owner="owner",
                repo_name="repo",
                allowed_actions="invalid",
            )

            assert "❌" in result
            assert (
                "allowed_actions must be 'all', 'local_only', or 'selected'" in result
            )

    @pytest.mark.asyncio
    async def test_no_parameters_provided(self):
        """Test that no parameters provided returns warning."""
        # Mock the client context to prevent authentication errors
        mock_client = MagicMock()

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_actions_permissions(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "⚠️" in result
            assert "No update parameters provided" in result

    @pytest.mark.asyncio
    async def test_api_error_response(self):
        """Test that API errors are reported properly."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 403
        mock_response.text = AsyncMock(return_value="Forbidden")
        mock_client.put = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_actions_permissions(
                repo_owner="owner",
                repo_name="repo",
                enabled=True,
            )

            assert "❌" in result
            assert "Failed to update Actions permissions" in result
            assert "403" in result
            assert "Forbidden" in result

    @pytest.mark.asyncio
    async def test_authentication_error(self):
        """Test that authentication errors are handled properly."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ValueError(
                "GitHub token not configured"
            )

            result = await github_update_actions_permissions(
                repo_owner="owner",
                repo_name="repo",
                enabled=True,
            )

            assert "❌" in result
            assert "GitHub token not configured" in result

    @pytest.mark.asyncio
    async def test_connection_error(self):
        """Test that connection errors are handled gracefully."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ConnectionError(
                "Network timeout"
            )

            result = await github_update_actions_permissions(
                repo_owner="owner",
                repo_name="repo",
                enabled=True,
            )

            assert "❌" in result
            assert "Network connection failed" in result
            assert "Network timeout" in result

    @pytest.mark.asyncio
    async def test_unexpected_error_handling(self):
        """Test that unexpected errors are caught and reported."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = RuntimeError(
                "Unexpected error"
            )

            result = await github_update_actions_permissions(
                repo_owner="owner",
                repo_name="repo",
                enabled=True,
            )

            assert "❌" in result
            assert "Error updating Actions permissions" in result
            assert "Unexpected error" in result


class TestGitHubGetWorkflowPermissions:
    """Test github_get_workflow_permissions function."""

    @pytest.mark.asyncio
    async def test_successful_retrieval_read_permissions(self):
        """Test retrieving workflow permissions with read-only default."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "default_workflow_permissions": "read",
                "can_approve_pull_request_reviews": False,
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_workflow_permissions(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "Workflow Permissions for owner/repo:" in result
            assert "Default Permissions: read" in result
            assert "Can Approve PR Reviews: ❌" in result

    @pytest.mark.asyncio
    async def test_successful_retrieval_write_permissions(self):
        """Test retrieving workflow permissions with write default."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "default_workflow_permissions": "write",
                "can_approve_pull_request_reviews": True,
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_workflow_permissions(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "Default Permissions: write" in result
            assert "Can Approve PR Reviews: ✅" in result

    @pytest.mark.asyncio
    async def test_repository_not_found_404(self):
        """Test that 404 error is handled with helpful message."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 404
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_workflow_permissions(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "❌" in result
            assert "Repository owner/repo not found" in result

    @pytest.mark.asyncio
    async def test_authentication_error(self):
        """Test that authentication errors are handled properly."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ValueError(
                "GitHub token not configured"
            )

            result = await github_get_workflow_permissions(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "❌" in result
            assert "GitHub token not configured" in result

    @pytest.mark.asyncio
    async def test_connection_error(self):
        """Test that connection errors are handled gracefully."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ConnectionError(
                "Network timeout"
            )

            result = await github_get_workflow_permissions(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "❌" in result
            assert "Network connection failed" in result
            assert "Network timeout" in result

    @pytest.mark.asyncio
    async def test_generic_api_error(self):
        """Test that other API errors are reported properly."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal Server Error")
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_workflow_permissions(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "❌" in result
            assert "Failed to get workflow permissions" in result
            assert "500" in result
            assert "Internal Server Error" in result

    @pytest.mark.asyncio
    async def test_unexpected_error_handling(self):
        """Test that unexpected errors are caught and reported."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = RuntimeError(
                "Unexpected error"
            )

            result = await github_get_workflow_permissions(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "❌" in result
            assert "Error getting workflow permissions" in result
            assert "Unexpected error" in result


class TestGitHubUpdateWorkflowPermissions:
    """Test github_update_workflow_permissions function."""

    @pytest.mark.asyncio
    async def test_successful_update_to_read(self):
        """Test successfully updating default permissions to read."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_client.put = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_workflow_permissions(
                repo_owner="owner",
                repo_name="repo",
                default_workflow_permissions="read",
            )

            assert "✅" in result
            assert "Successfully updated workflow permissions" in result
            assert "owner/repo" in result

    @pytest.mark.asyncio
    async def test_successful_update_to_write(self):
        """Test successfully updating default permissions to write."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 204
        mock_client.put = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_workflow_permissions(
                repo_owner="owner",
                repo_name="repo",
                default_workflow_permissions="write",
            )

            assert "✅" in result
            assert "Successfully updated workflow permissions" in result

    @pytest.mark.asyncio
    async def test_successful_update_pr_approval_enabled(self):
        """Test successfully enabling PR approval by workflows."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_client.put = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_workflow_permissions(
                repo_owner="owner",
                repo_name="repo",
                can_approve_pull_request_reviews=True,
            )

            assert "✅" in result

    @pytest.mark.asyncio
    async def test_successful_update_pr_approval_disabled(self):
        """Test successfully disabling PR approval by workflows."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_client.put = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_workflow_permissions(
                repo_owner="owner",
                repo_name="repo",
                can_approve_pull_request_reviews=False,
            )

            assert "✅" in result

    @pytest.mark.asyncio
    async def test_successful_update_both_parameters(self):
        """Test successfully updating both workflow permissions parameters."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_client.put = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_workflow_permissions(
                repo_owner="owner",
                repo_name="repo",
                default_workflow_permissions="read",
                can_approve_pull_request_reviews=False,
            )

            assert "✅" in result
            assert "Successfully updated workflow permissions" in result

    @pytest.mark.asyncio
    async def test_invalid_default_permissions_value(self):
        """Test that invalid default_workflow_permissions value is rejected."""
        # Mock the client context to prevent authentication errors
        mock_client = MagicMock()

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_workflow_permissions(
                repo_owner="owner",
                repo_name="repo",
                default_workflow_permissions="invalid",
            )

            assert "❌" in result
            assert "default_workflow_permissions must be 'read' or 'write'" in result

    @pytest.mark.asyncio
    async def test_no_parameters_provided(self):
        """Test that no parameters provided returns warning."""
        # Mock the client context to prevent authentication errors
        mock_client = MagicMock()

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_workflow_permissions(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "⚠️" in result
            assert "No update parameters provided" in result

    @pytest.mark.asyncio
    async def test_api_error_response(self):
        """Test that API errors are reported properly."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 403
        mock_response.text = AsyncMock(return_value="Forbidden")
        mock_client.put = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_workflow_permissions(
                repo_owner="owner",
                repo_name="repo",
                default_workflow_permissions="read",
            )

            assert "❌" in result
            assert "Failed to update workflow permissions" in result
            assert "403" in result
            assert "Forbidden" in result

    @pytest.mark.asyncio
    async def test_authentication_error(self):
        """Test that authentication errors are handled properly."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ValueError(
                "GitHub token not configured"
            )

            result = await github_update_workflow_permissions(
                repo_owner="owner",
                repo_name="repo",
                default_workflow_permissions="read",
            )

            assert "❌" in result
            assert "GitHub token not configured" in result

    @pytest.mark.asyncio
    async def test_connection_error(self):
        """Test that connection errors are handled gracefully."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ConnectionError(
                "Network timeout"
            )

            result = await github_update_workflow_permissions(
                repo_owner="owner",
                repo_name="repo",
                default_workflow_permissions="read",
            )

            assert "❌" in result
            assert "Network connection failed" in result
            assert "Network timeout" in result

    @pytest.mark.asyncio
    async def test_unexpected_error_handling(self):
        """Test that unexpected errors are caught and reported."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = RuntimeError(
                "Unexpected error"
            )

            result = await github_update_workflow_permissions(
                repo_owner="owner",
                repo_name="repo",
                default_workflow_permissions="read",
            )

            assert "❌" in result
            assert "Error updating workflow permissions" in result
            assert "Unexpected error" in result
