"""Stash operations for MCP Git Server."""

import logging

from ..utils.git_import import GitCommandError, Repo

logger = logging.getLogger(__name__)

__all__ = [
    "git_stash_list",
    "git_stash_push",
    "git_stash_pop",
    "git_stash_drop",
]


def git_stash_list(repo: Repo) -> str:
    """List all stashes"""
    try:
        stash_list = repo.git.stash("list")
        if not stash_list.strip():
            return "No stashes found"
        return f"Stash list:\n{stash_list}"
    except GitCommandError as e:
        return f"❌ Stash list failed: {str(e)}"
    except Exception as e:
        return f"❌ Stash list error: {str(e)}"


def git_stash_push(
    repo: Repo, message: str | None = None, include_untracked: bool = False
) -> str:
    """Create a new stash"""
    try:
        args = ["push"]
        if include_untracked:
            args.append("--include-untracked")
        if message:
            args.extend(["-m", message])

        repo.git.stash(*args)
        return "✅ Successfully created stash" + (f": {message}" if message else "")
    except GitCommandError as e:
        return f"❌ Stash push failed: {str(e)}"
    except Exception as e:
        return f"❌ Stash push error: {str(e)}"


def git_stash_pop(repo: Repo, stash_id: str | None = None) -> str:
    """Apply and remove a stash"""
    try:
        if stash_id:
            repo.git.stash("pop", stash_id)
            return f"✅ Successfully popped stash {stash_id}"
        else:
            repo.git.stash("pop")
            return "✅ Successfully popped latest stash"
    except GitCommandError as e:
        return f"❌ Stash pop failed: {str(e)}"
    except Exception as e:
        return f"❌ Stash pop error: {str(e)}"


def git_stash_drop(repo: Repo, stash_id: str | None = None) -> str:
    """Remove a stash without applying it"""
    try:
        if stash_id:
            repo.git.stash("drop", stash_id)
            return f"✅ Successfully dropped stash {stash_id}"
        else:
            repo.git.stash("drop")
            return "✅ Successfully dropped latest stash"
    except GitCommandError as e:
        return f"❌ Stash drop failed: {str(e)}"
    except Exception as e:
        return f"❌ Stash drop error: {str(e)}"
