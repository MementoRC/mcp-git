"""Repository initialization operations for MCP Git Server."""

from pathlib import Path

from ..utils.git_import import Repo

__all__ = ["git_init"]


def git_init(repo_path: str) -> str:
    """Initialize new Git repository"""
    try:
        path = Path(repo_path)
        path.mkdir(parents=True, exist_ok=True)

        # Initialize repository
        Repo.init(path)

        return f"✅ Initialized empty Git repository in {repo_path}"

    except Exception as e:
        return f"❌ Init failed: {str(e)}"
