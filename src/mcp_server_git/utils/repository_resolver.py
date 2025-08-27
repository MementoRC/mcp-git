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
        self.bound_repository_path = Path(bound_repository_path) if bound_repository_path else None
        self._resolved_repo_cache: Optional[Path] = None
        logger.debug(f"RepositoryResolver initialized with bound_path: {bound_repository_path}")

    def resolve_repository_path(self, requested_repo_path: Optional[str] = None) -> Optional[str]:
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
        # Priority 1: Use explicitly requested path
        if requested_repo_path and requested_repo_path != ".":
            logger.debug(f"Using explicitly requested repo_path: {requested_repo_path}")
            return requested_repo_path
            
        # Priority 2: Use bound repository (with worktree resolution)
        if self.bound_repository_path:
            resolved_path = self._resolve_with_worktree_support(self.bound_repository_path)
            logger.debug(f"Using bound repository (resolved): {resolved_path}")
            return str(resolved_path)
            
        # Priority 3: No repository determined - return blank
        logger.debug("No repository path determined - returning None")
        return None

    def _resolve_with_worktree_support(self, repo_path: Path) -> Path:
        """
        Resolve repository path with worktree support.
        
        If the path is a worktree, follow the gitdir reference to find the real repository.
        """
        # Check cache first
        if self._resolved_repo_cache:
            return self._resolved_repo_cache
            
        try:
            # Check if this is a worktree by looking for .git file (not directory)
            git_file = repo_path / ".git"
            
            if git_file.is_file():
                # This is likely a worktree - read the gitdir reference
                with open(git_file, 'r') as f:
                    git_content = f.read().strip()
                    
                if git_content.startswith("gitdir: "):
                    # Extract the gitdir path
                    gitdir_path = git_content[8:].strip()  # Remove "gitdir: " prefix
                    
                    if not Path(gitdir_path).is_absolute():
                        # Make relative path absolute relative to the worktree
                        gitdir_path = repo_path / gitdir_path
                    
                    gitdir_path = Path(gitdir_path).resolve()
                    
                    # The real repository is the parent of the worktrees directory
                    # e.g., /path/to/repo/.git/worktrees/feat-branch -> /path/to/repo
                    if "worktrees" in gitdir_path.parts:
                        # Find the .git directory that contains worktrees
                        git_dir = gitdir_path
                        while git_dir.name != ".git" and git_dir.parent != git_dir:
                            git_dir = git_dir.parent
                            
                        if git_dir.name == ".git":
                            real_repo_path = git_dir.parent
                            logger.info(f"Resolved worktree {repo_path} -> real repository {real_repo_path}")
                            self._resolved_repo_cache = real_repo_path
                            return real_repo_path
                            
            # Not a worktree or couldn't resolve - use original path
            logger.debug(f"Using original repository path: {repo_path}")
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
                "bound_repository": str(self.bound_repository_path) if self.bound_repository_path else None,
                "error": "No repository path could be determined"
            }
            
        try:
            resolved_path_obj = Path(resolved_path)
            
            # Check if it's a valid git repository
            repo = Repo(resolved_path)
            is_valid = True
            
            # Check if the bound path (if any) was a worktree
            is_worktree = False
            if self.bound_repository_path and self.bound_repository_path != resolved_path_obj:
                is_worktree = True
                
            return {
                "resolved_path": str(resolved_path_obj),
                "is_valid_repo": is_valid,
                "is_worktree": is_worktree,
                "bound_repository": str(self.bound_repository_path) if self.bound_repository_path else None,
                "working_dir": repo.working_dir,
                "git_dir": repo.git_dir,
            }
            
        except InvalidGitRepositoryError:
            return {
                "resolved_path": resolved_path,
                "is_valid_repo": False,
                "is_worktree": False,
                "bound_repository": str(self.bound_repository_path) if self.bound_repository_path else None,
                "error": f"Not a valid git repository: {resolved_path}"
            }
        except Exception as e:
            return {
                "resolved_path": resolved_path,
                "is_valid_repo": False,
                "is_worktree": False,
                "bound_repository": str(self.bound_repository_path) if self.bound_repository_path else None,
                "error": f"Error accessing repository: {e}"
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
            "bound_repository_path": str(self.bound_repository_path) if self.bound_repository_path else None,
            "resolved_repo_cache": str(self._resolved_repo_cache) if self._resolved_repo_cache else None,
            "resolver_initialized": self.bound_repository_path is not None,
        }