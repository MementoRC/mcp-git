"""Pre-flight guards for git_filter_paths (issue #283).

Each guard only reads the repository and returns a failure (``ToolFailure``)
or ``None``. They run before any backup or rewrite, so a refusal changes
nothing.
"""

import posixpath
from pathlib import Path

from ..utils.git_import import Repo
from ..utils.tool_failure import fail
from ._ref_validation import validate_ref

__all__ = [
    "ALL_REFS_PATTERNS",
    "ALL_REFS_REVS",
    "LITERAL_ENV",
    "capped",
    "configured_remotes",
    "dirty_tree_failure",
    "in_progress_failure",
    "leftover_backup_failure",
    "no_match_failure",
    "normalize_paths",
    "remote_failure",
    "resolve_revs",
    "scope_param_failure",
]

# Paths are file names, never pathspec magic or globs.
LITERAL_ENV = {"GIT_LITERAL_PATHSPECS": "1"}

# all_refs scope: local branches and tags only. Never --all, which would also
# rewrite refs/remotes/* (misrepresenting the remote) and refs/stash.
ALL_REFS_REVS = ("--branches", "--tags")
ALL_REFS_PATTERNS = ("refs/heads/", "refs/tags/")

_LIST_CAP = 50

_IN_PROGRESS_MARKERS = {
    "rebase-merge": "rebase",
    "rebase-apply": "rebase",
    "MERGE_HEAD": "merge",
    "CHERRY_PICK_HEAD": "cherry-pick",
    "REVERT_HEAD": "revert",
}


def capped(lines: list[str], cap: int = _LIST_CAP) -> list[str]:
    """*lines* limited to *cap* entries plus an "...and N more" line."""
    if len(lines) <= cap:
        return lines
    return [*lines[:cap], f"...and {len(lines) - cap} more"]


def _path_problem(path: str) -> str | None:
    if not path:
        return "empty paths are not allowed"
    if path.startswith("-"):
        return "must not start with '-'"
    if path.startswith("/"):
        return "absolute paths are not allowed"
    if ".." in path.split("/"):
        return "'..' components are not allowed"
    if posixpath.normpath(path) == ".":
        return "names the whole repository"
    return None


def normalize_paths(paths: list[str]) -> list[str] | str:
    """Validated, normalized (no trailing '/'), de-duplicated paths, or a failure."""
    if not paths:
        return fail("❌ paths must name at least one repo-relative path")
    normalized: list[str] = []
    for path in paths:
        problem = _path_problem(path)
        if problem:
            return fail(f"❌ Invalid path {path!r}: {problem}")
        clean = posixpath.normpath(path)
        if clean not in normalized:
            normalized.append(clean)
    return normalized


def scope_param_failure(all_refs: bool, branch: str | None) -> str | None:
    """Reject an option-like or unsafe branch, or branch combined with all_refs."""
    if branch is None:
        return None
    if all_refs:
        return fail("❌ branch cannot be combined with all_refs=True")
    if branch.startswith("-"):
        return fail(f"❌ branch must not start with '-': '{branch}'")
    return validate_ref(branch, "branch")


def dirty_tree_failure(repo: Repo) -> str | None:
    """Staged, unstaged or untracked changes (ignored files are fine)."""
    out = repo.git.status("--porcelain=v1", "--untracked-files=all")
    lines = [line for line in out.splitlines() if line.strip()]
    if not lines:
        return None
    listing = "\n".join(f"  {line}" for line in capped(lines))
    return fail(
        "❌ Working tree is not clean (ignored files are fine). Commit, stash "
        f"or remove these first:\n{listing}"
    )


def configured_remotes(repo: Repo) -> list[str]:
    return repo.git.remote().split()


def remote_failure(remotes: list[str], allow_with_remote: bool) -> str | None:
    if not remotes or allow_with_remote:
        return None
    return fail(
        f"❌ Remotes are configured ({', '.join(remotes)}). Rewriting history "
        "makes it diverge from them; pass allow_with_remote=True to proceed "
        "(this tool never pushes)"
    )


def in_progress_failure(repo: Repo) -> str | None:
    git_dir = Path(repo.git_dir)
    found = sorted(
        {
            op
            for marker, op in _IN_PROGRESS_MARKERS.items()
            if (git_dir / marker).exists()
        }
    )
    if not found:
        return None
    return fail(
        f"❌ A {'/'.join(found)} is in progress; finish it or run git_abort first"
    )


def leftover_backup_failure(repo: Repo) -> str | None:
    """refs/original/ left by an earlier filter-branch would block the run."""
    refs = repo.git.for_each_ref("--format=%(refname)", "refs/original/").split()
    if not refs:
        return None
    listing = "\n".join(f"  {ref}" for ref in capped(refs))
    return fail(
        "❌ refs/original/ already holds a backup from an earlier filter-branch:\n"
        f"{listing}\nCheck it is no longer needed, then delete each ref with "
        "`git update-ref -d <ref>` and retry"
    )


def resolve_revs(repo: Repo, all_refs: bool, branch: str | None) -> list[str] | str:
    """Revision arguments for the chosen scope, or a failure."""
    if all_refs:
        return list(ALL_REFS_REVS)
    if branch is None:
        if repo.head.is_detached:
            return fail("❌ HEAD is detached; pass branch or all_refs=True")
        branch = repo.active_branch.name
    ref = f"refs/heads/{branch}"
    if not repo.git.for_each_ref("--format=%(refname)", ref).strip():
        return fail(f"❌ Branch '{branch}' not found (or has no commits)")
    return [ref]


def no_match_failure(repo: Repo, revs: list[str], paths: list[str]) -> str | None:
    """Refuse when no commit in scope contains any listed path."""
    with repo.git.custom_environment(**LITERAL_ENV):
        hit = repo.git.rev_list("-1", "--full-history", *revs, "--", *paths)
    if hit.strip():
        return None
    return fail(
        f"❌ None of the paths ({', '.join(paths)}) appear in any commit of "
        f"{' '.join(revs)}; nothing to filter"
    )
