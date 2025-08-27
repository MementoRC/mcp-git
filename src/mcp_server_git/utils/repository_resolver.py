"""
Repository path resolution utilities with worktree support.

This module provides intelligent repository path resolution that:
1. Follows worktree references to find the real repository
2. Provides proper defaults based on --repository parameter
3. Prevents cross-session contamination
"""

from pathlib import Path
from typing import Optional

import logging

from ..utils.git_import import Repo, InvalidGitRepositoryError

logger = logging.getLogger(__name__)


class RepositoryResolver:
    """Intelligent repository path resolution with worktree support."""

    def __init__(self, bound_repository_path: Optional[str] = None):
        """Initialize with optional bound repository from --repository parameter."""
        self.bound_repository_path = (
            Path(bound_repository_path) if bound_repository_path else None
        )
        self._resolved_repo_cache: Optional[Path] = None
        logger.debug(
            f"RepositoryResolver initialized with bound_path: {bound_repository_path}"
        )

    def resolve_repository_path(
        self, requested_repo_path: Optional[str] = None
    ) -> Optional[str]:
        """
        Intelligently resolve repository path with the following priority:
        1. Use explicitly requested repo_path if provided
        2. Use bound repository from --repository parameter
        3. If bound repository is a worktree, resolve to real repository
        4. Return None (blank) if no repository can be determined

        Args:
            requested_repo_path: Explicitly requested repository path from tool call

        Returns:
            Resolved repository path or None if no repository can be determined
        """
        # Priority 1: Use explicitly requested path with validation
        if requested_repo_path and requested_repo_path != ".":
            path_obj = Path(requested_repo_path)
            if path_obj.exists():
                logger.debug(
                    f"Using explicitly requested repo_path: {requested_repo_path}"
                )
                return requested_repo_path
            else:
                logger.warning(
                    f"Requested repository path does not exist: {requested_repo_path}"
                )
                # Continue to next priority instead of returning invalid path

        # Priority 2: Use bound repository (with worktree resolution)
        if self.bound_repository_path:
            resolved_path = self._resolve_with_worktree_support(
                self.bound_repository_path
            )
            logger.debug(f"Using bound repository (resolved): {resolved_path}")
            return str(resolved_path)

        # Priority 3: No repository determined - return blank
        logger.debug("No repository path determined - returning None")
        return None

    def _resolve_with_worktree_support(self, repo_path: Path) -> Path:
        """
        Resolve repository path with worktree support using Git's formal worktree detection.

        If the path is a worktree, follow the gitdir reference to find the main repository.
        """
        # Check cache first
        if self._resolved_repo_cache:
            return self._resolved_repo_cache

        try:
            git_path = repo_path / ".git"

            # Formal worktree detection: .git is a file (not directory) in worktrees
            if git_path.is_file():
                # This is a worktree - read the gitdir reference
                try:
                    with open(git_path, "r", encoding="utf-8") as f:
                        git_content = f.read().strip()
                except (OSError, UnicodeDecodeError) as e:
                    logger.warning(f"Failed to read .git file {git_path}: {e}")
                    self._resolved_repo_cache = repo_path
                    return repo_path

                # Parse gitdir reference (standard Git worktree format)
                if git_content.startswith("gitdir: "):
                    gitdir_path = git_content[8:].strip()  # Remove "gitdir: " prefix

                    # Convert relative paths to absolute
                    if not Path(gitdir_path).is_absolute():
                        gitdir_path = repo_path / gitdir_path

                    gitdir_path = Path(gitdir_path).resolve()

                    # Standard Git worktree structure:
                    # main_repo/.git/worktrees/worktree_name/
                    # So gitdir_path points to: main_repo/.git/worktrees/worktree_name/
                    # We need to get to: main_repo/
                    if gitdir_path.parent and gitdir_path.parent.name == "worktrees":
                        main_git_dir = (
                            gitdir_path.parent.parent
                        )  # This is main_repo/.git/
                        if main_git_dir.name == ".git":
                            main_repo_path = main_git_dir.parent  # This is main_repo/
                            logger.info(
                                f"Resolved worktree {repo_path} -> main repository {main_repo_path}"
                            )
                            self._resolved_repo_cache = main_repo_path
                            return main_repo_path

                    logger.debug(
                        f"Worktree detected but couldn't resolve main repo from {gitdir_path}"
                    )

            elif git_path.is_dir():
                # This is a main repository (not a worktree)
                logger.debug(f"Main repository detected: {repo_path}")
            else:
                # No .git found
                logger.debug(f"No .git found at {repo_path}")

            # Use original path (either main repo or couldn't resolve worktree)
            self._resolved_repo_cache = repo_path
            return repo_path

        except Exception as e:
            logger.warning(f"Error resolving worktree for {repo_path}: {e}")
            self._resolved_repo_cache = repo_path
            return repo_path

    def get_repository_info(self, repo_path: Optional[str] = None) -> dict:
        """
        Get information about the resolved repository.

        Returns:
            Dictionary with repository information including worktree status
        """
        resolved_path = self.resolve_repository_path(repo_path)

        if not resolved_path:
            return {
                "resolved_path": None,
                "is_valid_repo": False,
                "is_worktree": False,
                "bound_repository": str(self.bound_repository_path)
                if self.bound_repository_path
                else None,
                "error": "No repository path could be determined",
            }

        try:
            resolved_path_obj = Path(resolved_path)

            # Check if it's a valid git repository
            repo = Repo(resolved_path)
            is_valid = True

            # Check if the bound path (if any) was a worktree
            is_worktree = False
            if (
                self.bound_repository_path
                and self.bound_repository_path != resolved_path_obj
            ):
                is_worktree = True

            return {
                "resolved_path": str(resolved_path_obj),
                "is_valid_repo": is_valid,
                "is_worktree": is_worktree,
                "bound_repository": str(self.bound_repository_path)
                if self.bound_repository_path
                else None,
                "working_dir": repo.working_dir,
                "git_dir": repo.git_dir,
            }

        except InvalidGitRepositoryError:
            return {
                "resolved_path": resolved_path,
                "is_valid_repo": False,
                "is_worktree": False,
                "bound_repository": str(self.bound_repository_path)
                if self.bound_repository_path
                else None,
                "error": f"Not a valid git repository: {resolved_path}",
            }
        except Exception as e:
            return {
                "resolved_path": resolved_path,
                "is_valid_repo": False,
                "is_worktree": False,
                "bound_repository": str(self.bound_repository_path)
                if self.bound_repository_path
                else None,
                "error": f"Error accessing repository: {e}",
            }

    def clear_cache(self):
        """Clear the resolved repository cache."""
        self._resolved_repo_cache = None
        logger.debug("Repository resolver cache cleared")

    def get_debug_info(self) -> dict:
        """
        Get debug information about the repository resolver state.

        Returns:
            Dictionary with resolver state and configuration
        """
        return {
            "bound_repository_path": str(self.bound_repository_path)
            if self.bound_repository_path
            else None,
            "resolved_repo_cache": str(self._resolved_repo_cache)
            if self._resolved_repo_cache
            else None,
            "resolver_initialized": self.bound_repository_path is not None,
        }
