"""Characterization tests for git_rm (#255 phase 2b)."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from mcp_server_git.git.operations_extended import git_rm
from mcp_server_git.utils.git_import import GitCommandError, Repo
from mcp_server_git.utils.tool_failure import ToolFailure


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    r = Repo.init(tmp_path, initial_branch="main")
    with r.config_writer() as cw:
        cw.set_value("user", "name", "Alice")
        cw.set_value("user", "email", "alice@example.com")
        cw.set_value("commit", "gpgsign", "false")
    (tmp_path / "a.txt").write_text("a\n")
    r.git.add("a.txt")
    r.git.commit("-m", "commit 0")
    return r


def test_git_rm_removes_file_when_tracked_and_clean(repo: Repo, tmp_path: Path):
    result = git_rm(repo, "a.txt")
    assert result == "✅ Removed 'a.txt' from working tree and index"
    assert not isinstance(result, ToolFailure)
    assert not (tmp_path / "a.txt").exists()


def test_git_rm_keeps_file_on_disk_when_cached(repo: Repo, tmp_path: Path):
    result = git_rm(repo, "a.txt", cached=True)
    assert result == "✅ Removed 'a.txt' from index (kept on disk)"
    assert (tmp_path / "a.txt").exists()


def test_git_rm_previews_only_when_dry_run(repo: Repo, tmp_path: Path):
    result = git_rm(repo, "a.txt", dry_run=True)
    assert result == "🔍 Dry-run: would remove 'a.txt'\nrm 'a.txt'"
    assert not isinstance(result, ToolFailure)
    assert (tmp_path / "a.txt").exists()


def test_git_rm_dry_run_wins_over_cached_message_when_both_set(repo: Repo):
    result = git_rm(repo, "a.txt", cached=True, dry_run=True)
    assert result.startswith("🔍 Dry-run: would remove 'a.txt'\n")


def test_git_rm_normalizes_and_strips_path_when_dotted_and_padded(repo: Repo):
    result = git_rm(repo, "  ./sub/../a.txt  ")
    assert result == "✅ Removed 'a.txt' from working tree and index"


def test_git_rm_passes_flags_in_order_when_cached_and_dry_run():
    m = Mock()
    m.git.rm.return_value = "out"
    git_rm(m, "f", cached=True, dry_run=True)
    m.git.rm.assert_called_once_with("--cached", "--dry-run", "--", "f")


@pytest.mark.parametrize("value", ["", "   "])
def test_git_rm_returns_failure_when_no_file(value: str):
    result = git_rm(Mock(), value)
    assert result == "❌ No file specified"
    assert isinstance(result, ToolFailure)


def test_git_rm_returns_failure_when_trailing_slash():
    result = git_rm(Mock(), "dir/")
    assert (
        result == "❌ Directory removal not supported. Specify an explicit file path."
    )
    assert isinstance(result, ToolFailure)


@pytest.mark.parametrize("value", [".", "..", "./", "a/..", "x/../.."])
def test_git_rm_returns_failure_when_dot_or_parent(value: str):
    result = git_rm(Mock(), value)
    if value == "./":
        assert result == (
            "❌ Directory removal not supported. Specify an explicit file path."
        )
    else:
        assert result == (
            "❌ Refusing to remove '.' or '..'. Specify an explicit file path."
        )
    assert isinstance(result, ToolFailure)


def test_git_rm_returns_failure_when_absolute_path():
    result = git_rm(Mock(), "/etc/passwd")
    assert result == (
        "❌ Absolute paths not allowed. Use a path relative to the repository root."
    )
    assert isinstance(result, ToolFailure)


@pytest.mark.parametrize("value", ["*.py", "a?.py", "a[1].py", "{a,b}"])
def test_git_rm_returns_failure_when_wildcard(value: str):
    result = git_rm(Mock(), value)
    assert result == "❌ Wildcards/globs not allowed. Specify an explicit file path."
    assert isinstance(result, ToolFailure)


def test_git_rm_returns_failure_when_dangerous_chars():
    m = Mock()
    result = git_rm(m, "a;b")
    assert result == "❌ Invalid characters detected in file path: 'a;b'"
    assert isinstance(result, ToolFailure)
    m.git.rm.assert_not_called()


def test_git_rm_returns_not_tracked_failure_when_file_untracked(
    repo: Repo, tmp_path: Path
):
    (tmp_path / "u.txt").write_text("u\n")
    result = git_rm(repo, "u.txt")
    assert result == "❌ File not found: 'u.txt' is not tracked by git"
    assert isinstance(result, ToolFailure)


def test_git_rm_returns_uncommitted_failure_when_local_modifications(
    repo: Repo, tmp_path: Path
):
    (tmp_path / "a.txt").write_text("changed\n")
    result = git_rm(repo, "a.txt")
    assert result == (
        "❌ File 'a.txt' has uncommitted changes. Stage or stash first, or use force."
    )
    assert isinstance(result, ToolFailure)


def test_git_rm_returns_uncommitted_failure_when_changes_staged(
    repo: Repo, tmp_path: Path
):
    (tmp_path / "a.txt").write_text("changed\n")
    repo.git.add("a.txt")
    result = git_rm(repo, "a.txt")
    assert result == (
        "❌ File 'a.txt' has uncommitted changes. Stage or stash first, or use force."
    )


def test_git_rm_returns_generic_failure_when_other_git_error():
    m = Mock()
    m.git.rm.side_effect = GitCommandError("rm", 128, stderr=b"fatal: weird")
    result = git_rm(m, "f")
    assert result == "❌ git rm failed: fatal: weird"
    assert isinstance(result, ToolFailure)


def test_git_rm_returns_failure_when_unexpected_exception():
    m = Mock()
    m.git.rm.side_effect = RuntimeError("kaput")
    result = git_rm(m, "f")
    assert result == "❌ Error during git rm: kaput"
    assert isinstance(result, ToolFailure)
