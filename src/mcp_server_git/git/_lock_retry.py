"""One-shot retry of an index-mutating op after reaping an orphaned index.lock."""

from collections.abc import Callable

from ..utils.git_import import Repo
from ..utils.tool_failure import ToolFailure

__all__ = ["READ_ONLY_ENV", "is_index_lock_conflict", "retry_after_lock_reap"]

# Env for read-only `git status` calls: stops git taking index.lock to
# refresh the index, which could race with (or orphan) a real writer.
READ_ONLY_ENV = {"GIT_OPTIONAL_LOCKS": "0"}


def is_index_lock_conflict(message: str) -> bool:
    """True if *message* is git's "index.lock: File exists" failure."""
    return "index.lock" in message and "File exists" in message


def retry_after_lock_reap(repo: Repo, attempt: Callable[[], str]) -> str:
    """Run *attempt*; on an index.lock conflict reap once and retry once.

    If the reaper does not remove the lock (live holder, too young), the
    original failure is returned unchanged (still a ToolFailure).
    """
    result = attempt()
    if not (isinstance(result, ToolFailure) and is_index_lock_conflict(result)):
        return result

    # Lazy import: the lean package imports the git package at load time.
    from ..lean.lock_reaper import reap_stale_index_lock

    if not reap_stale_index_lock(repo.git_dir):
        return result
    return attempt()
