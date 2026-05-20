"""Branch operations for MCP Git Server."""

import fnmatch
import logging
from typing import Any, Literal

from ..utils.git_import import GitCommandError, Repo

logger = logging.getLogger(__name__)

__all__ = [
    "git_create_branch",
    "git_checkout",
    "git_branch_list",
    "git_merge_base",
]


def git_create_branch(
    repo: Repo,
    branch_name: str,
    base_branch: str | None = None,
    start_point: str | None = None,
    checkout: bool = True,
) -> str:
    """Create a new branch and (by default) switch HEAD to it.

    Matches ``git checkout -b`` semantics: the new branch is created and
    becomes the active branch unless ``checkout=False`` is passed explicitly.
    See issue #162 — silent failure to switch HEAD caused commits to land
    on the previous branch in multi-agent workflows.
    """
    try:
        # Use start_point if provided, otherwise fall back to base_branch
        effective_base = start_point if start_point is not None else base_branch

        # Check if branch already exists
        existing_branches = [branch.name for branch in repo.branches]
        if branch_name in existing_branches:
            return f"❌ Branch '{branch_name}' already exists"

        # Create new branch
        if effective_base:
            # Build list of all valid branch references
            all_branches = list(existing_branches)

            # Add remote branches if remotes exist
            try:
                if repo.remotes:
                    for remote in repo.remotes:
                        # Include both full remote ref names (e.g., 'origin/main')
                        # and short names (e.g., 'main') for compatibility
                        all_branches.extend([ref.name for ref in remote.refs])
                        all_branches.extend(
                            [ref.name.split("/")[-1] for ref in remote.refs]
                        )
            except Exception:
                # Ignore remote access errors (e.g., no remotes configured)
                pass

            # Verify base branch exists
            if effective_base not in all_branches:
                return f"❌ Base branch '{effective_base}' not found"

            new_head = repo.create_head(branch_name, effective_base)
        else:
            new_head = repo.create_head(branch_name)

        if checkout:
            new_head.checkout()
            return f"✅ Created and switched to branch '{branch_name}'"
        return f"✅ Created branch '{branch_name}' (HEAD unchanged)"

    except GitCommandError as e:
        return f"❌ Branch creation failed: {str(e)}"
    except Exception as e:
        return f"❌ Branch creation error: {str(e)}"


def git_checkout(repo: Repo, branch_name: str) -> str:
    """Switch to a branch"""
    try:
        # Check if branch exists locally
        local_branches = [branch.name for branch in repo.branches]

        if branch_name in local_branches:
            # Switch to local branch
            repo.git.checkout(branch_name)
            return f"✅ Switched to branch '{branch_name}'"
        else:
            # Check if it's a full remote ref (e.g., 'origin/development')
            try:
                remote_refs = [ref.name for ref in repo.remote().refs]
                if branch_name in remote_refs:
                    # Checkout the remote ref directly (detached HEAD)
                    repo.git.checkout(branch_name)
                    return f"✅ Switched to '{branch_name}' (detached HEAD)"
            except Exception:
                pass

            # Check if branch exists on remote (short name)
            try:
                remote_branches = [
                    ref.name.split("/")[-1] for ref in repo.remote().refs
                ]
                if branch_name in remote_branches:
                    # Create local tracking branch
                    repo.git.checkout("-b", branch_name, f"origin/{branch_name}")
                    return f"✅ Created and switched to branch '{branch_name}' (tracking origin/{branch_name})"
                else:
                    return f"❌ Branch '{branch_name}' not found locally or on remote"
            except Exception:
                return f"❌ Branch '{branch_name}' not found"

    except GitCommandError as e:
        return f"❌ Checkout failed: {str(e)}"
    except Exception as e:
        return f"❌ Checkout error: {str(e)}"


