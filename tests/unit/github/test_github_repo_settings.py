"""
Unit tests for GitHub repository settings functions.

Tests the GitHub repository settings retrieval and update functionality including:
- Successful repository settings retrieval with all fields
- 404 error handling for non-existent repositories
- Authentication error handling
- Connection error handling
- Successful repository settings update with various configurations
- Validation errors for invalid settings
- Pydantic model validators for GitHubUpdateRepoSettings
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from src.mcp_server_git.github.api import (
    github_get_repo_settings,
    github_update_repo_settings,
)
from src.mcp_server_git.github.models import GitHubUpdateRepoSettings


class TestGitHubGetRepoSettings:
    """Test github_get_repo_settings function."""

    @pytest.mark.asyncio
    async def test_successful_repo_settings_retrieval(self):
        """Test retrieving complete repository settings with all fields."""
        mock_client = MagicMock()

        # Mock successful repository settings response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "name": "test-repo",
                "description": "A test repository for unit testing",
                "visibility": "public",
                "default_branch": "main",
                "homepage": "https://example.com",
                "has_issues": True,
                "has_wiki": True,
                "has_projects": True,
                "has_discussions": False,
                "allow_merge_commit": True,
                "allow_squash_merge": True,
                "allow_rebase_merge": False,
                "allow_auto_merge": True,
                "delete_branch_on_merge": True,
                "allow_update_branch": False,
                "squash_merge_commit_title": "PR_TITLE",
                "squash_merge_commit_message": "COMMIT_MESSAGES",
                "merge_commit_title": "PR_TITLE",
                "merge_commit_message": "PR_BODY",
                "archived": False,
                "web_commit_signoff_required": False,
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.repos.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_repo_settings(
                repo_owner="testowner",
                repo_name="test-repo",
            )

            # Verify all sections are present
            assert "Repository Settings for testowner/test-repo" in result
            assert "📋 Basic Information:" in result
            assert "Name: test-repo" in result
            assert "Description: A test repository for unit testing" in result
            assert "Visibility: public" in result
            assert "Default Branch: main" in result
            assert "Homepage: https://example.com" in result

            # Verify features section
            assert "🔧 Features:" in result
            assert "Issues: ✅" in result
            assert "Wiki: ✅" in result
            assert "Projects: ✅" in result
            assert "Discussions: ❌" in result

            # Verify merge settings
            assert "🔀 Merge Settings:" in result
            assert "Allow Merge Commits: ✅" in result
            assert "Allow Squash Merging: ✅" in result
            assert "Allow Rebase Merging: ❌" in result

    @pytest.mark.asyncio
    async def test_repo_settings_with_minimal_fields(self):
        """Test retrieving repository settings with minimal/missing fields."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "name": "minimal-repo",
                "description": None,
                "visibility": "private",
                "default_branch": "master",
                "homepage": None,
                "has_issues": False,
                "has_wiki": False,
                "has_projects": False,
                "has_discussions": False,
                "allow_merge_commit": False,
                "allow_squash_merge": False,
                "allow_rebase_merge": False,
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.repos.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_repo_settings(
                repo_owner="testowner",
                repo_name="minimal-repo",
            )

            assert "Name: minimal-repo" in result
            assert "Description: (none)" in result
            assert "Visibility: private" in result
            assert "Homepage: (none)" in result

    @pytest.mark.asyncio
    async def test_repository_not_found_404_error(self):
        """Test that 404 error is handled properly for non-existent repository."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 404
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.repos.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_repo_settings(
                repo_owner="nonexistent",
                repo_name="fake-repo",
            )

            assert "❌ Repository nonexistent/fake-repo not found" in result

    @pytest.mark.asyncio
    async def test_authentication_error(self):
        """Test that authentication errors are handled properly."""
        with patch(
            "src.mcp_server_git.github.repos.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ValueError(
                "GitHub token not configured"
            )

            result = await github_get_repo_settings(
                repo_owner="testowner",
                repo_name="test-repo",
            )

            assert "❌ GitHub token not configured" in result

    @pytest.mark.asyncio
    async def test_connection_error(self):
        """Test that connection errors are handled gracefully."""
        with patch(
            "src.mcp_server_git.github.repos.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ConnectionError(
                "Network timeout"
            )

            result = await github_get_repo_settings(
                repo_owner="testowner",
                repo_name="test-repo",
            )

            assert "❌ Network connection failed" in result
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
            "src.mcp_server_git.github.repos.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_repo_settings(
                repo_owner="testowner",
                repo_name="test-repo",
            )

            assert "❌ Failed to get repository settings" in result
            assert "500" in result
            assert "Internal Server Error" in result

    @pytest.mark.asyncio
    async def test_unexpected_error_handling(self):
        """Test that unexpected errors are caught and reported."""
        with patch(
            "src.mcp_server_git.github.repos.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = RuntimeError(
                "Unexpected error occurred"
            )

            result = await github_get_repo_settings(
                repo_owner="testowner",
                repo_name="test-repo",
            )

            assert "❌ Error getting repository settings" in result
            assert "Unexpected error occurred" in result


class TestGitHubUpdateRepoSettings:
    """Test github_update_repo_settings function."""

    @pytest.mark.asyncio
    async def test_successful_basic_settings_update(self):
        """Test updating basic repository settings (description, homepage)."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "full_name": "testowner/test-repo",
                "description": "Updated description",
                "homepage": "https://new-homepage.com",
            }
        )
        mock_client.patch = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.repos.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_repo_settings(
                repo_owner="testowner",
                repo_name="test-repo",
                description="Updated description",
                homepage="https://new-homepage.com",
            )

            assert "✅ Successfully updated repository settings" in result
            assert "testowner/test-repo" in result
            assert "description" in result
            assert "homepage" in result

    @pytest.mark.asyncio
    async def test_successful_visibility_update(self):
        """Test updating repository visibility settings."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "full_name": "testowner/test-repo",
                "visibility": "private",
            }
        )
        mock_client.patch = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.repos.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_repo_settings(
                repo_owner="testowner",
                repo_name="test-repo",
                visibility="private",
            )

            assert "✅ Successfully updated repository settings" in result
            assert "visibility" in result

    @pytest.mark.asyncio
    async def test_successful_feature_toggles_update(self):
        """Test updating repository feature toggles (issues, wiki, projects)."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "full_name": "testowner/test-repo",
                "has_issues": False,
                "has_wiki": True,
                "has_projects": False,
                "has_discussions": True,
            }
        )
        mock_client.patch = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.repos.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_repo_settings(
                repo_owner="testowner",
                repo_name="test-repo",
                has_issues=False,
                has_wiki=True,
                has_projects=False,
                has_discussions=True,
            )

            assert "✅ Successfully updated repository settings" in result
            assert "has_issues" in result
            assert "has_wiki" in result
            assert "has_projects" in result
            assert "has_discussions" in result

    @pytest.mark.asyncio
    async def test_successful_merge_settings_update(self):
        """Test updating repository merge settings."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "full_name": "testowner/test-repo",
                "allow_squash_merge": True,
                "allow_merge_commit": False,
                "allow_rebase_merge": True,
                "allow_auto_merge": True,
                "delete_branch_on_merge": True,
            }
        )
        mock_client.patch = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.repos.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_repo_settings(
                repo_owner="testowner",
                repo_name="test-repo",
                allow_squash_merge=True,
                allow_merge_commit=False,
                allow_rebase_merge=True,
                allow_auto_merge=True,
                delete_branch_on_merge=True,
            )

            assert "✅ Successfully updated repository settings" in result
            assert "allow_squash_merge" in result
            assert "allow_merge_commit" in result
            assert "allow_rebase_merge" in result

    @pytest.mark.asyncio
    async def test_successful_squash_merge_commit_options_update(self):
        """Test updating squash merge commit title and message options."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "full_name": "testowner/test-repo",
                "squash_merge_commit_title": "COMMIT_OR_PR_TITLE",
                "squash_merge_commit_message": "BLANK",
            }
        )
        mock_client.patch = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.repos.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_repo_settings(
                repo_owner="testowner",
                repo_name="test-repo",
                squash_merge_commit_title="COMMIT_OR_PR_TITLE",
                squash_merge_commit_message="BLANK",
            )

            assert "✅ Successfully updated repository settings" in result
            assert "squash_merge_commit_title" in result
            assert "squash_merge_commit_message" in result

    @pytest.mark.asyncio
    async def test_successful_merge_commit_options_update(self):
        """Test updating merge commit title and message options."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "full_name": "testowner/test-repo",
                "merge_commit_title": "MERGE_MESSAGE",
                "merge_commit_message": "PR_TITLE",
            }
        )
        mock_client.patch = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.repos.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_repo_settings(
                repo_owner="testowner",
                repo_name="test-repo",
                merge_commit_title="MERGE_MESSAGE",
                merge_commit_message="PR_TITLE",
            )

            assert "✅ Successfully updated repository settings" in result
            assert "merge_commit_title" in result
            assert "merge_commit_message" in result

    @pytest.mark.asyncio
    async def test_no_parameters_provided(self):
        """Test that providing no update parameters returns a warning."""
        mock_client = MagicMock()
        mock_client.patch = AsyncMock()

        with patch(
            "src.mcp_server_git.github.repos.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_repo_settings(
                repo_owner="testowner",
                repo_name="test-repo",
            )

            assert "⚠️ No update parameters provided" in result
            # Ensure no API call was made
            mock_client.patch.assert_not_called()

    @pytest.mark.asyncio
    async def test_authentication_error_on_update(self):
        """Test that authentication errors are handled properly during update."""
        with patch(
            "src.mcp_server_git.github.repos.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ValueError(
                "GitHub token not configured"
            )

            result = await github_update_repo_settings(
                repo_owner="testowner",
                repo_name="test-repo",
                description="New description",
            )

            assert "❌ GitHub token not configured" in result

    @pytest.mark.asyncio
    async def test_connection_error_on_update(self):
        """Test that connection errors are handled gracefully during update."""
        with patch(
            "src.mcp_server_git.github.repos.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ConnectionError(
                "Network timeout"
            )

            result = await github_update_repo_settings(
                repo_owner="testowner",
                repo_name="test-repo",
                description="New description",
            )

            assert "❌ Network connection failed" in result
            assert "Network timeout" in result

    @pytest.mark.asyncio
    async def test_api_error_on_update(self):
        """Test that API errors are reported properly during update."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 422
        mock_response.text = AsyncMock(
            return_value="Unprocessable Entity: Invalid field value"
        )
        mock_client.patch = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.repos.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_repo_settings(
                repo_owner="testowner",
                repo_name="test-repo",
                description="New description",
            )

            assert "❌ Failed to update repository settings" in result
            assert "422" in result
            assert "Unprocessable Entity" in result

    @pytest.mark.asyncio
    async def test_unexpected_error_on_update(self):
        """Test that unexpected errors are caught and reported during update."""
        with patch(
            "src.mcp_server_git.github.repos.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = RuntimeError(
                "Unexpected error occurred"
            )

            result = await github_update_repo_settings(
                repo_owner="testowner",
                repo_name="test-repo",
                description="New description",
            )

            assert "❌ Error updating repository settings" in result
            assert "Unexpected error occurred" in result


