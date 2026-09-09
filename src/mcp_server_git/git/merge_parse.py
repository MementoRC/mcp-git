"""Parsing of ``git merge-tree --write-tree`` output.

``git merge-tree`` performs a complete three-way merge and writes the result
into the object database, printing the resulting tree's OID before anything
else. Reporting only the ``CONFLICT`` prose throws that merge away: with the
OID in hand a caller can read any merged file -- conflict markers included --
via ``git_show(revision="<oid>:<path>")``, with no checkout and no
working-tree mutation.

Pure: parses already-captured stdout, never runs git.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# git abbreviates OIDs, so accept any plausible hex object name.
_OID = re.compile(r"^[0-9a-f]{7,64}$")
# "Conflicted file info" entries, in `git ls-files -u` form.
_STAGE_ENTRY = re.compile(
    r"^(?P<mode>[0-7]{6}) (?P<oid>[0-9a-f]{7,64}) (?P<stage>[1-3])\t(?P<path>.+)$"
)
_CONFLICT_LINE = re.compile(r"^CONFLICT \((?P<kind>[^)]*)\):\s*(?P<message>.*)$")

_MERGE_CONFLICT_IN = "Merge conflict in "


@dataclass(frozen=True)
class MergeTreeResult:
    """What ``git merge-tree --write-tree`` actually reported."""

    tree_oid: str | None = None
    conflict_paths: list[str] = field(default_factory=list)
    conflict_kinds: dict[str, str] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)
    other_lines: list[str] = field(default_factory=list)


def _path_from_message(message: str) -> str | None:
    """Recover the conflicting path from a CONFLICT message.

    Prose parsing is brittle by nature, which is why the conflicted-file-info
    section is preferred when git emits one; this is the fallback.
    """
    if _MERGE_CONFLICT_IN in message:
        return message.split(_MERGE_CONFLICT_IN, 1)[1].strip() or None
    first_token = message.split(" ", 1)[0].strip()
    return first_token or None


def parse_merge_tree_output(stdout: str) -> MergeTreeResult:
    """Split merge-tree stdout into its OID, conflicted paths, and messages.

    Degrades gracefully: output with no OID, no stage entries, or no CONFLICT
    lines still parses, with whatever was present preserved in ``other_lines``
    so nothing git said is silently dropped.
    """
    lines = stdout.splitlines()

    tree_oid: str | None = None
    if lines and _OID.match(lines[0].strip()):
        tree_oid = lines[0].strip()
        lines = lines[1:]

    staged_paths: list[str] = []
    message_paths: list[str] = []
    kinds: dict[str, str] = {}
    messages: list[str] = []
    other: list[str] = []

    for line in lines:
        stage_entry = _STAGE_ENTRY.match(line)
        if stage_entry:
            path = stage_entry.group("path")
            if path not in staged_paths:
                staged_paths.append(path)
            continue

        conflict = _CONFLICT_LINE.match(line.strip())
        if conflict:
            messages.append(line.strip())
            path = _path_from_message(conflict.group("message"))
            if path:
                if path not in message_paths:
                    message_paths.append(path)
                kinds.setdefault(path, conflict.group("kind"))
            continue

        if line.strip():
            other.append(line)

    paths = staged_paths or message_paths
    return MergeTreeResult(
        tree_oid=tree_oid,
        conflict_paths=paths,
        conflict_kinds={path: kinds[path] for path in paths if path in kinds},
        messages=messages,
        other_lines=other,
    )


def render_tree_hint(tree_oid: str) -> list[str]:
    """Render the lines that make the merged tree reachable."""
    return [
        f"🌳 Merged tree: {tree_oid}",
        "   Read any merged file, conflict markers included, with:",
        f'   git_show(revision="{tree_oid}:<path>")',
    ]


def render_conflict_paths(result: MergeTreeResult) -> list[str]:
    """Render the structured path list.

    Indented without a ``- `` bullet on purpose: the human-readable CONFLICT
    bullets above are what callers already parse, and adding bullets here
    would change that count.
    """
    if not result.conflict_paths:
        return []
    lines = [f"📄 Conflicted paths ({len(result.conflict_paths)}):"]
    for path in result.conflict_paths:
        kind = result.conflict_kinds.get(path)
        lines.append(f"    {path} [{kind}]" if kind else f"    {path}")
    return lines
