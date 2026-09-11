"""Unit tests for the stale index.lock reaper.

A git subprocess killed mid-operation can leave a zero-byte
``index.lock`` behind, permanently blocking every later index-mutating
git operation with "Unable to create '.git/index.lock': File exists"
until a human removes it. These tests cover the staleness gate
(``reap_stale_index_lock``) directly and its wiring into
``wrap_repo_op`` via an explicit ``mutates_index`` opt-in.
"""

import logging
import os
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from mcp_server_git.lean.lock_reaper import reap_stale_index_lock
from mcp_server_git.lean.registry_git import _register_git_tools


class _StubInterface:
    """Minimal stand-in for GitLeanInterface.register_tool."""

    def __init__(self):
        self.tool_registry = {}

    def register_tool(self, tool_def):
        self.tool_registry[tool_def.name] = tool_def


def _build_tool(name: str):
    interface = _StubInterface()
    _register_git_tools(interface, git_service=Mock())
    return interface.tool_registry[name]


def _age_file(path: Path, age_seconds: float) -> None:
    """Backdate a file's mtime/atime by age_seconds."""
    now = time.time()
    old = now - age_seconds
    os.utime(path, (old, old))


class TestReapStaleIndexLockDirect:
    """Exercise reap_stale_index_lock's staleness gate directly."""

    def test_old_zero_byte_lock_is_reaped(self, tmp_path, caplog):
        # Arrange
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        lock = git_dir / "index.lock"
        lock.write_bytes(b"")
        _age_file(lock, age_seconds=200)

        # Act
        with caplog.at_level(logging.WARNING):
            reap_stale_index_lock(str(git_dir))

        # Assert
        assert not lock.exists()
        assert any("index.lock" in r.message for r in caplog.records)
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    def test_non_zero_byte_lock_is_never_reaped_regardless_of_age(self, tmp_path):
        """Critical safety test: a partially-written lock means a real
        operation is mid-write. Never touch it, no matter how old."""
        # Arrange
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        lock = git_dir / "index.lock"
        lock.write_bytes(b"partial-content")
        _age_file(lock, age_seconds=10_000)

        # Act
        reap_stale_index_lock(str(git_dir))

        # Assert
        assert lock.exists()
        assert lock.read_bytes() == b"partial-content"

    def test_fresh_zero_byte_lock_within_threshold_is_not_reaped(self, tmp_path):
        """Protects a genuinely in-flight operation from being reaped."""
        # Arrange
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        lock = git_dir / "index.lock"
        lock.write_bytes(b"")
        _age_file(lock, age_seconds=5)

        # Act
        reap_stale_index_lock(str(git_dir))

        # Assert
        assert lock.exists()

    def test_no_lock_present_is_a_noop(self, tmp_path):
        # Arrange
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        # Act / Assert — must not raise
        reap_stale_index_lock(str(git_dir))
        assert not (git_dir / "index.lock").exists()

    def test_threshold_is_overridable_via_env_var(self, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv("MCP_GIT_INDEX_LOCK_MAX_AGE_SECONDS", "1")
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        lock = git_dir / "index.lock"
        lock.write_bytes(b"")
        _age_file(lock, age_seconds=5)

        # Act
        reap_stale_index_lock(str(git_dir))

        # Assert — 5s age exceeds the overridden 1s threshold
        assert not lock.exists()


class TestReapStaleIndexLockWorktree:
    """A linked worktree's .git is a FILE pointing at the real gitdir via
    'gitdir: <path>'. The lock lives in that resolved gitdir, not at
    <repo>/.git/index.lock. Uses a real worktree, no mocked resolution."""

    def test_worktree_resolves_to_real_gitdir_and_reaps_lock_there(self, tmp_path):
        pytest.importorskip("git")
        from git import Repo

        # Arrange: a real main repo with a real linked worktree
        main_repo_path = tmp_path / "main"
        main_repo_path.mkdir()
        main_repo = Repo.init(main_repo_path)
        (main_repo_path / "README.md").write_text("init\n")
        main_repo.index.add(["README.md"])
        main_repo.index.commit("initial commit")

        worktree_path = tmp_path / "wt"
        main_repo.git.worktree("add", str(worktree_path), "-b", "wt-branch")

        # The worktree's .git must be a FILE, not a directory.
        worktree_dotgit = worktree_path / ".git"
        assert worktree_dotgit.is_file()

        worktree_repo = Repo(str(worktree_path))
        resolved_git_dir = Path(worktree_repo.git_dir)
        assert resolved_git_dir != worktree_dotgit
        assert "worktrees" in str(resolved_git_dir)

        # Plant a stale zero-byte lock in the RESOLVED gitdir.
        lock = resolved_git_dir / "index.lock"
        lock.write_bytes(b"")
        _age_file(lock, age_seconds=200)

        # A naive <repo>/.git/index.lock path would look here and find
        # nothing, since .git is a file in a worktree.
        naive_wrong_path = worktree_dotgit / "index.lock"
        assert not naive_wrong_path.parent.is_dir()

        # Act
        reap_stale_index_lock(worktree_repo.git_dir)

        # Assert
        assert not lock.exists()


class TestWrapRepoOpMutatesIndexGate:
    """The reaper only fires for tools registered with mutates_index=True,
    and a reaped lock lets the underlying index-mutating op succeed."""

    def test_git_commit_reaps_stale_lock_before_running(self, tmp_path):
        pytest.importorskip("git")
        from git import Repo

        # Arrange: a real repo with a staged file and a stale lock
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        repo = Repo.init(repo_path)
        (repo_path / "a.txt").write_text("hello\n")
        repo.index.add(["a.txt"])

        lock = Path(repo.git_dir) / "index.lock"
        lock.write_bytes(b"")
        _age_file(lock, age_seconds=200)

        tool_def = _build_tool("git_commit")

        # Act
        result = tool_def.implementation(
            repo_path=str(repo_path), message="reaped commit"
        )

        # Assert — the op succeeded, meaning the lock was reaped first
        assert not lock.exists()
        assert "reaped commit" in str(result) or result is not None

    def test_git_status_read_only_does_not_reap(self, tmp_path):
        """Read-only tools must not have mutates_index wiring — a stale
        lock there is left for an actual mutating op to clean up."""
        pytest.importorskip("git")
        from git import Repo

        # Arrange
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        repo = Repo.init(repo_path)
        (repo_path / "a.txt").write_text("hello\n")
        repo.index.add(["a.txt"])
        repo.index.commit("initial")

        lock = Path(repo.git_dir) / "index.lock"
        lock.write_bytes(b"")
        _age_file(lock, age_seconds=200)

        tool_def = _build_tool("git_status")

        # Act
        tool_def.implementation(repo_path=str(repo_path))

        # Assert — git_status is read-only and not opted into the
        # reaper, so the stale lock is untouched.
        assert lock.exists()
