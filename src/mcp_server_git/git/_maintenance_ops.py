"""git_reflog_expire and git_gc: finish a history scrub (issue #283).

After ``git_filter_paths`` the removed content is still reachable through
reflogs and loose objects. ``git_reflog_expire`` empties the reflogs and
``git_gc`` prunes what is then unreachable. Both default to ``dry_run=True``;
a destructive run needs an explicit ``dry_run=False``. Age values reach git as
single ``--opt=value`` argv items (never a shell) and are validated first.
The stash is never expired unless ``include_stash=True``: its reflog is the
stash stack, shared across worktrees and sessions, so ``--all`` is not used.
"""

import re

from ..utils.git_import import GitCommandError, Repo
from ..utils.tool_failure import ToolFailure, fail
from .error_text import clean_git_error_text

__all__ = ["git_gc", "git_reflog_expire"]

_STASH = "refs/stash"
_TOP_REFS = 10
_COUNT_FIELDS = ("count", "size", "in-pack", "size-pack", "prune-packable", "garbage")
_AGE = re.compile(
    r"now|never|all"
    r"|\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?"
    r"|\d+\.(?:second|minute|hour|day|week|month|year)s?\.ago",
    re.ASCII,
)


def _age_failure(label: str, value: str) -> ToolFailure | None:
    """Reject anything but the allowed forms; reads nothing, runs nothing."""
    if _AGE.fullmatch(value):
        return None
    return fail(
        f"❌ Invalid {label} value {value!r}: use 'now', 'never', 'all', an ISO "
        "date (YYYY-MM-DD, optionally with ' HH:MM[:SS]') or '<n>.<unit>.ago' "
        "(unit second|minute|hour|day|week|month|year)"
    )


def _has_reflog(repo: Repo, ref: str) -> bool:
    status, _, _ = repo.git.reflog(
        "exists", ref, with_extended_output=True, with_exceptions=False
    )
    return status == 0


def _reflog_refs(repo: Repo) -> list[str]:
    """HEAD plus every ref that has a reflog (stash included)."""
    names = ["HEAD", *repo.git.for_each_ref("--format=%(refname)").split()]
    return [name for name in names if _has_reflog(repo, name)]


def _entry_count(repo: Repo, ref: str) -> int:
    out = repo.git.reflog("show", "--format=%H", ref, "--")
    return len([line for line in out.splitlines() if line.strip()])


def _would_prune(repo: Repo, opts: list[str], ref: str) -> int:
    """Entries ``reflog expire`` would remove from *ref*; changes nothing."""
    _, out, err = repo.git.reflog(
        "expire",
        "--dry-run",
        "--verbose",
        *opts,
        "--",
        ref,
        with_extended_output=True,
    )
    lines = f"{out}\n{err}".splitlines()
    # git 2.39 prints "prune <msg>" even with --dry-run; newer: "would prune".
    return sum(1 for line in lines if line.startswith(("prune ", "would prune ")))


def _expire_opts(expire: str, expire_unreachable: str | None) -> list[str]:
    opts = [f"--expire={expire}"]
    if expire_unreachable is not None:
        opts.append(f"--expire-unreachable={expire_unreachable}")
    return opts


def _expire_rows(
    repo: Repo, opts: list[str], targets: list[str], dry_run: bool
) -> list[tuple[str, int, int]]:
    """(ref, entries before, entries after); a dry run only predicts 'after'."""
    counts = [(ref, _entry_count(repo, ref)) for ref in targets]
    if dry_run:
        return [(ref, n, n - _would_prune(repo, opts, ref)) for ref, n in counts]
    repo.git.reflog("expire", *opts, "--", *targets)
    return [(ref, n, _entry_count(repo, ref)) for ref, n in counts]


def _stash_line(stash_entries: int | None, include_stash: bool) -> str:
    if stash_entries is None:
        return "Stash: none"
    if include_stash:
        return f"Stash: expired too (it held {stash_entries} entries)"
    return (
        f"Stash: skipped ({stash_entries} entries kept; include_stash=True "
        "expires them, which destroys every session's stashes)"
    )


def _expire_report(
    rows: list[tuple[str, int, int]],
    dry_run: bool,
    stash_line: str,
    argv: str,
) -> str:
    before = sum(row[1] for row in rows)
    after = sum(row[2] for row in rows)
    removed = before - after
    head = (
        f"✅ Reflog expire DRY RUN: would remove {removed} of {before} entries "
        f"across {len(rows)} ref(s); nothing was changed"
        if dry_run
        else f"✅ Reflog expire: removed {removed} of {before} entries across "
        f"{len(rows)} ref(s) ({before} -> {after})"
    )
    top = sorted((r for r in rows if r[1] > r[2]), key=lambda r: r[2] - r[1])
    lines = [head, f"Command: {argv}"]
    lines += [f"  {ref}: {b} -> {a}" for ref, b, a in top[:_TOP_REFS]]
    if len(top) > _TOP_REFS:
        lines.append(f"  ... and {len(top) - _TOP_REFS} more ref(s)")
    lines.append(stash_line)
    lines.append(
        "Next: git_gc(prune='now', dry_run=False) prunes the now-unreachable "
        "objects, once no other session uses the repo"
        if not dry_run
        else "Re-run with dry_run=False to remove them"
    )
    return "\n".join(lines)


