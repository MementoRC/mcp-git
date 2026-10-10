"""Characterization tests for git_reflog.

Pins current behaviour. The NUL-in-argv defect (the OS rejected a raw NUL in
the format string) was fixed in #258 by using git's %x00 placeholder, so real
repositories now return entries.
"""

import re
from pathlib import Path
from unittest.mock import Mock

import pytest

from mcp_server_git.git.operations import git_reflog
from mcp_server_git.utils.git_import import Repo


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


@pytest.mark.parametrize("kwargs", [{}, {"all": True}, {"max_count": 1}])
def test_git_reflog_returns_entries_when_real_repo(repo: Repo, kwargs: dict):
    result = git_reflog(repo, **kwargs)
    assert isinstance(result, list)
    assert result
    for entry in result:
        assert isinstance(entry, dict)
        assert re.fullmatch(r"[0-9a-f]{40}", entry["new_sha"])
        if kwargs.get("all"):
            assert "old_sha" not in entry


def test_git_reflog_passes_ref_after_flags_when_max_count_and_ref_given():
    repo = Mock()
    repo.git.reflog.return_value = ""
    git_reflog(repo, ref="main", max_count=2)
    args = repo.git.reflog.call_args[0]
    assert args[0] == "show"
    assert args[-3:] == ("-n", "2", "main")


def test_git_reflog_skips_blank_and_malformed_lines_when_output_noisy():
    repo = Mock()
    sha = "a" * 40
    repo.git.reflog.return_value = (
        f"\n  \nmalformed\x00only-two\n{sha}\x00HEAD@{{0}}\x00commit: x\n"
    )
    result = git_reflog(repo)
    assert result == [
        {
            "new_sha": sha,
            "label": "HEAD@{0}",
            "action": "commit",
            "message": "commit: x",
        }
    ]


def test_git_reflog_returns_empty_list_when_output_only_whitespace():
    repo = Mock()
    repo.git.reflog.return_value = "  \n "
    assert git_reflog(repo) == []


def test_git_reflog_action_falls_back_to_first_word_when_verb_not_word_start():
    repo = Mock()
    repo.git.reflog.return_value = "a" * 40 + "\x00HEAD@{0}\x00-weird thing: msg"
    result = git_reflog(repo)
    assert result[0]["action"] == "-weird"


def test_git_reflog_warning_counts_entries_before_append_when_large_output():
    repo = Mock()
    sha = "a" * 40
    repo.git.reflog.return_value = "\n".join(
        f"{sha}\x00HEAD@{{{i}}}\x00checkout: moving from b{i} to b{i + 1}"
        for i in range(600)
    )
    result = git_reflog(repo)
    assert isinstance(result, list)
    assert len(result) == 601
    assert result[-1]["warning"].startswith("⚠️  Large reflog detected (599 entries, ~")
    assert result[-1]["warning"].endswith("Consider using max_count to limit output.")
