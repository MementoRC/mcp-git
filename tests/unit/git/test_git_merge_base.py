"""
Unit tests for git_merge_base operation.

These tests verify the git_merge_base function that finds the common
ancestor (merge-base) of two references.
"""

from datetime import datetime
from unittest.mock import Mock

import pytest

from mcp_server_git.git.operations import git_merge_base
from mcp_server_git.utils.git_import import GitCommandError


class TestGitMergeBaseSuccess:
    """Test successful git_merge_base scenarios."""

    def test_git_merge_base_returns_formatted_output(self):
        """Should return formatted merge-base information."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.merge_base.return_value = (
            "abc1234567890def1234567890abcdef12345678"
        )

        mock_commit = Mock()
        mock_commit.author.name = "Test Author"
        mock_commit.author.email = "test@example.com"
        mock_commit.committed_datetime = datetime(2024, 1, 15, 12, 0, 0)
        mock_commit.message = "Initial commit"
        mock_repo.commit.return_value = mock_commit

        # Act
        result = git_merge_base(mock_repo, "main", "feature")

        # Assert
        assert "Merge base: abc12345" in result
        assert "Full SHA: abc1234567890def1234567890abcdef12345678" in result
        assert "Author: Test Author <test@example.com>" in result
        assert "Date: 2024-01-15T12:00:00" in result
        assert "Message: Initial commit" in result
        mock_repo.git.merge_base.assert_called_once_with("main", "feature")

    def test_git_merge_base_with_commit_hashes(self):
        """Should work with commit hashes as references."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.merge_base.return_value = "deadbeef12345678"

        mock_commit = Mock()
        mock_commit.author.name = "Developer"
        mock_commit.author.email = "dev@example.com"
        mock_commit.committed_datetime = datetime(2024, 6, 20, 15, 30, 0)
        mock_commit.message = "Feature implementation"
        mock_repo.commit.return_value = mock_commit

        # Act
        result = git_merge_base(mock_repo, "abc123", "def456")

        # Assert
        assert "Merge base: deadbeef" in result
        mock_repo.git.merge_base.assert_called_once_with("abc123", "def456")

    def test_git_merge_base_with_same_ref(self):
        """Should work when both refs point to same commit."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.merge_base.return_value = "samehash123456789"

        mock_commit = Mock()
        mock_commit.author.name = "Author"
        mock_commit.author.email = "author@example.com"
        mock_commit.committed_datetime = datetime(2024, 3, 10, 9, 0, 0)
        mock_commit.message = "Same commit"
        mock_repo.commit.return_value = mock_commit

        # Act
        result = git_merge_base(mock_repo, "main", "main")

        # Assert
        assert "Merge base: samehash" in result
        mock_repo.git.merge_base.assert_called_once_with("main", "main")


class TestGitMergeBaseInputValidation:
    """Test input validation for git_merge_base."""

    @pytest.mark.parametrize(
        "dangerous_char",
        [";", "|", "&", "`", "$", "(", ")"],
    )
    def test_git_merge_base_rejects_dangerous_chars_in_ref1(self, dangerous_char):
        """Should reject dangerous characters in ref1."""
        # Arrange
        mock_repo = Mock()
        malicious_ref = f"main{dangerous_char}echo pwned"

        # Act
        result = git_merge_base(mock_repo, malicious_ref, "feature")

        # Assert
        assert "❌ Invalid characters detected in ref1" in result
        mock_repo.git.merge_base.assert_not_called()

    @pytest.mark.parametrize(
        "dangerous_char",
        [";", "|", "&", "`", "$", "(", ")"],
    )
    def test_git_merge_base_rejects_dangerous_chars_in_ref2(self, dangerous_char):
        """Should reject dangerous characters in ref2."""
        # Arrange
        mock_repo = Mock()
        malicious_ref = f"feature{dangerous_char}rm -rf /"

        # Act
        result = git_merge_base(mock_repo, "main", malicious_ref)

        # Assert
        assert "❌ Invalid characters detected in ref2" in result
        mock_repo.git.merge_base.assert_not_called()

    def test_git_merge_base_accepts_valid_branch_names(self):
        """Should accept valid branch names with common characters."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.merge_base.return_value = "abc123"

        mock_commit = Mock()
        mock_commit.author.name = "Test"
        mock_commit.author.email = "test@test.com"
        mock_commit.committed_datetime = datetime(2024, 1, 1, 0, 0, 0)
        mock_commit.message = "Test"
        mock_repo.commit.return_value = mock_commit

        # Act - valid branch names with slashes, hyphens, underscores
        result = git_merge_base(mock_repo, "feature/my-branch_v2", "origin/main")

        # Assert
        assert "Merge base:" in result
        mock_repo.git.merge_base.assert_called_once()


class TestGitMergeBaseErrorHandling:
    """Test error handling for git_merge_base."""

    def test_git_merge_base_handles_git_command_error(self):
        """Should handle GitCommandError gracefully."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.merge_base.side_effect = GitCommandError(
            "git merge-base", 128, b"", b"fatal: Not a valid object name"
        )

        # Act
        result = git_merge_base(mock_repo, "nonexistent", "also-nonexistent")

        # Assert
        assert "❌" in result
        assert "merge-base" in result.lower() or "error" in result.lower()

    def test_git_merge_base_handles_no_common_ancestor(self):
        """Should handle case when refs have no common ancestor."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.merge_base.side_effect = GitCommandError(
            "git merge-base", 1, b"", b"fatal: no merge base"
        )

        # Act
        result = git_merge_base(mock_repo, "orphan-branch", "main")

        # Assert
        assert "❌" in result

    def test_git_merge_base_handles_general_exception(self):
        """Should handle unexpected exceptions gracefully."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.merge_base.side_effect = Exception("Unexpected error")

        # Act
        result = git_merge_base(mock_repo, "main", "feature")

        # Assert
        assert "❌" in result
        assert "error" in result.lower()

    def test_git_merge_base_handles_commit_lookup_error(self):
        """Should handle error when commit lookup fails."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.merge_base.return_value = "abc123"
        mock_repo.commit.side_effect = Exception("Commit not found")

        # Act
        result = git_merge_base(mock_repo, "main", "feature")

        # Assert
        assert "❌" in result
