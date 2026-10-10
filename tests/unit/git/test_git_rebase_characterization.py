"""Characterization tests for git_rebase against real repositories (#255)."""

from pathlib import Path

import git
import pytest

from mcp_server_git.git.operations import git_rebase


def _commit(repo: git.Repo, name: str, content: str, message: str) -> None:
    path = Path(repo.working_dir) / name
    path.write_text(content)
    repo.index.add([name])
    repo.index.commit(message)


@pytest.fixture
def repo(tmp_path: Path) -> git.Repo:
    """Repo with main and a diverged non-conflicting feature branch."""
    r = git.Repo.init(tmp_path / "repo", initial_branch="main")
    with r.config_writer() as cw:
        cw.set_value("user", "name", "Test")
        cw.set_value("user", "email", "t@example.com")
        cw.set_value("commit", "gpgsign", "false")
    _commit(r, "a.txt", "base\n", "base")
    r.git.checkout("-b", "feature")
    _commit(r, "b.txt", "feature\n", "feature work")
    r.git.checkout("main")
    _commit(r, "c.txt", "main\n", "main work")
    r.git.checkout("feature")
    return r


def _make_conflict(repo: git.Repo) -> None:
    repo.git.checkout("main")
    _commit(repo, "a.txt", "main line\n", "main edit")
    repo.git.checkout("feature")
    _commit(repo, "a.txt", "feature line\n", "feature edit")


def test_git_rebase_returns_success_when_target_exists(repo):
    result = git_rebase(repo, "main")
    assert result.startswith("✅ Successfully rebased feature onto main\n")


def test_git_rebase_returns_not_found_when_target_missing(repo):
    assert git_rebase(repo, "nope") == "❌ Target branch 'nope' not found"


def test_git_rebase_returns_success_when_branch_param_given(repo):
    repo.git.checkout("main")
    result = git_rebase(repo, "main", branch="feature")
    assert result.startswith("✅ Successfully rebased feature onto main\n")


def test_git_rebase_returns_success_when_onto_and_fork_point_given(repo):
    fork = repo.git.merge_base("main", "feature")
    result = git_rebase(repo, "ignored", onto="main", fork_point=fork)
    assert result.startswith(
        f"✅ Successfully rebased feature --onto main (from {fork})\n"
    )


def test_git_rebase_returns_success_when_onto_with_branch(repo):
    fork = repo.git.merge_base("main", "feature")
    repo.git.checkout("main")
    result = git_rebase(repo, "x", onto="main", fork_point=fork, branch="feature")
    assert result.startswith(
        f"✅ Successfully rebased feature --onto main (from {fork})\n"
    )


def test_git_rebase_returns_conflict_message_when_branches_conflict(repo):
    _make_conflict(repo)
    assert git_rebase(repo, "main") == (
        "❌ Rebase failed due to conflicts. "
        "Resolve conflicts and run 'git rebase --continue'"
    )


def test_git_rebase_returns_failed_when_branch_param_unknown(repo):
    result = git_rebase(repo, "main", branch="ghost")
    assert result.startswith("❌ Rebase failed: ")


def test_git_rebase_returns_failed_when_fork_point_unknown(repo):
    result = git_rebase(repo, "x", onto="main", fork_point="ghost")
    assert result.startswith("❌ Rebase failed: ")


def test_git_rebase_returns_error_when_head_detached(repo):
    repo.git.checkout("--detach")
    result = git_rebase(repo, "main")
    assert result.startswith("❌ Rebase error: ")


def test_git_rebase_passes_existence_check_when_target_is_remote_only(repo, tmp_path):
    remote = repo.clone(str(tmp_path / "remote"))
    remote.git.branch("only-remote")
    repo.create_remote("origin", str(tmp_path / "remote")).fetch()
    result = git_rebase(repo, "only-remote")
    assert "not found" not in result
    assert result.startswith("❌ Rebase failed: ")


def test_git_rebase_returns_invalid_chars_when_param_dangerous(repo):
    assert git_rebase(repo, "main", branch="a;b") == (
        "❌ Invalid characters detected in branch: 'a;b'"
    )


def test_git_rebase_returns_pairing_errors_when_onto_or_fork_missing(repo):
    assert git_rebase(repo, "main", onto="x") == (
        "❌ --onto requires fork_point (the old base to rebase from)"
    )
    assert git_rebase(repo, "main", fork_point="x") == (
        "❌ fork_point requires --onto (the new base to rebase onto)"
    )
