"""Index-lock hardening for git_add / git_commit / git_status (issue #276)."""

import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from git import Git, GitCommandError, Repo

from mcp_server_git.git._commit_ops import git_commit, git_status
from mcp_server_git.git._commit_runner import (
    CommitProcessResult,
    CommitTimeoutError,
    run_commit_process,
)
from mcp_server_git.git._staging_ops import git_add
from mcp_server_git.utils.tool_failure import ToolFailure

LOCK_ERROR = "fatal: Unable to create '/x/.git/index.lock': File exists."


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "repo"
    path.mkdir()
    r = Repo.init(path)
    (path / "a.txt").write_text("hello\n")
    return r


def _plant_lock(repo: Repo, age_seconds: float) -> Path:
    lock = Path(repo.git_dir) / "index.lock"
    lock.write_bytes(b"")
    old = time.time() - age_seconds
    os.utime(lock, (old, old))
    return lock


class TestGitAddLockRetry:
    def test_git_add_succeeds_after_reaping_orphaned_lock_when_lock_exists(self, repo):
        lock = _plant_lock(repo, age_seconds=60)

        result = git_add(repo, files=["a.txt"])

        assert result.startswith("✅"), result
        assert not lock.exists()
        assert "a.txt" in repo.git.diff("--cached", "--name-only")

    def test_git_add_returns_tool_failure_when_lock_is_too_young_to_reap(self, repo):
        lock = _plant_lock(repo, age_seconds=1)

        result = git_add(repo, files=["a.txt"])

        assert isinstance(result, ToolFailure)
        assert "index.lock" in result
        assert lock.exists()

    def test_git_add_retries_exactly_once_when_lock_persists_after_reap(self, repo):
        attempts = []

        def always_locked(name, *_args, **_kwargs):
            if name != "add":
                return ""
            attempts.append(1)
            _plant_lock(repo, age_seconds=60)
            raise GitCommandError(["git", "add"], 128, stderr=LOCK_ERROR)

        with patch.object(Git, "_call_process", side_effect=always_locked):
            result = git_add(repo, files=["a.txt"])

        assert len(attempts) == 2
        assert isinstance(result, ToolFailure)


class TestGitCommitLockRetryAndTimeout:
    def _mock_repo(self, git_dir: str) -> MagicMock:
        mock_repo = MagicMock()
        mock_repo.working_dir = "/tmp/test_repo"
        mock_repo.git_dir = git_dir
        mock_repo.config_reader.return_value.get_value.return_value = "KEY"
        return mock_repo

    def test_git_commit_retries_once_when_lock_reaped(self, repo):
        lock = _plant_lock(repo, age_seconds=60)
        locked = CommitProcessResult(128, "", LOCK_ERROR)
        ok = CommitProcessResult(0, "", "")
        with (
            patch(
                "mcp_server_git.git._commit_ops.run_commit_process",
                side_effect=[locked, ok],
            ) as run,
            patch(
                "mcp_server_git.git._commit_ops.subprocess.run",
                return_value=MagicMock(returncode=0, stdout="abc12345\n"),
            ),
            patch(
                "mcp_server_git.git.security.enforce_secure_git_config",
                return_value="ok",
            ),
        ):
            result = git_commit(self._mock_repo(repo.git_dir), message="m")

        assert run.call_count == 2
        assert result.startswith("✅")
        assert not lock.exists()

    def test_git_commit_returns_tool_failure_without_retry_when_lock_not_reaped(
        self, repo
    ):
        _plant_lock(repo, age_seconds=1)
        locked = CommitProcessResult(128, "", LOCK_ERROR)
        with (
            patch(
                "mcp_server_git.git._commit_ops.run_commit_process",
                return_value=locked,
            ) as run,
            patch(
                "mcp_server_git.git.security.enforce_secure_git_config",
                return_value="ok",
            ),
        ):
            result = git_commit(self._mock_repo(repo.git_dir), message="m")

        assert run.call_count == 1
        assert isinstance(result, ToolFailure)
        assert "index.lock" in result

    def test_git_commit_returns_tool_failure_when_commit_times_out(self, repo):
        with (
            patch(
                "mcp_server_git.git._commit_ops.run_commit_process",
                side_effect=CommitTimeoutError(1),
            ),
            patch(
                "mcp_server_git.git.security.enforce_secure_git_config",
                return_value="ok",
            ),
        ):
            result = git_commit(self._mock_repo(repo.git_dir), message="m")

        assert isinstance(result, ToolFailure)
        assert "timed out" in result


class TestRunCommitProcess:
    def test_run_commit_process_sets_terminal_prompt_off_when_spawning(self, tmp_path):
        result = run_commit_process(
            ["sh", "-c", "echo $GIT_TERMINAL_PROMPT"], str(tmp_path)
        )

        assert result.stdout.strip() == "0"

    def test_run_commit_process_raises_timeout_when_process_exceeds_limit(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("MCP_GIT_COMMIT_TIMEOUT_SECONDS", "0.5")
        start = time.monotonic()

        with pytest.raises(CommitTimeoutError):
            run_commit_process(["sleep", "30"], str(tmp_path))

        assert time.monotonic() - start < 10

    def test_run_commit_process_sigkills_group_when_sigterm_is_ignored(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("MCP_GIT_COMMIT_TIMEOUT_SECONDS", "0.5")
        monkeypatch.setattr(
            "mcp_server_git.git._commit_runner._TERM_GRACE_SECONDS", 0.5
        )
        pidfile = tmp_path / "pid"
        script = f'echo $$ > {pidfile}; trap "" TERM; while :; do sleep 1; done'

        with pytest.raises(CommitTimeoutError):
            run_commit_process(["sh", "-c", script], str(tmp_path))

        pid = int(pidfile.read_text())
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)

    def test_run_commit_process_uses_default_timeout_when_env_invalid(
        self, monkeypatch
    ):
        from mcp_server_git.git._commit_runner import commit_timeout_seconds

        monkeypatch.setenv("MCP_GIT_COMMIT_TIMEOUT_SECONDS", "bogus")

        assert commit_timeout_seconds() == 120.0


class TestStatusUsesOptionalLocksOff:
    @staticmethod
    def _status_envs(repo: Repo, run) -> list[dict]:
        """Environments in effect for every `git status` that `run` triggers."""
        seen: list[dict] = []

        def record(name, *_args, **kwargs):
            if name == "status":
                seen.append(dict(kwargs.get("env") or {}))
            return ""

        with patch.object(Git, "_call_process", side_effect=record):
            run()
        return seen

    def test_git_status_sets_optional_locks_off_when_reading(self, repo):
        envs = self._status_envs(repo, lambda: git_status(repo, porcelain=True))

        assert envs
        assert all(env.get("GIT_OPTIONAL_LOCKS") == "0" for env in envs)

    def test_git_add_files_sets_optional_locks_off_when_checking_status(self, repo):
        envs = self._status_envs(repo, lambda: git_add(repo, files=["a.txt"]))

        assert envs
        assert all(env.get("GIT_OPTIONAL_LOCKS") == "0" for env in envs)
