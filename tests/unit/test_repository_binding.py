"""Tests for RepositoryBindingManager using real git repositories."""

import git
import pytest

from mcp_server_git.repository_binding import RepositoryBindingManager


@pytest.mark.asyncio
async def test_bind_repository_returns_binding_with_none_remote_when_no_expectation(
    tmp_path,
):
    git.Repo.init(tmp_path)
    manager = RepositoryBindingManager(server_name="test-binding")

    binding = await manager.bind_repository(
        tmp_path, expected_remote_url=None, verify_remote=False
    )

    assert binding.expected_remote_url is None
    assert binding.verify_integrity() is True
