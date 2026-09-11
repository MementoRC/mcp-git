"""Submodule operations for MCP Git Server."""

import logging

from ..utils.git_import import GitCommandError, Repo
from .error_text import clean_git_error_text

logger = logging.getLogger(__name__)

__all__ = [
    "git_submodule_status",
    "git_submodule_add",
    "git_submodule_update",
    "git_submodule_sync",
]


def git_submodule_status(repo: Repo) -> str:
    """List submodules and their current status.

    Args:
        repo: Git repository object

    Returns:
        Formatted list of submodules with paths, SHAs, and branches
    """
    try:
        output = repo.git.submodule("status")
        if not output.strip():
            return "No submodules found in this repository"
        lines = output.strip().split("\n")
        result_lines = ["Submodules:"]
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Parse status indicator
            status = "up-to-date"
            if line.startswith("+"):
                status = "modified"
                line = line[1:]
            elif line.startswith("-"):
                status = "not initialized"
                line = line[1:]
            elif line.startswith("U"):
                status = "merge conflict"
                line = line[1:]

            parts = line.strip().split()
            sha = parts[0] if parts else "unknown"
            path = parts[1] if len(parts) > 1 else "unknown"
            branch = parts[2].strip("()") if len(parts) > 2 else ""

            branch_info = f" ({branch})" if branch else ""
            result_lines.append(f"  {path}: {sha[:8]}{branch_info} [{status}]")

        return "\n".join(result_lines)
    except GitCommandError as e:
        return f"❌ Submodule status failed: {clean_git_error_text(e.stderr, 'stderr')}"
    except Exception as e:
        return f"❌ Submodule status error: {str(e)}"


def git_submodule_add(
    repo: Repo,
    url: str,
    path: str,
    branch: str | None = None,
) -> str:
    """Add a new submodule to the repository.

    Args:
        repo: Git repository object
        url: URL of the submodule repository
        path: Local path where the submodule will be placed
        branch: Branch to track (optional)

    Returns:
        Success or error message
    """
    # Validate URL scheme
    allowed_schemes = ("https://", "http://", "git://", "ssh://", "git@")
    if not any(url.startswith(scheme) for scheme in allowed_schemes):
        return f"❌ Invalid URL scheme. Allowed: {', '.join(allowed_schemes)}"
    # Validate no shell injection in path or url
    dangerous_chars = [";", "|", "&", "`", "$", "(", ")"]
    if any(char in path for char in dangerous_chars):
        return f"❌ Invalid characters in submodule path: {path}"
    if any(char in url for char in dangerous_chars):
        return f"❌ Invalid characters in URL: {url}"
    try:
        args = ["add"]
        if branch:
            args.extend(["--branch", branch])
        args.extend([url, path])
        repo.git.submodule(*args)
        branch_info = f" (branch: {branch})" if branch else ""
        return f"✅ Submodule added at '{path}' from {url}{branch_info}"
    except GitCommandError as e:
        return f"❌ Submodule add failed: {clean_git_error_text(e.stderr, 'stderr')}"
    except Exception as e:
        return f"❌ Submodule add error: {str(e)}"


def git_submodule_update(
    repo: Repo,
    init: bool = True,
    recursive: bool = False,
    remote: bool = False,
    paths: list[str] | None = None,
) -> str:
    """Update submodules (optionally init, recursive, or from remote).

    Args:
        repo: Git repository object
        init: Initialize uninitialized submodules before updating
        recursive: Recursively update nested submodules
        remote: Update to latest remote commit instead of recorded SHA
        paths: Specific submodule paths to update (default: all)

    Returns:
        Success or error message
    """
    try:
        args = ["update"]
        if init:
            args.append("--init")
        if recursive:
            args.append("--recursive")
        if remote:
            args.append("--remote")
        if paths:
            args.extend(paths)
        repo.git.submodule(*args)
        scope = ", ".join(paths) if paths else "all submodules"
        flags = []
        if init:
            flags.append("init")
        if recursive:
            flags.append("recursive")
        if remote:
            flags.append("remote")
        flag_info = f" [{', '.join(flags)}]" if flags else ""
        return f"✅ Submodules updated{flag_info}: {scope}"
    except GitCommandError as e:
        return f"❌ Submodule update failed: {clean_git_error_text(e.stderr, 'stderr')}"
    except Exception as e:
        return f"❌ Submodule update error: {str(e)}"


def git_submodule_sync(
    repo: Repo,
    recursive: bool = False,
) -> str:
    """Sync submodule URLs from .gitmodules to .git/config.

    Args:
        repo: Git repository object
        recursive: Recursively sync nested submodules

    Returns:
        Success or error message
    """
    try:
        args = ["sync"]
        if recursive:
            args.append("--recursive")
        repo.git.submodule(*args)
        recursive_info = " (recursive)" if recursive else ""
        return f"✅ Submodule URLs synced from .gitmodules{recursive_info}"
    except GitCommandError as e:
        return f"❌ Submodule sync failed: {clean_git_error_text(e.stderr, 'stderr')}"
    except Exception as e:
        return f"❌ Submodule sync error: {str(e)}"
