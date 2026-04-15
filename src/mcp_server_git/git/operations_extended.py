"""Extended git operations for MCP Git Server.

New tools added to avoid bloating operations.py (2284 lines, tracked in #139/#140).
"""

import logging
import re

from ..utils.git_import import GitCommandError, Repo

logger = logging.getLogger(__name__)

DANGEROUS_CHARS = re.compile(r"[;&|`$()]")

__all__ = [
    "git_restore",
    "git_branch_update",
]


def _validate_ref(ref: str, param_name: str) -> str | None:
    """Validate a git ref for dangerous characters. Returns error string or None."""
    if DANGEROUS_CHARS.search(ref):
        return f"❌ Invalid characters detected in {param_name}: '{ref}'"
    return None


def git_restore(
    repo: Repo,
    files: list[str],
    staged: bool = False,
    source: str | None = None,
) -> str:
    """Restore working tree files or unstage files."""
    if not files:
        return "❌ No files specified to restore"

    if source:
        error = _validate_ref(source, "source")
        if error:
            return error

    try:
        args = []
        if staged:
            args.append("--staged")
        if source:
            args.extend(["--source", source])
        args.extend(files)

        repo.git.restore(*args)

        mode = "unstaged" if staged else "restored"
        file_list = ", ".join(files[:5])
        suffix = f" (+{len(files) - 5} more)" if len(files) > 5 else ""
        return f"✅ Restored {len(files)} file(s): {file_list}{suffix} ({mode})"

    except GitCommandError as e:
        return f"❌ Restore failed: {e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr}"
    except Exception as e:
        return f"❌ Error during restore: {str(e)}"


def git_branch_update(
    repo: Repo,
    branch_name: str,
    target: str | None = None,
    delete: bool = False,
    force: bool = False,
) -> str:
    """Force-update a branch ref or delete a branch."""
    error = _validate_ref(branch_name, "branch_name")
    if error:
        return error

    if target and delete:
        return "❌ Cannot specify both target and delete"
    if not target and not delete:
        return "❌ Must specify either target (force-update) or delete"

    if target:
        error = _validate_ref(target, "target")
        if error:
            return error

    try:
        if delete:
            flag = "-D" if force else "-d"
            repo.git.branch(flag, branch_name)
            return f"✅ Deleted branch '{branch_name}'"
        else:
            repo.git.branch("-f", branch_name, target)
            return f"✅ Updated branch '{branch_name}' → {target}"

    except GitCommandError as e:
        stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr
        return f"❌ Branch update failed: {stderr}"
    except Exception as e:
        return f"❌ Error updating branch: {str(e)}"
