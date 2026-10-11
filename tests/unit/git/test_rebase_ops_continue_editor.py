"""Regression: git_continue must not need an editor (headless server)."""

import os
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


@pytest.fixture(autouse=True)
def _no_editor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip every editor source, including core.editor from user/system config."""
    for var in ("GIT_EDITOR", "EDITOR", "VISUAL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("TERM", "dumb")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


def _resolve(repo: git.Repo) -> None:
    (Path(repo.working_dir) / "a.txt").write_text("resolved\n")
    repo.git.add("a.txt")


def test_git_continue_returns_success_when_rebase_resolved_without_editor(repo):
    repo.git.checkout("feature")
    with pytest.raises(git.GitCommandError):
        repo.git.rebase("main")
    _resolve(repo)

    result = git_continue(repo, "rebase")

    git_dir = Path(repo.git_dir)
    assert result.startswith("✅")
    assert not (git_dir / "rebase-merge").exists()
    assert not (git_dir / "rebase-apply").exists()
    assert "feature edit" in repo.git.log("-1", "--format=%s")


def test_git_continue_returns_success_when_merge_resolved_without_editor(repo):
    with pytest.raises(git.GitCommandError):
        repo.git.merge("feature")
    _resolve(repo)

    result = git_continue(repo, "merge")

    assert result.startswith("✅")
    assert not (Path(repo.git_dir) / "MERGE_HEAD").exists()


def test_git_continue_returns_success_when_cherry_pick_resolved_without_editor(repo):
    with pytest.raises(git.GitCommandError):
        repo.git.cherry_pick("feature")
    _resolve(repo)

    result = git_continue(repo, "cherry-pick")

    assert result.startswith("✅")
    assert not (Path(repo.git_dir) / "CHERRY_PICK_HEAD").exists()
