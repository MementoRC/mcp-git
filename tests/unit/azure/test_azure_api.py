"""Unit tests for Azure DevOps API operations."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp_server_git.azure.api import (
    azure_get_build_logs,
    azure_get_build_status,
    azure_get_failing_jobs,
    azure_list_builds,
)


class TestAzureGetBuildStatus:
    """Test azure_get_build_status function."""

    @pytest.mark.asyncio
    async def test_successful_build_status(self):
        """Test getting status of a successful build."""
        mock_client = MagicMock()

        # Mock build response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "id": 123,
                "buildNumber": "20240101.1",
                "status": "completed",
                "result": "succeeded",
                "definition": {"name": "CI Pipeline"},
                "sourceBranch": "refs/heads/main",
                "sourceVersion": "abc123def456",
                "queueTime": "2024-01-01T10:00:00Z",
                "startTime": "2024-01-01T10:01:00Z",
                "finishTime": "2024-01-01T10:10:00Z",
                "requestedFor": {"displayName": "John Doe"},
                "_links": {
                    "web": {
                        "href": "https://dev.azure.com/org/project/_build/results?buildId=123"
                    }
                },
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.mcp_server_git.azure.api.azure_client_context") as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await azure_get_build_status(project="myproject", build_id=123)

            assert "Build #123" in result
            assert "CI Pipeline" in result
            assert "succeeded" in result
            assert "refs/heads/main" in result

    @pytest.mark.asyncio
    async def test_failed_build_status(self):
        """Test getting status of a failed build."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "id": 124,
                "buildNumber": "20240101.2",
                "status": "completed",
                "result": "failed",
                "definition": {"name": "CI Pipeline"},
                "sourceBranch": "refs/heads/feature/test",
                "sourceVersion": "xyz789abc123",
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.mcp_server_git.azure.api.azure_client_context") as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await azure_get_build_status(project="myproject", build_id=124)

            assert "Build #124" in result
            assert "failed" in result

    @pytest.mark.asyncio
    async def test_build_not_found(self):
        """Test getting status of non-existent build."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 404
        mock_response.text = AsyncMock(return_value="Build not found")
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.mcp_server_git.azure.api.azure_client_context") as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await azure_get_build_status(project="myproject", build_id=999)

            assert "❌" in result
            assert "404" in result


class TestAzureGetBuildLogs:
    """Test azure_get_build_logs function."""

    @pytest.mark.asyncio
    async def test_list_all_logs(self):
        """Test listing all logs for a build."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "value": [
                    {
                        "id": 1,
                        "type": "Container",
                        "lineCount": 100,
                        "url": "https://...",
                    },
                    {
                        "id": 2,
                        "type": "Container",
                        "lineCount": 50,
                        "url": "https://...",
                    },
                ]
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.mcp_server_git.azure.api.azure_client_context") as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await azure_get_build_logs(project="myproject", build_id=123)

            assert "Log #1" in result
            assert "Log #2" in result
            assert "100 lines" in result

    @pytest.mark.asyncio
    async def test_get_specific_log(self):
        """Test getting a specific log by ID."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {"Content-Type": "application/json"}
        # Azure DevOps returns log content as JSON with a "value" array
        mock_response.json = AsyncMock(
            return_value={
                "value": ["Build log line 1", "Build log line 2", "Build log line 3"]
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.mcp_server_git.azure.api.azure_client_context") as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await azure_get_build_logs(
                project="myproject", build_id=123, log_id=1
            )

            assert "Log #1" in result
            assert "Build log line 1" in result
            assert "Build log line 2" in result
            assert "Build log line 3" in result

    @pytest.mark.asyncio
    async def test_get_specific_log_with_tail_lines(self):
        """Test getting a specific log with tail_lines parameter."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {"Content-Type": "application/json"}
        # Create a log with many lines
        log_lines = [f"Log line {i}" for i in range(1, 101)]
        mock_response.json = AsyncMock(return_value={"value": log_lines})
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.mcp_server_git.azure.api.azure_client_context") as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await azure_get_build_logs(
                project="myproject", build_id=123, log_id=1, tail_lines=20
            )

            assert "Log #1" in result
            assert "Log line 81" in result  # Should start from line 81 (100 - 20 + 1)
            assert "Log line 100" in result
            # Check that early lines are not in the output (avoiding the truncation message)
            assert (
                "Log line 10\n" not in result
            )  # Early line with newline to avoid matching in message
            assert "truncated 80 lines" in result
            assert "showing last 20 of 100 lines" in result  # New format


