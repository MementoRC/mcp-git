"""Remote operations (push, pull, fetch, remote management) for MCP Git Server."""

from pathlib import Path

from ..utils.git_import import GitCommandError, Repo
from ._github_token import _get_github_token_from_cli
from ._push_ops import git_push
from .error_text import clean_git_error_text

__all__ = [
    "_get_github_token_from_cli",
    "git_clone",
    "git_push",
    "git_pull",
    "git_remote_list",
    "git_remote_add",
    "git_remote_remove",
    "git_remote_rename",
    "git_remote_set_url",
    "git_remote_get_url",
    "git_fetch",
]


def git_pull(repo: Repo, remote: str = "origin", branch: str | None = None) -> str:
    """Pull changes from remote repository"""
    try:
        # Get current branch if not specified
        if not branch:
            try:
                branch = repo.active_branch.name
            except TypeError:  # Detached HEAD or no commits
                return "❌ No active branch found and no branch specified"

        # Perform pull
        if branch:
            result = repo.git.pull(remote, branch)
        else:
            result = repo.git.pull(remote)

        return f"✅ Successfully pulled from {remote}/{branch}\n{result}"

    except GitCommandError as e:
        error_text = clean_git_error_text(e.stderr, "stderr")
        if "Authentication failed" in error_text:
            return f"❌ Authentication failed. Check credentials for {remote}"
        elif "merge conflict" in error_text.lower():
            return "❌ Pull failed due to merge conflicts. Resolve conflicts and retry"
        else:
            return f"❌ Pull failed (exit {e.status}): {error_text}"
    except Exception as e:
        return f"❌ Pull error: {str(e)}"


def git_remote_list(repo: Repo, verbose: bool = False) -> str:
    """List all remote repositories"""
    try:
        if verbose:
            return repo.git.remote("-v")
        else:
            return repo.git.remote()
    except GitCommandError as e:
        return f"❌ Remote list failed: {clean_git_error_text(e.stderr, 'stderr')}"
    except Exception as e:
        return f"❌ Remote list error: {str(e)}"


def git_remote_add(repo: Repo, name: str, url: str) -> str:
    """Add a new remote repository"""
    try:
        repo.git.remote("add", name, url)
        return f"✅ Successfully added remote '{name}' -> {url}"
    except GitCommandError as e:
        return f"❌ Remote add failed: {clean_git_error_text(e.stderr, 'stderr')}"
    except Exception as e:
        return f"❌ Remote add error: {str(e)}"


def git_remote_remove(repo: Repo, name: str) -> str:
    """Remove a remote repository"""
    try:
        repo.git.remote("remove", name)
        return f"✅ Successfully removed remote '{name}'"
    except GitCommandError as e:
        return f"❌ Remote remove failed: {clean_git_error_text(e.stderr, 'stderr')}"
    except Exception as e:
        return f"❌ Remote remove error: {str(e)}"


def git_remote_rename(repo: Repo, old_name: str, new_name: str) -> str:
    """Rename a remote repository"""
    try:
        repo.git.remote("rename", old_name, new_name)
        return f"✅ Successfully renamed remote '{old_name}' to '{new_name}'"
    except GitCommandError as e:
        return f"❌ Remote rename failed: {clean_git_error_text(e.stderr, 'stderr')}"
    except Exception as e:
        return f"❌ Remote rename error: {str(e)}"


def git_remote_set_url(repo: Repo, name: str, url: str) -> str:
    """Set URL for a remote repository"""
    try:
        repo.git.remote("set-url", name, url)
        return f"✅ Successfully set URL for remote '{name}' -> {url}"
    except GitCommandError as e:
        return f"❌ Remote set-url failed: {clean_git_error_text(e.stderr, 'stderr')}"
    except Exception as e:
        return f"❌ Remote set-url error: {str(e)}"


def git_remote_get_url(repo: Repo, name: str) -> str:
    """Get URL for a remote repository"""
    try:
        url = repo.git.remote("get-url", name)
        return f"Remote '{name}' URL: {url}"
    except GitCommandError as e:
        return f"❌ Remote get-url failed: {clean_git_error_text(e.stderr, 'stderr')}"
    except Exception as e:
        return f"❌ Remote get-url error: {str(e)}"


def git_clone(
    repo_url: str,
    target_path: str,
    branch: str | None = None,
    depth: int | None = None,
    single_branch: bool = False,
    recurse_submodules: bool = False,
) -> str:
    """Clone a remote repository to a local path"""
    try:
        target = Path(target_path)
        if not target.parent.exists():
            raise ValueError(f"Parent directory does not exist: {target.parent}")
        if target.exists() and any(target.iterdir()):
            raise ValueError(
                f"Target path already exists and is not empty: {target_path}"
            )

        multi_options = []
        if branch:
            multi_options.append(f"--branch={branch}")
        if depth is not None:
            multi_options.append(f"--depth={depth}")
        if single_branch:
            multi_options.append("--single-branch")
        if recurse_submodules:
            multi_options.append("--recurse-submodules")

        Repo.clone_from(repo_url, target_path, multi_options=multi_options)

        return f"✅ Cloned {repo_url} to {target_path}"
    except ValueError:
        raise
    except GitCommandError as e:
        return f"❌ Clone failed (exit {e.status}): {clean_git_error_text(e.stderr, 'stderr')}"
    except Exception as e:
        return f"❌ Clone error: {str(e)}"


def git_fetch(
    repo: Repo,
    remote: str = "origin",
    branch: str | None = None,
    prune: bool = False,
) -> str:
    """Fetch changes from remote repository"""
    try:
        args = [remote]
        if branch:
            args.append(branch)
        if prune:
            args.append("--prune")

        repo.git.fetch(*args)

        if branch:
            return f"✅ Successfully fetched {remote}/{branch}" + (
                " (with prune)" if prune else ""
            )
        else:
            return f"✅ Successfully fetched from {remote}" + (
                " (with prune)" if prune else ""
            )
    except GitCommandError as e:
        return f"❌ Fetch failed: {clean_git_error_text(e.stderr, 'stderr')}"
    except Exception as e:
        return f"❌ Fetch error: {str(e)}"
