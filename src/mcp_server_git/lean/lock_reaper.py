"""Stale ``index.lock`` reaper.

A git subprocess killed mid-operation (e.g. an agent process terminated
while a commit/add/checkout was in flight) can leave a zero-byte
``index.lock`` file behind. Every later index-mutating git operation then
fails with ``Unable to create '.git/index.lock': File exists`` until a
human manually deletes the stale lock — this has repeatedly bricked git
access for automated agents.

This module removes such a lock immediately before an index-mutating
operation runs, but ONLY when it is provably stale. All three conditions
below must hold before the lock is unlinked:

1. The lock file exists.
2. Its size is EXACTLY 0 bytes. Git writes lock content incrementally
   while an operation is genuinely in progress, so a partially-written
   (non-zero-byte) lock means a real operation is mid-write right now —
   that file is NEVER touched, regardless of its age. Zero bytes is the
   only size a lock can safely have while no live operation is actually
   writing through it.
3. Its mtime is older than a threshold (default 120s, overridable via
   ``MCP_GIT_INDEX_LOCK_MAX_AGE_SECONDS``). This protects a genuinely
   in-flight but not-yet-written lock from being reaped out from under a
   live, slow operation.

If any condition fails, the lock file is left alone and the underlying
git error is allowed to surface normally — this reaper never masks a real
concurrent-access conflict.

Every reap is logged at WARNING level (resolved lock path + age) so this
never becomes a silent side effect.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from .lock_holders import has_live_lock_holder

logger = logging.getLogger(__name__)

_DEFAULT_MAX_AGE_SECONDS = 120.0
_MAX_AGE_ENV_VAR = "MCP_GIT_INDEX_LOCK_MAX_AGE_SECONDS"
_DEFAULT_ORPHAN_AGE_SECONDS = 15.0
_ORPHAN_AGE_ENV_VAR = "MCP_GIT_INDEX_LOCK_ORPHAN_AGE_SECONDS"


def _env_seconds(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning(
            "Invalid %s=%r, falling back to default %.1fs", name, raw, default
        )
        return default


def _max_age_seconds() -> float:
    return _env_seconds(_MAX_AGE_ENV_VAR, _DEFAULT_MAX_AGE_SECONDS)


def _is_reapable(size: int, age_seconds: float, holder: bool | None) -> bool:
    """Decide whether a lock may be removed.

    With a known holder status: never while held; once orphaned, reap
    regardless of size after the short orphan threshold. With unknown holder
    status (no /proc): the conservative zero-byte + long-age rule.
    """
    if holder is True:
        return False
    if holder is False:
        return age_seconds >= _env_seconds(
            _ORPHAN_AGE_ENV_VAR, _DEFAULT_ORPHAN_AGE_SECONDS
        )
    return size == 0 and age_seconds >= _max_age_seconds()


def reap_stale_index_lock(git_dir: str) -> bool:
    """Remove ``<git_dir>/index.lock`` if it is provably stale.

    Returns True if a lock was removed. When no live process holds the lock
    (see ``lock_holders``) it is reaped regardless of size once older than
    ``MCP_GIT_INDEX_LOCK_ORPHAN_AGE_SECONDS`` (default 15s). If holder
    detection is unavailable the conservative rule described in the module
    docstring applies unchanged.

    ``git_dir`` must already be the RESOLVED git directory (i.e.
    ``Repo.git_dir``, not a bare ``<repo>/.git``) so this works correctly
    for linked worktrees, where ``.git`` is a file pointing at
    ``<main-gitdir>/worktrees/<name>`` and the lock lives there, not at
    ``<repo>/.git/index.lock``.

    The common case — no lock file present — costs a single ``stat()``
    call and returns immediately, so this is safe to call unconditionally
    from performance-sensitive call sites.
    """
    lock_path = Path(git_dir) / "index.lock"

    try:
        stat_result = lock_path.stat()
    except OSError:
        # No lock present (the common case) or the path is otherwise
        # inaccessible — nothing to reap, let the caller proceed normally.
        return False

    age_seconds = time.time() - stat_result.st_mtime
    if not _is_reapable(
        stat_result.st_size, age_seconds, has_live_lock_holder(git_dir)
    ):
        # Held by a live process, or too fresh / partially written under the
        # conservative rule. Never touch it.
        return False

    try:
        lock_path.unlink()
    except OSError:
        # Lost a race with the process that owns the lock, or a
        # permissions issue — let the underlying git error surface
        # normally rather than raising from the reaper.
        return False

    logger.warning(
        "Reaped stale index.lock at %s (size=%d, age=%.1fs)",
        lock_path,
        stat_result.st_size,
        age_seconds,
    )
    return True
