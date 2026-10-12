"""Characterization tests for git_worktree_list and git_worktree_add (#255 phase 2b).

Pins current return strings before the C901 refactor.
"""

from pathlib import Path
from unittest.mock import Mock

import pytest

from mcp_server_git.git.operations_extended import (
    git_branch_update,
    git_merge_tree,
    git_restore,
    git_worktree_add,
    git_worktree_list,
)
from mcp_server_git.utils.git_import import GitCommandError, Repo
from mcp_server_git.utils.tool_failure import ToolFailure


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    path = tmp_path / "main_repo"
    path.mkdir()
    r = Repo.init(path, initial_branch="main")
    with r.config_writer() as cw:
        cw.set_value("user", "name", "Alice")
        cw.set_value("user", "email", "alice@example.com")
        cw.set_value("commit", "gpgsign", "false")
    (path / "a.txt").write_text("a\n")
    r.git.add("a.txt")
    r.git.commit("-m", "commit 0")
    return r


def _mock_repo(output: str) -> Mock:
    m = Mock()
    m.git.worktree.return_value = output
    return m


# ---------------------------------------------------------------- list


def test_git_worktree_list_returns_single_entry_when_only_main_worktree(repo: Repo):
    result = git_worktree_list(repo)
    head = repo.head.commit.hexsha[:8]
    root = str(Path(repo.working_dir).resolve())
    assert result == f"Worktrees (1):\n  {root} [main] ({head})"
    assert not isinstance(result, ToolFailure)


def test_git_worktree_list_returns_all_entries_when_linked_worktree_exists(
    repo: Repo, tmp_path: Path
):
    wt = tmp_path / "wt1"
    repo.git.worktree("add", "-b", "feat", str(wt))
    result = git_worktree_list(repo)
    head = repo.head.commit.hexsha[:8]
    root = str(Path(repo.working_dir).resolve())
    assert result == (
        f"Worktrees (2):\n  {root} [main] ({head})\n  {wt.resolve()} [feat] ({head})"
    )


def test_git_worktree_list_labels_detached_when_worktree_detached(
    repo: Repo, tmp_path: Path
):
    wt = tmp_path / "wt_det"
    repo.git.worktree("add", "--detach", str(wt))
    result = git_worktree_list(repo)
    head = repo.head.commit.hexsha[:8]
    assert result.endswith(f"  {wt.resolve()} [detached] ({head})")


def test_git_worktree_list_returns_no_worktrees_when_output_blank():
    result = git_worktree_list(_mock_repo("  \n"))
    assert result == "No worktrees found"
    assert not isinstance(result, ToolFailure)


def test_git_worktree_list_labels_bare_and_unknown_head_when_bare_entry():
    out = "worktree /srv/bare.git\nbare\n"
    result = git_worktree_list(_mock_repo(out))
    assert result == "Worktrees (1):\n  /srv/bare.git [bare] (???)"


def test_git_worktree_list_strips_refs_heads_and_truncates_head_when_porcelain():
    sha = "0123456789abcdef0123456789abcdef01234567"
    out = (
        f"worktree /a\nHEAD {sha}\nbranch refs/heads/feat/x\n\n"
        f"worktree /b\nHEAD {sha}\ndetached\n"
    )
    result = git_worktree_list(_mock_repo(out))
    assert (
        result == "Worktrees (2):\n  /a [feat/x] (01234567)\n  /b [detached] (01234567)"
    )


def test_git_worktree_list_ignores_unknown_lines_when_porcelain_has_extras():
    out = "worktree /a\nlocked\nprunable gone\nbranch refs/heads/m\n"
    result = git_worktree_list(_mock_repo(out))
    assert result == "Worktrees (1):\n  /a [m] (???)"


def test_git_worktree_list_returns_failure_when_git_command_error():
    m = Mock()
    m.git.worktree.side_effect = GitCommandError("worktree", 128, stderr=b"fatal: boom")
    result = git_worktree_list(m)
    assert result == "❌ Failed to list worktrees: fatal: boom"
    assert isinstance(result, ToolFailure)


