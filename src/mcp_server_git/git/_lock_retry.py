"""Centralized index.lock handling for index-mutating ops (#276, #292).

``run_index_op`` is the single entry point used by the lean ``wrap_repo_op``:
reap a provably stale lock up front, run the op, and on an ``index.lock``
conflict reap-and-retry exactly once. A young lock whose holder is known to
be dead is waited out (bounded by the orphan-age threshold) instead of being
reported as a failure.
"""

import time
from collections.abc import Callable
from pathlib import Path

from ..utils.git_import import Repo
from ..utils.tool_failure import ToolFailure

__all__ = [
    "READ_ONLY_ENV",
    "is_index_lock_conflict",
    "retry_after_lock_reap",
    "run_index_op",
]

# Env for read-only git calls (status, diff): stops git taking index.lock to
# refresh the index, which could race with (or orphan) a real writer.
READ_ONLY_ENV = {"GIT_OPTIONAL_LOCKS": "0"}

# Patchable so tests never actually wait.
_sleep = time.sleep

# Cushion so the lock is strictly past the threshold when we wake up.
_WAKE_MARGIN_SECONDS = 0.05


def is_index_lock_conflict(message: str) -> bool:
    """True if *message* is git's "index.lock: File exists" failure."""
    return "index.lock" in message and "File exists" in message


def _wait_out_young_orphan(git_dir: str) -> None:
    """Sleep until a dead-holder lock reaches the orphan age (never longer)."""
    # Lazy imports: the lean package imports the git package at load time.
    from ..lean.lock_holders import has_live_lock_holder
    from ..lean.lock_reaper import orphan_age_seconds

    try:
        mtime = (Path(git_dir) / "index.lock").stat().st_mtime
    except OSError:
        return
    threshold = orphan_age_seconds()
    remaining = threshold - (time.time() - mtime)
    if remaining <= 0 or has_live_lock_holder(git_dir) is not False:
        return
    _sleep(min(remaining + _WAKE_MARGIN_SECONDS, threshold))


def retry_after_lock_reap(
    repo: Repo, attempt: Callable[[], str], op_name: str | None = None
) -> str:
    """Run *attempt*; on an index.lock conflict reap once and retry once.

    If the lock is still there afterwards (live holder, unknown holder and
    too young), the original failure is returned unchanged (a ToolFailure).
    """
    result = attempt()
    if not (isinstance(result, ToolFailure) and is_index_lock_conflict(result)):
        return result

    from ..lean.lock_reaper import reap_stale_index_lock

    _wait_out_young_orphan(repo.git_dir)
    reaped = reap_stale_index_lock(repo.git_dir, op=op_name)
    if not reaped and (Path(repo.git_dir) / "index.lock").exists():
        return result
    # Reaped, or the lock was released meanwhile: one more attempt.
    return attempt()


def run_index_op(
    repo: Repo, attempt: Callable[[], str], op_name: str | None = None
) -> str:
    """Pre-reap a stale lock, then run *attempt* with one reap-and-retry."""
    from ..lean.lock_reaper import reap_stale_index_lock

    reap_stale_index_lock(repo.git_dir, op=op_name)
    return retry_after_lock_reap(repo, attempt, op_name)
