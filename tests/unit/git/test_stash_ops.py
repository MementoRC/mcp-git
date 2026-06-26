"""Tests for stash operations — including worktree scenarios (issue #189)."""

import shutil
import tempfile
from pathlib import Path

import pytest

from src.mcp_server_git.git._stash_ops import (
    git_stash_drop,
    git_stash_list,
    git_stash_pop,
    git_stash_push,
)
from src.mcp_server_git.utils.git_import import Repo


def _make_repo(path: Path) -> Repo:
    """Create a minimal git repo with an initial commit."""
    repo = Repo.init(str(path))
    repo.config_writer().set_value("user", "name", "Test").release()
    repo.config_writer().set_value("user", "email", "test@test.com").release()
    readme = path / "README.md"
    readme.write_text("initial")
    repo.index.add(["README.md"])
    repo.index.commit("initial commit")
    return repo


class TestGitStashPush:
    def setup_method(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = _make_repo(self.tmp)

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_git_stash_push_returns_success_when_changes_exist(self):
        (self.tmp / "README.md").write_text("modified")
        result = git_stash_push(self.repo)
        assert "✅" in result
        assert "stash" in result.lower()

    def test_git_stash_push_with_message(self):
        (self.tmp / "README.md").write_text("modified")
        result = git_stash_push(self.repo, message="my fix")
        assert "✅" in result
        assert "my fix" in result

    def test_git_stash_push_with_message_containing_spaces(self):
        (self.tmp / "README.md").write_text("modified")
        result = git_stash_push(self.repo, message="my stash message")
        assert "✅" in result
        assert "my stash message" in result

    def test_git_stash_push_returns_info_when_nothing_to_stash(self):
        result = git_stash_push(self.repo)
        assert "ℹ️" in result or "No local changes" in result

    def test_git_stash_push_in_worktree(self, tmp_path):
        """Regression test for issue #189: stash push must work in a linked worktree."""
        worktree_path = tmp_path / "linked-wt"
        self.repo.git.worktree("add", str(worktree_path), "HEAD")
        try:
            wt_repo = Repo(str(worktree_path))
            (worktree_path / "README.md").write_text("worktree change")
            result = git_stash_push(wt_repo)
            assert "✅" in result, f"Expected success in worktree, got: {result}"
        finally:
            self.repo.git.worktree("remove", "--force", str(worktree_path))

    def test_git_stash_push_include_untracked(self):
        new_file = self.tmp / "untracked.txt"
        new_file.write_text("new")
        result = git_stash_push(self.repo, include_untracked=True)
        assert "✅" in result


class TestGitStashList:
    def setup_method(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = _make_repo(self.tmp)

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_git_stash_list_empty(self):
        result = git_stash_list(self.repo)
        assert "No stashes found" in result

    def test_git_stash_list_shows_stash(self):
        (self.tmp / "README.md").write_text("modified")
        git_stash_push(self.repo, message="test-stash")
        result = git_stash_list(self.repo)
        assert "stash@{0}" in result
        assert "test-stash" in result


class TestGitStashPopDrop:
    def setup_method(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = _make_repo(self.tmp)
        (self.tmp / "README.md").write_text("modified")
        git_stash_push(self.repo, message="pop-test")

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_git_stash_pop_latest(self):
        result = git_stash_pop(self.repo)
        assert "✅" in result
        assert "popped" in result.lower()

    def test_git_stash_drop_latest(self):
        result = git_stash_drop(self.repo)
        assert "✅" in result
        assert "dropped" in result.lower()

    def test_git_stash_drop_by_id(self):
        result = git_stash_drop(self.repo, stash_id="stash@{0}")
        assert "✅" in result
        assert "stash@{0}" in result
