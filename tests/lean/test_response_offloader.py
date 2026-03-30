"""Tests for response offloading to /tmp files."""

import json
import os
import time

import pytest

from mcp_server_git.lean.response_offloader import ResponseOffloader
from mcp_server_git.lean.token_limiter import MCPTokenLimiter


@pytest.fixture
def tmp_offload_dir(tmp_path):
    """Provide a temporary directory for offloaded files."""
    return str(tmp_path)


@pytest.fixture
def limiter():
    """Token limiter with low limit to trigger offloading."""
    return MCPTokenLimiter(default_limit=100)


@pytest.fixture
def offloader(limiter, tmp_offload_dir):
    return ResponseOffloader(token_limiter=limiter, offload_dir=tmp_offload_dir)


class TestShouldOffload:
    def test_small_response_no_offload(self, tmp_offload_dir):
        limiter = MCPTokenLimiter(default_limit=2000)
        offloader = ResponseOffloader(token_limiter=limiter, offload_dir=tmp_offload_dir)
        assert offloader.should_offload({"result": "short"}, "git_status") is False

    def test_large_response_triggers_offload(self, offloader):
        assert offloader.should_offload({"result": "x" * 2000}, "git_diff") is True


class TestWriteToTmp:
    def test_file_created_with_correct_content(self, offloader):
        content = "full diff output here\n+added\n-removed"
        path = offloader._write_to_tmp(content, "git_diff")
        assert os.path.exists(path)
        with open(path) as f:
            assert f.read() == content

    def test_file_path_contains_tool_name(self, offloader):
        path = offloader._write_to_tmp("test", "git_log")
        assert "mcp-git-git_log-" in os.path.basename(path)

    def test_file_in_offload_dir(self, offloader, tmp_offload_dir):
        path = offloader._write_to_tmp("test", "git_status")
        assert path.startswith(tmp_offload_dir)


class TestCleanupOldFiles:
    def test_removes_expired_files(self, offloader, tmp_offload_dir):
        old_file = os.path.join(tmp_offload_dir, "mcp-git-test-old.txt")
        with open(old_file, "w") as f:
            f.write("old")
        old_time = time.time() - 7200
        os.utime(old_file, (old_time, old_time))
        offloader._cleanup_old_files(max_age_seconds=3600)
        assert not os.path.exists(old_file)

    def test_preserves_recent_files(self, offloader, tmp_offload_dir):
        recent_file = os.path.join(tmp_offload_dir, "mcp-git-test-recent.txt")
        with open(recent_file, "w") as f:
            f.write("recent")
        offloader._cleanup_old_files(max_age_seconds=3600)
        assert os.path.exists(recent_file)

    def test_ignores_non_mcp_files(self, offloader, tmp_offload_dir):
        other_file = os.path.join(tmp_offload_dir, "other-file.txt")
        with open(other_file, "w") as f:
            f.write("keep")
        old_time = time.time() - 7200
        os.utime(other_file, (old_time, old_time))
        offloader._cleanup_old_files(max_age_seconds=3600)
        assert os.path.exists(other_file)

    def test_concurrent_cleanup_no_exceptions(self, offloader, tmp_offload_dir):
        ghost_file = os.path.join(tmp_offload_dir, "mcp-git-ghost.txt")
        with open(ghost_file, "w") as f:
            f.write("ghost")
        old_time = time.time() - 7200
        os.utime(ghost_file, (old_time, old_time))
        os.remove(ghost_file)
        offloader._cleanup_old_files(max_age_seconds=3600)
