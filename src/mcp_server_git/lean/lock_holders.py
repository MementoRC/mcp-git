"""Live-holder detection for ``index.lock`` (Linux ``/proc`` only).

A lock is considered held when either:

* some process has the lock file open (``/proc/<pid>/fd`` symlink), or
* a process whose ``argv[0]`` basename is ``git`` has its cwd, or its
  ``GIT_DIR`` environment variable, pointing into this git dir / worktree.

Unreadable or vanished pids are skipped. When ``/proc`` is unavailable
(e.g. macOS) the answer is ``None`` ("unknown") and callers must fall back
to a conservative rule.
"""

from __future__ import annotations

import os
from pathlib import Path

_PROC = Path("/proc")


def _is_within(path: str, roots: list[str]) -> bool:
    return any(path == root or path.startswith(root + os.sep) for root in roots)


def _roots(git_dir: str) -> list[str]:
    """Paths that identify this repository: the git dir and its worktree."""
    real_git_dir = os.path.realpath(git_dir)
    roots = [real_git_dir]
    pointer = Path(real_git_dir) / "gitdir"
    try:
        # Linked worktree: <git_dir>/gitdir holds "<worktree>/.git".
        roots.append(os.path.dirname(os.path.realpath(pointer.read_text().strip())))
    except OSError:
        roots.append(os.path.dirname(real_git_dir))
    return roots


def _holds_file_open(pid_dir: Path, lock_real: str) -> bool:
    try:
        for fd in os.listdir(pid_dir / "fd"):
            try:
                if os.path.realpath(os.readlink(pid_dir / "fd" / fd)) == lock_real:
                    return True
            except OSError:
                continue
    except OSError:
        return False
    return False


def _is_git_process(pid_dir: Path) -> bool:
    """True for a `git` process that can take locks.

    GitPython's persistent ``git cat-file --batch`` readers linger in the
    repo cwd (often spawned by this very server) and never take index.lock,
    so they are not holders.
    """
    try:
        argv = (pid_dir / "cmdline").read_bytes().split(b"\0")
    except OSError:
        return False
    if os.path.basename(argv[0].decode(errors="replace")) != "git":
        return False
    return b"cat-file" not in argv[1:]


def _environ_git_dir(pid_dir: Path) -> str | None:
    try:
        environ = (pid_dir / "environ").read_bytes().split(b"\0")
    except OSError:
        return None
    for entry in environ:
        if entry.startswith(b"GIT_DIR="):
            return os.path.realpath(entry[8:].decode(errors="replace"))
    return None


def _git_process_targets(pid_dir: Path, roots: list[str]) -> bool:
    if not _is_git_process(pid_dir):
        return False
    try:
        cwd = os.path.realpath(os.readlink(pid_dir / "cwd"))
    except OSError:
        cwd = None
    if cwd is not None and _is_within(cwd, roots):
        return True
    env_git_dir = _environ_git_dir(pid_dir)
    return env_git_dir is not None and _is_within(env_git_dir, roots)


def has_live_lock_holder(git_dir: str) -> bool | None:
    """True if a live process holds ``index.lock``; None if undeterminable."""
    if not (_PROC / "self" / "fd").is_dir():
        return None
    lock_real = os.path.realpath(os.path.join(git_dir, "index.lock"))
    roots = _roots(git_dir)
    try:
        pids = [p for p in os.listdir(_PROC) if p.isdigit()]
    except OSError:
        return None
    own = str(os.getpid())
    for pid in pids:
        pid_dir = _PROC / pid
        if _holds_file_open(pid_dir, lock_real):
            return True
        if pid != own and _git_process_targets(pid_dir, roots):
            return True
    return False
