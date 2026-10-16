"""Read-only probes and report text for git_filter_paths (issue #283)."""

from ..utils.git_import import Repo
from ._filter_guards import ALL_REFS_PATTERNS, ALL_REFS_REVS, LITERAL_ENV, capped

__all__ = [
    "commit_count",
    "dry_run_report",
    "ref_changes",
    "ref_snapshot",
]

_BULLET = "\n  "


def _under(path: str, prefixes: list[str]) -> bool:
    return any(path == p or path.startswith(f"{p}/") for p in prefixes)


def _log_entries(
    repo: Repo, revs: list[str], paths: list[str] | None
) -> list[tuple[str, list[str]]]:
    """(``<short sha> <subject>``, changed files) per commit, newest first."""
    args = ["--full-history", "--format=%x00%h %s", "--name-only", *revs]
    if paths:
        args += ["--", *paths]
    with repo.git.custom_environment(**LITERAL_ENV):
        out = repo.git.log(*args)
    entries = []
    for chunk in out.split("\0")[1:]:
        header, _, rest = chunk.partition("\n")
        entries.append((header, [f for f in rest.splitlines() if f]))
    return entries


def _affected(
    repo: Repo, revs: list[str], paths: list[str], invert: bool
) -> tuple[list[str], list[str]]:
    """Commits that change and the distinct files that would be removed."""
    commits: list[str] = []
    files: dict[str, None] = {}
    for header, changed in _log_entries(repo, revs, None if invert else paths):
        removed = [f for f in changed if not (invert and _under(f, paths))]
        if removed:
            commits.append(header)
            files.update(dict.fromkeys(removed))
    return commits, list(files)


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
) -> str:
    """What a real run would do; reads only."""
    commits, files = _affected(repo, revs, paths, invert)
    mode = "keep only" if invert else "remove"
    return "\n".join(
        [
            "🔍 Dry run: nothing was changed (no bundle, no rewrite)",
            f"Mode: {mode} {', '.join(paths)}",
            _section("Commits that would change", commits),
            _section("Paths that would be removed", files),
            _section("Refs that would be rewritten", sorted(ref_snapshot(repo, revs))),
            f"Commits would be signed: {'yes' if signs else 'no'}",
            *warnings,
        ]
    )