class TestGitHubUpdateRepoSettingsModel:
    """Test Pydantic model validators for GitHubUpdateRepoSettings."""

    def test_valid_visibility_public(self):
        """Test that 'public' visibility is valid."""
        model = GitHubUpdateRepoSettings(
            repo_owner="testowner",
            repo_name="test-repo",
            visibility="public",
        )
        assert model.visibility == "public"

    def test_valid_visibility_private(self):
        """Test that 'private' visibility is valid."""
        model = GitHubUpdateRepoSettings(
            repo_owner="testowner",
            repo_name="test-repo",
            visibility="private",
        )
        assert model.visibility == "private"

    def test_valid_visibility_internal(self):
        """Test that 'internal' visibility is valid."""
        model = GitHubUpdateRepoSettings(
            repo_owner="testowner",
            repo_name="test-repo",
            visibility="internal",
        )
        assert model.visibility == "internal"

    def test_invalid_visibility(self):
        """Test that invalid visibility value raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            GitHubUpdateRepoSettings(
                repo_owner="testowner",
                repo_name="test-repo",
                visibility="invalid-visibility",
            )
        assert "visibility must be one of" in str(exc_info.value)

    def test_valid_squash_merge_commit_title_pr_title(self):
        """Test that 'PR_TITLE' is valid for squash_merge_commit_title."""
        model = GitHubUpdateRepoSettings(
            repo_owner="testowner",
            repo_name="test-repo",
            squash_merge_commit_title="PR_TITLE",
        )
        assert model.squash_merge_commit_title == "PR_TITLE"

    def test_valid_squash_merge_commit_title_commit_or_pr_title(self):
        """Test that 'COMMIT_OR_PR_TITLE' is valid for squash_merge_commit_title."""
        model = GitHubUpdateRepoSettings(
            repo_owner="testowner",
            repo_name="test-repo",
            squash_merge_commit_title="COMMIT_OR_PR_TITLE",
        )
        assert model.squash_merge_commit_title == "COMMIT_OR_PR_TITLE"

    def test_invalid_squash_merge_commit_title(self):
        """Test that invalid squash_merge_commit_title raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            GitHubUpdateRepoSettings(
                repo_owner="testowner",
                repo_name="test-repo",
                squash_merge_commit_title="INVALID_VALUE",
            )
        assert "squash_merge_commit_title must be one of" in str(exc_info.value)

    def test_valid_squash_merge_commit_message_pr_body(self):
        """Test that 'PR_BODY' is valid for squash_merge_commit_message."""
        model = GitHubUpdateRepoSettings(
            repo_owner="testowner",
            repo_name="test-repo",
            squash_merge_commit_message="PR_BODY",
        )
        assert model.squash_merge_commit_message == "PR_BODY"

    def test_valid_squash_merge_commit_message_commit_messages(self):
        """Test that 'COMMIT_MESSAGES' is valid for squash_merge_commit_message."""
        model = GitHubUpdateRepoSettings(
            repo_owner="testowner",
            repo_name="test-repo",
            squash_merge_commit_message="COMMIT_MESSAGES",
        )
        assert model.squash_merge_commit_message == "COMMIT_MESSAGES"

    def test_valid_squash_merge_commit_message_blank(self):
        """Test that 'BLANK' is valid for squash_merge_commit_message."""
        model = GitHubUpdateRepoSettings(
            repo_owner="testowner",
            repo_name="test-repo",
            squash_merge_commit_message="BLANK",
        )
        assert model.squash_merge_commit_message == "BLANK"

    def test_invalid_squash_merge_commit_message(self):
        """Test that invalid squash_merge_commit_message raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            GitHubUpdateRepoSettings(
                repo_owner="testowner",
                repo_name="test-repo",
                squash_merge_commit_message="INVALID_VALUE",
            )
        assert "squash_merge_commit_message must be one of" in str(exc_info.value)

    def test_valid_merge_commit_title_pr_title(self):
        """Test that 'PR_TITLE' is valid for merge_commit_title."""
        model = GitHubUpdateRepoSettings(
            repo_owner="testowner",
            repo_name="test-repo",
            merge_commit_title="PR_TITLE",
        )
        assert model.merge_commit_title == "PR_TITLE"

    def test_valid_merge_commit_title_merge_message(self):
        """Test that 'MERGE_MESSAGE' is valid for merge_commit_title."""
        model = GitHubUpdateRepoSettings(
            repo_owner="testowner",
            repo_name="test-repo",
            merge_commit_title="MERGE_MESSAGE",
        )
        assert model.merge_commit_title == "MERGE_MESSAGE"

    def test_invalid_merge_commit_title(self):
        """Test that invalid merge_commit_title raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            GitHubUpdateRepoSettings(
                repo_owner="testowner",
                repo_name="test-repo",
                merge_commit_title="INVALID_VALUE",
            )
        assert "merge_commit_title must be one of" in str(exc_info.value)

    def test_valid_merge_commit_message_pr_body(self):
        """Test that 'PR_BODY' is valid for merge_commit_message."""
        model = GitHubUpdateRepoSettings(
            repo_owner="testowner",
            repo_name="test-repo",
            merge_commit_message="PR_BODY",
        )
        assert model.merge_commit_message == "PR_BODY"

    def test_valid_merge_commit_message_pr_title(self):
        """Test that 'PR_TITLE' is valid for merge_commit_message."""
        model = GitHubUpdateRepoSettings(
            repo_owner="testowner",
            repo_name="test-repo",
            merge_commit_message="PR_TITLE",
        )
        assert model.merge_commit_message == "PR_TITLE"

    def test_valid_merge_commit_message_blank(self):
        """Test that 'BLANK' is valid for merge_commit_message."""
        model = GitHubUpdateRepoSettings(
            repo_owner="testowner",
            repo_name="test-repo",
            merge_commit_message="BLANK",
        )
        assert model.merge_commit_message == "BLANK"

    def test_invalid_merge_commit_message(self):
        """Test that invalid merge_commit_message raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            GitHubUpdateRepoSettings(
                repo_owner="testowner",
                repo_name="test-repo",
                merge_commit_message="INVALID_VALUE",
            )
        assert "merge_commit_message must be one of" in str(exc_info.value)

    def test_none_values_are_valid(self):
        """Test that None values pass validation for optional fields."""
        model = GitHubUpdateRepoSettings(
            repo_owner="testowner",
            repo_name="test-repo",
            visibility=None,
            squash_merge_commit_title=None,
            squash_merge_commit_message=None,
            merge_commit_title=None,
            merge_commit_message=None,
        )
        assert model.visibility is None
        assert model.squash_merge_commit_title is None
        assert model.squash_merge_commit_message is None
        assert model.merge_commit_title is None
        assert model.merge_commit_message is None

    def test_model_with_all_valid_fields(self):
        """Test creating model with all valid fields populated."""
        model = GitHubUpdateRepoSettings(
            repo_owner="testowner",
            repo_name="test-repo",
            description="Test description",
            homepage="https://example.com",
            private=True,
            visibility="private",
            has_issues=True,
            has_projects=False,
            has_wiki=True,
            has_discussions=False,
            allow_squash_merge=True,
            allow_merge_commit=False,
            allow_rebase_merge=True,
            allow_auto_merge=False,
            delete_branch_on_merge=True,
            allow_update_branch=False,
            squash_merge_commit_title="PR_TITLE",
            squash_merge_commit_message="COMMIT_MESSAGES",
            merge_commit_title="MERGE_MESSAGE",
            merge_commit_message="PR_BODY",
            archived=False,
            web_commit_signoff_required=True,
        )

        assert model.repo_owner == "testowner"
        assert model.repo_name == "test-repo"
        assert model.description == "Test description"
        assert model.visibility == "private"
        assert model.has_issues is True
        assert model.allow_squash_merge is True
        assert model.squash_merge_commit_title == "PR_TITLE"
        assert model.merge_commit_message == "PR_BODY"
