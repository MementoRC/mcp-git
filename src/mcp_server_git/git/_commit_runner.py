"""Run ``git commit`` in its own session with a timeout and group kill."""

import logging
import os
import signal
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_TIMEOUT_ENV_VAR = "MCP_GIT_COMMIT_TIMEOUT_SECONDS"
_DEFAULT_TIMEOUT_SECONDS = 120.0
_TERM_GRACE_SECONDS = 5.0


class CommitTimeoutError(Exception):
    """The commit process exceeded its timeout and was terminated."""

    def __init__(self, timeout: float):
        super().__init__(f"git commit timed out after {timeout:g}s")
        self.timeout = timeout


@dataclass(frozen=True)
class CommitProcessResult:
    returncode: int
    stdout: str
    stderr: str


def commit_timeout_seconds() -> float:
    raw = os.environ.get(_TIMEOUT_ENV_VAR)
    if raw is None:
        return _DEFAULT_TIMEOUT_SECONDS
    try:
        return float(raw)
    except ValueError:
        logger.warning(
            "Invalid %s=%r, falling back to default %.1fs",
            _TIMEOUT_ENV_VAR,
            raw,
            _DEFAULT_TIMEOUT_SECONDS,
        )
        return _DEFAULT_TIMEOUT_SECONDS


def _signal_group(proc: subprocess.Popen, sig: signal.Signals) -> None:
    try:
        os.killpg(proc.pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _terminate_group(proc: subprocess.Popen) -> None:
    """SIGTERM the process group, SIGKILL only if it outlives the grace."""
    _signal_group(proc, signal.SIGTERM)
    try:
        proc.communicate(timeout=_TERM_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        _signal_group(proc, signal.SIGKILL)
        proc.communicate()


def run_commit_process(cmd: list[str], cwd: str) -> CommitProcessResult:
    """Run *cmd* in a new session; raise CommitTimeoutError on timeout."""
    timeout = commit_timeout_seconds()
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _terminate_group(proc)
        raise CommitTimeoutError(timeout) from None
    return CommitProcessResult(proc.returncode, stdout, stderr)
