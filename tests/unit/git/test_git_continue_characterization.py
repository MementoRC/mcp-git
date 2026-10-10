"""Characterization tests for git_continue against real repositories (#255)."""

import subprocess
from pathlib import Path

import git
import pytest

from mcp_server_git.git.operations import git_continue


def _commit(repo: git.Repo, name: str, content: str, message: str) -> None:
    (Path(repo.working_dir) / name).write_text(content)
    repo.index.add([name])
    repo.index.commit(message)


@pytest.fixture
def repo(tmp_path: Path) -> git.Repo:
    """Repo where main and feature edit the same line of a.txt."""
    r = git.Repo.init(tmp_path / "repo", initial_branch="main")
    with r.config_writer() as cw:
        cw.set_value("user", "name", "Test")
        cw.set_value("user", "email", "t@example.com")
        cw.set_value("commit", "gpgsign", "false")
    _commit(r, "a.txt", "base\n", "base")
    r.git.checkout("-b", "feature")
    _commit(r, "a.txt", "feature line\n", "feature edit")
    r.git.checkout("main")
    _commit(r, "a.txt", "main line\n", "main edit")
    return r


def _resolve(repo: git.Repo) -> None:
    (Path(repo.working_dir) / "a.txt").write_text("resolved\n")
    repo.git.add("a.txt")


def _run_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_EDITOR", "true")


def test_git_continue_returns_invalid_when_operation_unknown(repo):
    assert git_continue(repo, "bisect") == (
        "❌ Invalid operation 'bisect'. Valid operations: rebase, merge, cherry-pick"
    )


@pytest.mark.parametrize("operation", ["rebase", "merge", "cherry-pick"])
def test_git_continue_returns_no_operation_when_nothing_in_progress(repo, operation):
    result = git_continue(repo, operation)
    assert result.startswith("❌")
    assert operation in result


def test_git_continue_returns_success_when_rebase_conflict_resolved(repo, monkeypatch):
    _run_env(monkeypatch)
    repo.git.checkout("feature")
    with pytest.raises(git.GitCommandError):
        repo.git.rebase("main")
    _resolve(repo)
    result = git_continue(repo, "rebase")
    assert result.startswith("✅ Successfully continued rebase")


def test_git_continue_returns_failure_when_rebase_conflict_unresolved(repo):
    repo.git.checkout("feature")
    with pytest.raises(git.GitCommandError):
        repo.git.rebase("main")
    result = git_continue(repo, "rebase")
    assert result.startswith("❌")
    assert "rebase" in result


def test_git_continue_returns_success_when_merge_conflict_resolved(repo, monkeypatch):
    _run_env(monkeypatch)
    with pytest.raises(git.GitCommandError):
        repo.git.merge("feature")
    _resolve(repo)
    result = git_continue(repo, "merge")
    assert result.startswith("✅ Successfully continued merge")


def test_git_continue_returns_failure_when_merge_conflict_unresolved(repo):
    with pytest.raises(git.GitCommandError):
        repo.git.merge("feature")
    result = git_continue(repo, "merge")
    assert result.startswith("❌")
    assert "merge" in result


def test_git_continue_returns_success_when_cherry_pick_conflict_resolved(
    repo, monkeypatch
):
    _run_env(monkeypatch)
    with pytest.raises(git.GitCommandError):
        repo.git.cherry_pick("feature")
    _resolve(repo)
    result = git_continue(repo, "cherry-pick")
    assert result.startswith("✅ Successfully continued cherry-pick")


def test_git_continue_returns_failure_when_cherry_pick_conflict_unresolved(repo):
    with pytest.raises(git.GitCommandError):
        repo.git.cherry_pick("feature")
    result = git_continue(repo, "cherry-pick")
    assert result.startswith("❌")
    assert "cherry-pick" in result


def test_git_continue_returns_timeout_when_subprocess_times_out(repo, monkeypatch):
    def _boom(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="git", timeout=60)

    monkeypatch.setattr(subprocess, "run", _boom)
    assert git_continue(repo, "rebase") == (
        "❌ rebase continue operation timed out after 60 seconds"
    )
