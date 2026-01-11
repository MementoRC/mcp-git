"""
Unit tests for git_log operation with advanced filtering and formatting.

These tests verify the enhanced git_log function that provides comprehensive
filtering, formatting, and search capabilities for commit history.
"""

from unittest.mock import Mock, patch

import pytest

from mcp_server_git.git.operations import git_log
from mcp_server_git.utils.git_import import GitCommandError


class TestGitLogBasic:
    """Test basic git_log functionality."""

    def test_git_log_default_parameters(self):
        """Should return commit log with default parameters."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.log.return_value = "commit abc123\nAuthor: Test\n\nCommit message"

        # Act
        result = git_log(mock_repo)

        # Assert
        assert "commit abc123" in result
        mock_repo.git.log.assert_called_once_with("-n", "10")

    def test_git_log_custom_max_count(self):
        """Should limit commits to specified max_count."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.log.return_value = "commit abc123"

        # Act
        result = git_log(mock_repo, max_count=5)

        # Assert
        mock_repo.git.log.assert_called_once_with("-n", "5")

    def test_git_log_oneline_format(self):
        """Should use oneline format when specified."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.log.return_value = "abc123 Commit message"

        # Act
        result = git_log(mock_repo, max_count=10, oneline=True)

        # Assert
        mock_repo.git.log.assert_called_once_with("-n", "10", "--oneline")

    def test_git_log_with_graph(self):
        """Should show graph when specified."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.log.return_value = "* abc123 Commit"

        # Act
        result = git_log(mock_repo, max_count=10, graph=True)

        # Assert
        args = mock_repo.git.log.call_args[0]
        assert "-n" in args
        assert "10" in args
        assert "--graph" in args

    def test_git_log_custom_format(self):
        """Should use custom format string."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.log.return_value = "abc123 - Test Author"
        format_str = "%h - %an"

        # Act
        result = git_log(mock_repo, max_count=10, format_str=format_str)

        # Assert
        args = mock_repo.git.log.call_args[0]
        assert "--pretty=format:%h - %an" in args

    def test_git_log_empty_repository(self):
        """Should return message when no commits found."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.log.return_value = ""

        # Act
        result = git_log(mock_repo)

        # Assert
        assert "No commits found matching the specified criteria" in result

    def test_git_log_with_max_count_zero(self):
        """Should not add -n flag when max_count is 0."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.log.return_value = ""

        # Act
        result = git_log(mock_repo, max_count=0)

        # Assert
        args = mock_repo.git.log.call_args[0]
        assert "-n" not in args


class TestGitLogFiltering:
    """Test git_log filtering capabilities."""

    def test_git_log_with_since_filter(self):
        """Should filter commits after specified date."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.log.return_value = "commit abc123"

        # Act
        result = git_log(mock_repo, max_count=10, since="2024-01-01")

        # Assert
        args = mock_repo.git.log.call_args[0]
        assert "--since" in args
        assert "2024-01-01" in args

    def test_git_log_with_until_filter(self):
        """Should filter commits before specified date."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.log.return_value = "commit abc123"

        # Act
        result = git_log(mock_repo, max_count=10, until="yesterday")

        # Assert
        args = mock_repo.git.log.call_args[0]
        assert "--until" in args
        assert "yesterday" in args

    def test_git_log_with_date_range(self):
        """Should filter commits within date range."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.log.return_value = "commit abc123"

        # Act
        result = git_log(
            mock_repo, max_count=10, since="2024-01-01", until="2024-12-31"
        )

        # Assert
        args = mock_repo.git.log.call_args[0]
        assert "--since" in args
        assert "2024-01-01" in args
        assert "--until" in args
        assert "2024-12-31" in args

    def test_git_log_with_author_filter(self):
        """Should filter commits by author."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.log.return_value = "commit abc123"

        # Act
        result = git_log(mock_repo, max_count=10, author="john@example.com")

        # Assert
        args = mock_repo.git.log.call_args[0]
        assert "--author" in args
        assert "john@example.com" in args

    def test_git_log_with_grep_filter(self):
        """Should filter commits by message pattern."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.log.return_value = "commit abc123"

        # Act
        result = git_log(mock_repo, max_count=10, grep="fix:")

        # Assert
        args = mock_repo.git.log.call_args[0]
        assert "--grep" in args
        assert "fix:" in args

    def test_git_log_with_branch_filter(self):
        """Should show log for specific branch."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.log.return_value = "commit abc123"

        # Act
        result = git_log(mock_repo, max_count=10, branch="feature/new-feature")

        # Assert
        args = mock_repo.git.log.call_args[0]
        assert "feature/new-feature" in args
        # Branch should be first argument
        assert args[0] == "feature/new-feature"


class TestGitLogMergeFiltering:
    """Test merge commit filtering."""

    def test_git_log_only_merges(self):
        """Should show only merge commits when merges=True."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.log.return_value = "commit abc123 (merge)"

        # Act
        result = git_log(mock_repo, max_count=10, merges=True)

        # Assert
        args = mock_repo.git.log.call_args[0]
        assert "--merges" in args

    def test_git_log_no_merges(self):
        """Should exclude merge commits when merges=False."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.log.return_value = "commit abc123"

        # Act
        result = git_log(mock_repo, max_count=10, merges=False)

        # Assert
        args = mock_repo.git.log.call_args[0]
        assert "--no-merges" in args

    def test_git_log_all_commits_when_merges_none(self):
        """Should include all commits when merges=None."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.log.return_value = "commit abc123"

        # Act
        result = git_log(mock_repo, max_count=10, merges=None)

        # Assert
        args = mock_repo.git.log.call_args[0]
        assert "--merges" not in args
        assert "--no-merges" not in args


