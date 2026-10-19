"""git_filter_paths: remove (or keep only) paths across history (issue #283).

Engine: ``git filter-branch --index-filter`` (no git-filter-repo). The run is
guarded (clean tree, no remotes unless allowed, no operation in progress, no
leftover refs/original/), backed up first to a verified bundle, signed while
the server enforces signing, and never pushes or fetches. filter-branch keeps
author and committer names and dates. refs/original/ is deleted afterwards:
the bundle is the backup.
"""

import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..utils.git_import import GitCommandError, Repo
from ..utils.tool_failure import ToolFailure, fail
from ._bundle_ops import git_bundle_create, git_bundle_verify
from ._commit_ops import signing_enforced
from ._filter_guards import (
    LITERAL_ENV,
    configured_remotes,
    dirty_tree_failure,
    in_progress_failure,
    leftover_backup_failure,
    no_match_failure,
    normalize_paths,
    remote_failure,
    resolve_revs,
    scope_param_failure,
)
from ._filter_report import commit_count, dry_run_report, ref_changes, ref_snapshot
from ._filter_scripts import filter_branch_args
from ._gpg import resolve_gpg_key
from .error_text import clean_git_error_text

__all__ = ["git_filter_paths"]

_RUN_ENV = {
    "FILTER_BRANCH_SQUELCH_WARNING": "1",
    "GIT_EDITOR": "true",
    **LITERAL_ENV,
}
_STDERR_TAIL = 15


@dataclass(frozen=True)
class _Plan:
    paths: list[str]
    revs: list[str]
    remotes: list[str]
    invert: bool


def _plan(
    repo: Repo,
    paths: list[str],
    invert: bool,
    all_refs: bool,
    branch: str | None,
    allow_with_remote: bool,
) -> _Plan | str:
    """Validate parameters and run every guard, in order; reads only."""
    normalized = normalize_paths(paths)
    if isinstance(normalized, str):
        return normalized
    remotes = configured_remotes(repo)
    failure = (
        scope_param_failure(all_refs, branch)
        or dirty_tree_failure(repo)
        or remote_failure(remotes, allow_with_remote)
        or in_progress_failure(repo)
        or leftover_backup_failure(repo)
    )
    if failure:
        return failure
    revs = resolve_revs(repo, all_refs, branch)
    if isinstance(revs, str):
        return revs
    return no_match_failure(repo, revs, normalized) or _Plan(
        normalized, revs, remotes, invert
    )


def _sign_key(repo: Repo, gpg_sign: bool) -> str | None | ToolFailure:
    """Key to sign with (None: unsigned), or a failure if none resolves."""
    if not (gpg_sign or signing_enforced()):
        return None
    key, error = resolve_gpg_key(repo, None)
    return error or key


def _default_backup(repo: Repo) -> Path:
    root = Path(repo.working_tree_dir or repo.git_dir)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return root.parent / f"{root.name}-pre-filter-{stamp}.bundle"


def _make_backup(repo: Repo, backup: Path) -> str | None:
    """Create and verify the all-refs bundle; a failure means nothing changed."""
    if not backup.is_absolute():
        return fail(f"❌ backup_path must be absolute: {backup}")
    if backup.exists():
        return fail(
            f"❌ Backup file already exists: {backup}; choose another backup_path. "
            "Nothing was changed"
        )
    for step in (git_bundle_create, git_bundle_verify):
        result = step(repo, str(backup))
        if isinstance(result, ToolFailure):
            return fail(f"{result}\n❌ Backup failed; nothing was rewritten")
    return None


def _stderr_tail(stderr: str) -> str:
    lines = [
        line
        for line in stderr.replace("\r", "\n").splitlines()
        if line.strip() and not line.startswith("Rewrite ")
    ]
    return "\n".join(lines[-_STDERR_TAIL:])


def _run_filter_branch(
    repo: Repo, plan: _Plan, prune_empty: bool, sign_key: str | None, backup: Path
) -> str | None:
    with tempfile.TemporaryDirectory(prefix="mcp-git-filter-") as tmp:
        # filter-branch's scratch dir lives outside the repo and must not exist yet.
        argv = filter_branch_args(
            plan.paths,
            plan.invert,
            prune_empty,
            sign_key,
            plan.revs,
            str(Path(tmp) / "work"),
        )
        try:
            with repo.git.custom_environment(**_RUN_ENV):
                repo.git.filter_branch(*argv)
        except GitCommandError as e:
            detail = _stderr_tail(clean_git_error_text(e.stderr, "stderr"))
            return fail(
                f"❌ git filter-branch failed:\n{detail}\nThe repository may be "
                f"partly rewritten. Restore it from the verified bundle {backup} "
                "(nothing was restored automatically)"
            )
    return None


def _drop_original_refs(repo: Repo) -> int:
    refs = repo.git.for_each_ref("--format=%(refname)", "refs/original/").split()
    for ref in refs:
        repo.git.update_ref("-d", ref)
    return len(refs)


