"""Branch operations for MCP Git Server."""

import logging

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


def git_branch_list(
    repo: Repo,
    remote: bool = False,
    all: bool = False,
    pattern: str | None = None,
) -> str:
    """List branches in the repository

    Args:
        repo: Repository object
        remote: If True, list remote branches (git branch -r)
        all: If True, list all branches including remote (git branch -a)
        pattern: Optional pattern to filter branches (supports glob patterns like 'feature/*')

    Returns:
        String containing the list of branches
    """
    try:
        args = []

        # Add branch listing flags
        if all:
            args.append("-a")
        elif remote:
            args.append("-r")

        # When using pattern, we need to add --list flag
        if pattern and pattern.strip():
            args.append("--list")
            args.append(pattern)

        branch_output = repo.git.branch(*args)

        if not branch_output.strip():
            return "No branches found"

        return f"Branches:\n{branch_output}"
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
