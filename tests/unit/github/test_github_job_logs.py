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
            assert "Truncated" in result
            # The result should be much smaller than 11MB (100KB limit)
            assert len(result) < 150 * 1024  # 150KB with overhead

    @pytest.mark.asyncio
    async def test_get_job_logs_default_llm_limit(self):
        """Test that logs are limited to 500 lines by default for LLM context."""
        mock_client = MagicMock()

        mock_job_response = AsyncMock()
        mock_job_response.status = 200
        mock_job_response.json = AsyncMock(
            return_value={
                "id": 12345,
                "name": "Many Lines Job",
                "status": "completed",
            }
        )

        # Create log with 1000 lines (more than default 500)
        log_lines = "\n".join([f"Log line {i}" for i in range(1000)])
        mock_logs_response = AsyncMock()
        mock_logs_response.status = 200
        mock_logs_response.text = AsyncMock(return_value=log_lines)

        mock_client.get = AsyncMock(side_effect=[mock_job_response, mock_logs_response])

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_context.return_value.__aexit__ = AsyncMock(return_value=None)

            # No tail_lines specified - should use default 500
            result = await github_get_job_logs("owner", "repo", 12345)

            assert "last 500 of 1000 lines" in result
            assert "Log line 999" in result  # Last line should be present
            assert "Log line 500" in result  # 500th from end
            assert "Log line 499\n" not in result  # 501st from end should be cut

    @pytest.mark.asyncio
    async def test_get_job_logs_full_log_flag(self):
        """Test that full_log=True bypasses line limit."""
        mock_client = MagicMock()

        mock_job_response = AsyncMock()
        mock_job_response.status = 200
        mock_job_response.json = AsyncMock(
            return_value={
                "id": 12345,
                "name": "Full Log Job",
                "status": "completed",
            }
        )

        # Create log with 600 lines (more than default 500)
        log_lines = "\n".join([f"Line {i}" for i in range(600)])
        mock_logs_response = AsyncMock()
        mock_logs_response.status = 200
        mock_logs_response.text = AsyncMock(return_value=log_lines)

        mock_client.get = AsyncMock(side_effect=[mock_job_response, mock_logs_response])

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_context.return_value.__aexit__ = AsyncMock(return_value=None)

            # full_log=True should return all 600 lines
            result = await github_get_job_logs("owner", "repo", 12345, full_log=True)

            assert "600 lines" in result
            assert "Line 0" in result  # First line should be present
            assert "Line 599" in result  # Last line should be present

    @pytest.mark.asyncio
    async def test_get_job_logs_char_limit(self):
        """Test that logs exceeding 100KB char limit are truncated."""
        mock_client = MagicMock()

        mock_job_response = AsyncMock()
        mock_job_response.status = 200
        mock_job_response.json = AsyncMock(
            return_value={
                "id": 12345,
                "name": "Large Char Job",
                "status": "completed",
            }
        )

        # Create log with very long lines (will exceed 100KB but have few lines)
        long_line = "X" * 1000  # 1KB per line
        log_lines = "\n".join([f"{i:03d}:{long_line}" for i in range(200)])  # 200KB
        mock_logs_response = AsyncMock()
        mock_logs_response.status = 200
        mock_logs_response.text = AsyncMock(return_value=log_lines)

        mock_client.get = AsyncMock(side_effect=[mock_job_response, mock_logs_response])

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_context.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await github_get_job_logs("owner", "repo", 12345, full_log=True)

            # Should indicate char truncation
            assert "⚠️" in result
            assert "100KB" in result
            # Result should be under 150KB (100KB limit + overhead)
            assert len(result) < 150 * 1024


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

    def test_model_with_full_log(self):
        """Test model with full_log parameter."""
        model = GitHubGetJobLogs(
            repo_owner="owner",
            repo_name="repo",
            job_id=12345,
            full_log=True,
        )
        assert model.full_log is True

    def test_model_schema(self):
        """Test model generates valid JSON schema."""
        schema = GitHubGetJobLogs.model_json_schema()
        assert "properties" in schema
        assert "repo_owner" in schema["properties"]
        assert "repo_name" in schema["properties"]
        assert "job_id" in schema["properties"]
        assert "tail_lines" in schema["properties"]
        assert "full_log" in schema["properties"]
