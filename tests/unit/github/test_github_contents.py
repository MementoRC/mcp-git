"""
Unit tests for GitHub read-by-ref content functions (Issue #193).

Tests the lightweight read-by-ref GitHub tools:
- github_get_content: fetch a file's decoded contents at an optional ref
- github_resolve_ref: resolve a branch/tag/short-SHA to a full commit SHA
"""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp_server_git.github.api import github_get_content, github_resolve_ref


class TestGitHubGetContent:
    """Test github_get_content function."""

    @pytest.mark.asyncio
    async def test_get_content_returns_decoded_text_when_file_found(self):
        """Test that file content is decoded and sha/size are reported."""
        mock_client = MagicMock()

        raw_text = "print('hello world')\n"
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "type": "file",
                "encoding": "base64",
                "content": base64.b64encode(raw_text.encode("utf-8")).decode("ascii"),
                "sha": "abc123def456",
                "size": len(raw_text),
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.contents.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_content(
                repo_owner="owner",
                repo_name="repo",
                path="src/main.py",
                ref="main",
            )

            assert "print('hello world')" in result
            assert "abc123def456" in result
            assert f"{len(raw_text)} bytes" in result

    @pytest.mark.asyncio
    async def test_get_content_returns_not_found_message_when_status_404(self):
        """Test that a 404 status yields a not-found message."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 404
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.contents.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_content(
                repo_owner="owner",
                repo_name="repo",
                path="missing.py",
                ref="main",
            )

            assert "❌" in result
            assert "not found" in result
            assert "missing.py" in result

    @pytest.mark.asyncio
    async def test_get_content_lists_entries_when_path_is_directory(self):
        """Test that a directory path returns a listing of entries."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value=[
                {"type": "file", "name": "a.py", "size": 100},
                {"type": "dir", "name": "subdir", "size": 0},
            ]
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.contents.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_content(
                repo_owner="owner",
                repo_name="repo",
                path="src",
            )

            assert "Directory listing" in result
            assert "a.py" in result
            assert "subdir" in result

    @pytest.mark.asyncio
    async def test_get_content_reports_too_large_when_encoding_none(self):
        """Test that files too large for the contents API report a clear error."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "type": "file",
                "encoding": "none",
                "content": "",
                "sha": "bigfilesha",
                "size": 5_000_000,
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.contents.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_content(
                repo_owner="owner",
                repo_name="repo",
                path="big/asset.bin",
            )

            assert "❌" in result
            assert "too large" in result
            assert "5000000" in result


class TestGitHubResolveRef:
    """Test github_resolve_ref function."""

    @pytest.mark.asyncio
    async def test_resolve_ref_returns_full_sha_when_ref_found(self):
        """Test that a branch/tag/short-SHA resolves to the full commit SHA."""
        mock_client = MagicMock()

        full_sha = "a" * 40
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "sha": full_sha,
                "commit": {
                    "author": {
                        "name": "Test Author",
                        "email": "author@example.com",
                        "date": "2024-01-01T00:00:00Z",
                    },
                    "message": "Fix bug\n\nDetailed description here",
                },
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.contents.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_resolve_ref(
                repo_owner="owner",
                repo_name="repo",
                ref="main",
            )

            assert full_sha in result
            assert "Fix bug" in result
            mock_client.get.assert_called_once_with("/repos/owner/repo/commits/main")

    @pytest.mark.asyncio
    async def test_resolve_ref_returns_not_found_message_when_status_404(self):
        """Test that a 404 status yields a not-found message."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 404
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.contents.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_resolve_ref(
                repo_owner="owner",
                repo_name="repo",
                ref="nonexistent-branch",
            )

            assert "❌" in result
            assert "not found" in result

    @pytest.mark.asyncio
    async def test_resolve_ref_returns_not_found_message_when_status_422(self):
        """Test that a 422 status (unprocessable ref) yields a not-found message."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 422
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.contents.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_resolve_ref(
                repo_owner="owner",
                repo_name="repo",
                ref="deadbeef",
            )

            assert "❌" in result
            assert "not found" in result