class TestGitLogFileFiltering:
    """Test file-specific filtering."""

    def test_git_log_with_single_file(self):
        """Should show commits affecting single file."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.log.return_value = "commit abc123"

        # Act
        result = git_log(mock_repo, max_count=10, files=["src/main.py"])

        # Assert
        args = mock_repo.git.log.call_args[0]
        assert "--" in args
        assert "src/main.py" in args
        # Files should come after --
        dash_index = args.index("--")
        assert "src/main.py" in args[dash_index + 1 :]

    def test_git_log_with_multiple_files(self):
        """Should show commits affecting multiple files."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.log.return_value = "commit abc123"

        # Act
        result = git_log(mock_repo, max_count=10, files=["src/main.py", "src/utils.py"])

        # Assert
        args = mock_repo.git.log.call_args[0]
        assert "--" in args
        assert "src/main.py" in args
        assert "src/utils.py" in args


class TestGitLogOrdering:
    """Test commit ordering options."""

    def test_git_log_reverse_order(self):
        """Should reverse commit order when reverse=True."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.log.return_value = "commit abc123"

        # Act
        result = git_log(mock_repo, max_count=10, reverse=True)

        # Assert
        args = mock_repo.git.log.call_args[0]
        assert "--reverse" in args

    def test_git_log_normal_order(self):
        """Should use normal order when reverse=False."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.log.return_value = "commit abc123"

        # Act
        result = git_log(mock_repo, max_count=10, reverse=False)

        # Assert
        args = mock_repo.git.log.call_args[0]
        assert "--reverse" not in args


