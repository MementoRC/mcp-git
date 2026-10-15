"""Live-holder aware reaping of index.lock (issue #276). Linux /proc only."""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from mcp_server_git.lean.lock_holders import has_live_lock_holder
from mcp_server_git.lean.lock_reaper import reap_stale_index_lock

pytestmark = pytest.mark.skipif(
    not Path("/proc/self/fd").is_dir(), reason="requires Linux /proc"
)


def _make_lock(git_dir: Path, content: bytes, age_seconds: float) -> Path:
    git_dir.mkdir(parents=True, exist_ok=True)
    lock = git_dir / "index.lock"
    lock.write_bytes(content)
    old = time.time() - age_seconds
    os.utime(lock, (old, old))
    return lock


@pytest.fixture
def open_holder():
    """Spawn a child holding the given file open; yields a factory."""
    procs: list[subprocess.Popen] = []

    def start(path: Path) -> subprocess.Popen:
        code = (
            "import sys,time\n"
            f"f=open({str(path)!r},'rb')\n"
            "print('ready',flush=True)\n"
            "time.sleep(60)\n"
        )
        proc = subprocess.Popen(
            [sys.executable, "-c", code], stdout=subprocess.PIPE, text=True
        )
        procs.append(proc)
        assert proc.stdout is not None
        proc.stdout.readline()
        return proc

    yield start
    for proc in procs:
        proc.kill()
        proc.wait()


@pytest.fixture
def git_named_process():
    """Spawn a `sleep` whose argv[0] basename is `git`, in a given cwd."""
    procs: list[subprocess.Popen] = []

    def start(bin_dir: Path, cwd: Path) -> subprocess.Popen:
        bin_dir.mkdir(exist_ok=True)
        link = bin_dir / "git"
        link.symlink_to(shutil.which("sleep") or "/bin/sleep")
        proc = subprocess.Popen([str(link), "60"], cwd=cwd)
        procs.append(proc)
        time.sleep(0.2)
        return proc

    yield start
    for proc in procs:
        proc.kill()
        proc.wait()


class TestHasLiveLockHolder:
    def test_has_live_lock_holder_returns_false_when_no_process_holds_lock(
        self, tmp_path
    ):
        _make_lock(tmp_path / ".git", b"", 100)

        assert has_live_lock_holder(str(tmp_path / ".git")) is False

    def test_has_live_lock_holder_returns_true_when_child_has_lock_open(
        self, tmp_path, open_holder
    ):
        lock = _make_lock(tmp_path / ".git", b"", 100)
        open_holder(lock)

        assert has_live_lock_holder(str(tmp_path / ".git")) is True

    def test_has_live_lock_holder_returns_true_when_git_process_cwd_in_worktree(
        self, tmp_path, git_named_process
    ):
        _make_lock(tmp_path / "repo" / ".git", b"", 100)
        git_named_process(tmp_path / "bin", tmp_path / "repo")

        assert has_live_lock_holder(str(tmp_path / "repo" / ".git")) is True

    def test_has_live_lock_holder_returns_false_when_non_git_process_cwd_in_worktree(
        self, tmp_path
    ):
        _make_lock(tmp_path / "repo" / ".git", b"", 100)
        proc = subprocess.Popen(["sleep", "60"], cwd=tmp_path / "repo")
        try:
            time.sleep(0.2)
            assert has_live_lock_holder(str(tmp_path / "repo" / ".git")) is False
        finally:
            proc.kill()
            proc.wait()

    def test_has_live_lock_holder_returns_none_when_proc_unavailable(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "mcp_server_git.lean.lock_holders._PROC", tmp_path / "no-proc"
        )

        assert has_live_lock_holder(str(tmp_path)) is None


class TestReapWithHolderCheck:
    def test_reap_stale_index_lock_reaps_non_zero_byte_lock_when_orphaned_past_threshold(
        self, tmp_path
    ):
        lock = _make_lock(tmp_path / ".git", b"partial", 30)

        reaped = reap_stale_index_lock(str(tmp_path / ".git"))

        assert reaped is True
        assert not lock.exists()

    def test_reap_stale_index_lock_keeps_orphaned_lock_when_younger_than_orphan_age(
        self, tmp_path
    ):
        lock = _make_lock(tmp_path / ".git", b"", 3)

        reaped = reap_stale_index_lock(str(tmp_path / ".git"))

        assert reaped is False
        assert lock.exists()

    def test_reap_stale_index_lock_honours_orphan_age_env_var_when_set(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("MCP_GIT_INDEX_LOCK_ORPHAN_AGE_SECONDS", "1")
        lock = _make_lock(tmp_path / ".git", b"", 3)

        reap_stale_index_lock(str(tmp_path / ".git"))

        assert not lock.exists()

    def test_reap_stale_index_lock_keeps_old_lock_when_child_has_it_open(
        self, tmp_path, open_holder
    ):
        lock = _make_lock(tmp_path / ".git", b"", 10_000)
        open_holder(lock)

        reaped = reap_stale_index_lock(str(tmp_path / ".git"))

        assert reaped is False
        assert lock.exists()

    def test_reap_stale_index_lock_keeps_old_lock_when_git_process_runs_in_worktree(
        self, tmp_path, git_named_process
    ):
        lock = _make_lock(tmp_path / "repo" / ".git", b"", 10_000)
        git_named_process(tmp_path / "bin", tmp_path / "repo")

        reaped = reap_stale_index_lock(str(tmp_path / "repo" / ".git"))

        assert reaped is False
        assert lock.exists()

    def test_reap_stale_index_lock_uses_conservative_rule_when_holder_unknown(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "mcp_server_git.lean.lock_reaper.has_live_lock_holder", lambda _: None
        )
        young_zero = _make_lock(tmp_path / "a", b"", 30)
        old_zero = _make_lock(tmp_path / "b", b"", 200)

        reap_stale_index_lock(str(tmp_path / "a"))
        reap_stale_index_lock(str(tmp_path / "b"))

        assert young_zero.exists()
        assert not old_zero.exists()
