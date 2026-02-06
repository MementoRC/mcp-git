"""
Unit tests for GitHub branch protection functions.

Tests the GitHub branch protection functionality including:
- Get branch protection rules with full configuration
- Update branch protection with various options
- Delete branch protection rules
- 404 error handling (no protection, branch not found)
- Authentication and connection error handling
- Pydantic model validators for invalid branch names
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from src.mcp_server_git.github.api import (
    github_delete_branch_protection,
    github_get_branch_protection,
    github_update_branch_protection,
)
from src.mcp_server_git.github.models import (
    GitHubDeleteBranchProtection,
    GitHubGetBranchProtection,
    GitHubUpdateBranchProtection,
)


class TestGitHubGetBranchProtection:
    """Test github_get_branch_protection function."""

    @pytest.mark.asyncio
    async def test_successful_branch_protection_full_rules(self):
        """Test retrieving branch protection with all rules enabled."""
        mock_client = MagicMock()

        # Mock successful response with comprehensive protection rules
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "required_status_checks": {
                    "strict": True,
                    "contexts": ["ci/test", "ci/lint", "ci/security"],
                },
                "required_pull_request_reviews": {
                    "dismiss_stale_reviews": True,
                    "require_code_owner_reviews": True,
                    "required_approving_review_count": 2,
                    "require_last_push_approval": True,
                },
                "enforce_admins": {"enabled": True},
                "restrictions": {
                    "users": [{"login": "admin1"}, {"login": "admin2"}],
                    "teams": [{"slug": "core-team"}, {"slug": "security-team"}],
                },
                "required_linear_history": {"enabled": True},
                "allow_force_pushes": {"enabled": False},
                "allow_deletions": {"enabled": False},
                "required_conversation_resolution": {"enabled": True},
                "lock_branch": {"enabled": False},
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_branch_protection(
                repo_owner="owner",
                repo_name="repo",
                branch="main",
            )

            # Verify API call
            mock_client.get.assert_called_once_with(
                "/repos/owner/repo/branches/main/protection"
            )

            # Verify output contains all expected fields
            assert "Branch Protection for owner/repo:main" in result
            assert "✅ Required Status Checks:" in result
            assert "Strict: ✅" in result
            assert "Contexts: ci/test, ci/lint, ci/security" in result
            assert "✅ Required Pull Request Reviews:" in result
            assert "Dismiss Stale Reviews: ✅" in result
            assert "Require Code Owner Reviews: ✅" in result
            assert "Required Approving Review Count: 2" in result
            assert "Require Last Push Approval: ✅" in result
            assert "👮 Enforce Admins: ✅" in result
            assert "🔒 Push Restrictions: Enabled" in result
            assert "Users: admin1, admin2" in result
            assert "Teams: core-team, security-team" in result
            assert "Required Linear History: ✅" in result
            assert "Allow Force Pushes: ❌" in result
            assert "Allow Deletions: ❌" in result
            assert "Required Conversation Resolution: ✅" in result
            assert "Lock Branch: ❌" in result

    @pytest.mark.asyncio
    async def test_minimal_branch_protection(self):
        """Test retrieving branch protection with minimal rules."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "required_status_checks": None,
                "required_pull_request_reviews": None,
                "enforce_admins": None,
                "restrictions": None,
                "required_linear_history": {"enabled": False},
                "allow_force_pushes": {"enabled": False},
                "allow_deletions": {"enabled": False},
                "required_conversation_resolution": {"enabled": False},
                "lock_branch": {"enabled": False},
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_branch_protection(
                repo_owner="owner",
                repo_name="repo",
                branch="develop",
            )

            assert "Branch Protection for owner/repo:develop" in result
            assert "❌ Required Status Checks: Not configured" in result
            assert "❌ Required Pull Request Reviews: Not configured" in result
            assert "🔓 Push Restrictions: Not configured" in result

    @pytest.mark.asyncio
    async def test_branch_protection_not_found_404(self):
        """Test that 404 error indicates no protection or branch not found."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 404
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_branch_protection(
                repo_owner="owner",
                repo_name="repo",
                branch="feature/new-branch",
            )

            assert "❌ Branch protection not found for feature/new-branch" in result
            assert (
                "The branch may not exist or have no protection rules" in result
            )

    @pytest.mark.asyncio
    async def test_authentication_error(self):
        """Test that authentication errors are handled properly."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ValueError(
                "GitHub token not configured"
            )

            result = await github_get_branch_protection(
                repo_owner="owner",
                repo_name="repo",
                branch="main",
            )

            assert "GitHub token not configured" in result
            assert "❌" in result

    @pytest.mark.asyncio
    async def test_connection_error(self):
        """Test that connection errors are handled gracefully."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ConnectionError(
                "Network timeout"
            )

            result = await github_get_branch_protection(
                repo_owner="owner",
                repo_name="repo",
                branch="main",
            )

            assert "Network connection failed" in result
            assert "Network timeout" in result

    @pytest.mark.asyncio
    async def test_api_error_403_forbidden(self):
        """Test handling of 403 Forbidden error (insufficient permissions)."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 403
        mock_response.text = AsyncMock(return_value="Forbidden - insufficient permissions")
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_branch_protection(
                repo_owner="owner",
                repo_name="private-repo",
                branch="main",
            )

            assert "Failed to get branch protection" in result
            assert "403" in result
            assert "Forbidden - insufficient permissions" in result

    @pytest.mark.asyncio
    async def test_unexpected_error_handling(self):
        """Test that unexpected errors are caught and reported."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = RuntimeError(
                "Unexpected error"
            )

            result = await github_get_branch_protection(
                repo_owner="owner",
                repo_name="repo",
                branch="main",
            )

            assert "Error getting branch protection" in result
            assert "Unexpected error" in result


class TestGitHubUpdateBranchProtection:
    """Test github_update_branch_protection function."""

    @pytest.mark.asyncio
    async def test_successful_update_with_status_checks(self):
        """Test updating branch protection with required status checks."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_client.put = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_branch_protection(
                repo_owner="owner",
                repo_name="repo",
                branch="main",
                required_status_checks_strict=True,
                required_status_checks_contexts=["ci/test", "ci/lint"],
            )

            # Verify API call with correct payload
            mock_client.put.assert_called_once()
            call_args = mock_client.put.call_args
            assert call_args[0][0] == "/repos/owner/repo/branches/main/protection"
            payload = call_args[1]["json"]
            assert payload["required_status_checks"]["strict"] is True
            assert payload["required_status_checks"]["contexts"] == ["ci/test", "ci/lint"]

            assert "✅ Successfully updated branch protection for owner/repo:main" in result

    @pytest.mark.asyncio
    async def test_successful_update_with_pr_reviews(self):
        """Test updating branch protection with PR review requirements."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_client.put = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_branch_protection(
                repo_owner="owner",
                repo_name="repo",
                branch="main",
                require_pull_request_reviews=True,
                dismiss_stale_reviews=True,
                require_code_owner_reviews=True,
                required_approving_review_count=2,
                require_last_push_approval=True,
            )

            # Verify payload structure
            call_args = mock_client.put.call_args
            payload = call_args[1]["json"]
            pr_reviews = payload["required_pull_request_reviews"]
            assert pr_reviews["dismiss_stale_reviews"] is True
            assert pr_reviews["require_code_owner_reviews"] is True
            assert pr_reviews["required_approving_review_count"] == 2
            assert pr_reviews["require_last_push_approval"] is True

            assert "✅ Successfully updated branch protection" in result

    @pytest.mark.asyncio
    async def test_successful_update_with_restrictions(self):
        """Test updating branch protection with push restrictions."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_client.put = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_branch_protection(
                repo_owner="owner",
                repo_name="repo",
                branch="main",
                restrict_pushes=True,
                push_allowances_users=["admin1", "admin2"],
                push_allowances_teams=["core-team"],
            )

            # Verify restrictions payload
            call_args = mock_client.put.call_args
            payload = call_args[1]["json"]
            restrictions = payload["restrictions"]
            assert restrictions["users"] == ["admin1", "admin2"]
            assert restrictions["teams"] == ["core-team"]

            assert "✅ Successfully updated branch protection" in result

    @pytest.mark.asyncio
    async def test_successful_update_with_other_settings(self):
        """Test updating branch protection with other settings."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_client.put = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_branch_protection(
                repo_owner="owner",
                repo_name="repo",
                branch="main",
                enforce_admins=True,
                required_linear_history=True,
                allow_force_pushes=False,
                allow_deletions=False,
                required_conversation_resolution=True,
                lock_branch=False,
            )

            # Verify other settings
            call_args = mock_client.put.call_args
            payload = call_args[1]["json"]
            assert payload["enforce_admins"] is True
            assert payload["required_linear_history"] is True
            assert payload["allow_force_pushes"] is False
            assert payload["allow_deletions"] is False
            assert payload["required_conversation_resolution"] is True
            assert payload["lock_branch"] is False

            assert "✅ Successfully updated branch protection" in result

    @pytest.mark.asyncio
    async def test_successful_update_with_201_created(self):
        """Test that 201 Created status is also considered success."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 201
        mock_client.put = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_branch_protection(
                repo_owner="owner",
                repo_name="repo",
                branch="main",
                required_linear_history=True,
            )

            assert "✅ Successfully updated branch protection" in result

    @pytest.mark.asyncio
    async def test_update_without_pr_reviews_sets_null(self):
        """Test that not requiring PR reviews sets the field to None."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_client.put = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_branch_protection(
                repo_owner="owner",
                repo_name="repo",
                branch="main",
                require_pull_request_reviews=False,
            )

            # Verify PR reviews is set to None when not required
            call_args = mock_client.put.call_args
            payload = call_args[1]["json"]
            assert payload["required_pull_request_reviews"] is None

            assert "✅ Successfully updated branch protection" in result

    @pytest.mark.asyncio
    async def test_update_api_error_422_validation(self):
        """Test handling of 422 validation error."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 422
        mock_response.text = AsyncMock(
            return_value="Validation error: Invalid status check context"
        )
        mock_client.put = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_branch_protection(
                repo_owner="owner",
                repo_name="repo",
                branch="main",
                required_status_checks_contexts=["invalid context"],
            )

            assert "Failed to update branch protection" in result
            assert "422" in result
            assert "Validation error" in result

    @pytest.mark.asyncio
    async def test_update_authentication_error(self):
        """Test that authentication errors are handled properly."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ValueError(
                "GitHub token not configured"
            )

            result = await github_update_branch_protection(
                repo_owner="owner",
                repo_name="repo",
                branch="main",
                enforce_admins=True,
            )

            assert "GitHub token not configured" in result
            assert "❌" in result

    @pytest.mark.asyncio
    async def test_update_connection_error(self):
        """Test that connection errors are handled gracefully."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ConnectionError(
                "Network timeout"
            )

            result = await github_update_branch_protection(
                repo_owner="owner",
                repo_name="repo",
                branch="main",
                enforce_admins=True,
            )

            assert "Network connection failed" in result
            assert "Network timeout" in result

    @pytest.mark.asyncio
    async def test_update_unexpected_error(self):
        """Test that unexpected errors are caught and reported."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = RuntimeError(
                "Unexpected error"
            )

            result = await github_update_branch_protection(
                repo_owner="owner",
                repo_name="repo",
                branch="main",
                enforce_admins=True,
            )

            assert "Error updating branch protection" in result
            assert "Unexpected error" in result


class TestGitHubDeleteBranchProtection:
    """Test github_delete_branch_protection function."""

    @pytest.mark.asyncio
    async def test_successful_delete(self):
        """Test successfully deleting branch protection rules."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 204
        mock_client.delete = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_delete_branch_protection(
                repo_owner="owner",
                repo_name="repo",
                branch="main",
            )

            # Verify API call
            mock_client.delete.assert_called_once_with(
                "/repos/owner/repo/branches/main/protection"
            )

            assert "✅ Successfully deleted branch protection for owner/repo:main" in result

    @pytest.mark.asyncio
    async def test_delete_not_found_404(self):
        """Test deleting non-existent branch protection returns 404."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 404
        mock_client.delete = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_delete_branch_protection(
                repo_owner="owner",
                repo_name="repo",
                branch="non-existent-branch",
            )

            assert "❌ Branch protection not found for non-existent-branch" in result

    @pytest.mark.asyncio
    async def test_delete_api_error_403_forbidden(self):
        """Test handling of 403 Forbidden error (insufficient permissions)."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 403
        mock_response.text = AsyncMock(return_value="Forbidden - admin access required")
        mock_client.delete = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_delete_branch_protection(
                repo_owner="owner",
                repo_name="repo",
                branch="main",
            )

            assert "Failed to delete branch protection" in result
            assert "403" in result
            assert "Forbidden - admin access required" in result

    @pytest.mark.asyncio
    async def test_delete_authentication_error(self):
        """Test that authentication errors are handled properly."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ValueError(
                "GitHub token not configured"
            )

            result = await github_delete_branch_protection(
                repo_owner="owner",
                repo_name="repo",
                branch="main",
            )

            assert "GitHub token not configured" in result
            assert "❌" in result

    @pytest.mark.asyncio
    async def test_delete_connection_error(self):
        """Test that connection errors are handled gracefully."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ConnectionError(
                "Network timeout"
            )

            result = await github_delete_branch_protection(
                repo_owner="owner",
                repo_name="repo",
                branch="main",
            )

            assert "Network connection failed" in result
            assert "Network timeout" in result

    @pytest.mark.asyncio
    async def test_delete_unexpected_error(self):
        """Test that unexpected errors are caught and reported."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = RuntimeError(
                "Unexpected error"
            )

            result = await github_delete_branch_protection(
                repo_owner="owner",
                repo_name="repo",
                branch="main",
            )

            assert "Error deleting branch protection" in result
            assert "Unexpected error" in result


class TestBranchNameValidation:
    """Test Pydantic model validators for branch names."""

    def test_valid_branch_names(self):
        """Test that valid branch names pass validation."""
        valid_branches = [
            "main",
            "develop",
            "feature/new-feature",
            "bugfix/issue-123",
            "release/v1.0.0",
            "hotfix/urgent-fix",
            "user/john/experimental",
        ]

        for branch in valid_branches:
            # Test GitHubGetBranchProtection
            model = GitHubGetBranchProtection(
                repo_owner="owner",
                repo_name="repo",
                branch=branch,
            )
            assert model.branch == branch

            # Test GitHubUpdateBranchProtection
            model = GitHubUpdateBranchProtection(
                repo_owner="owner",
                repo_name="repo",
                branch=branch,
            )
            assert model.branch == branch

            # Test GitHubDeleteBranchProtection
            model = GitHubDeleteBranchProtection(
                repo_owner="owner",
                repo_name="repo",
                branch=branch,
            )
            assert model.branch == branch

    def test_invalid_branch_starting_with_dash(self):
        """Test that branch names starting with - are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            GitHubGetBranchProtection(
                repo_owner="owner",
                repo_name="repo",
                branch="-invalid-branch",
            )
        assert "Invalid branch name" in str(exc_info.value)
        assert "start with '-'" in str(exc_info.value)

    def test_invalid_branch_containing_double_dots(self):
        """Test that branch names containing .. are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            GitHubUpdateBranchProtection(
                repo_owner="owner",
                repo_name="repo",
                branch="feature..invalid",
            )
        assert "Invalid branch name" in str(exc_info.value)
        assert "contain '..'" in str(exc_info.value)

    def test_invalid_branch_containing_tilde(self):
        """Test that branch names containing ~ are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            GitHubDeleteBranchProtection(
                repo_owner="owner",
                repo_name="repo",
                branch="feature~invalid",
            )
        assert "Invalid branch name" in str(exc_info.value)
        assert "'~'" in str(exc_info.value)

    def test_invalid_branch_containing_caret(self):
        """Test that branch names containing ^ are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            GitHubGetBranchProtection(
                repo_owner="owner",
                repo_name="repo",
                branch="feature^invalid",
            )
        assert "Invalid branch name" in str(exc_info.value)
        assert "'^'" in str(exc_info.value)

    def test_invalid_branch_containing_colon(self):
        """Test that branch names containing : are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            GitHubUpdateBranchProtection(
                repo_owner="owner",
                repo_name="repo",
                branch="feature:invalid",
            )
        assert "Invalid branch name" in str(exc_info.value)
        assert "':'" in str(exc_info.value)

    def test_invalid_branch_containing_backslash(self):
        """Test that branch names containing \\ are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            GitHubDeleteBranchProtection(
                repo_owner="owner",
                repo_name="repo",
                branch="feature\\invalid",
            )
        assert "Invalid branch name" in str(exc_info.value)
        # The error message contains a single backslash in the display
        assert "'\\\\" in str(exc_info.value) or "'\\" in str(exc_info.value)

    def test_invalid_branch_containing_at_brace(self):
        """Test that branch names containing @{ are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            GitHubGetBranchProtection(
                repo_owner="owner",
                repo_name="repo",
                branch="feature@{invalid",
            )
        assert "Invalid branch name" in str(exc_info.value)
        # The error message may contain '@{' or '@{{' depending on escaping
        assert "'@{" in str(exc_info.value)

    def test_invalid_branch_ending_with_lock(self):
        """Test that branch names ending with .lock are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            GitHubUpdateBranchProtection(
                repo_owner="owner",
                repo_name="repo",
                branch="feature.lock",
            )
        assert "Invalid branch name" in str(exc_info.value)
        assert "end with '/' or '.lock'" in str(exc_info.value)

    def test_invalid_branch_starting_with_slash(self):
        """Test that branch names starting with / are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            GitHubDeleteBranchProtection(
                repo_owner="owner",
                repo_name="repo",
                branch="/invalid-branch",
            )
        assert "Invalid branch name" in str(exc_info.value)
        assert "start with '-' or '/'" in str(exc_info.value)

    def test_invalid_branch_ending_with_slash(self):
        """Test that branch names ending with / are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            GitHubGetBranchProtection(
                repo_owner="owner",
                repo_name="repo",
                branch="invalid-branch/",
            )
        assert "Invalid branch name" in str(exc_info.value)
        assert "end with '/' or '.lock'" in str(exc_info.value)

    def test_invalid_empty_branch_name(self):
        """Test that empty branch names are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            GitHubUpdateBranchProtection(
                repo_owner="owner",
                repo_name="repo",
                branch="",
            )
        assert "branch name cannot be empty" in str(exc_info.value)

    def test_invalid_whitespace_only_branch_name(self):
        """Test that whitespace-only branch names are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            GitHubDeleteBranchProtection(
                repo_owner="owner",
                repo_name="repo",
                branch="   ",
            )
        assert "branch name cannot be empty" in str(exc_info.value)

    def test_multiple_invalid_patterns(self):
        """Test branch names with multiple invalid patterns."""
        invalid_branches = [
            "-feature..invalid~branch",
            "feature^branch:invalid",
            "branch\\with@{multiple",
            "/start/and/end/",
        ]

        for branch in invalid_branches:
            with pytest.raises(ValidationError) as exc_info:
                GitHubGetBranchProtection(
                    repo_owner="owner",
                    repo_name="repo",
                    branch=branch,
                )
            assert "Invalid branch name" in str(exc_info.value)
