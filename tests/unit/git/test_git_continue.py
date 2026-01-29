"""
Unit tests for git_continue operation fix for issue #97.

These tests verify that git_continue uses subprocess instead of GitPython
to avoid MCP client timeout issues with interactive operations.

Critical for TDD Compliance:
    These tests define the behavior that the implementation must satisfy.
    DO NOT modify these tests to match a broken implementation - the
    implementation must be fixed to pass these tests.
"""

import subprocess
from unittest.mock import Mock, patch

import pytest

from mcp_server_git.git.operations import git_continue


class TestGitContinueSubprocessFix:
    """Test git_continue uses subprocess for reliable execution."""

    @patch("mcp_server_git.git.operations.subprocess.run")
    def test_git_continue_uses_subprocess_for_rebase(self, mock_subprocess):
        """Should use subprocess.run instead of GitPython for rebase continue."""
        # Arrange
        mock_repo = Mock()
        mock_repo.working_dir = "/test/repo"

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Successfully rebased"
        mock_result.stderr = ""
        mock_subprocess.return_value = mock_result

        # Act
        result = git_continue(mock_repo, "rebase")

        # Assert
        assert "✅ Successfully continued rebase" in result
        mock_subprocess.assert_called_once_with(
            ["git", "rebase", "--continue"],
            cwd="/test/repo",
            capture_output=True,
            text=True,
            timeout=60,
        )

    @patch("mcp_server_git.git.operations.subprocess.run")
    def test_git_continue_uses_subprocess_for_merge(self, mock_subprocess):
        """Should use subprocess.run for merge continue."""
        # Arrange
        mock_repo = Mock()
        mock_repo.working_dir = "/test/repo"

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Merge completed"
        mock_result.stderr = ""
        mock_subprocess.return_value = mock_result

        # Act
        result = git_continue(mock_repo, "merge")

        # Assert
        assert "✅ Successfully continued merge" in result
        mock_subprocess.assert_called_once_with(
            ["git", "merge", "--continue"],
            cwd="/test/repo",
            capture_output=True,
            text=True,
            timeout=60,
        )

    @patch("mcp_server_git.git.operations.subprocess.run")
    def test_git_continue_uses_subprocess_for_cherry_pick(self, mock_subprocess):
        """Should use subprocess.run for cherry-pick continue."""
        # Arrange
        mock_repo = Mock()
        mock_repo.working_dir = "/test/repo"

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Cherry-pick completed"
        mock_result.stderr = ""
        mock_subprocess.return_value = mock_result

        # Act
        result = git_continue(mock_repo, "cherry-pick")

        # Assert
        assert "✅ Successfully continued cherry-pick" in result
        mock_subprocess.assert_called_once_with(
            ["git", "cherry-pick", "--continue"],
            cwd="/test/repo",
            capture_output=True,
            text=True,
            timeout=60,
        )

    @patch("mcp_server_git.git.operations.subprocess.run")
    def test_git_continue_handles_no_operation_in_progress(self, mock_subprocess):
        """Should provide helpful message when no operation is in progress."""
        # Arrange
        mock_repo = Mock()
        mock_repo.working_dir = "/test/repo"

        mock_result = Mock()
        mock_result.returncode = 128
        mock_result.stdout = ""
        mock_result.stderr = "fatal: No rebase in progress?"
        mock_subprocess.return_value = mock_result

        # Act
        result = git_continue(mock_repo, "rebase")

        # Assert
        assert "❌ No rebase in progress to continue" in result

    @patch("mcp_server_git.git.operations.subprocess.run")
    def test_git_continue_handles_unresolved_conflicts(self, mock_subprocess):
        """Should detect and report unresolved conflicts."""
        # Arrange
        mock_repo = Mock()
        mock_repo.working_dir = "/test/repo"

        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error: you must resolve conflicts before continuing"
        mock_subprocess.return_value = mock_result

        # Act
        result = git_continue(mock_repo, "rebase")

        # Assert
        assert "❌ Unresolved conflicts remain" in result
        assert "Resolve conflicts before continuing" in result

    @patch("mcp_server_git.git.operations.subprocess.run")
    def test_git_continue_handles_nothing_to_commit(self, mock_subprocess):
        """Should detect when there are no changes to commit."""
        # Arrange
        mock_repo = Mock()
        mock_repo.working_dir = "/test/repo"

        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "nothing to commit, working tree clean"
        mock_subprocess.return_value = mock_result

        # Act
        result = git_continue(mock_repo, "rebase")

        # Assert
        assert "❌ No changes to commit" in result

    @patch("mcp_server_git.git.operations.subprocess.run")
    def test_git_continue_handles_timeout(self, mock_subprocess):
        """Should handle subprocess timeout gracefully."""
        # Arrange
        mock_repo = Mock()
        mock_repo.working_dir = "/test/repo"

        mock_subprocess.side_effect = subprocess.TimeoutExpired(
            cmd=["git", "rebase", "--continue"], timeout=60
        )

        # Act
        result = git_continue(mock_repo, "rebase")

        # Assert
        assert "❌ rebase continue operation timed out" in result

    def test_git_continue_rejects_invalid_operation(self):
        """Should reject invalid operation types."""
        # Arrange
        mock_repo = Mock()

        # Act
        result = git_continue(mock_repo, "invalid-op")

        # Assert
        assert "❌ Invalid operation" in result
        assert "Valid operations: rebase, merge, cherry-pick" in result

    @patch("mcp_server_git.git.operations.subprocess.run")
    def test_git_continue_includes_output_in_success_message(self, mock_subprocess):
        """Should include git command output in success message."""
        # Arrange
        mock_repo = Mock()
        mock_repo.working_dir = "/test/repo"

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Applying: commit message\n3 files changed"
        mock_result.stderr = ""
        mock_subprocess.return_value = mock_result

        # Act
        result = git_continue(mock_repo, "rebase")

        # Assert
        assert "✅ Successfully continued rebase" in result
        assert "Applying: commit message" in result
        assert "3 files changed" in result

    @patch("mcp_server_git.git.operations.subprocess.run")
    def test_git_continue_handles_stderr_in_success(self, mock_subprocess):
        """Should include stderr in output even on success."""
        # Arrange
        mock_repo = Mock()
        mock_repo.working_dir = "/test/repo"

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = "Already on 'main'"
        mock_subprocess.return_value = mock_result

        # Act
        result = git_continue(mock_repo, "merge")

        # Assert
        assert "✅ Successfully continued merge" in result
        assert "Already on 'main'" in result

    @patch("mcp_server_git.git.operations.subprocess.run")
    def test_git_continue_prefers_stderr_on_failure(self, mock_subprocess):
        """Should report stderr on failure, falling back to stdout."""
        # Arrange
        mock_repo = Mock()
        mock_repo.working_dir = "/test/repo"

        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = "Some stdout"
        mock_result.stderr = "fatal: error message"
        mock_subprocess.return_value = mock_result

        # Act
        result = git_continue(mock_repo, "rebase")

        # Assert
        assert "❌" in result
        assert "fatal: error message" in result
        assert "Some stdout" not in result

    @patch("mcp_server_git.git.operations.subprocess.run")
    def test_git_continue_falls_back_to_stdout_on_empty_stderr(self, mock_subprocess):
        """Should use stdout if stderr is empty on failure."""
        # Arrange
        mock_repo = Mock()
        mock_repo.working_dir = "/test/repo"

        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = "Error in stdout"
        mock_result.stderr = ""
        mock_subprocess.return_value = mock_result

        # Act
        result = git_continue(mock_repo, "rebase")

        # Assert
        assert "❌" in result
        assert "Error in stdout" in result


# Integration tests are skipped in ClaudeCode environments
# due to PATH redirector conflicts with subprocess git commands.
# Unit tests with mocks provide sufficient coverage of the subprocess fix.


# Mark for test organization
pytestmark = [pytest.mark.unit, pytest.mark.git_operations, pytest.mark.issue_97]
