import asyncio
import tempfile
from pathlib import Path

import pytest

from unittest.mock import AsyncMock, patch


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def mock_server(monkeypatch):
    """
    Fixture to mock the MCP Git Server process and its async I/O.
    """
    # Patch out actual GitHub and git calls
    with (
        patch(
            "src.mcp_server_git.github.client.GitHubClient", autospec=True
        ) as mock_gh_client,
        patch(
            "src.mcp_server_git.git.security.enforce_secure_git_config",
            return_value="OK",
        ),
    ):
        # Mock GitHubClient methods
        instance = mock_gh_client.return_value
        instance.get.return_value = AsyncMock()
        instance.post.return_value = AsyncMock()
        instance.patch.return_value = AsyncMock()
        instance.put.return_value = AsyncMock()
        yield {
            "github_client": instance,
        }


@pytest.fixture
async def temp_git_repo():
    """
    Fixture to create a temporary git repository for testing.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir)
        # Optionally, initialize a git repo here if needed
        yield repo_path


@pytest.fixture
def sample_cancelled_notification():
    return {
        "jsonrpc": "2.0",
        "method": "notifications/cancelled",
        "params": {"requestId": "test-req-1", "reason": "User cancelled"},
    }


@pytest.fixture
def malformed_notification():
    return {
        "jsonrpc": "2.0",
        "method": "notifications/cancelled",
        "params": {},  # Missing requestId
    }