def _resolve_branch_type(
    branch_type: Literal["local", "remote", "all"],
    remote: bool,
    all: bool,  # noqa: A002
) -> Literal["local", "remote", "all"]:
    """Resolve branch_type from new param or legacy bool aliases."""
    legacy_used = remote or all
    explicit_type = branch_type != "local"

    if explicit_type and legacy_used:
        raise ValueError(
            "Cannot combine 'branch_type' with legacy 'remote'/'all' flags. "
            "Use 'branch_type' only."
        )

    if legacy_used:
        if all:
            return "all"
        return "remote"

    return branch_type


def _get_contains_set(repo: Repo, contains: str) -> set[str]:
    """Return set of branch names (stripped) that contain the given commit-ish."""
    raw = repo.git.branch("--contains", contains)
    names = set()
    for line in raw.splitlines():
        name = line.lstrip("* ").strip()
        if name:
            names.add(name)
    return names


def _get_merged_set(repo: Repo, *, merged: bool) -> set[str]:
    """Return set of branch names filtered by --merged or --no-merged."""
    flag = "--merged" if merged else "--no-merged"
    raw = repo.git.branch(flag)
    names = set()
    for line in raw.splitlines():
        name = line.lstrip("* ").strip()
        if name:
            names.add(name)
    return names


def _build_branch_record(
    name: str,
    sha: str,
    is_current: bool,
    upstream: str | None,
) -> dict[str, Any]:
    return {"name": name, "sha": sha, "is_current": is_current, "upstream": upstream}


def _collect_local_branches(repo: Repo) -> list[dict[str, Any]]:
    """Collect local branch records."""
    try:
        active = repo.active_branch.name
    except TypeError:
        active = None  # detached HEAD

    records = []
    for head in repo.branches:
        try:
            upstream = (
                head.tracking_branch().name
                if head.tracking_branch() is not None
                else None
            )
        except Exception:
            upstream = None
        records.append(
            _build_branch_record(
                name=head.name,
                sha=head.commit.hexsha,
                is_current=(head.name == active),
                upstream=upstream,
            )
        )
    return records


def _collect_remote_branches(repo: Repo) -> list[dict[str, Any]]:
    """Collect remote branch records (remotes/origin/... style names)."""
    records = []
    for remote in repo.remotes:
        for ref in remote.refs:
            if ref.name.endswith("/HEAD"):
                continue
            records.append(
                _build_branch_record(
                    name=ref.name,
                    sha=ref.commit.hexsha,
                    is_current=False,
                    upstream=None,
                )
            )
    return records


def _collect_sorted_branches(
    repo: Repo,
    effective_type: Literal["local", "remote", "all"],
    sort: str,
) -> list[dict[str, Any]]:
    """Collect branches in sorted order using git for-each-ref."""
    patterns: list[str]
    if effective_type == "local":
        patterns = ["refs/heads"]
    elif effective_type == "remote":
        patterns = ["refs/remotes"]
    else:
        patterns = ["refs/heads", "refs/remotes"]

    fmt = "%(refname:short)%00%(objectname)%00%(upstream:short)"
    raw = repo.git.for_each_ref(f"--sort={sort}", f"--format={fmt}", *patterns)

    try:
        active = repo.active_branch.name
    except TypeError:
        active = None  # detached HEAD

    records = []
    for line in raw.splitlines():
        if not line:
            continue
        parts = line.split("\x00")
        if len(parts) < 3:  # pragma: no cover
            continue
        name, sha, upstream = parts[0], parts[1], parts[2]
        # Skip remote HEAD symbolic refs
        if name.endswith("/HEAD"):
            continue
        records.append(
            _build_branch_record(
                name=name,
                sha=sha,
                is_current=(name == active),
                upstream=upstream if upstream else None,
            )
        )
    return records


