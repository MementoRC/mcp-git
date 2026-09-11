"""Unit tests for Azure DevOps API operations."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp_server_git.azure.api import (
    azure_get_build_logs,
    azure_get_build_status,
    azure_get_failing_jobs,
)
from src.mcp_server_git.azure.client import AzureClient


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

    @pytest.mark.asyncio
    async def test_get_specific_log_requests_text_plain_accept_header(self):
        """Fetching a specific log must call client.get with accept='text/plain'."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {"Content-Type": "text/plain"}
        mock_response.text = AsyncMock(
            return_value="Build log line 1\nBuild log line 2\nBuild log line 3"
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.mcp_server_git.azure.api.azure_client_context") as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await azure_get_build_logs(
                project="myproject", build_id=123, log_id=1
            )

            mock_client.get.assert_called_once()
            _, kwargs = mock_client.get.call_args
            assert kwargs.get("accept") == "text/plain"

            assert "Log #1" in result
            assert "Build log line 1" in result
            assert "Build log line 2" in result
            assert "Build log line 3" in result


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

    @pytest.mark.asyncio
    async def test_get_failing_jobs_does_not_raise_when_log_is_none(self):
        """A failed record whose 'log' key is present but null must not raise
        AttributeError ('NoneType' object has no attribute 'get') and must
        not attempt a log fetch for that record."""
        mock_client = MagicMock()

        build_response = AsyncMock()
        build_response.status = 200
        build_response.json = AsyncMock(return_value={"id": 123, "result": "failed"})

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
                        "log": None,
                    }
                ]
            }
        )

        async def mock_get(url, **kwargs):
            if "timeline" in url:
                return timeline_response
            elif "logs" in url:
                raise AssertionError(
                    "Log fetch should not be attempted when log is None"
                )
            return build_response

        mock_client.get = AsyncMock(side_effect=mock_get)

        with patch("src.mcp_server_git.azure.api.azure_client_context") as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await azure_get_failing_jobs(
                project="myproject", build_id=123, include_logs=True
            )

            assert isinstance(result, str)
            assert "Failed Jobs" in result
            assert "Build Job" in result


class TestAzureClientAnonymousMode:
    """Test that the Azure client works without a token (anonymous / public projects)."""

    def test_auth_returns_none_when_no_token(self):
        """_auth() must return None so no Authorization header is sent."""
        mock_session = MagicMock()
        client = AzureClient(
            token=None, organization="conda-forge", session=mock_session
        )
        assert client._auth() is None

    def test_auth_returns_basicauth_when_token_present(self):
        """_auth() must return BasicAuth when a token is configured."""
        import aiohttp

        mock_session = MagicMock()
        # Use a syntactically valid-looking PAT (40 base64 chars)
        fake_token = "a" * 40
        client = AzureClient(
            token=fake_token, organization="conda-forge", session=mock_session
        )
        auth = client._auth()
        assert isinstance(auth, aiohttp.BasicAuth)

    @pytest.mark.asyncio
    async def test_get_request_sends_no_auth_header_when_token_is_none(self):
        """GET without a token must call session.get() without an auth= kwarg."""
        mock_response = AsyncMock()
        mock_response.status = 200

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_response)

        client = AzureClient(
            token=None, organization="conda-forge", session=mock_session
        )
        await client.get("someproject/_apis/build/builds/1?api-version=7.1")

        # Verify session.get was called exactly once
        mock_session.get.assert_called_once()
        _, kwargs = mock_session.get.call_args
        # auth must NOT be present in kwargs — omitting it prevents the
        # Authorization header from being sent, enabling anonymous access.
        assert "auth" not in kwargs, (
            "Expected no 'auth' kwarg when token is None, "
            f"but got: {kwargs.get('auth')}"
        )

    @pytest.mark.asyncio
    async def test_post_raises_without_token(self):
        """POST must raise ValueError when no token is configured."""
        mock_session = AsyncMock()
        client = AzureClient(
            token=None, organization="conda-forge", session=mock_session
        )

        with pytest.raises(
            ValueError, match="AZURE_DEVOPS_TOKEN required for write operations"
        ):
            await client.post("someproject/_apis/something")

    @pytest.mark.asyncio
    async def test_patch_raises_without_token(self):
        """PATCH must raise ValueError when no token is configured."""
        mock_session = AsyncMock()
        client = AzureClient(
            token=None, organization="conda-forge", session=mock_session
        )

        with pytest.raises(
            ValueError, match="AZURE_DEVOPS_TOKEN required for write operations"
        ):
            await client.patch("someproject/_apis/something")

    def test_get_azure_client_defaults_to_conda_forge_org(self):
        """get_azure_client() must default org to conda-forge when env var is unset."""
        from src.mcp_server_git.azure.client import get_azure_client

        with (
            patch("src.mcp_server_git.azure.client.os.getenv") as mock_getenv,
            patch("src.mcp_server_git.azure.client.aiohttp.ClientSession"),
        ):
            # Simulate both env vars being absent
            mock_getenv.side_effect = lambda key, *args: None

            client = get_azure_client()

            assert client is not None
            assert client.organization == "conda-forge"
            assert client.token is None

    def test_get_azure_client_anonymous_when_token_empty_string(self):
        """An empty AZURE_DEVOPS_TOKEN must be treated as absent (anonymous mode)."""
        from src.mcp_server_git.azure.client import get_azure_client

        with (
            patch("src.mcp_server_git.azure.client.os.getenv") as mock_getenv,
            patch("src.mcp_server_git.azure.client.aiohttp.ClientSession"),
        ):

            def _env(key, *args):
                return "" if key == "AZURE_DEVOPS_TOKEN" else "my-org"

            mock_getenv.side_effect = _env

            client = get_azure_client()

            assert client is not None
            assert client.token is None
            assert client.organization == "my-org"