def git_reflog_expire(
    repo: Repo,
    expire: str = "now",
    expire_unreachable: str | None = None,
    include_stash: bool = False,
    dry_run: bool = True,
) -> str:
    """Expire reflog entries of HEAD and every ref that has a reflog.

    The ref list is explicit (never ``--all``); refs/stash is left out unless
    ``include_stash``. ``dry_run`` (default) counts what would go and mutates
    nothing; ``dry_run=False`` runs ``git reflog expire`` for real.
    """
    try:
        failure = _age_failure("expire", expire)
        if failure is None and expire_unreachable is not None:
            failure = _age_failure("expire_unreachable", expire_unreachable)
        if failure is not None:
            return failure
        refs = _reflog_refs(repo)
        stash = _entry_count(repo, _STASH) if _STASH in refs else None
        targets = [r for r in refs if include_stash or r != _STASH]
        if not targets:
            return "✅ No reflogs to expire"
        opts = _expire_opts(expire, expire_unreachable)
        rows = _expire_rows(repo, opts, targets, dry_run)
        mode = ["--dry-run", "--verbose"] if dry_run else []
        argv = " ".join(["git reflog expire", *mode, *opts, "--", *targets])
        stash_line = _stash_line(stash, include_stash)
        report = _expire_report(rows, dry_run, stash_line, argv)
        note = _worktree_note(repo)
        return f"{report}\n{note}" if note else report
    except GitCommandError as e:
        detail = clean_git_error_text(e.stderr, "stderr")
        return fail(f"❌ Reflog expire failed: {detail}")
    except Exception as e:
        return fail(f"❌ Reflog expire error: {e}")


def _count_objects(repo: Repo) -> dict[str, str]:
    out = repo.git.count_objects("-v")
    pairs = (line.split(": ", 1) for line in out.splitlines() if ": " in line)
    return {key: value.strip() for key, value in pairs}


def _count_line(label: str, counts: dict[str, str]) -> str:
    fields = ", ".join(f"{key}={counts.get(key, '?')}" for key in _COUNT_FIELDS)
    return f"{label}: {fields} (sizes in KiB)"


def _prune_candidates(repo: Repo, prune: str) -> int:
    out = repo.git.prune("--dry-run", f"--expire={prune}")
    return len([line for line in out.splitlines() if line.strip()])


def _reflog_note(repo: Repo) -> str | None:
    refs = [ref for ref in _reflog_refs(repo) if ref != _STASH]
    total = sum(_entry_count(repo, ref) for ref in refs)
    if not total:
        return None
    return (
        f"Note: {total} reflog entries still keep unreachable-looking objects "
        "alive; run git_reflog_expire first for a scrub"
    )


def _worktree_note(repo: Repo) -> str | None:
    """Warn when linked worktrees exist: their HEAD reflogs are not touched."""
    out = repo.git.worktree("list", "--porcelain")
    if sum(1 for line in out.splitlines() if line.startswith("worktree ")) < 2:
        return None
    return (
        "Note: other linked worktrees exist; their HEAD reflogs were not "
        "touched and may keep objects reachable"
    )


def _run_gc(repo: Repo, opts: list[str]) -> None:
    """``git gc`` with reflog expiry disabled for this call only.

    Plain gc runs ``reflog expire --all`` (including refs/stash); reflog
    expiry belongs to git_reflog_expire alone.
    """
    repo.git.execute(
        [
            "git",
            "-c",
            "gc.reflogExpire=never",
            "-c",
            "gc.reflogExpireUnreachable=never",
            "gc",
            *opts,
        ]
    )


def git_gc(
    repo: Repo,
    prune: str = "2.weeks.ago",
    aggressive: bool = False,
    dry_run: bool = True,
) -> str:
    """Report (default) or run ``git gc --prune=<prune>``; never expires reflogs.

    ``dry_run`` reports ``git count-objects -v`` and how many loose objects
    ``git prune --dry-run`` would remove; it changes nothing. ``dry_run=False``
    runs ``git gc`` and reports the counts before and after. To finish a
    scrub pass ``prune="now"``, and only when no other process or session is
    using the repository (git documents it as unsafe with concurrent writers;
    all worktrees share one object store).
    """
    try:
        failure = _age_failure("prune", prune)
        if failure is not None:
            return failure
        before = _count_objects(repo)
        notes = [n for n in (_reflog_note(repo), _worktree_note(repo)) if n]
        if dry_run:
            lines = [
                f"✅ GC DRY RUN: would prune {_prune_candidates(repo, prune)} "
                "loose object(s); nothing was changed",
                f"Command: git prune --dry-run --expire={prune}",
                _count_line("Objects", before),
            ]
        else:
            opts = [f"--prune={prune}", *(["--aggressive"] if aggressive else [])]
            _run_gc(repo, opts)
            lines = [
                f"✅ git gc {' '.join(opts)} completed",
                _count_line("Before", before),
                _count_line("After", _count_objects(repo)),
            ]
        return "\n".join([*lines, *notes])
    except GitCommandError as e:
        detail = clean_git_error_text(e.stderr, "stderr")
        return fail(f"❌ GC failed: {detail}")
    except Exception as e:
        return fail(f"❌ GC error: {e}")