def test_git_worktree_list_returns_failure_when_unexpected_exception():
    m = Mock()
    m.git.worktree.side_effect = RuntimeError("kaput")
    result = git_worktree_list(m)
    assert result == "❌ Error listing worktrees: kaput"
    assert isinstance(result, ToolFailure)


# ----------------------------------------------------------------- add


def test_git_worktree_add_returns_detached_when_no_options(repo: Repo, tmp_path: Path):
    wt = tmp_path / "w_plain"
    result = git_worktree_add(repo, str(wt))
    assert result == f"✅ Worktree added at {wt} (detached HEAD)"
    assert not isinstance(result, ToolFailure)
    assert wt.is_dir()


def test_git_worktree_add_checks_out_branch_when_branch_given(
    repo: Repo, tmp_path: Path
):
    repo.git.branch("other")
    wt = tmp_path / "w_branch"
    result = git_worktree_add(repo, str(wt), branch="other")
    assert result == f"✅ Worktree added at {wt} (branch other)"
    assert repo.git.worktree("list").count("[other]") == 1


def test_git_worktree_add_creates_branch_when_new_branch_only(
    repo: Repo, tmp_path: Path
):
    wt = tmp_path / "w_new"
    result = git_worktree_add(repo, str(wt), new_branch="nb")
    assert result == f"✅ Worktree added at {wt} (new branch nb)"
    assert "nb" in [h.name for h in repo.heads]


def test_git_worktree_add_creates_branch_from_start_when_commit_ish_given(
    repo: Repo, tmp_path: Path
):
    wt = tmp_path / "w_newc"
    result = git_worktree_add(repo, str(wt), new_branch="nb", commit_ish="HEAD")
    assert result == f"✅ Worktree added at {wt} (new branch nb from HEAD)"


def test_git_worktree_add_uses_branch_as_start_when_new_branch_and_branch(
    repo: Repo, tmp_path: Path
):
    wt = tmp_path / "w_legacy"
    result = git_worktree_add(repo, str(wt), branch="main", new_branch="nb")
    assert result == f"✅ Worktree added at {wt} (new branch nb from main)"


def test_git_worktree_add_prefers_commit_ish_when_all_three_given(
    repo: Repo, tmp_path: Path
):
    wt = tmp_path / "w_all"
    result = git_worktree_add(
        repo, str(wt), branch="nonexistent", new_branch="nb", commit_ish="HEAD"
    )
    assert result == f"✅ Worktree added at {wt} (new branch nb from HEAD)"


def test_git_worktree_add_returns_detached_at_when_commit_ish_only(
    repo: Repo, tmp_path: Path
):
    wt = tmp_path / "w_ci"
    result = git_worktree_add(repo, str(wt), commit_ish="HEAD")
    assert result == f"✅ Worktree added at {wt} (detached HEAD at HEAD)"


def test_git_worktree_add_passes_force_and_capital_b_when_force_new_branch():
    m = Mock()
    result = git_worktree_add(m, "/p", new_branch="nb", commit_ish="abc", force=True)
    m.git.worktree.assert_called_once_with("add", "--force", "-B", "nb", "/p", "abc")
    assert result == "✅ Worktree added at /p (new branch nb from abc)"


def test_git_worktree_add_passes_lowercase_b_when_new_branch_without_force():
    m = Mock()
    git_worktree_add(m, "/p", new_branch="nb")
    m.git.worktree.assert_called_once_with("add", "-b", "nb", "/p")


def test_git_worktree_add_passes_force_before_path_when_force_only():
    m = Mock()
    git_worktree_add(m, "/p", branch="b", force=True)
    m.git.worktree.assert_called_once_with("add", "--force", "/p", "b")


def test_git_worktree_add_treats_empty_commit_ish_as_set_when_not_none():
    m = Mock()
    result = git_worktree_add(m, "/p", branch="b", commit_ish="")
    m.git.worktree.assert_called_once_with("add", "/p")
    assert result == "✅ Worktree added at /p (branch b)"


