"""Three-way merge of a single file across three arbitrary revisions.

``git_merge_tree`` merges whole branches; this merges ONE file, which is the
natural unit when hand-resolving a transplant where most conflicting paths
are generated files you intend to regenerate rather than merge. Nothing in
the working tree or the index is touched.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from ..text_limits import MAX_CHARS_FOR_LLM, cap_characters
from ..utils.git_import import GitCommandError, Repo
from .operations_extended import _clean_git_error_text, _validate_ref

logger = logging.getLogger(__name__)

__all__ = ["git_merge_file"]

_DEFAULT_LABELS = ("ours", "base", "theirs")
_SEPARATOR = "-" * 60
# git merge-file reports the conflict count as its exit status, capped at 127.
_MAX_CONFLICT_STATUS = 127


def _read_blob(repo: Repo, revision: str, path: str) -> tuple[str, bool]:
    """Return ``(content, present)`` for ``<revision>:<path>``.

    A missing path is not an error: absent on one side is exactly how an
    added or deleted file presents itself to a three-way merge.
    """
    try:
        return repo.git.show(f"{revision}:{path}"), True
    except GitCommandError:
        return "", False


def _resolve_labels(labels: list[str] | None) -> tuple[list[str] | None, str | None]:
    """Validate the three conflict-marker labels. Returns ``(labels, error)``."""
    if labels is None:
        return list(_DEFAULT_LABELS), None
    if len(labels) != 3:
        return None, (
            f"❌ labels must be exactly three entries (ours, base, theirs), got {len(labels)}"
        )
    for index, label in enumerate(labels):
        error = _validate_ref(label, f"labels[{index}]")
        if error:
            return None, error
    return list(labels), None


def _run_merge_file(
    repo: Repo, labels: list[str], ours: Path, base: Path, theirs: Path
) -> tuple[str, int, str | None]:
    """Run ``git merge-file -p``. Returns ``(merged, conflicts, error)``."""
    try:
        merged = repo.git.merge_file(
            "-L",
            labels[0],
            "-L",
            labels[1],
            "-L",
            labels[2],
            "-p",
            str(ours),
            str(base),
            str(theirs),
        )
        return merged, 0, None
    except GitCommandError as exc:
        stdout = _clean_git_error_text(exc.stdout, "stdout")
        stderr = _clean_git_error_text(exc.stderr, "stderr")
        status = exc.status if isinstance(exc.status, int) else -1
        if 0 < status <= _MAX_CONFLICT_STATUS:
            return stdout, status, None
        return "", 0, f"❌ Merge-file failed: {stderr or stdout}"


def _write_output(output: list[str], output_path: str, merged: str) -> str:
    """Write the complete merge result to disk and return metadata only."""
    path = Path(output_path)
    if not path.is_absolute():
        return f"❌ output_path must be an absolute path, got: {output_path}"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(merged, encoding="utf-8")
    except OSError as exc:
        return f"❌ Failed to write merge result to {output_path}: {exc}"

    output.append(f"💾 Full merge result written to {output_path}")
    output.append(
        f"📊 Total: {len(merged.splitlines()):,} lines / {len(merged):,} bytes | "
        "Returned: written to disk | Truncated: no"
    )
    return "\n".join(output)


def git_merge_file(
    repo: Repo,
    path: str,
    base_rev: str,
    ours_rev: str,
    theirs_rev: str,
    labels: list[str] | None = None,
    output_path: str | None = None,
) -> str:
    """Three-way merge one file across three revisions, with conflict markers.

    The working tree and index are left untouched: each side is read out of
    the object database with ``git show`` and merged in a temporary directory.

    Args:
        repo: Repository to read the revisions from
        path: File path as it appears in each revision
        base_rev: Merge base revision
        ours_rev: Our side revision
        theirs_rev: Their side revision
        labels: Three conflict-marker labels (default: ours, base, theirs)
        output_path: Absolute path to write the complete merged result to,
            instead of returning it inline

    Returns:
        The merged content with conflict markers, plus the conflict count --
        or, with output_path, only the write metadata.
    """
    for ref, name in (
        (base_rev, "base_rev"),
        (ours_rev, "ours_rev"),
        (theirs_rev, "theirs_rev"),
    ):
        error = _validate_ref(ref, name)
        if error:
            return error
    error = _validate_ref(path, "path")
    if error:
        return error

    resolved_labels, label_error = _resolve_labels(labels)
    if resolved_labels is None:
        return label_error or "❌ Invalid labels"

    sides = {}
    for name, revision in (
        ("ours", ours_rev),
        ("base", base_rev),
        ("theirs", theirs_rev),
    ):
        sides[name] = _read_blob(repo, revision, path)

    if not any(present for _content, present in sides.values()):
        return (
            f"❌ {path} does not exist in any of {ours_rev}, {base_rev}, {theirs_rev}"
        )

    try:
        with tempfile.TemporaryDirectory(prefix="mcp-git-merge-") as workspace:
            root = Path(workspace)
            written = {}
            for name, (content, _present) in sides.items():
                side_path = root / name
                side_path.write_text(content, encoding="utf-8")
                written[name] = side_path

            merged, conflicts, merge_error = _run_merge_file(
                repo,
                resolved_labels,
                written["ours"],
                written["base"],
                written["theirs"],
            )
            if merge_error:
                return merge_error
    except OSError as exc:
        return f"❌ Error preparing merge inputs: {exc}"
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"Unexpected error during merge-file: {exc}", exc_info=True)
        return f"❌ Error during merge-file: {exc}"

    output = [
        f"🔀 Merged {path}",
        f"   ours:   {ours_rev}" + ("" if sides["ours"][1] else "  (absent)"),
        f"   base:   {base_rev}" + ("" if sides["base"][1] else "  (absent)"),
        f"   theirs: {theirs_rev}" + ("" if sides["theirs"][1] else "  (absent)"),
    ]
    output.append(
        "✅ Clean merge (0 conflicts)"
        if conflicts == 0
        else f"⚠️ {conflicts} conflict region(s) — markers included in the content below"
    )

    if output_path is not None:
        return _write_output(output, output_path, merged)

    text, truncated = cap_characters(merged, keep_head=True, limit=MAX_CHARS_FOR_LLM)
    output.append(
        f"📊 Total: {len(merged.splitlines()):,} lines / {len(merged):,} bytes | "
        f"Truncated: {'yes' if truncated else 'no'}"
    )
    if truncated:
        output.append(
            "⚠️ Truncated for LLM context (chars: exceeded 100KB limit) — "
            "pass output_path=<absolute path> for the complete result"
        )
    labels_line = " / ".join(resolved_labels)
    output.append(f"\n📄 Merged content ({labels_line}):")
    output.append(_SEPARATOR)
    output.append(text)
    output.append(_SEPARATOR)
    return "\n".join(output)
