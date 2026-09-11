"""
Unit tests for git_branch_update operation.

These tests verify the git_branch_update function that force-updates or deletes
branch refs.
"""

from unittest.mock import Mock

import pytest

from mcp_server_git.git.operations_extended import git_branch_update
from mcp_server_git.utils.git_import import GitCommandError


class TestGitBranchUpdateSuccess:
    """Test successful git_branch_update scenarios."""

    def test_git_branch_update_force_update_branch_returns_success(self):
        """Should force-update branch ref and return success message."""
        mock_repo = Mock()

        result = git_branch_update(mock_repo, branch_name="feature", target="main")

        assert "✅" in result
        assert "feature" in result
        assert "main" in result
        mock_repo.git.branch.assert_called_once_with("-f", "feature", "main")

    def test_git_branch_update_delete_branch_returns_success(self):
        """Should delete branch and return success message."""
        mock_repo = Mock()

        result = git_branch_update(mock_repo, branch_name="old-branch", delete=True)

        assert "✅" in result
        assert "old-branch" in result
        assert "Deleted" in result
        mock_repo.git.branch.assert_called_once_with("-d", "old-branch")

    def test_git_branch_update_force_delete_branch_uses_capital_D(self):
        """Should use -D flag for force delete (unmerged branch)."""
        mock_repo = Mock()

        result = git_branch_update(
            mock_repo, branch_name="unmerged-branch", delete=True, force=True
        )

        assert "✅" in result
        assert "unmerged-branch" in result
        mock_repo.git.branch.assert_called_once_with("-D", "unmerged-branch")

    def test_git_branch_update_force_update_with_commit_hash(self):
        """Should force-update branch to a commit hash."""
        mock_repo = Mock()

        result = git_branch_update(mock_repo, branch_name="release", target="abc1234")

        assert "✅" in result
        assert "release" in result
        assert "abc1234" in result
        mock_repo.git.branch.assert_called_once_with("-f", "release", "abc1234")


class TestGitBranchUpdateInputValidation:
    """Test input validation for git_branch_update."""

    def test_git_branch_update_rejects_no_action(self):
        """Should reject when neither target nor delete specified."""
        mock_repo = Mock()

        result = git_branch_update(mock_repo, branch_name="feature")

        assert "❌" in result
        assert "Must specify either target" in result
        mock_repo.git.branch.assert_not_called()

    def test_git_branch_update_rejects_conflicting_target_and_delete(self):
        """Should reject when both target and delete are specified."""
        mock_repo = Mock()

        result = git_branch_update(
            mock_repo, branch_name="feature", target="main", delete=True
        )

        assert "❌" in result
        assert "Cannot specify both target and delete" in result
        mock_repo.git.branch.assert_not_called()

    @pytest.mark.parametrize("dangerous_char", [";", "|", "&", "`", "$"])
    def test_git_branch_update_rejects_dangerous_chars_in_branch_name(
        self, dangerous_char
    ):
        """Should reject dangerous characters in branch_name."""
        mock_repo = Mock()
        malicious_name = f"feature{dangerous_char}rm -rf /"

        result = git_branch_update(mock_repo, branch_name=malicious_name, target="main")

        assert "❌" in result
        assert "Invalid characters detected in branch_name" in result
        mock_repo.git.branch.assert_not_called()

    @pytest.mark.parametrize("dangerous_char", [";", "|", "&", "`", "$"])
    def test_git_branch_update_rejects_dangerous_chars_in_target(self, dangerous_char):
        """Should reject dangerous characters in target ref."""
        mock_repo = Mock()
        malicious_target = f"main{dangerous_char}rm -rf /"

        result = git_branch_update(
            mock_repo, branch_name="feature", target=malicious_target
        )

        assert "❌" in result
        assert "Invalid characters detected in target" in result
        mock_repo.git.branch.assert_not_called()

    def test_git_branch_update_accepts_valid_branch_names(self):
        """Should accept valid branch names with slashes and hyphens."""
        mock_repo = Mock()

        result = git_branch_update(
            mock_repo, branch_name="feature/my-branch_v2", target="main"
        )

        assert "✅" in result
        mock_repo.git.branch.assert_called_once()

    def test_git_branch_update_accepts_valid_target_refs(self):
        """Should accept valid target refs including tags and remote branches."""
        mock_repo = Mock()

        result = git_branch_update(mock_repo, branch_name="local", target="origin/main")

        assert "✅" in result
        mock_repo.git.branch.assert_called_once_with("-f", "local", "origin/main")


class TestGitBranchUpdateErrorHandling:
    """Test error handling for git_branch_update."""

    def test_git_branch_update_handles_git_command_error_bytes_stderr(self):
        """Should handle GitCommandError with bytes stderr for delete-current-branch."""
        mock_repo = Mock()
        mock_repo.git.branch.side_effect = GitCommandError(
            "git branch", 1, b"", b"error: Cannot delete branch 'main' checked out"
        )

        result = git_branch_update(mock_repo, branch_name="main", delete=True)

        assert "❌" in result
        assert "Branch update failed" in result

    def test_git_branch_update_handles_git_command_error_string_stderr(self):
        """Should handle GitCommandError with string stderr gracefully."""
        mock_repo = Mock()
        error = GitCommandError("git branch", 1, b"", b"error: not fully merged")
        error.stderr = "error: not fully merged"
        mock_repo.git.branch.side_effect = error

        result = git_branch_update(mock_repo, branch_name="unmerged", delete=True)

        assert "❌" in result
        assert "Branch update failed" in result

    def test_git_branch_update_handles_general_exception(self):
        """Should handle unexpected exceptions gracefully."""
        mock_repo = Mock()
        mock_repo.git.branch.side_effect = Exception("Unexpected failure")

        result = git_branch_update(mock_repo, branch_name="feature", target="main")

        assert "❌" in result
        assert "Error updating branch" in result
        assert "Unexpected failure" in result
