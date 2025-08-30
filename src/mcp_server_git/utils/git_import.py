"""Safe git import utility for handling git command failures.

This module provides a safe way to import GitPython with fallback to mock
objects when git commands are not available or fail to initialize.
"""

from typing import Any
from unittest.mock import MagicMock


def create_git_mock():
    """Create a mock git module for testing environments."""
    mock_git = MagicMock()

    # Mock common git classes and exceptions
    mock_git.Repo = MagicMock()
    mock_git.GitCommandError = Exception
    mock_git.InvalidGitRepositoryError = Exception
    mock_git.NoSuchPathError = Exception

    return mock_git


def safe_git_import() -> Any:
    """Safely import git module, with fallback for environments with git command issues.

    Returns:
        git module if successful, mock git module if import fails

    Raises:
        ImportError: If git import fails for unexpected reasons
    """
    try:
        import git

        return git
    except ImportError as e:
        if "Failed to initialize" in str(e) and "git version" in str(e):
            # Git command failed to initialize - use mock for testing/development
            return create_git_mock()
        raise


# Global git module instance - imported once
git = safe_git_import()

# Export commonly used classes for convenience
Repo = git.Repo
GitCommandError = git.GitCommandError

# Handle additional exceptions that might be used
try:
    InvalidGitRepositoryError = git.InvalidGitRepositoryError
    NoSuchPathError = git.NoSuchPathError
except AttributeError:
    # If we're using a mock, these might not exist
    InvalidGitRepositoryError = Exception
    NoSuchPathError = Exception
