"""Tests for submodule and config operations."""

import re
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from git.exc import GitCommandError
from git.repo import Repo

from mcp_server_git.git.operations import (
    _validate_config_file,
    _validate_config_key,
    git_config_get,
    git_config_list,
    git_config_set,
    git_submodule_add,
    git_submodule_status,
    git_submodule_sync,
    git_submodule_update,
)


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repository."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True
    )
    # Initial commit so repo is valid
    (repo_path / "README.md").write_text("# Test")
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=repo_path, check=True, capture_output=True
    )
    return Repo(str(repo_path))


class TestValidateConfigKey:
    def test_valid_keys(self):
        _validate_config_key("user.name")
        _validate_config_key("core.autocrlf")
        _validate_config_key("submodule.sub-packages/foo.url")

    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            _validate_config_key("")

    def test_rejects_shell_injection(self):
        with pytest.raises(ValueError):
            _validate_config_key("user.name; rm -rf /")

    def test_rejects_spaces(self):
        with pytest.raises(ValueError):
            _validate_config_key("user name")


class TestValidateConfigFile:
    def test_valid_relative_path(self, git_repo):
        # .gitmodules is a valid config file target
        _validate_config_file(git_repo, ".gitmodules")

    def test_rejects_traversal(self, git_repo):
        with pytest.raises(ValueError):
            _validate_config_file(git_repo, "../../../etc/passwd")

    def test_rejects_absolute_outside_repo(self, git_repo):
        with pytest.raises(ValueError):
            _validate_config_file(git_repo, "/etc/passwd")


class TestGitConfigOperations:
    def test_config_set_and_get(self, git_repo):
        result = git_config_set(git_repo, "test.key", "test_value")
        assert "✅" in result

        result = git_config_get(git_repo, "test.key")
        assert "test_value" in result

    def test_config_set_rejects_bad_key(self, git_repo):
        result = git_config_set(git_repo, "bad;key", "value")
        assert "❌" in result

    def test_config_list(self, git_repo):
        result = git_config_list(git_repo)
        assert "user.name" in result

    def test_config_get_missing_key(self, git_repo):
        result = git_config_get(git_repo, "nonexistent.key")
        assert "❌" in result or "not set" in result.lower()


class TestGitSubmoduleOperations:
    def test_submodule_status_empty(self, git_repo):
        result = git_submodule_status(git_repo)
        assert "No submodules" in result

    def test_submodule_add_rejects_bad_url(self, git_repo):
        result = git_submodule_add(git_repo, "ftp://bad.com/repo", "sub")
        assert "❌" in result
        assert "Invalid URL" in result

    def test_submodule_add_rejects_injection(self, git_repo):
        result = git_submodule_add(
            git_repo, "https://example.com/repo.git", "sub;rm -rf /"
        )
        assert "❌" in result

    def test_submodule_sync_no_submodules(self, git_repo):
        result = git_submodule_sync(git_repo)
        # Should succeed even with no submodules
        assert "❌" not in result or "error" not in result.lower()

    def test_submodule_update_no_submodules(self, git_repo):
        result = git_submodule_update(git_repo)
        assert "❌" not in result or "No submodules" in result
