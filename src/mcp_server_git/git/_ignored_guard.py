"""Guard against silently clobbering ignored working-tree files (issue #283).

Git overwrites (checkout/merge) or removes (fast-forward) *ignored* files
without any warning when the target ref tracks a file at that path. Such files
are not in the index, so git's usual "untracked file would be overwritten"
protection does not apply, and their content is unrecoverable.

``ignored_overwrite_failure`` detects them cheaply and read-only: it only
looks at paths the target ref tracks that are absent from the index but
present on disk, then asks ``git check-ignore`` which of those are ignored.
"""

import logging
import os
import subprocess

from ..utils.git_import import GitCommandError, Repo
from ..utils.tool_failure import ToolFailure, fail
from ._lock_retry import READ_ONLY_ENV
from .error_text import clean_git_error_text

logger = logging.getLogger(__name__)

__all__ = ["find_ignored_overwrites", "ignored_overwrite_failure"]

_MAX_LISTED = 10


def _nul_list(output: str) -> list[str]:
    return [item for item in output.split("\0") if item]


def _target_paths(repo: Repo, target: str, *, only_changed: bool) -> list[str]:
    """Paths the target tracks (for a merge: only those differing from the base)."""
    if only_changed:
        # No common ancestor (unrelated histories) -> empty output -> full tree.
        base = repo.git.merge_base(
            "HEAD", target, env=READ_ONLY_ENV, with_exceptions=False
        ).strip()
        if base:
            diff = repo.git.diff(
                "--name-only", "-z", "--diff-filter=d", base, target, env=READ_ONLY_ENV
            )
            return _nul_list(diff)
    tree = repo.git.ls_tree("-r", "--name-only", "-z", target, env=READ_ONLY_ENV)
    return _nul_list(tree)


def _ignored_subset(working_dir: str, paths: list[str]) -> list[str]:
    """Which of *paths* are matched by ignore rules (read-only, no index lock)."""
    if not paths:
        return []
    proc = subprocess.run(
        ["git", "check-ignore", "--no-index", "--stdin", "-z"],
        cwd=working_dir,
        input="\0".join(paths) + "\0",
        capture_output=True,
        text=True,
        env={**os.environ, **READ_ONLY_ENV},
    )
    if proc.returncode not in (0, 1):
        raise OSError(f"git check-ignore failed: {proc.stderr.strip()}")
    return _nul_list(proc.stdout)


def find_ignored_overwrites(
    repo: Repo, target: str, *, only_changed: bool = False
) -> list[str]:
    """Ignored on-disk files that switching to / merging *target* would clobber.

    With ``only_changed`` (merges) only paths whose content differs between
    the merge base and *target* count, since git leaves the rest alone.
    """
    working_dir = repo.working_dir
    if not working_dir:
        return []
    tracked = set(_nul_list(repo.git.ls_files("-z", env=READ_ONLY_ENV)))
    candidates = [
        path
        for path in _target_paths(repo, target, only_changed=only_changed)
        if path not in tracked and os.path.lexists(os.path.join(str(working_dir), path))
    ]
    return sorted(_ignored_subset(str(working_dir), candidates))


def ignored_overwrite_failure(
    repo: Repo,
    target: str,
    action: str,
    *,
    allow: bool = False,
    only_changed: bool = False,
) -> ToolFailure | None:
    """A failure listing the ignored files at risk, or None when safe to proceed.

    The check itself never blocks an operation by erroring: if it cannot run
    (bad ref, odd repo state) git's own error handling reports the real problem.
    """
    if allow:
        return None
    try:
        files = find_ignored_overwrites(repo, target, only_changed=only_changed)
    except GitCommandError as err:
        reason = clean_git_error_text(err.stderr, "stderr")
        logger.warning("ignored-file guard skipped for %s: %s", target, reason)
        return None
    except OSError as err:
        logger.warning("ignored-file guard skipped for %s: %s", target, err)
        return None
    if not files:
        return None
    shown = ", ".join(files[:_MAX_LISTED])
    extra = len(files) - _MAX_LISTED
    suffix = f" (+{extra} more)" if extra > 0 else ""
    return fail(
        f"❌ Refusing to {action} '{target}': {len(files)} ignored working-tree "
        f"file(s) would be overwritten or removed: {shown}{suffix}. "
        "Back them up, or pass allow_overwrite_ignored=True to proceed."
    )
