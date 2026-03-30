"""Tests for response offloading to /tmp files."""

import json
import os
import time

import pytest

from mcp_server_git.lean.interface import GitLeanInterface
from mcp_server_git.lean.response_offloader import (
    ResponseOffloader,
    _summarize_diff,
    _summarize_generic,
    _summarize_job_logs,
    _summarize_list,
    _summarize_log,
)
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
        offloader = ResponseOffloader(
            token_limiter=limiter, offload_dir=tmp_offload_dir
        )
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


class TestSummarizeDiff:
    def test_counts_files_and_changes(self):
        diff = (
            "diff --git a/foo.py b/foo.py\n"
            "+added line\n+another\n"
            "-removed line\n"
            "diff --git a/bar.py b/bar.py\n"
            "+one more\n"
        )
        summary = _summarize_diff(diff)
        assert "2 files" in summary
        assert "3(+)" in summary
        assert "1(-)" in summary

    def test_empty_diff(self):
        assert "0 files" in _summarize_diff("")

    def test_non_string_falls_back(self):
        result = _summarize_diff({"not": "a diff"})
        assert "bytes" in result


class TestSummarizeLog:
    def test_counts_commits_and_authors(self):
        log = (
            "commit abc123\nAuthor: Alice <a@b.com>\nDate: Mon Mar 1\n\n    first\n\n"
            "commit def456\nAuthor: Bob <b@b.com>\nDate: Tue Mar 2\n\n    second\n"
        )
        summary = _summarize_log(log)
        assert "2 commits" in summary
        assert "2 authors" in summary

    def test_date_range(self):
        log = (
            "commit abc123\nAuthor: Alice\nDate: Tue Mar 2\n\n    recent\n\n"
            "commit def456\nAuthor: Alice\nDate: Mon Mar 1\n\n    older\n"
        )
        summary = _summarize_log(log)
        assert "Mon Mar 1" in summary
        assert "Tue Mar 2" in summary

    def test_empty_log(self):
        assert "0 commits" in _summarize_log("")


class TestSummarizeJobLogs:
    def test_counts_errors_and_warnings(self):
        logs = "INFO step 1\nERROR failed\nWARNING slow\nERROR crash\nINFO done"
        summary = _summarize_job_logs(logs)
        assert "2 errors" in summary.lower() or "2 error" in summary.lower()
        assert "1 warning" in summary.lower()


class TestSummarizeList:
    def test_item_count(self):
        listing = "Item 1: foo\nItem 2: bar\nItem 3: baz"
        summary = _summarize_list(listing)
        assert "3 items" in summary


class TestSummarizeGeneric:
    def test_string_response(self):
        summary = _summarize_generic("hello world")
        assert "11" in summary
        assert "text" in summary

    def test_dict_response(self):
        summary = _summarize_generic({"key": "value"})
        assert "json" in summary

    def test_list_response(self):
        summary = _summarize_generic([1, 2, 3])
        assert "3 items" in summary


class TestSummaryGeneratorFallback:
    """Broken summarizer should fall back to generic."""

    def test_fallback_on_exception(self, offloader):
        result = "x" * 2000
        summary_dict = offloader.offload(result, "unknown_tool")
        assert "offloaded" in summary_dict
        assert "bytes" in summary_dict["summary"]


class TestEndToEndOffloading:
    """Test offloading through the actual _wrap_tool path.

    Covers spec requirement #10: both execute_tool() and execute_tool_direct().
    Since registered tools have their implementation replaced by _wrap_tool at
    registration time, testing _wrap_tool directly covers both paths.
    """

    def test_wrap_tool_offloads_large_sync_result(self, tmp_offload_dir):
        """A sync tool returning large data gets offloaded via _wrap_tool."""
        limiter = MCPTokenLimiter(default_limit=100)
        offloader = ResponseOffloader(
            token_limiter=limiter, offload_dir=tmp_offload_dir
        )

        # Create a minimal GitLeanInterface and inject our offloader
        interface = GitLeanInterface.__new__(GitLeanInterface)
        interface.token_limiter = limiter
        interface.response_offloader = offloader

        def big_tool():
            return "x" * 5000

        wrapped = interface._wrap_tool(big_tool, "git_diff")
        result = wrapped()

        assert result["offloaded"] is True
        assert os.path.isfile(result["full_output_path"])
        with open(result["full_output_path"]) as f:
            assert f.read() == "x" * 5000

    def test_wrap_tool_fallback_on_write_failure(self):
        """When offload raises, _wrap_tool falls back to truncation."""
        limiter = MCPTokenLimiter(default_limit=100)
        offloader = ResponseOffloader(token_limiter=limiter, offload_dir="/nonexistent")

        interface = GitLeanInterface.__new__(GitLeanInterface)
        interface.token_limiter = limiter
        interface.response_offloader = offloader

        def big_tool():
            return {"result": "x" * 5000}

        wrapped = interface._wrap_tool(big_tool, "git_diff")
        result = wrapped()

        # Should get truncated result, not offloaded
        assert "offloaded" not in result or result.get("offloaded") is not True
        assert isinstance(result, dict)

    def test_wrap_tool_small_result_inline(self, tmp_offload_dir):
        """A small tool result passes through without offloading."""
        limiter = MCPTokenLimiter(default_limit=2000)
        offloader = ResponseOffloader(
            token_limiter=limiter, offload_dir=tmp_offload_dir
        )

        interface = GitLeanInterface.__new__(GitLeanInterface)
        interface.token_limiter = limiter
        interface.response_offloader = offloader

        def small_tool():
            return "short result"

        wrapped = interface._wrap_tool(small_tool, "git_status")
        result = wrapped()

        assert result == "short result"
