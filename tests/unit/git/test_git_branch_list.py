"""
Unit tests for git_branch_list operation in mcp_server_git.git.operations module.

These tests verify the git_branch_list function that lists local and remote branches
with optional filtering capabilities.
"""

from unittest.mock import Mock

import pytest

from mcp_server_git.git.operations import git_branch_list
from mcp_server_git.utils.git_import import GitCommandError


class TestGitBranchList:
    """Test git_branch_list operations with comprehensive validation."""

    def test_git_branch_list_local_branches_successfully(self):
        """Should list local branches successfully (default behavior)."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.branch.return_value = "  develop\n* main\n  feature/new-feature"

        # Act
        result = git_branch_list(mock_repo)

        # Assert
        assert "Branches:" in result
        assert "develop" in result
        assert "main" in result
        assert "feature/new-feature" in result
        mock_repo.git.branch.assert_called_once_with()

    def test_git_branch_list_remote_branches_successfully(self):
        """Should list remote branches when remote=True."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.branch.return_value = (
            "  origin/develop\n  origin/main\n  origin/feature/task-1"
        )

        # Act
        result = git_branch_list(mock_repo, remote=True)

        # Assert
        assert "Branches:" in result
        assert "origin/develop" in result
        assert "origin/main" in result
        assert "origin/feature/task-1" in result
        mock_repo.git.branch.assert_called_once_with("-r")

    def test_git_branch_list_all_branches_successfully(self):
        """Should list all branches (local and remote) when all=True."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.branch.return_value = (
            "  develop\n* main\n  remotes/origin/develop\n  remotes/origin/main"
        )

        # Act
        result = git_branch_list(mock_repo, all=True)

        # Assert
        assert "Branches:" in result
        assert "develop" in result
        assert "main" in result
        assert "remotes/origin/develop" in result
        assert "remotes/origin/main" in result
        mock_repo.git.branch.assert_called_once_with("-a")

    def test_git_branch_list_with_pattern_filter(self):
        """Should filter branches by pattern when pattern is provided."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.branch.return_value = "  feature/task-1\n  feature/task-2"

        # Act
        result = git_branch_list(mock_repo, pattern="feature/*")

        # Assert
        assert "Branches:" in result
        assert "feature/task-1" in result
        assert "feature/task-2" in result
        mock_repo.git.branch.assert_called_once_with("--list", "feature/*")

    def test_git_branch_list_all_with_pattern(self):
        """Should combine all flag with pattern filtering."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.branch.return_value = (
            "  feature/task-1\n  remotes/origin/feature/task-1"
        )

        # Act
        result = git_branch_list(mock_repo, all=True, pattern="feature/*")

        # Assert
        assert "Branches:" in result
        assert "feature/task-1" in result
        mock_repo.git.branch.assert_called_once_with("-a", "--list", "feature/*")

    def test_git_branch_list_no_branches_found(self):
        """Should return appropriate message when no branches are found."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.branch.return_value = ""

        # Act
        result = git_branch_list(mock_repo, pattern="nonexistent/*")

        # Assert
        assert "No branches found" in result

    def test_git_branch_list_handles_git_command_error(self):
        """Should handle GitCommandError gracefully."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.branch.side_effect = GitCommandError(
            "branch", "fatal: not a git repository"
        )

        # Act
        result = git_branch_list(mock_repo)

        # Assert
        assert "❌ Branch list failed:" in result
        assert "fatal: not a git repository" in result

    def test_git_branch_list_handles_generic_exception(self):
        """Should handle generic exceptions gracefully."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.branch.side_effect = Exception("Unexpected error")

        # Act
        result = git_branch_list(mock_repo)

        # Assert
        assert "❌ Branch list error:" in result
        assert "Unexpected error" in result

    def test_git_branch_list_precedence_all_over_remote(self):
        """Should give precedence to 'all' flag when both all and remote are True."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.branch.return_value = (
            "  develop\n* main\n  remotes/origin/develop"
        )

        # Act
        result = git_branch_list(mock_repo, all=True, remote=True)

        # Assert
        # When both are specified, 'all' should take precedence
        assert "Branches:" in result
        mock_repo.git.branch.assert_called_once_with("-a")

    def test_git_branch_list_empty_pattern_ignored(self):
        """Should ignore empty pattern string."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.branch.return_value = "  develop\n* main"

        # Act
        result = git_branch_list(mock_repo, pattern="")

        # Assert
        assert "Branches:" in result
        # Empty pattern should not be passed to git branch
        mock_repo.git.branch.assert_called_once_with()
