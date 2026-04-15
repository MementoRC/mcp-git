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
