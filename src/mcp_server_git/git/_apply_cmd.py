"""``git_apply``: apply a unified-diff patch to the working tree (issue #334)."""

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ..utils.git_import import GitCommandError, Repo
from ..utils.tool_failure import fail
from .error_text import clean_git_error_text

__all__ = ["git_apply"]


def _resolve_patch_path(repo: Repo, patch_path: str) -> tuple[str | None, str | None]:
    """Return ``(absolute_path, error)`` for an on-disk patch file."""
    if patch_path.startswith("-"):
        return None, fail(
            f"❌ patch_path must not start with '-': '{patch_path}' "
            "would be parsed as a git option"
        )
    path = Path(patch_path)
    if not path.is_absolute():
        path = Path(repo.working_tree_dir or ".") / path
    if not path.exists():
        return None, fail(f"❌ Patch file not found: {path}")
    if not path.is_file():
        return None, fail(f"❌ Patch path is not a file: {path}")
    return str(path), None


@contextmanager
def _inline_patch(patch_text: str) -> Iterator[str]:
    """Write ``patch_text`` to a temp file outside the repo; always remove it."""
    if not patch_text.endswith("\n"):
        patch_text += "\n"
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".patch", delete=False, encoding="utf-8"
    ) as handle:
        handle.write(patch_text)
    try:
        yield handle.name
    finally:
        os.unlink(handle.name)


def _numstat_lines(repo: Repo, patch: str, reverse: bool) -> list[str]:
    args = ["--numstat"] + (["--reverse"] if reverse else []) + [patch]
    lines = []
    for raw in repo.git.apply(*args).splitlines():
        parts = raw.split("\t", 2)
        if len(parts) == 3:
            lines.append(f"  +{parts[0]} -{parts[1]} {parts[2]}")
    return lines


def _flags(index: bool, three_way: bool, reverse: bool) -> list[str]:
    flags = []
    if index:
        flags.append("--index")
    if three_way:
        flags.append("--3way")
    if reverse:
        flags.append("--reverse")
    return flags


def _apply_patch(
    repo: Repo, patch: str, flags: list[str], check: bool, index: bool, reverse: bool
) -> str:
    try:
        repo.git.apply("--check", *flags, patch)
    except GitCommandError as e:
        return fail(
            f"❌ Patch does not apply: {clean_git_error_text(e.stderr, 'stderr')}"
        )
    lines = _numstat_lines(repo, patch, reverse)
    body = "\n".join(lines)
    if check:
        return (
            "✅ Patch applies cleanly (check only, nothing changed): "
            f"{len(lines)} file(s)\n{body}"
        )
    try:
        repo.git.apply(*flags, patch)
    except GitCommandError as e:
        return fail(f"❌ git apply failed: {clean_git_error_text(e.stderr, 'stderr')}")
    suffix = (" (index updated)" if index else "") + (" (reversed)" if reverse else "")
    return f"✅ Applied patch to {len(lines)} file(s){suffix}\n{body}"


def git_apply(
    repo: Repo,
    patch_path: str | None = None,
    patch_text: str | None = None,
    check: bool = False,
    index: bool = False,
    three_way: bool = False,
    reverse: bool = False,
) -> str:
    """Apply a unified-diff patch (file or inline text) to the working tree.

    Exactly one of ``patch_path`` / ``patch_text``. The patch is always
    verified with ``git apply --check`` first, so a failure changes nothing.
    ``check`` stops after verification; ``index`` also updates the index;
    ``three_way`` enables ``--3way``; ``reverse`` un-applies (issue #334).
    """
    if (patch_path is None) == (patch_text is None):
        return fail("❌ Provide exactly one of patch_path or patch_text")
    flags = _flags(index, three_way, reverse)
    try:
        if patch_text is not None:
            with _inline_patch(patch_text) as patch:
                return _apply_patch(repo, patch, flags, check, index, reverse)
        resolved, error = _resolve_patch_path(repo, patch_path or "")
        if error or resolved is None:
            return error or fail("❌ patch_path is required")
        return _apply_patch(repo, resolved, flags, check, index, reverse)
    except GitCommandError as e:
        return fail(f"❌ git apply failed: {clean_git_error_text(e.stderr, 'stderr')}")
    except Exception as e:
        return fail(f"❌ Apply error: {str(e)}")
