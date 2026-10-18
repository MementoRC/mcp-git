"""Read-only probes and report text for git_filter_paths (issue #283)."""

from typing import NamedTuple

from ..utils.git_import import Repo
from ._filter_guards import (
    ALL_REFS_PATTERNS,
    ALL_REFS_REVS,
    LITERAL_ENV,
    capped,
    tree_matches,
)

__all__ = [
    "commit_count",
    "dry_run_report",
    "ref_changes",
    "ref_snapshot",
]

_BULLET = "\n  "


def _under(path: str, prefixes: list[str]) -> bool:
    return any(path == p or path.startswith(f"{p}/") for p in prefixes)


class _Commit(NamedTuple):
    sha: str
    parents: list[str]
    label: str  # "<short sha> <subject>"


class _Scan(NamedTuple):
    changing: list[str]  # labels, newest first
    files: list[str]
    rewritten: int
    emptied: int | None  # None when prune_empty is off


def _scope(repo: Repo, revs: list[str]) -> list[_Commit]:
    """Every commit reachable from *revs*, parents before children."""
    out = repo.git.log(
        "--full-history",
        "--topo-order",
        "--reverse",
        "--format=%H%x00%P%x00%h %s",
        *revs,
    )
    rows = (line.split("\0", 2) for line in out.splitlines() if line)
    return [_Commit(sha, parents.split(), label) for sha, parents, label in rows]


def _removed_files(repo: Repo, sha: str, paths: list[str], invert: bool) -> list[str]:
    """Files of the commit's tree the filter would drop."""
    if not invert:
        return tree_matches(repo, sha, paths)
    with repo.git.custom_environment(**LITERAL_ENV):
        out = repo.git.ls_tree("-r", "-z", "--name-only", sha)
    return [n for n in out.split("\0") if n and not _under(n, paths)]


def _becomes_empty(repo: Repo, commit: _Commit, paths: list[str], invert: bool) -> bool:
    """A non-merge commit whose only changes are to files the filter drops."""
    args = ["-r", "-z", "--name-only"]
    if not commit.parents:
        args.append("--root")
    out = repo.git.diff_tree(*args, *commit.parents, commit.sha)
    changed = [n for n in out.split("\0") if n]
    return all(_under(n, paths) != invert for n in changed)


def _scan(
    repo: Repo, revs: list[str], paths: list[str], invert: bool, prune_empty: bool
) -> _Scan:
    """Commits whose tree changes, files dropped, and every commit rewritten.

    A commit is rewritten (new sha) when its own tree changes or any parent is
    rewritten. Trees are compared, so merges that history simplification hides
    are counted.
    """
    changing: list[str] = []
    files: dict[str, None] = {}
    rewritten: set[str] = set()
    emptied = 0
    for commit in _scope(repo, revs):
        removed = _removed_files(repo, commit.sha, paths, invert)
        if removed:
            changing.append(commit.label)
            files.update(dict.fromkeys(removed))
        dropped = (
            prune_empty
            and len(commit.parents) <= 1
            and _becomes_empty(repo, commit, paths, invert)
        )
        emptied += dropped
        if removed or dropped or rewritten.intersection(commit.parents):
            rewritten.add(commit.sha)
    return _Scan(
        changing[::-1], list(files), len(rewritten), emptied if prune_empty else None
    )


def ref_snapshot(repo: Repo, revs: list[str]) -> dict[str, str]:
    """``{refname: sha}`` for exactly the refs filter-branch rewrites."""
    patterns = ALL_REFS_PATTERNS if revs == list(ALL_REFS_REVS) else revs
    out = repo.git.for_each_ref("--format=%(refname) %(objectname)", *patterns)
    pairs = (line.split(" ", 1) for line in out.splitlines() if line)
    return dict(pairs)


def commit_count(repo: Repo, revs: list[str]) -> int:
    """Commits reachable from the scope (0 when every ref is gone)."""
    if not ref_snapshot(repo, revs):
        return 0
    return int(repo.git.rev_list("--count", *revs))


def ref_changes(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """``ref: old -> new`` lines for refs whose target changed."""
    lines = []
    for ref, old in sorted(before.items()):
        new = after.get(ref)
        if new is None:
            lines.append(f"{ref}: {old[:8]} -> (deleted: every commit was pruned)")
        elif new != old:
            lines.append(f"{ref}: {old[:8]} -> {new[:8]}")
    return lines


def _section(title: str, lines: list[str]) -> str:
    body = _BULLET.join(capped(lines)) if lines else "(none)"
    return f"{title} ({len(lines)}):{_BULLET}{body}"


def dry_run_report(
    repo: Repo,
    revs: list[str],
    paths: list[str],
    invert: bool,
    signs: bool,
    warnings: list[str],
    prune_empty: bool = True,
) -> str:
    """What a real run would do; reads only."""
    scan = _scan(repo, revs, paths, invert, prune_empty)
    mode = "keep only" if invert else "remove"
    emptied = (
        []
        if scan.emptied is None
        else [f"Commits that would be dropped as empty: {scan.emptied}"]
    )
    return "\n".join(
        [
            "🔍 Dry run: nothing was changed (no bundle, no rewrite)",
            f"Mode: {mode} {', '.join(paths)}",
            _section("Commits that would change", scan.changing),
            f"Commits that will be rewritten (new sha): {scan.rewritten}",
            *emptied,
            _section("Paths that would be removed", scan.files),
            _section("Refs that would be rewritten", sorted(ref_snapshot(repo, revs))),
            f"Commits would be signed: {'yes' if signs else 'no'}",
            *warnings,
        ]
    )
