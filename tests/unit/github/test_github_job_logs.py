"""
Unit tests for GitHub Actions job logs functionality.

Tests the github_get_job_logs function including:
- Fetching logs for a specific job
- Tail lines filtering
- Error handling for missing jobs
- Log content parsing
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp_server_git.github.api import github_get_job_logs
from src.mcp_server_git.github.models import GitHubGetJobLogs


class TestGitHubGetJobLogs:
    """Test github_get_job_logs function."""

    @pytest.mark.asyncio
    async def test_get_job_logs_success(self):
        """Test successfully fetching job logs."""
        mock_client = MagicMock()

        # Mock job details response
        mock_job_response = AsyncMock()
        mock_job_response.status = 200
        mock_job_response.json = AsyncMock(
            return_value={
                "id": 12345,
                "name": "Build and Test",
                "status": "completed",
                "conclusion": "failure",
                "started_at": "2024-01-15T10:00:00Z",
                "completed_at": "2024-01-15T10:05:00Z",
                "html_url": "https://github.com/owner/repo/actions/runs/123/jobs/12345",
            }
        )

        # Mock logs response
        mock_logs_response = AsyncMock()
        mock_logs_response.status = 200
        mock_logs_response.text = AsyncMock(
            return_value="2024-01-15T10:00:00Z Starting build...\n"
            "2024-01-15T10:01:00Z Running tests...\n"
            "2024-01-15T10:05:00Z Error: Test failed\n"
        )

        mock_client.get = AsyncMock(side_effect=[mock_job_response, mock_logs_response])

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_context.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await github_get_job_logs("owner", "repo", 12345)

            assert "Job #12345 - Build and Test" in result
            assert "Status: completed" in result
            assert "Conclusion: failure" in result
            assert "Starting build..." in result
            assert "Error: Test failed" in result

    @pytest.mark.asyncio
    async def test_get_job_logs_with_tail_lines(self):
        """Test fetching logs with tail_lines filter."""
        mock_client = MagicMock()

        mock_job_response = AsyncMock()
        mock_job_response.status = 200
        mock_job_response.json = AsyncMock(
            return_value={
                "id": 12345,
                "name": "Build",
                "status": "completed",
                "conclusion": "success",
            }
        )

        # Multi-line log content
        log_lines = "\n".join([f"Line {i}" for i in range(100)])
        mock_logs_response = AsyncMock()
        mock_logs_response.status = 200
        mock_logs_response.text = AsyncMock(return_value=log_lines)

        mock_client.get = AsyncMock(side_effect=[mock_job_response, mock_logs_response])

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_context.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await github_get_job_logs("owner", "repo", 12345, tail_lines=10)

            assert "last 10 of 100 lines" in result
            assert "Line 99" in result
            assert "Line 90" in result
            # Earlier lines should not be present
            assert "Line 0\n" not in result

    @pytest.mark.asyncio
    async def test_get_job_logs_job_not_found(self):
        """Test handling of non-existent job."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 404

        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_context.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await github_get_job_logs("owner", "repo", 99999)

            assert "❌" in result
            assert "not found" in result

    @pytest.mark.asyncio
    async def test_get_job_logs_logs_not_available(self):
        """Test handling when logs are not available (deleted)."""
        mock_client = MagicMock()

        mock_job_response = AsyncMock()
        mock_job_response.status = 200
        mock_job_response.json = AsyncMock(
            return_value={
                "id": 12345,
                "name": "Old Job",
                "status": "completed",
                "conclusion": "success",
            }
        )

        mock_logs_response = AsyncMock()
        mock_logs_response.status = 404

        mock_client.get = AsyncMock(side_effect=[mock_job_response, mock_logs_response])

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_context.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await github_get_job_logs("owner", "repo", 12345)

            assert "⚠️" in result
            assert "not available" in result

    @pytest.mark.asyncio
    async def test_get_job_logs_empty_logs(self):
        """Test handling of empty log content."""
        mock_client = MagicMock()

        mock_job_response = AsyncMock()
        mock_job_response.status = 200
        mock_job_response.json = AsyncMock(
            return_value={
                "id": 12345,
                "name": "Empty Job",
                "status": "completed",
            }
        )

        mock_logs_response = AsyncMock()
        mock_logs_response.status = 200
        mock_logs_response.text = AsyncMock(return_value="")

        mock_client.get = AsyncMock(side_effect=[mock_job_response, mock_logs_response])

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_context.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await github_get_job_logs("owner", "repo", 12345)

            assert "📭" in result
            assert "empty" in result

    @pytest.mark.asyncio
    async def test_get_job_logs_rate_limited_job(self):
        """Test handling of rate limiting (429) when fetching job details."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 429

        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_context.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await github_get_job_logs("owner", "repo", 12345)

            assert "❌" in result
            assert "rate limit" in result.lower()

    @pytest.mark.asyncio
    async def test_get_job_logs_access_denied(self):
        """Test handling of access denied (403) for job details."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 403

        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_context.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await github_get_job_logs("owner", "repo", 12345)

            assert "❌" in result
            assert "Access denied" in result

    @pytest.mark.asyncio
    async def test_get_job_logs_rate_limited_logs(self):
        """Test handling of rate limiting (429) when fetching logs."""
        mock_client = MagicMock()

        mock_job_response = AsyncMock()
        mock_job_response.status = 200
        mock_job_response.json = AsyncMock(
            return_value={
                "id": 12345,
                "name": "Test Job",
                "status": "completed",
            }
        )

        mock_logs_response = AsyncMock()
        mock_logs_response.status = 429

        mock_client.get = AsyncMock(side_effect=[mock_job_response, mock_logs_response])

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_context.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await github_get_job_logs("owner", "repo", 12345)

            assert "❌" in result
            assert "rate limit" in result.lower()

    @pytest.mark.asyncio
    async def test_get_job_logs_large_log_truncation(self):
        """Test that large logs are truncated to prevent memory issues."""
        mock_client = MagicMock()

        mock_job_response = AsyncMock()
        mock_job_response.status = 200
        mock_job_response.json = AsyncMock(
            return_value={
                "id": 12345,
                "name": "Large Log Job",
                "status": "completed",
            }
        )

        # Create a log larger than the 10MB limit
        large_log = "X" * (11 * 1024 * 1024)  # 11 MB
        mock_logs_response = AsyncMock()
        mock_logs_response.status = 200
        mock_logs_response.text = AsyncMock(return_value=large_log)

        mock_client.get = AsyncMock(side_effect=[mock_job_response, mock_logs_response])

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_context.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await github_get_job_logs("owner", "repo", 12345)

            # Should indicate truncation occurred
            assert "⚠️" in result
            assert "truncated" in result.lower()
            # The result should not be the full 11MB
            assert len(result) < 11 * 1024 * 1024


class TestGitHubGetJobLogsModel:
    """Test GitHubGetJobLogs Pydantic model."""

    def test_model_basic(self):
        """Test basic model creation."""
        model = GitHubGetJobLogs(
            repo_owner="owner",
            repo_name="repo",
            job_id=12345,
        )
        assert model.repo_owner == "owner"
        assert model.repo_name == "repo"
        assert model.job_id == 12345
        assert model.tail_lines is None

    def test_model_with_tail_lines(self):
        """Test model with tail_lines parameter."""
        model = GitHubGetJobLogs(
            repo_owner="owner",
            repo_name="repo",
            job_id=12345,
            tail_lines=100,
        )
        assert model.tail_lines == 100

    def test_model_schema(self):
        """Test model generates valid JSON schema."""
        schema = GitHubGetJobLogs.model_json_schema()
        assert "properties" in schema
        assert "repo_owner" in schema["properties"]
        assert "repo_name" in schema["properties"]
        assert "job_id" in schema["properties"]
        assert "tail_lines" in schema["properties"]
