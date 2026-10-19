"""git update-index operation for MCP Git Server (issues #236, #312)."""

from ..utils.git_import import GitCommandError, Repo
from ..utils.tool_failure import fail
from ._staging_ops import _format_file_list
from .error_text import clean_git_error_text

__all__ = ["git_update_index"]

_VALID_CHMOD = ("+x", "-x")


def _build_args(chmod: str | None, add: bool, remove: bool) -> list[str]:
    """Assemble explicit update-index flags (no GitPython kwarg rendering)."""
    args = []
    if add:
        args.append("--add")
    if remove:
        args.append("--remove")
    if chmod:
        args.append(f"--chmod={chmod}")
    return args


def _describe(chmod: str | None, add: bool, remove: bool) -> str:
    parts = []
    if add:
        parts.append("Added to index")
    if remove:
        parts.append("Removed from index if deleted")
    if chmod:
        parts.append(
            "Set executable bit (+x)"
            if chmod == "+x"
            else "Cleared executable bit (-x)"
        )
    return "; ".join(parts)


def _validate(
    files: list[str], chmod: str | None, add: bool, remove: bool
) -> str | None:
    if not files:
        return fail("❌ No files specified. Provide at least one file path.")
    if not (chmod or add or remove):
        return fail("❌ Nothing to do. Provide at least one of chmod, add, remove.")
    if chmod and chmod not in _VALID_CHMOD:
        return fail(f"❌ Invalid chmod '{chmod}'. Use '+x' or '-x'.")
    return None


def git_update_index(
    repo: Repo,
    files: list[str],
    chmod: str | None = None,
    add: bool = False,
    remove: bool = False,
) -> str:
    """Update the git INDEX directly via `git update-index`.

    --chmod records the mode in the index regardless of core.filemode.
    --add registers untracked files (even if ignored, no -f needed).
    --remove drops files deleted from the working tree.

    Args:
        repo: Git repository object
        files: File paths to update
        chmod: "+x" or "-x" (optional)
        add: pass --add
        remove: pass --remove

    Returns:
        Success or error message string
    """
    try:
        invalid = _validate(files, chmod, add, remove)
        if invalid:
            return invalid

        if not add:
            untracked = [f for f in files if not repo.git.ls_files("--", f).strip()]
            if untracked:
                return fail(
                    f"❌ Not tracked by git, stage first with git_add "
                    f"(or pass add=True): {_format_file_list(untracked)}"
                )

        repo.git.update_index(*_build_args(chmod, add, remove), "--", *files)
        action = _describe(chmod, add, remove)
        return f"✅ {action} on {len(files)} file(s): {_format_file_list(files)}"

    except GitCommandError as e:
        return fail(
            f"❌ git update-index failed: {clean_git_error_text(e.stderr, 'stderr')}"
        )
    except Exception as e:
        return fail(f"❌ git update-index failed: {str(e)}")
