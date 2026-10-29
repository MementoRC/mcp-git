"""Characterization tests pinning every outcome branch of git_add (issue #255).

Run against a REAL temporary repository so the exact message strings are
checked against actual index state.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mcp_server_git.git.operations import git_add

pytest.importorskip("git")
from git import Repo  # noqa: E402


@pytest.fixture
def repo(tmp_path):
    r = Repo.init(tmp_path)
    with r.config_writer() as cw:
        cw.set_value("user", "name", "T")
        cw.set_value("user", "email", "t@example.com")
    (tmp_path / "tracked.txt").write_text("v1\n")
    r.git.add("tracked.txt")
    r.git.commit("-m", "init")
    return r


def _write(repo, name, text="x\n"):
    (Path(repo.working_dir) / name).write_text(text)


def test_git_add_returns_no_files_message_when_nothing_specified(repo):
    assert git_add(repo) == (
        "❌ No files specified. Use files, update_only, or patterns parameter."
    )


def test_git_add_returns_conflict_message_when_files_and_update_only_given(repo):
    assert git_add(repo, files=["a"], update_only=True) == (
        "❌ Conflicting parameters: files, update_only. "
        "Use only one method to specify what to add."
    )


def test_git_add_returns_conflict_message_when_all_three_given(repo):
    assert git_add(repo, files=["a"], update_only=True, patterns=["*.py"]) == (
        "❌ Conflicting parameters: files, update_only, patterns. "
        "Use only one method to specify what to add."
    )


def test_git_add_returns_tracked_updates_count_when_update_only(repo):
    _write(repo, "tracked.txt", "v2\n")
    _write(repo, "untracked.txt")
    assert git_add(repo, update_only=True) == (
        "✅ Added 1 file(s) to staging area (tracked updates)"
    )


def test_git_add_returns_zero_count_when_update_only_and_nothing_changed(repo):
    assert git_add(repo, update_only=True) == (
        "✅ Added 0 file(s) to staging area (tracked updates)"
    )


@pytest.mark.parametrize("bad", [";", "|", "&", "`", "$", "(", ")"])
def test_git_add_returns_invalid_characters_when_pattern_has_dangerous_char(repo, bad):
    pattern = f"a{bad}b"
    assert git_add(repo, patterns=[pattern]) == (
        f"❌ Invalid characters detected in pattern: {pattern}"
    )


def test_git_add_returns_added_list_when_patterns_match_new_files(repo):
    _write(repo, "a.py")
    _write(repo, "b.py")
    assert git_add(repo, patterns=["*.py"]) == (
        "✅ Added 2 file(s) to staging area: a.py, b.py (matching *.py)"
    )


def test_git_add_returns_no_match_warning_when_patterns_stage_nothing_new(repo):
    _write(repo, "a.py")
    repo.git.add("a.py")
    assert git_add(repo, patterns=["*.py"]) == "⚠️ No files matched patterns: *.py"


def test_git_add_returns_pattern_failure_when_pathspec_matches_nothing(repo):
    result = git_add(repo, patterns=["*.zzz", "*.yyy"])
    assert result.startswith("❌ Pattern matching failed: ")


def test_git_add_returns_not_found_when_files_missing(repo):
    assert git_add(repo, files=["nope.txt", "nope2.txt"]) == (
        "❌ Files not found: nope.txt, nope2.txt"
    )


def test_git_add_returns_added_list_when_files_are_new(repo):
    _write(repo, "new.txt")
    assert git_add(repo, files=["new.txt"]) == (
        "✅ Added 1 file(s) to staging area: new.txt"
    )


def test_git_add_returns_already_staged_report_when_files_already_staged(repo):
    _write(repo, "new.txt")
    repo.git.add("new.txt")
    assert git_add(repo, files=["new.txt"]) == (
        "✅ Already staged; index matches working tree (1 path(s)): new.txt"
    )


def test_git_add_returns_truncated_list_when_more_than_limit_staged(repo):
    for i in range(22):
        _write(repo, f"f{i:02d}.txt")
    result = git_add(repo, files=["."])
    assert result.startswith("✅ Added 22 file(s) to staging area: f00.txt, ")
    assert result.endswith(" (and 2 more)")


def test_git_add_returns_git_failure_when_file_is_ignored(repo):
    _write(repo, ".gitignore", "ign.txt\n")
    _write(repo, "ign.txt")
    result = git_add(repo, files=["ign.txt"])
    assert result.startswith("❌ Git add failed: ")


def test_git_add_returns_generic_failure_when_unexpected_exception_raised():
    broken = MagicMock()
    broken.git.status.side_effect = RuntimeError("boom")
    assert git_add(broken, files=["x"]) == "❌ Git add failed: boom"