@pytest.mark.parametrize(
    ("kwargs", "label"),
    [
        ({"worktree_path": "/p;x"}, "worktree path"),
        ({"worktree_path": "/p", "branch": "b|x"}, "branch"),
        ({"worktree_path": "/p", "new_branch": "n$x"}, "new_branch"),
        ({"worktree_path": "/p", "commit_ish": "c`x"}, "commit_ish"),
    ],
)
def test_git_worktree_add_returns_failure_when_dangerous_chars(kwargs, label):
    m = Mock()
    result = git_worktree_add(m, **kwargs)
    bad = next(v for k, v in kwargs.items() if any(c in v for c in ";|$`"))
    assert result == f"❌ Invalid characters in {label}: '{bad}'"
    assert isinstance(result, ToolFailure)
    m.git.worktree.assert_not_called()


def test_git_worktree_add_validates_path_before_branch_when_both_dangerous():
    result = git_worktree_add(Mock(), "/p;x", branch="b;y")
    assert result == "❌ Invalid characters in worktree path: '/p;x'"


def test_git_worktree_add_returns_failure_when_commit_ish_and_branch_conflict():
    m = Mock()
    result = git_worktree_add(m, "/p", branch="b", commit_ish="c")
    assert result == (
        "❌ commit_ish and branch are mutually exclusive unless new_branch "
        "is set: 'branch' checks out an existing branch, 'commit_ish' "
        "creates a detached worktree."
    )
    assert isinstance(result, ToolFailure)
    m.git.worktree.assert_not_called()


def test_git_worktree_add_returns_failure_when_branch_already_exists(
    repo: Repo, tmp_path: Path
):
    result = git_worktree_add(repo, str(tmp_path / "w_dup"), new_branch="main")
    assert result.startswith("❌ Failed to add worktree: ")
    assert "main" in result
    assert isinstance(result, ToolFailure)


def test_git_worktree_add_returns_failure_when_git_command_error():
    m = Mock()
    m.git.worktree.side_effect = GitCommandError("worktree", 128, stderr=b"fatal: nope")
    result = git_worktree_add(m, "/p")
    assert result == "❌ Failed to add worktree: fatal: nope"
    assert isinstance(result, ToolFailure)


def test_git_worktree_add_returns_failure_when_unexpected_exception():
    m = Mock()
    m.git.worktree.side_effect = RuntimeError("kaput")
    result = git_worktree_add(m, "/p")
    assert result == "❌ Error adding worktree: kaput"
    assert isinstance(result, ToolFailure)


# ------------------------------------------------- invalid-ref failures


def test_git_restore_returns_failure_when_source_ref_invalid():
    result = git_restore(Mock(), ["a.txt"], source="bad;ref")
    assert result == "❌ Invalid characters detected in source: 'bad;ref'"
    assert isinstance(result, ToolFailure)


def test_git_branch_update_returns_failure_when_branch_name_invalid():
    result = git_branch_update(Mock(), "bad;ref", target="main")
    assert result == "❌ Invalid characters detected in branch_name: 'bad;ref'"
    assert isinstance(result, ToolFailure)


def test_git_branch_update_returns_failure_when_target_ref_invalid():
    result = git_branch_update(Mock(), "ok", target="bad;ref")
    assert result == "❌ Invalid characters detected in target: 'bad;ref'"
    assert isinstance(result, ToolFailure)


@pytest.mark.parametrize(
    ("b1", "b2", "name"),
    [("bad;ref", "main", "branch1"), ("main", "bad;ref", "branch2")],
)
def test_git_merge_tree_returns_failure_when_ref_invalid(b1, b2, name):
    result = git_merge_tree(Mock(), b1, b2)
    assert result == f"❌ Invalid characters detected in {name}: 'bad;ref'"
    assert isinstance(result, ToolFailure)
