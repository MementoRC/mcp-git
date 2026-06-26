"""Stash operations for MCP Git Server."""

import logging
import os
import subprocess

from ..utils.git_import import Repo

logger = logging.getLogger(__name__)

__all__ = [
    "git_stash_list",
    "git_stash_push",
    "git_stash_pop",
    "git_stash_drop",
]

# Git environment variables that can interfere with worktree stash operations.
# Stripping these lets git auto-detect the repo from the working directory,
# which matches what a plain shell `git stash` does.
_GIT_ENV_KEYS = frozenset(
    {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"}
)


def _clean_git_env() -> dict[str, str]:
    """Return os.environ without keys that confuse git in worktrees."""
    return {k: v for k, v in os.environ.items() if k not in _GIT_ENV_KEYS}


def _run_git(args: list[str], cwd: str) -> subprocess.CompletedProcess[str]:
    """Run a git command in *cwd* with a worktree-safe environment."""
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=_clean_git_env(),
        capture_output=True,
        text=True,
    )


def git_stash_list(repo: Repo) -> str:
    """List all stashes"""
    try:
        result = _run_git(["stash", "list"], cwd=repo.working_dir)
        if result.returncode != 0:
            return f"❌ Stash list failed: {result.stderr.strip() or result.stdout.strip()}"
        output = result.stdout.strip()
        if not output:
            return "No stashes found"
        return f"Stash list:\n{output}"
    except Exception as e:
        return f"❌ Stash list error: {str(e)}"


def git_stash_push(
    repo: Repo, message: str | None = None, include_untracked: bool = False
) -> str:
    """Create a new stash.

    Uses subprocess rather than repo.git.stash() to avoid GitPython's GIT_DIR
    handling that causes exit-code-1 failures in git linked worktrees (#189).
    """
    try:
        args = ["stash", "push"]
        if include_untracked:
            args.append("--include-untracked")
        if message:
            args.extend(["-m", message])

        result = _run_git(args, cwd=repo.working_dir)

        if result.returncode == 0:
            return "✅ Successfully created stash" + (f": {message}" if message else "")

        output = result.stdout.strip()
        if result.returncode == 1 and "No local changes to save" in output:
            return "ℹ️ No local changes to stash"

        error = result.stderr.strip() or output
        return f"❌ Stash push failed: {error}"
    except Exception as e:
        return f"❌ Stash push error: {str(e)}"


def git_stash_pop(repo: Repo, stash_id: str | None = None) -> str:
    """Apply and remove a stash"""
    try:
        args = ["stash", "pop"]
        if stash_id:
            args.append(stash_id)

        result = _run_git(args, cwd=repo.working_dir)
        if result.returncode != 0:
            return f"❌ Stash pop failed: {result.stderr.strip() or result.stdout.strip()}"

        if stash_id:
            return f"✅ Successfully popped stash {stash_id}"
        return "✅ Successfully popped latest stash"
    except Exception as e:
        return f"❌ Stash pop error: {str(e)}"


def git_stash_drop(repo: Repo, stash_id: str | None = None) -> str:
    """Remove a stash without applying it"""
    try:
        args = ["stash", "drop"]
        if stash_id:
            args.append(stash_id)

        result = _run_git(args, cwd=repo.working_dir)
        if result.returncode != 0:
            return f"❌ Stash drop failed: {result.stderr.strip() or result.stdout.strip()}"

        if stash_id:
            return f"✅ Successfully dropped stash {stash_id}"
        return "✅ Successfully dropped latest stash"
    except Exception as e:
        return f"❌ Stash drop error: {str(e)}"
