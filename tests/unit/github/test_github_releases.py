"""
Unit tests for GitHub release management functions.

Tests the GitHub release management functionality including:
- Creating releases with various configurations
- Retrieving releases by ID or tag
- Listing releases with pagination
- Updating releases with different field combinations
- Deleting releases
- Uploading release assets
- Listing release assets
- Deleting release assets
- Pydantic model validators for GitHubGetRelease
- Authentication and connection error handling
- API error responses (404, 422, etc.)
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest
from pydantic import ValidationError

from src.mcp_server_git.github.api import (
    github_create_release,
    github_delete_release,
    github_delete_release_asset,
    github_get_release,
    github_list_release_assets,
    github_list_releases,
    github_update_release,
    github_upload_release_asset,
)
from src.mcp_server_git.github.models import GitHubGetRelease


class TestGitHubCreateRelease:
    """Test github_create_release function."""

    @pytest.mark.asyncio
    async def test_create_release_success(self):
        """Test successfully creating a release with basic parameters."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 201
        mock_response.json = AsyncMock(
            return_value={
                "id": 12345,
                "tag_name": "v1.0.0",
                "name": "Version 1.0.0",
                "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
            }
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_create_release(
                repo_owner="owner",
                repo_name="repo",
                tag_name="v1.0.0",
                name="Version 1.0.0",
                body="Release notes here",
            )

            assert "✅ Release v1.0.0 created successfully" in result
            assert "https://github.com/owner/repo/releases/tag/v1.0.0" in result
            assert "12345" in result
            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_release_draft(self):
        """Test creating a draft release."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 201
        mock_response.json = AsyncMock(
            return_value={
                "id": 12345,
                "tag_name": "v2.0.0",
                "html_url": "https://github.com/owner/repo/releases/tag/v2.0.0",
            }
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_create_release(
                repo_owner="owner",
                repo_name="repo",
                tag_name="v2.0.0",
                draft=True,
            )

            assert "✅ Release v2.0.0 created successfully" in result
            assert "(draft)" in result

    @pytest.mark.asyncio
    async def test_create_release_prerelease(self):
        """Test creating a pre-release."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 201
        mock_response.json = AsyncMock(
            return_value={
                "id": 12345,
                "tag_name": "v3.0.0-beta",
                "html_url": "https://github.com/owner/repo/releases/tag/v3.0.0-beta",
            }
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_create_release(
                repo_owner="owner",
                repo_name="repo",
                tag_name="v3.0.0-beta",
                prerelease=True,
            )

            assert "✅ Release v3.0.0-beta created successfully" in result
            assert "(pre-release)" in result

    @pytest.mark.asyncio
    async def test_create_release_draft_and_prerelease(self):
        """Test creating a draft pre-release."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 201
        mock_response.json = AsyncMock(
            return_value={
                "id": 12345,
                "tag_name": "v4.0.0-rc",
                "html_url": "https://github.com/owner/repo/releases/tag/v4.0.0-rc",
            }
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_create_release(
                repo_owner="owner",
                repo_name="repo",
                tag_name="v4.0.0-rc",
                draft=True,
                prerelease=True,
            )

            assert "✅ Release v4.0.0-rc created successfully" in result
            assert "(draft, pre-release)" in result

    @pytest.mark.asyncio
    async def test_create_release_repo_not_found_404(self):
        """Test that 404 error is handled for non-existent repository."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 404
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_create_release(
                repo_owner="nonexistent",
                repo_name="fake-repo",
                tag_name="v1.0.0",
            )

            assert "❌ Repository nonexistent/fake-repo not found" in result

    @pytest.mark.asyncio
    async def test_create_release_validation_error_422(self):
        """Test that 422 validation error is handled properly."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 422
        mock_response.json = AsyncMock(
            return_value={
                "message": "Validation Failed: Tag already exists",
            }
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_create_release(
                repo_owner="owner",
                repo_name="repo",
                tag_name="v1.0.0",
            )

            assert "❌ Failed to create release" in result
            assert "Tag already exists" in result

    @pytest.mark.asyncio
    async def test_create_release_auth_error(self):
        """Test that authentication errors are handled properly."""
        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ValueError(
                "GitHub token not configured"
            )

            result = await github_create_release(
                repo_owner="owner",
                repo_name="repo",
                tag_name="v1.0.0",
            )

            assert "❌ GitHub token not configured" in result

    @pytest.mark.asyncio
    async def test_create_release_connection_error(self):
        """Test that connection errors are handled gracefully."""
        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ConnectionError(
                "Network timeout"
            )

            result = await github_create_release(
                repo_owner="owner",
                repo_name="repo",
                tag_name="v1.0.0",
            )

            assert "❌ Network connection failed" in result
            assert "Network timeout" in result


class TestGitHubGetRelease:
    """Test github_get_release function."""

    @pytest.mark.asyncio
    async def test_get_release_by_id_success(self):
        """Test successfully retrieving a release by ID."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "id": 12345,
                "tag_name": "v1.0.0",
                "name": "Version 1.0.0",
                "body": "Release notes here",
                "draft": False,
                "prerelease": False,
                "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                "created_at": "2024-01-01T00:00:00Z",
                "published_at": "2024-01-01T01:00:00Z",
                "author": {"login": "testuser"},
                "assets": [
                    {"name": "app.zip", "size": 1024},
                    {"name": "app.tar.gz", "size": 2048},
                ],
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_release(
                repo_owner="owner",
                repo_name="repo",
                release_id=12345,
            )

            assert "Release Information for owner/repo" in result
            assert "📦 Tag: v1.0.0" in result
            assert "📋 Name: Version 1.0.0" in result
            assert "Release notes here" in result
            assert "👤 Author: testuser" in result
            assert "📎 Assets (2)" in result
            assert "app.zip" in result
            assert "app.tar.gz" in result

    @pytest.mark.asyncio
    async def test_get_release_by_tag_success(self):
        """Test successfully retrieving a release by tag."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "id": 12345,
                "tag_name": "v2.0.0",
                "name": "Version 2.0.0",
                "body": None,
                "draft": False,
                "prerelease": False,
                "html_url": "https://github.com/owner/repo/releases/tag/v2.0.0",
                "created_at": "2024-02-01T00:00:00Z",
                "published_at": "2024-02-01T01:00:00Z",
                "author": {"login": "testuser"},
                "assets": [],
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_release(
                repo_owner="owner",
                repo_name="repo",
                tag="v2.0.0",
            )

            assert "Release Information for owner/repo" in result
            assert "📦 Tag: v2.0.0" in result
            assert "📎 Assets: None" in result

    @pytest.mark.asyncio
    async def test_get_release_draft_status(self):
        """Test that draft status is displayed correctly."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "id": 12345,
                "tag_name": "v3.0.0",
                "name": "Version 3.0.0",
                "draft": True,
                "prerelease": False,
                "html_url": "https://github.com/owner/repo/releases/tag/v3.0.0",
                "created_at": "2024-03-01T00:00:00Z",
                "published_at": None,
                "author": {"login": "testuser"},
                "assets": [],
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_release(
                repo_owner="owner",
                repo_name="repo",
                release_id=12345,
            )

            assert "🏷️  Status: draft" in result
            assert "📅 Published: Not published" in result

    @pytest.mark.asyncio
    async def test_get_release_prerelease_status(self):
        """Test that pre-release status is displayed correctly."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "id": 12345,
                "tag_name": "v4.0.0-beta",
                "name": "Version 4.0.0 Beta",
                "draft": False,
                "prerelease": True,
                "html_url": "https://github.com/owner/repo/releases/tag/v4.0.0-beta",
                "created_at": "2024-04-01T00:00:00Z",
                "published_at": "2024-04-01T01:00:00Z",
                "author": {"login": "testuser"},
                "assets": [],
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_release(
                repo_owner="owner",
                repo_name="repo",
                tag="v4.0.0-beta",
            )

            assert "🏷️  Status: pre-release" in result

    @pytest.mark.asyncio
    async def test_get_release_not_found_404(self):
        """Test that 404 error is handled for non-existent release."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 404
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_release(
                repo_owner="owner",
                repo_name="repo",
                release_id=99999,
            )

            assert "❌ Release ID 99999 not found" in result

    @pytest.mark.asyncio
    async def test_get_release_auth_error(self):
        """Test that authentication errors are handled properly."""
        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ValueError(
                "GitHub token not configured"
            )

            result = await github_get_release(
                repo_owner="owner",
                repo_name="repo",
                release_id=12345,
            )

            assert "❌ GitHub token not configured" in result


class TestGitHubListReleases:
    """Test github_list_releases function."""

    @pytest.mark.asyncio
    async def test_list_releases_success(self):
        """Test successfully listing releases."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {"Link": ""}
        mock_response.json = AsyncMock(
            return_value=[
                {
                    "tag_name": "v1.0.0",
                    "name": "Version 1.0.0",
                    "draft": False,
                    "prerelease": False,
                    "created_at": "2024-01-01T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                },
                {
                    "tag_name": "v0.9.0",
                    "name": None,
                    "draft": False,
                    "prerelease": True,
                    "created_at": "2023-12-01T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v0.9.0",
                },
            ]
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_list_releases(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "Releases for owner/repo" in result
            assert "📦 v1.0.0: Version 1.0.0" in result
            assert "📦 v0.9.0: v0.9.0" in result
            assert "[pre-release]" in result
            assert "2024-01-01" in result
            assert "2023-12-01" in result

    @pytest.mark.asyncio
    async def test_list_releases_empty(self):
        """Test listing releases when none exist."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=[])
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_list_releases(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "No releases found for owner/repo" in result

    @pytest.mark.asyncio
    async def test_list_releases_with_pagination(self):
        """Test listing releases with pagination info."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {
            "Link": '<https://api.github.com/repos/owner/repo/releases?page=3>; rel="next"'
        }
        mock_response.json = AsyncMock(
            return_value=[
                {
                    "tag_name": "v1.0.0",
                    "name": "Version 1.0.0",
                    "draft": False,
                    "prerelease": False,
                    "created_at": "2024-01-01T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                }
            ]
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_list_releases(
                repo_owner="owner",
                repo_name="repo",
                page=2,
            )

            assert "📄 Page 2 (use page parameter to see more)" in result

    @pytest.mark.asyncio
    async def test_list_releases_auth_error(self):
        """Test that authentication errors are handled properly."""
        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ValueError(
                "GitHub token not configured"
            )

            result = await github_list_releases(
                repo_owner="owner",
                repo_name="repo",
            )

            assert "❌ GitHub token not configured" in result


class TestGitHubUpdateRelease:
    """Test github_update_release function."""

    @pytest.mark.asyncio
    async def test_update_release_success(self):
        """Test successfully updating a release."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "tag_name": "v1.0.0",
                "name": "Updated Release Title",
                "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
            }
        )
        mock_client.patch = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_release(
                repo_owner="owner",
                repo_name="repo",
                release_id=12345,
                name="Updated Release Title",
                body="Updated release notes",
            )

            assert "✅ Release v1.0.0 (ID: 12345) updated successfully" in result
            assert "https://github.com/owner/repo/releases/tag/v1.0.0" in result

    @pytest.mark.asyncio
    async def test_update_release_publish_draft(self):
        """Test publishing a draft release."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "tag_name": "v2.0.0",
                "name": "Version 2.0.0",
                "html_url": "https://github.com/owner/repo/releases/tag/v2.0.0",
            }
        )
        mock_client.patch = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_release(
                repo_owner="owner",
                repo_name="repo",
                release_id=12345,
                draft=False,
            )

            assert "✅ Release v2.0.0 (ID: 12345) updated successfully" in result

    @pytest.mark.asyncio
    async def test_update_release_no_fields(self):
        """Test that providing no update fields returns warning."""
        mock_client = MagicMock()
        mock_client.patch = AsyncMock()

        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_release(
                repo_owner="owner",
                repo_name="repo",
                release_id=12345,
            )

            assert "❌ No fields provided to update" in result
            mock_client.patch.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_release_not_found_404(self):
        """Test that 404 error is handled for non-existent release."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 404
        mock_client.patch = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_update_release(
                repo_owner="owner",
                repo_name="repo",
                release_id=99999,
                name="New Name",
            )

            assert "❌ Release 99999 not found" in result

    @pytest.mark.asyncio
    async def test_update_release_auth_error(self):
        """Test that authentication errors are handled properly."""
        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ValueError(
                "GitHub token not configured"
            )

            result = await github_update_release(
                repo_owner="owner",
                repo_name="repo",
                release_id=12345,
                name="New Name",
            )

            assert "❌ GitHub token not configured" in result


class TestGitHubDeleteRelease:
    """Test github_delete_release function."""

    @pytest.mark.asyncio
    async def test_delete_release_success(self):
        """Test successfully deleting a release."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 204
        mock_client.delete = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_delete_release(
                repo_owner="owner",
                repo_name="repo",
                release_id=12345,
            )

            assert "✅ Release 12345 deleted successfully" in result
            assert "owner/repo" in result
            mock_client.delete.assert_called_once_with(
                "/repos/owner/repo/releases/12345"
            )

    @pytest.mark.asyncio
    async def test_delete_release_not_found_404(self):
        """Test that 404 error is handled for non-existent release."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 404
        mock_client.delete = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_delete_release(
                repo_owner="owner",
                repo_name="repo",
                release_id=99999,
            )

            assert "❌ Release 99999 not found" in result

    @pytest.mark.asyncio
    async def test_delete_release_auth_error(self):
        """Test that authentication errors are handled properly."""
        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ValueError(
                "GitHub token not configured"
            )

            result = await github_delete_release(
                repo_owner="owner",
                repo_name="repo",
                release_id=12345,
            )

            assert "❌ GitHub token not configured" in result

    @pytest.mark.asyncio
    async def test_delete_release_connection_error(self):
        """Test that connection errors are handled gracefully."""
        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ConnectionError(
                "Network timeout"
            )

            result = await github_delete_release(
                repo_owner="owner",
                repo_name="repo",
                release_id=12345,
            )

            assert "❌ Network connection failed" in result
            assert "Network timeout" in result


class TestGitHubUploadReleaseAsset:
    """Test github_upload_release_asset function."""

    @pytest.mark.asyncio
    async def test_upload_asset_success(self):
        """Test successfully uploading a release asset."""
        mock_client = MagicMock()

        # Mock the release response
        release_response = AsyncMock()
        release_response.status = 200
        release_response.json = AsyncMock(
            return_value={
                "upload_url": "https://uploads.github.com/repos/owner/repo/releases/12345/assets{?name,label}"
            }
        )

        # Mock the upload response
        upload_response = AsyncMock()
        upload_response.status = 201
        upload_response.json = AsyncMock(
            return_value={
                "id": 67890,
                "name": "app.zip",
                "size": 1024,
                "browser_download_url": "https://github.com/owner/repo/releases/download/v1.0.0/app.zip",
            }
        )

        async def mock_get_post(url, **kwargs):
            if "releases/12345/assets" in url or "releases/12345" in url:
                if kwargs.get("data"):
                    return upload_response
                return release_response
            return release_response

        mock_client.get = AsyncMock(return_value=release_response)
        mock_client.post = AsyncMock(side_effect=mock_get_post)

        with (
            patch(
                "src.mcp_server_git.github.releases.github_client_context"
            ) as mock_context,
            patch("builtins.open", mock_open(read_data=b"file content")),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.is_file", return_value=True),
        ):
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_upload_release_asset(
                repo_owner="owner",
                repo_name="repo",
                release_id=12345,
                file_path="/tmp/app.zip",
                name="app.zip",
                label="Application archive",
            )

            assert "✅ Asset 'app.zip' uploaded successfully" in result
            assert "1024 bytes" in result
            assert "67890" in result

    @pytest.mark.asyncio
    async def test_upload_asset_file_not_found(self):
        """Test that file not found error is handled."""
        with patch("pathlib.Path.exists", return_value=False):
            result = await github_upload_release_asset(
                repo_owner="owner",
                repo_name="repo",
                release_id=12345,
                file_path="/tmp/nonexistent.zip",
            )

            assert "❌ File not found: /tmp/nonexistent.zip" in result

    @pytest.mark.asyncio
    async def test_upload_asset_release_not_found(self):
        """Test that 404 error is handled for non-existent release."""
        mock_client = MagicMock()

        release_response = AsyncMock()
        release_response.status = 404
        mock_client.get = AsyncMock(return_value=release_response)

        with (
            patch(
                "src.mcp_server_git.github.releases.github_client_context"
            ) as mock_context,
            patch("builtins.open", mock_open(read_data=b"file content")),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.is_file", return_value=True),
        ):
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_upload_release_asset(
                repo_owner="owner",
                repo_name="repo",
                release_id=99999,
                file_path="/tmp/app.zip",
            )

            assert "❌ Release 99999 not found" in result

    @pytest.mark.asyncio
    async def test_upload_asset_auth_error(self):
        """Test that authentication errors are handled properly."""
        with (
            patch(
                "src.mcp_server_git.github.releases.github_client_context"
            ) as mock_context,
            patch("builtins.open", mock_open(read_data=b"file content")),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.is_file", return_value=True),
        ):
            mock_context.return_value.__aenter__.side_effect = ValueError(
                "GitHub token not configured"
            )

            result = await github_upload_release_asset(
                repo_owner="owner",
                repo_name="repo",
                release_id=12345,
                file_path="/tmp/app.zip",
            )

            assert "❌ GitHub token not configured" in result


class TestGitHubListReleaseAssets:
    """Test github_list_release_assets function."""

    @pytest.mark.asyncio
    async def test_list_assets_success(self):
        """Test successfully listing release assets."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {"Link": ""}
        mock_response.json = AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "name": "app.zip",
                    "size": 1024,
                    "download_count": 42,
                    "content_type": "application/zip",
                    "browser_download_url": "https://github.com/owner/repo/releases/download/v1.0.0/app.zip",
                },
                {
                    "id": 2,
                    "name": "app.tar.gz",
                    "size": 2048000,
                    "download_count": 10,
                    "content_type": "application/gzip",
                    "browser_download_url": "https://github.com/owner/repo/releases/download/v1.0.0/app.tar.gz",
                },
            ]
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_list_release_assets(
                repo_owner="owner",
                repo_name="repo",
                release_id=12345,
            )

            assert "Assets for Release 12345" in result
            assert "📎 app.zip" in result
            assert "1.0 KB" in result
            assert "Downloads: 42" in result
            assert "📎 app.tar.gz" in result
            assert "2.0 MB" in result
            assert "Downloads: 10" in result

    @pytest.mark.asyncio
    async def test_list_assets_empty(self):
        """Test listing assets when none exist."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=[])
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_list_release_assets(
                repo_owner="owner",
                repo_name="repo",
                release_id=12345,
            )

            assert "No assets found for release 12345" in result

    @pytest.mark.asyncio
    async def test_list_assets_not_found_404(self):
        """Test that 404 error is handled for non-existent release."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 404
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_list_release_assets(
                repo_owner="owner",
                repo_name="repo",
                release_id=99999,
            )

            assert "❌ Release 99999 not found" in result


class TestGitHubDeleteReleaseAsset:
    """Test github_delete_release_asset function."""

    @pytest.mark.asyncio
    async def test_delete_asset_success(self):
        """Test successfully deleting a release asset."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 204
        mock_client.delete = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_delete_release_asset(
                repo_owner="owner",
                repo_name="repo",
                asset_id=67890,
            )

            assert "✅ Asset 67890 deleted successfully" in result
            assert "owner/repo" in result
            mock_client.delete.assert_called_once_with(
                "/repos/owner/repo/releases/assets/67890"
            )

    @pytest.mark.asyncio
    async def test_delete_asset_not_found_404(self):
        """Test that 404 error is handled for non-existent asset."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 404
        mock_client.delete = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_delete_release_asset(
                repo_owner="owner",
                repo_name="repo",
                asset_id=99999,
            )

            assert "❌ Asset 99999 not found" in result

    @pytest.mark.asyncio
    async def test_delete_asset_auth_error(self):
        """Test that authentication errors are handled properly."""
        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ValueError(
                "GitHub token not configured"
            )

            result = await github_delete_release_asset(
                repo_owner="owner",
                repo_name="repo",
                asset_id=67890,
            )

            assert "❌ GitHub token not configured" in result

    @pytest.mark.asyncio
    async def test_delete_asset_connection_error(self):
        """Test that connection errors are handled gracefully."""
        with patch(
            "src.mcp_server_git.github.releases.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ConnectionError(
                "Network timeout"
            )

            result = await github_delete_release_asset(
                repo_owner="owner",
                repo_name="repo",
                asset_id=67890,
            )

            assert "❌ Network connection failed" in result
            assert "Network timeout" in result


class TestGitHubGetReleaseModel:
    """Test Pydantic model validators for GitHubGetRelease."""

    def test_valid_with_release_id(self):
        """Test that providing release_id is valid."""
        model = GitHubGetRelease(
            repo_owner="owner",
            repo_name="repo",
            release_id=12345,
        )
        assert model.release_id == 12345
        assert model.tag is None

    def test_valid_with_tag(self):
        """Test that providing tag is valid."""
        model = GitHubGetRelease(
            repo_owner="owner",
            repo_name="repo",
            tag="v1.0.0",
        )
        assert model.tag == "v1.0.0"
        assert model.release_id is None

    def test_invalid_neither_provided(self):
        """Test that providing neither release_id nor tag raises ValidationError.

        Note: The validator is on release_id field, so we need to explicitly
        set release_id to None to trigger the validation.
        """
        with pytest.raises(ValidationError) as exc_info:
            GitHubGetRelease(
                repo_owner="owner",
                repo_name="repo",
                release_id=None,
                tag=None,
            )
        assert "Either release_id or tag must be provided" in str(exc_info.value)

    def test_invalid_both_provided(self):
        """Test that providing both release_id and tag raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            GitHubGetRelease(
                repo_owner="owner",
                repo_name="repo",
                release_id=12345,
                tag="v1.0.0",
            )
        assert "Cannot specify both release_id and tag" in str(exc_info.value)
