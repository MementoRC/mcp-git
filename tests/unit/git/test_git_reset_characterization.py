"""Characterization tests pinning every outcome branch of git_reset (issue #255).

Run against a REAL temporary repository so the exact message strings are
checked against actual index state.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mcp_server_git.git.operations import git_reset

pytest.importorskip("git")
from git import Repo  # noqa: E402


@pytest.fixture
def repo(tmp_path):
    r = Repo.init(tmp_path)
    with r.config_writer() as cw:
        cw.set_value("user", "name", "T")
        cw.set_value("user", "email", "t@example.com")
    (tmp_path / "m.txt").write_text("v1\n")
    r.git.add("m.txt")
    r.git.commit("-m", "init")
    return r


def _stage(repo, name):
    (Path(repo.working_dir) / name).write_text("x\n")
    repo.git.add(name)


def test_git_reset_returns_invalid_mode_when_mode_unknown(repo):
    assert git_reset(repo, mode="bogus") == (
        "❌ Invalid reset mode 'bogus'. Valid modes: soft, mixed, hard"
    )


def test_git_reset_returns_missing_target_when_target_does_not_exist(repo):
    assert git_reset(repo, target="nope") == "❌ Target 'nope' does not exist"


def test_git_reset_returns_missing_file_when_file_does_not_exist(repo):
    assert git_reset(repo, files=["nope.txt"]) == ("❌ File 'nope.txt' does not exist")


def test_git_reset_returns_file_count_and_unstages_when_files_given(repo):
    _stage(repo, "s.txt")
    assert git_reset(repo, files=["s.txt"]) == "✅ Reset 1 file(s): s.txt"
    assert repo.git.diff("--cached", "--name-only") == ""


def test_git_reset_returns_file_count_when_files_given_with_mode_and_target(repo):
    _stage(repo, "s.txt")
    assert git_reset(repo, mode="mixed", target="HEAD", files=["s.txt"]) == (
        "✅ Reset 1 file(s): s.txt"
    )


def test_git_reset_returns_soft_message_when_soft_without_target(repo):
    assert git_reset(repo, mode="soft") == (
        "✅ Soft reset to HEAD - keeping changes in index"
    )


def test_git_reset_returns_soft_message_when_soft_with_target(repo):
    assert git_reset(repo, mode="soft", target="HEAD") == (
        "✅ Soft reset to HEAD - keeping changes in index"
    )


def test_git_reset_returns_no_staged_changes_when_default_mode_and_clean(repo):
    assert git_reset(repo) == "✅ Mixed reset - no staged changes"


def test_git_reset_returns_staged_list_when_default_mode_and_staged(repo):
    _stage(repo, "s.txt")
    assert git_reset(repo) == "✅ Mixed reset - staged files: s.txt"


def test_git_reset_returns_target_message_when_mixed_with_target(repo):
    assert git_reset(repo, mode="mixed", target="HEAD") == (
        "✅ Mixed reset to HEAD - no staged changes"
    )


def test_git_reset_returns_overflow_suffix_when_more_than_five_staged(repo):
    for i in range(7):
        _stage(repo, f"s{i}.txt")
    result = git_reset(repo, mode="mixed")
    assert result.startswith("✅ Mixed reset - staged files: ")
    assert result.endswith(" (and 2 more)")
    assert result.count(".txt") == 5


def test_git_reset_returns_no_changes_discarded_when_hard_and_clean(repo):
    assert git_reset(repo, mode="hard") == "✅ Hard reset - no changes discarded"


def test_git_reset_returns_staged_and_modified_when_hard_with_both(repo):
    _stage(repo, "s.txt")
    (Path(repo.working_dir) / "m.txt").write_text("v2\n")
    assert git_reset(repo, mode="hard", target="HEAD") == (
        "✅ Hard reset to HEAD - staged files: s.txt, modified files: m.txt discarded"
    )


def test_git_reset_returns_modified_only_when_hard_with_unstaged_changes(repo):
    (Path(repo.working_dir) / "m.txt").write_text("v2\n")
    assert git_reset(repo, mode="hard") == (
        "✅ Hard reset - modified files: m.txt discarded"
    )


def test_git_reset_returns_modified_overflow_when_hard_with_many_modified(repo):
    for i in range(7):
        (Path(repo.working_dir) / f"m{i}.txt").write_text("a\n")
        repo.git.add(f"m{i}.txt")
    repo.git.commit("-m", "more")
    for i in range(7):
        (Path(repo.working_dir) / f"m{i}.txt").write_text("b\n")
    result = git_reset(repo, mode="hard")
    assert result.startswith("✅ Hard reset - modified files: ")
    assert result.endswith(" (and 2 more) discarded")


def test_git_reset_returns_reset_failed_when_git_rejects_hard_with_paths(repo):
    result = git_reset(repo, mode="hard", files=["m.txt"])
    assert result.startswith("❌ Reset failed: ")


def test_git_reset_returns_generic_error_when_unexpected_exception_raised(tmp_path):
    broken = MagicMock()
    broken.working_dir = str(tmp_path)
    broken.git.reset.side_effect = RuntimeError("boom")
    assert git_reset(broken) == "❌ Reset error: boom"
