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

logger = logging.getLogger(__name__)

_DEFAULT_MAX_AGE_SECONDS = 120.0
_MAX_AGE_ENV_VAR = "MCP_GIT_INDEX_LOCK_MAX_AGE_SECONDS"


def _max_age_seconds() -> float:
    raw = os.environ.get(_MAX_AGE_ENV_VAR)
    if raw is None:
        return _DEFAULT_MAX_AGE_SECONDS
    try:
        return float(raw)
    except ValueError:
        logger.warning(
            "Invalid %s=%r, falling back to default %.1fs",
            _MAX_AGE_ENV_VAR,
            raw,
            _DEFAULT_MAX_AGE_SECONDS,
        )
        return _DEFAULT_MAX_AGE_SECONDS


def reap_stale_index_lock(git_dir: str) -> None:
    """Remove ``<git_dir>/index.lock`` if it is provably stale.

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
        return

    if stat_result.st_size != 0:
        # A real operation is mid-write. Never touch it.
        return

    age_seconds = time.time() - stat_result.st_mtime
    if age_seconds < _max_age_seconds():
        # Fresh zero-byte lock — could be a genuinely in-flight operation
        # that hasn't started writing yet. Leave it alone.
        return

    try:
        lock_path.unlink()
    except OSError:
        # Lost a race with the process that owns the lock, or a
        # permissions issue — let the underlying git error surface
        # normally rather than raising from the reaper.
        return

    logger.warning(
        "Reaped stale zero-byte index.lock at %s (age=%.1fs)",
        lock_path,
        age_seconds,
    )
