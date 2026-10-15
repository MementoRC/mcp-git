"""Centralized index.lock retry for every mutates_index op (issue #292).

Real repos and real 0-byte lock files; only the sleep is patched so a young
orphan "ages" instantly instead of being waited out for real.
"""

import logging
import os
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from git import Repo

from mcp_server_git.lean.registry_git import _register_git_tools
from mcp_server_git.utils.tool_failure import ToolFailure

ORPHAN_AGE = 15.0


def _tool(name: str):
    registry = {}
    interface = MagicMock()
    interface.register_tool.side_effect = lambda t: registry.__setitem__(t.name, t)
    _register_git_tools(interface, git_service=MagicMock())
    return registry[name].implementation


def _set_age(lock: Path, age_seconds: float) -> None:
    old = time.time() - age_seconds
    os.utime(lock, (old, old))


@pytest.fixture(autouse=True)
def orphan_age(monkeypatch):
    monkeypatch.setenv("MCP_GIT_INDEX_LOCK_ORPHAN_AGE_SECONDS", str(ORPHAN_AGE))


@pytest.fixture
def repo(tmp_path) -> Repo:
    path = tmp_path / "repo"
    path.mkdir()
    r = Repo.init(path)
    with r.config_writer() as cw:
        cw.set_value("user", "name", "T")
        cw.set_value("user", "email", "t@example.com")
    (path / "a.txt").write_text("hello\n")
    r.index.add(["a.txt"])
    r.index.commit("initial")
    r.create_head("other")
    return r


@pytest.fixture
def lock(repo) -> Path:
    """A fresh (age 0) zero-byte lock that no process holds."""
    path = Path(repo.git_dir) / "index.lock"
    path.write_bytes(b"")
    return path


@pytest.fixture
def sleeps(monkeypatch, lock) -> list[float]:
    """Patched sleep: records the request and ages the lock past the threshold."""
    calls: list[float] = []

    def fake_sleep(seconds: float) -> None:
        calls.append(seconds)
        _set_age(lock, ORPHAN_AGE + 5)

    monkeypatch.setattr("mcp_server_git.git._lock_retry._sleep", fake_sleep)
    return calls


@pytest.fixture
def live_holder(lock) -> Iterator[subprocess.Popen]:
    """A real child process holding the lock file open."""
    proc = subprocess.Popen(
        ["sh", "-c", 'exec 3>"$0"; echo ready; exec sleep 60', str(lock)],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert proc.stdout is not None
    assert proc.stdout.readline().strip() == "ready"
    try:
        yield proc
    finally:
        proc.kill()
        proc.wait()


class TestFreshOrphanIsWaitedOut:
    def test_git_checkout_succeeds_when_fresh_orphan_lock_ages_out(
        self, repo, lock, sleeps
    ):
        result = _tool("git_checkout")(repo_path=repo.working_dir, branch_name="other")

        assert not isinstance(result, ToolFailure), result
        assert repo.active_branch.name == "other"
        assert not lock.exists()
        assert len(sleeps) == 1
        assert 0 < sleeps[0] <= ORPHAN_AGE

    def test_git_reset_succeeds_when_fresh_orphan_lock_ages_out(
        self, repo, lock, sleeps
    ):
        result = _tool("git_reset")(repo_path=repo.working_dir, mode="mixed")

        assert not isinstance(result, ToolFailure), result
        assert not lock.exists()
        assert len(sleeps) == 1

    def test_git_create_branch_checks_out_when_fresh_orphan_lock_ages_out(
        self, repo, lock, sleeps
    ):
        result = _tool("git_create_branch")(
            repo_path=repo.working_dir, branch_name="feat/x", checkout=True
        )

        assert not isinstance(result, ToolFailure), result
        assert repo.active_branch.name == "feat/x"
        assert not lock.exists()
        assert len(sleeps) == 1


class TestNoWaitWithoutDeadHolder:
    def test_git_checkout_returns_failure_without_waiting_when_holder_is_live(
        self, repo, lock, sleeps, live_holder
    ):
        result = _tool("git_checkout")(repo_path=repo.working_dir, branch_name="other")

        assert isinstance(result, ToolFailure)
        assert "index.lock" in result
        assert sleeps == []
        assert lock.exists()

    def test_git_checkout_returns_failure_without_waiting_when_holder_unknown(
        self, repo, lock, sleeps, monkeypatch
    ):
        monkeypatch.setattr(
            "mcp_server_git.lean.lock_holders.has_live_lock_holder", lambda _: None
        )
        monkeypatch.setattr(
            "mcp_server_git.lean.lock_reaper.has_live_lock_holder", lambda _: None
        )

        result = _tool("git_checkout")(repo_path=repo.working_dir, branch_name="other")

        assert isinstance(result, ToolFailure)
        assert sleeps == []
        assert lock.exists()

    def test_git_create_branch_reports_created_not_checked_out_when_lock_is_held(
        self, repo, lock, sleeps, live_holder
    ):
        result = _tool("git_create_branch")(
            repo_path=repo.working_dir, branch_name="feat/y", checkout=True
        )

        assert isinstance(result, ToolFailure)
        assert "feat/y" in result
        assert "created but NOT checked out" in result
        assert "feat/y" in [h.name for h in repo.heads]
        assert sleeps == []


class TestCreateBranchDuplicate:
    def test_git_create_branch_returns_already_exists_when_called_twice(self, repo):
        create = _tool("git_create_branch")
        create(repo_path=repo.working_dir, branch_name="feat/z", checkout=False)

        result = create(repo_path=repo.working_dir, branch_name="feat/z", checkout=True)

        assert isinstance(result, ToolFailure)
        assert "already exists" in result
        assert repo.active_branch.name != "feat/z"


class TestReapLogging:
    def test_reap_logs_info_with_lock_details_when_orphan_is_removed(
        self, repo, lock, caplog
    ):
        _set_age(lock, 200)

        with caplog.at_level(logging.INFO, logger="mcp_server_git.lean.lock_reaper"):
            _tool("git_checkout")(repo_path=repo.working_dir, branch_name="other")

        records = [r for r in caplog.records if "Reaped" in r.getMessage()]
        assert len(records) == 1
        assert records[0].levelno == logging.INFO
        message = records[0].getMessage()
        assert str(lock) in message
        assert "size=0 bytes" in message
        assert "age=200" in message
        assert "live_holder=False" in message
        assert "op=git_checkout" in message
