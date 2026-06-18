"""
Unit tests for git_branch_delete operation.

These tests verify the git_branch_delete function that deletes a local branch
by delegating to git_branch_update.
"""

from unittest.mock import Mock

import pytest

from mcp_server_git.git.operations_extended import git_branch_delete
from mcp_server_git.utils.git_import import GitCommandError


class TestGitBranchDeleteSuccess:
    """Test successful git_branch_delete scenarios."""

    def test_git_branch_delete_removes_branch_returns_success(self):
        """Should delete branch and return success message."""
        mock_repo = Mock()

        result = git_branch_delete(mock_repo, branch_name="old-branch")

        assert "✅" in result
        assert "old-branch" in result
        assert "Deleted" in result
        mock_repo.git.branch.assert_called_once_with("-d", "old-branch")

    def test_git_branch_delete_force_deletes_unmerged_branch_uses_capital_D(self):
        """Should use -D flag when force=True (unmerged branch)."""
        mock_repo = Mock()

        result = git_branch_delete(mock_repo, branch_name="unmerged-branch", force=True)

        assert "✅" in result
        assert "unmerged-branch" in result
        mock_repo.git.branch.assert_called_once_with("-D", "unmerged-branch")

    def test_git_branch_delete_force_false_uses_lowercase_d(self):
        """Should use -d flag when force=False (default)."""
        mock_repo = Mock()

        result = git_branch_delete(mock_repo, branch_name="feature")

        mock_repo.git.branch.assert_called_once_with("-d", "feature")


class TestGitBranchDeleteInputValidation:
    """Test input validation for git_branch_delete."""

    @pytest.mark.parametrize("dangerous_char", [";", "|", "&", "`", "$"])
    def test_git_branch_delete_rejects_dangerous_chars_in_branch_name(self, dangerous_char):
        """Should reject dangerous characters in branch_name."""
        mock_repo = Mock()
        malicious_name = f"feature{dangerous_char}rm -rf /"

        result = git_branch_delete(mock_repo, branch_name=malicious_name)

        assert "❌" in result
        assert "Invalid characters detected in branch_name" in result
        mock_repo.git.branch.assert_not_called()

    def test_git_branch_delete_accepts_valid_branch_names_with_slashes_and_hyphens(self):
        """Should accept valid branch names with slashes and hyphens."""
        mock_repo = Mock()

        result = git_branch_delete(mock_repo, branch_name="feature/my-branch_v2")

        assert "✅" in result
        mock_repo.git.branch.assert_called_once()


class TestGitBranchDeleteErrorHandling:
    """Test error handling for git_branch_delete."""

    def test_git_branch_delete_raises_error_when_unmerged_without_force(self):
        """Should return error when deleting unmerged branch without force."""
        mock_repo = Mock()
        mock_repo.git.branch.side_effect = GitCommandError(
            "git branch", 1, b"", b"error: The branch 'feature' is not fully merged."
        )

        result = git_branch_delete(mock_repo, branch_name="feature", force=False)

        assert "❌" in result
        assert "Branch update failed" in result

    def test_git_branch_delete_handles_git_command_error_bytes_stderr(self):
        """Should handle GitCommandError with bytes stderr."""
        mock_repo = Mock()
        mock_repo.git.branch.side_effect = GitCommandError(
            "git branch", 1, b"", b"error: Cannot delete branch 'main' checked out"
        )

        result = git_branch_delete(mock_repo, branch_name="main")

        assert "❌" in result
        assert "Branch update failed" in result

    def test_git_branch_delete_handles_general_exception(self):
        """Should handle unexpected exceptions gracefully."""
        mock_repo = Mock()
        mock_repo.git.branch.side_effect = Exception("Unexpected failure")

        result = git_branch_delete(mock_repo, branch_name="feature")

        assert "❌" in result
        assert "Error updating branch" in result
        assert "Unexpected failure" in result