class TestGitLogComplexScenarios:
    """Test complex combinations of filters."""

    def test_git_log_multiple_filters_combined(self):
        """Should handle multiple filters simultaneously."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.log.return_value = "abc123 Fix bug"

        # Act
        result = git_log(
            mock_repo,
            max_count=20,
            oneline=True,
            since="1 week ago",
            author="john@example.com",
            grep="fix:",
            merges=False,
        )

        # Assert
        args = mock_repo.git.log.call_args[0]
        assert "-n" in args
        assert "20" in args
        assert "--oneline" in args
        assert "--since" in args
        assert "1 week ago" in args
        assert "--author" in args
        assert "john@example.com" in args
        assert "--grep" in args
        assert "fix:" in args
        assert "--no-merges" in args

    def test_git_log_with_branch_and_files(self):
        """Should filter by branch and specific files."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.log.return_value = "commit abc123"

        # Act
        result = git_log(mock_repo, max_count=10, branch="main", files=["src/main.py"])

        # Assert
        args = mock_repo.git.log.call_args[0]
        assert "main" in args
        assert "--" in args
        assert "src/main.py" in args

    def test_git_log_full_feature_set(self):
        """Should handle all parameters together."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.log.return_value = "abc123 Fix bug"

        # Act
        result = git_log(
            mock_repo,
            max_count=50,
            oneline=True,
            graph=True,
            since="2024-01-01",
            until="2024-12-31",
            author="john@example.com",
            grep="fix",
            files=["src/main.py"],
            branch="develop",
            reverse=False,
            merges=False,
        )

        # Assert
        args = mock_repo.git.log.call_args[0]
        # Verify key elements are present
        assert "develop" in args
        assert "-n" in args
        assert "50" in args
        assert "--oneline" in args
        assert "--graph" in args
        assert "--since" in args
        assert "--until" in args
        assert "--author" in args
        assert "--grep" in args
        assert "--no-merges" in args
        assert "--" in args
        assert "src/main.py" in args


class TestGitLogErrorHandling:
    """Test error handling in git_log."""

    def test_git_log_handles_git_command_error(self):
        """Should return error message on GitCommandError."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.log.side_effect = GitCommandError("git log", 128, "error")

        # Act
        result = git_log(mock_repo)

        # Assert
        assert "❌ Log failed:" in result

    def test_git_log_handles_general_exception(self):
        """Should return error message on general exception."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.log.side_effect = Exception("Unexpected error")

        # Act
        result = git_log(mock_repo)

        # Assert
        assert "❌ Log error:" in result


class TestGitLogRealWorldScenarios:
    """Test real-world usage scenarios."""

    def test_git_log_find_recent_fixes(self):
        """Scenario: Find recent fix commits."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.log.return_value = (
            "abc123 fix: resolve bug\ndef456 fix: memory leak"
        )

        # Act
        result = git_log(mock_repo, max_count=20, grep="fix:", oneline=True)

        # Assert
        assert "abc123" in result or "resolve bug" in result

    def test_git_log_changes_by_author_last_month(self):
        """Scenario: Find all commits by specific author in last month."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.log.return_value = "commit abc123\nAuthor: john@example.com"

        # Act
        result = git_log(
            mock_repo,
            max_count=100,
            author="john@example.com",
            since="1 month ago",
            oneline=True,
        )

        # Assert
        args = mock_repo.git.log.call_args[0]
        assert "--author" in args
        assert "--since" in args

    def test_git_log_file_history(self):
        """Scenario: View history of specific file."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.log.return_value = "commit abc123\n\nChanged file"

        # Act
        result = git_log(mock_repo, max_count=50, files=["src/critical.py"])

        # Assert
        args = mock_repo.git.log.call_args[0]
        assert "--" in args
        assert "src/critical.py" in args

    def test_git_log_generate_changelog(self):
        """Scenario: Generate changelog between versions."""
        # Arrange
        mock_repo = Mock()
        mock_repo.git.log.return_value = "abc123 - feat: new feature (john)"
        format_str = "%h - %s (%an)"

        # Act
        result = git_log(
            mock_repo,
            max_count=100,
            format_str=format_str,
            since="v1.0.0",
            until="v1.1.0",
            grep="^feat|^fix",
        )

        # Assert
        args = mock_repo.git.log.call_args[0]
        assert "--pretty=format:%h - %s (%an)" in args
        assert "--since" in args
        assert "--until" in args
        assert "--grep" in args