def _format_branches(records: list[dict[str, Any]]) -> str:
    if not records:
        return "No branches found"
    lines = []
    for r in records:
        marker = "* " if r["is_current"] else "  "
        sha_short = r["sha"][:8]
        upstream_info = f" -> {r['upstream']}" if r["upstream"] else ""
        lines.append(f"{marker}{r['name']} [{sha_short}]{upstream_info}")
    return "Branches:\n" + "\n".join(lines)


def git_branch_list(
    repo: Repo,
    branch_type: Literal["local", "remote", "all"] = "local",
    pattern: str | None = None,
    contains: str | None = None,
    merged: bool | None = None,
    sort: str | None = None,
    # Deprecated back-compat aliases — derive branch_type from these if branch_type
    # is at default ("local") and no explicit branch_type was set.
    remote: bool = False,
    all: bool = False,  # noqa: A002
) -> str:
    """List branches in the repository.

    Args:
        repo: Repository object
        branch_type: Which branches to list — "local" (default), "remote", or "all"
        pattern: Optional fnmatch glob to filter branch names, e.g. 'feature/*'
        contains: commit-ish; only branches containing this commit are returned
        merged: True = only merged into HEAD, False = only unmerged, None = no filter
        sort: Sort key for git for-each-ref, e.g. '-committerdate'. None = legacy path.
        remote: Deprecated. Use branch_type='remote' instead.
        all: Deprecated. Use branch_type='all' instead.

    Returns:
        Formatted string listing branches with sha and upstream info.
    """
    try:
        effective_type = _resolve_branch_type(branch_type, remote, all)

        # Collect candidate records
        if sort is not None:
            records = _collect_sorted_branches(repo, effective_type, sort)
        elif effective_type == "local":
            records = _collect_local_branches(repo)
        elif effective_type == "remote":
            records = _collect_remote_branches(repo)
        else:  # "all"
            records = _collect_local_branches(repo) + _collect_remote_branches(repo)

        # Apply pattern filter
        if pattern and pattern.strip():
            records = [r for r in records if fnmatch.fnmatch(r["name"], pattern)]

        # Apply contains filter
        if contains is not None:
            allowed = _get_contains_set(repo, contains)
            records = [r for r in records if r["name"] in allowed]

        # Apply merged filter
        if merged is not None:
            allowed = _get_merged_set(repo, merged=merged)
            records = [r for r in records if r["name"] in allowed]

        return _format_branches(records)

    except ValueError as e:
        return f"❌ Branch list error: {str(e)}"
    except GitCommandError as e:
        return f"❌ Branch list failed: {str(e)}"
    except Exception as e:
        return f"❌ Branch list error: {str(e)}"


def git_merge_base(
    repo: Repo,
    ref1: str,
    ref2: str,
) -> str:
    """Find the common ancestor (merge-base) of two references.

    Args:
        repo: Git repository object
        ref1: First reference (branch, commit, or tag)
        ref2: Second reference (branch, commit, or tag)

    Returns:
        Formatted merge-base information including SHA, author, date, and message
    """
    try:
        # Validate inputs for dangerous characters
        dangerous_chars = [";", "|", "&", "`", "$", "(", ")"]
        for ref_name, ref_value in [("ref1", ref1), ("ref2", ref2)]:
            if any(char in ref_value for char in dangerous_chars):
                return f"❌ Invalid characters detected in {ref_name}: {ref_value}"

        # Execute git merge-base
        merge_base_sha = repo.git.merge_base(ref1, ref2)

        # Get commit details for context
        commit = repo.commit(merge_base_sha)

        # Format output
        return (
            f"Merge base: {merge_base_sha[:8]}\n"
            f"Full SHA: {merge_base_sha}\n"
            f"Author: {commit.author.name} <{commit.author.email}>\n"
            f"Date: {commit.committed_datetime.isoformat()}\n"
            f"Message: {commit.message.strip()}"
        )
    except GitCommandError as e:
        return f"❌ Error finding merge-base: {str(e)}"
    except Exception as e:
        return f"❌ Merge-base error: {str(e)}"
