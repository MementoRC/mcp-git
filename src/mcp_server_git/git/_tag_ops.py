"""Tag operations for MCP Git Server."""

import logging

from ..utils.git_import import GitCommandError, Repo

logger = logging.getLogger(__name__)

__all__ = [
    "git_tag_list",
    "git_tag_create",
    "git_tag_delete",
]


def git_tag_list(repo: Repo) -> str:
    """List all tags"""
    try:
        tag_list = repo.git.tag("-l")
        if not tag_list.strip():
            return "No tags found"
        return f"Tags:\n{tag_list}"
    except GitCommandError as e:
        return f"❌ Tag list failed: {str(e)}"
    except Exception as e:
        return f"❌ Tag list error: {str(e)}"


def git_tag_create(
    repo: Repo,
    tag_name: str,
    message: str | None = None,
    commit: str | None = None,
) -> str:
    """Create a new tag"""
    try:
        args = [tag_name]
        if message:
            args.extend(["-m", message])
        if commit:
            args.append(commit)

        repo.git.tag(*args)
        return f"✅ Successfully created tag '{tag_name}'" + (
            f" on {commit}" if commit else ""
        )
    except GitCommandError as e:
        return f"❌ Tag create failed: {str(e)}"
    except Exception as e:
        return f"❌ Tag create error: {str(e)}"


def git_tag_delete(repo: Repo, tag_name: str) -> str:
    """Delete a tag"""
    try:
        repo.git.tag("-d", tag_name)
        return f"✅ Successfully deleted tag '{tag_name}'"
    except GitCommandError as e:
        return f"❌ Tag delete failed: {str(e)}"
    except Exception as e:
        return f"❌ Tag delete error: {str(e)}"
