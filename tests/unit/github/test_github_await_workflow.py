"""
Unit tests for github_await_workflow_completion function.

Tests the workflow monitoring functionality including:
- Polling workflow run status until completion
- Timeout handling
- Latest run detection when no run_id provided
- Failed job information gathering
- Error handling
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp_server_git.github.api import github_await_workflow_completion


class TestGitHubAwaitWorkflowCompletion:
    """Test github_await_workflow_completion function."""

    @pytest.mark.asyncio
    async def test_successful_workflow_run(self):
        """Test monitoring a successful workflow run."""
        mock_client = MagicMock()

        # Mock workflow run response - completed successfully
        mock_run_response = AsyncMock()
        mock_run_response.status = 200
        mock_run_response.json = AsyncMock(
            return_value={
                "id": 12345,
                "status": "completed",
                "conclusion": "success",
                "name": "CI Tests",
                "head_branch": "main",
                "head_sha": "abc123def456",
                "html_url": "https://github.com/owner/repo/actions/runs/12345",
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2023-01-01T00:05:00Z",
            }
        )
        mock_client.get = AsyncMock(return_value=mock_run_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result_str = await github_await_workflow_completion(
                repo_owner="owner",
                repo_name="repo",
                run_id=12345,
                timeout_minutes=1,
                poll_interval_seconds=1,
            )

            result = json.loads(result_str)
            assert result["status"] == "success"
            assert result["conclusion"] == "success"
            assert result["run_id"] == 12345
            assert result["workflow_name"] == "CI Tests"
            assert "duration_seconds" in result

    @pytest.mark.asyncio
    async def test_failed_workflow_run(self):
        """Test monitoring a failed workflow run."""
        mock_client = MagicMock()

        # Mock workflow run response - completed with failure
        mock_run_response = AsyncMock()
        mock_run_response.status = 200
        mock_run_response.json = AsyncMock(
            return_value={
                "id": 12345,
                "status": "completed",
                "conclusion": "failure",
                "name": "CI Tests",
                "head_branch": "main",
                "head_sha": "abc123def456",
                "html_url": "https://github.com/owner/repo/actions/runs/12345",
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2023-01-01T00:05:00Z",
            }
        )

        # Mock jobs response - one failed job
        mock_jobs_response = AsyncMock()
        mock_jobs_response.status = 200
        mock_jobs_response.json = AsyncMock(
            return_value={
                "jobs": [
                    {
                        "id": 1,
                        "name": "Test Suite",
                        "status": "completed",
                        "conclusion": "failure",
                        "html_url": "https://github.com/owner/repo/actions/runs/12345/job/1",
                        "steps": [
                            {"name": "Setup", "conclusion": "success"},
                            {"name": "Run Tests", "conclusion": "failure"},
                        ],
                    }
                ]
            }
        )

        # Setup mock to return different responses for different endpoints
        async def mock_get(endpoint, **kwargs):
            if "jobs" in endpoint:
                return mock_jobs_response
            return mock_run_response

        mock_client.get = AsyncMock(side_effect=mock_get)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result_str = await github_await_workflow_completion(
                repo_owner="owner",
                repo_name="repo",
                run_id=12345,
                timeout_minutes=1,
                poll_interval_seconds=1,
            )

            result = json.loads(result_str)
            assert result["status"] == "failure"
            assert result["conclusion"] == "failure"
            assert len(result["failed_jobs"]) == 1
            assert result["failed_jobs"][0]["name"] == "Test Suite"
            assert result["failed_jobs"][0]["failed_steps"] == ["Run Tests"]

    @pytest.mark.asyncio
    async def test_timeout_while_waiting(self):
        """Test that timeout is handled gracefully."""
        mock_client = MagicMock()

        # Mock workflow run response - still in progress
        mock_run_response = AsyncMock()
        mock_run_response.status = 200
        mock_run_response.json = AsyncMock(
            return_value={
                "id": 12345,
                "status": "in_progress",
                "conclusion": None,
                "name": "CI Tests",
                "head_branch": "main",
                "head_sha": "abc123def456",
                "html_url": "https://github.com/owner/repo/actions/runs/12345",
            }
        )
        mock_client.get = AsyncMock(return_value=mock_run_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            # Use very short timeout to trigger timeout quickly
            result_str = await github_await_workflow_completion(
                repo_owner="owner",
                repo_name="repo",
                run_id=12345,
                timeout_minutes=0.01,  # ~0.6 seconds
                poll_interval_seconds=1,
            )

            result = json.loads(result_str)
            assert result["status"] == "timeout"
            assert result["run_id"] == 12345
            assert "elapsed_seconds" in result

    @pytest.mark.asyncio
    async def test_latest_run_detection(self):
        """Test that latest run is detected when no run_id provided."""
        mock_client = MagicMock()

        # Mock list runs response - get latest
        mock_list_response = AsyncMock()
        mock_list_response.status = 200
        mock_list_response.json = AsyncMock(
            return_value={
                "workflow_runs": [
                    {"id": 99999, "status": "in_progress"},
                ]
            }
        )

        # Mock workflow run response - completed
        mock_run_response = AsyncMock()
        mock_run_response.status = 200
        mock_run_response.json = AsyncMock(
            return_value={
                "id": 99999,
                "status": "completed",
                "conclusion": "success",
                "name": "CI Tests",
                "head_branch": "main",
                "head_sha": "abc123def456",
                "html_url": "https://github.com/owner/repo/actions/runs/99999",
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2023-01-01T00:05:00Z",
            }
        )

        # Setup mock to return different responses
        call_count = [0]

        async def mock_get(endpoint, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:  # First call for listing runs
                return mock_list_response
            return mock_run_response  # Subsequent calls for run status

        mock_client.get = AsyncMock(side_effect=mock_get)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result_str = await github_await_workflow_completion(
                repo_owner="owner",
                repo_name="repo",
                run_id=None,  # No run_id - should get latest
                timeout_minutes=1,
                poll_interval_seconds=1,
            )

            result = json.loads(result_str)
            assert result["run_id"] == 99999
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_polling_until_complete(self):
        """Test that polling continues until workflow completes."""
        mock_client = MagicMock()

        # Track call count to simulate workflow progression
        call_count = [0]

        async def mock_get(endpoint, **kwargs):
            call_count[0] += 1
            mock_response = AsyncMock()
            mock_response.status = 200

            # First 2 polls: in_progress, then completed
            if call_count[0] <= 2:
                mock_response.json = AsyncMock(
                    return_value={
                        "id": 12345,
                        "status": "in_progress",
                        "conclusion": None,
                        "name": "CI Tests",
                        "head_branch": "main",
                        "head_sha": "abc123",
                    }
                )
            else:
                mock_response.json = AsyncMock(
                    return_value={
                        "id": 12345,
                        "status": "completed",
                        "conclusion": "success",
                        "name": "CI Tests",
                        "head_branch": "main",
                        "head_sha": "abc123",
                        "html_url": "https://github.com/owner/repo/actions/runs/12345",
                        "created_at": "2023-01-01T00:00:00Z",
                        "updated_at": "2023-01-01T00:00:30Z",
                    }
                )
            return mock_response

        mock_client.get = AsyncMock(side_effect=mock_get)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result_str = await github_await_workflow_completion(
                repo_owner="owner",
                repo_name="repo",
                run_id=12345,
                timeout_minutes=1,
                poll_interval_seconds=1,
            )

            result = json.loads(result_str)
            assert result["status"] == "success"
            assert call_count[0] >= 3  # Should have polled multiple times

    @pytest.mark.asyncio
    async def test_authentication_error(self):
        """Test that authentication errors are handled properly."""
        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ValueError(
                "GitHub token not configured"
            )

            result_str = await github_await_workflow_completion(
                repo_owner="owner", repo_name="repo", run_id=12345
            )

            assert "Authentication error:" in result_str
            assert "GitHub token not configured" in result_str

    @pytest.mark.asyncio
    async def test_api_error(self):
        """Test that API errors are handled properly."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 404
        mock_response.text = AsyncMock(return_value="Not Found")
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.api.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result_str = await github_await_workflow_completion(
                repo_owner="owner", repo_name="repo", run_id=12345
            )

            assert "Failed to get workflow run" in result_str
            assert "404" in result_str