class TestAzureGetFailingJobs:
    """Test azure_get_failing_jobs function."""

    @pytest.mark.asyncio
    async def test_get_failing_jobs(self):
        """Test getting failing jobs from a build."""
        mock_client = MagicMock()

        # Mock build response
        build_response = AsyncMock()
        build_response.status = 200
        build_response.json = AsyncMock(
            return_value={
                "id": 123,
                "result": "failed",
            }
        )

        # Mock timeline response
        timeline_response = AsyncMock()
        timeline_response.status = 200
        timeline_response.json = AsyncMock(
            return_value={
                "records": [
                    {
                        "id": "job1",
                        "type": "Job",
                        "name": "Build Job",
                        "result": "failed",
                        "state": "completed",
                        "startTime": "2024-01-01T10:00:00Z",
                        "finishTime": "2024-01-01T10:05:00Z",
                        "issues": [
                            {"type": "error", "message": "Build failed with error"},
                        ],
                        "log": {"id": 5},
                    }
                ]
            }
        )

        # Mock log response
        log_response = AsyncMock()
        log_response.status = 200
        log_response.headers = {"Content-Type": "application/json"}
        log_response.json = AsyncMock(
            return_value={"value": ["Error log line 1", "Error log line 2"]}
        )

        async def mock_get(url, **kwargs):
            if "timeline" in url:
                return timeline_response
            elif "logs" in url:
                return log_response
            else:
                return build_response

        mock_client.get = AsyncMock(side_effect=mock_get)

        with patch("src.mcp_server_git.azure.api.azure_client_context") as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await azure_get_failing_jobs(
                project="myproject", build_id=123, include_logs=True
            )

            assert "Failed Jobs" in result
            assert "Build Job" in result
            assert "failed" in result
            assert "Build failed with error" in result
            assert "Error log line" in result


class TestAzureListBuilds:
    """Test azure_list_builds function."""

    @pytest.mark.asyncio
    async def test_list_builds(self):
        """Test listing builds for a project."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {}
        mock_response.json = AsyncMock(
            return_value={
                "value": [
                    {
                        "id": 123,
                        "buildNumber": "20240101.1",
                        "status": "completed",
                        "result": "succeeded",
                        "definition": {"name": "CI Pipeline"},
                        "sourceBranch": "refs/heads/main",
                        "queueTime": "2024-01-01T10:00:00Z",
                        "_links": {"web": {"href": "https://..."}},
                    },
                    {
                        "id": 124,
                        "buildNumber": "20240101.2",
                        "status": "inProgress",
                        "definition": {"name": "CD Pipeline"},
                        "sourceBranch": "refs/heads/develop",
                        "queueTime": "2024-01-01T11:00:00Z",
                        "_links": {"web": {"href": "https://..."}},
                    },
                ]
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.mcp_server_git.azure.api.azure_client_context") as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await azure_list_builds(project="myproject")

            assert "Build #123" in result
            assert "Build #124" in result
            assert "20240101.1" in result
            assert "20240101.2" in result
            assert "succeeded" in result
            assert "inProgress" in result

    @pytest.mark.asyncio
    async def test_list_builds_with_filters(self):
        """Test listing builds with filters."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {}
        mock_response.json = AsyncMock(return_value={"value": []})
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.mcp_server_git.azure.api.azure_client_context") as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await azure_list_builds(
                project="myproject",
                branch_name="refs/heads/main",
                status="completed",
                result="succeeded",
            )

            # Verify the filters were passed to the API call
            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            assert "params" in call_args[1]
            params = call_args[1]["params"]
            assert params["branchName"] == "refs/heads/main"
            assert params["statusFilter"] == "completed"
            assert params["resultFilter"] == "succeeded"