def _restore_removed_files(repo: Repo, old_head: str | None, paths: list[str]) -> int:
    """Put back working copies that filter-branch's checkout deleted.

    Only the history is rewritten: files at the removed paths stay on disk as
    untracked files (the #283 concern was silently losing .mcp.json & co).
    """
    root = repo.working_tree_dir
    if not old_head or root is None:
        return 0
    with repo.git.custom_environment(**LITERAL_ENV):
        listed = repo.git.ls_tree("-r", "-z", "--name-only", old_head, "--", *paths)
        missing = [
            name
            for name in listed.split("\0")
            if name and not os.path.lexists(Path(root) / name)
        ]
        if missing:
            repo.git.restore(f"--source={old_head}", "--worktree", "--", *missing)
    return len(missing)


def _head_sha(repo: Repo) -> str | None:
    sha = repo.git.rev_parse("--verify", "--quiet", "HEAD", with_exceptions=False)
    return sha or None


def _summary(
    plan: _Plan,
    changes: list[str],
    counts: tuple[int, int],
    sign_key: str | None,
    backup: Path,
    cleanup: tuple[int, int],
) -> str:
    action = "Kept only" if plan.invert else "Removed"
    dropped, restored = cleanup
    lines = [
        f"✅ {action} {', '.join(plan.paths)} in the history of {' '.join(plan.revs)}",
        "Refs rewritten (old -> new):",
        *(f"  {line}" for line in changes or ["(none changed)"]),
        f"Commits: {counts[0]} -> {counts[1]}",
        f"Signed: yes (key {sign_key})" if sign_key else "Signed: no",
        f"Backup: {backup} (verified bundle of all refs; restore from it if needed)",
        f"refs/original/: {dropped} filter-branch backup ref(s) deleted; "
        "the bundle is the backup",
    ]
    if restored:
        lines.append(
            f"Working tree: {restored} removed file(s) were left on disk as "
            "untracked files; add them to .gitignore so they are not committed again"
        )
    if "--tags" in plan.revs:
        lines.append(
            "Note: rewritten annotated tags lose their GPG signatures "
            "(--tag-name-filter cat)"
        )
    if plan.remotes:
        lines.append(
            f"⚠️ Remotes ({', '.join(plan.remotes)}) still have the old history; "
            "the local history is now divergent from them. This tool never pushes"
        )
    lines.append(
        "Reminder: old objects stay reachable via the reflog and loose objects "
        "until git_reflog_expire(dry_run=False) then git_gc(prune='now', "
        "dry_run=False) have run, once no other session uses the repo. "
        "Nothing was pushed or fetched"
    )
    return "\n".join(lines)


def _dry_run(repo: Repo, plan: _Plan, sign_key: str | None, prune_empty: bool) -> str:
    """Report only; a missing signing key is a warning here, not a refusal."""
    warnings = []
    if isinstance(sign_key, ToolFailure):
        warnings.append(
            "⚠️ WARNING: a real run would refuse: signing is required but no GPG "
            "signing key resolves (set GPG_SIGNING_KEY or user.signingkey)"
        )
    return dry_run_report(
        repo,
        plan.revs,
        plan.paths,
        plan.invert,
        sign_key is not None,
        warnings,
        prune_empty,
    )


def _execute(
    repo: Repo, plan: _Plan, prune_empty: bool, sign_key: str | None, backup: Path
) -> str:
    """Backup, rewrite, clean up refs/original/ and report."""
    failed = _make_backup(repo, backup)
    if failed:
        return failed
    before = ref_snapshot(repo, plan.revs)
    count_before = commit_count(repo, plan.revs)
    old_head = _head_sha(repo)
    failed = _run_filter_branch(repo, plan, prune_empty, sign_key, backup)
    if failed:
        return failed
    dropped = _drop_original_refs(repo)
    restored = 0 if plan.invert else _restore_removed_files(repo, old_head, plan.paths)
    return _summary(
        plan,
        ref_changes(before, ref_snapshot(repo, plan.revs)),
        (count_before, commit_count(repo, plan.revs)),
        sign_key,
        backup,
        (dropped, restored),
    )


def git_filter_paths(
    repo: Repo,
    paths: list[str],
    invert: bool = False,
    all_refs: bool = False,
    branch: str | None = None,
    prune_empty: bool = True,
    dry_run: bool = False,
    allow_with_remote: bool = False,
    gpg_sign: bool = False,
    backup_path: str | None = None,
) -> str:
    """Remove *paths* from history (or keep only them with ``invert=True``).

    Refuses, changing nothing, on invalid paths, a dirty working tree,
    configured remotes (unless ``allow_with_remote``), an operation in
    progress or a leftover refs/original/. ``dry_run`` only reports. A real
    run writes and verifies a bundle of all refs first, rewrites with
    ``git filter-branch`` (signed while signing is enforced), then deletes
    refs/original/. Never pushes or fetches.
    """
    try:
        plan = _plan(repo, paths, invert, all_refs, branch, allow_with_remote)
        if isinstance(plan, str):
            return plan
        sign_key = _sign_key(repo, gpg_sign)
        if dry_run:
            return _dry_run(repo, plan, sign_key, prune_empty)
        if isinstance(sign_key, ToolFailure):
            return sign_key
        backup = Path(backup_path) if backup_path else _default_backup(repo)
        return _execute(repo, plan, prune_empty, sign_key, backup)
    except GitCommandError as e:
        return fail(
            f"❌ Filter paths failed: {clean_git_error_text(e.stderr, 'stderr')}"
        )
    except Exception as e:
        return fail(f"❌ Filter paths error: {e}")
