"""
Unit tests for git_restore operation.

These tests verify the git_restore function that restores working tree files
or unstages staged files.
"""

from unittest.mock import Mock

import pytest

from mcp_server_git.git.operations_extended import git_restore
from mcp_server_git.utils.git_import import GitCommandError


class TestGitRestoreSuccess:
    """Test successful git_restore scenarios."""

    def test_git_restore_working_tree_returns_success(self):
        """Should restore working tree file and return success message."""
        mock_repo = Mock()

        result = git_restore(mock_repo, files=["src/file.py"])

        assert "✅" in result
        assert "1 file(s)" in result
        assert "src/file.py" in result
        assert "restored" in result
        mock_repo.git.restore.assert_called_once_with("src/file.py")

    def test_git_restore_staged_files_returns_unstaged_mode(self):
        """Should unstage files and indicate unstaged mode."""
        mock_repo = Mock()

        result = git_restore(mock_repo, files=["README.md"], staged=True)

        assert "✅" in result
        assert "unstaged" in result
        mock_repo.git.restore.assert_called_once_with("--staged", "README.md")

    def test_git_restore_from_source_commit(self):
        """Should restore from a specific commit/ref."""
        mock_repo = Mock()

        result = git_restore(mock_repo, files=["src/main.py"], source="HEAD~1")

        assert "✅" in result
        assert "src/main.py" in result
        mock_repo.git.restore.assert_called_once_with("--source", "HEAD~1", "src/main.py")

    def test_git_restore_staged_with_source(self):
        """Should combine --staged and --source flags."""
        mock_repo = Mock()

        result = git_restore(mock_repo, files=["config.yaml"], staged=True, source="abc123")

        assert "✅" in result
        mock_repo.git.restore.assert_called_once_with("--staged", "--source", "abc123", "config.yaml")

    def test_git_restore_multiple_files(self):
        """Should restore multiple files and list them in the result."""
        mock_repo = Mock()
        files = ["a.py", "b.py", "c.py"]

        result = git_restore(mock_repo, files=files)

        assert "✅" in result
        assert "3 file(s)" in result
        mock_repo.git.restore.assert_called_once_with("a.py", "b.py", "c.py")

    def test_git_restore_truncates_long_file_list(self):
        """Should truncate file list display beyond 5 files."""
        mock_repo = Mock()
        files = [f"file{i}.py" for i in range(8)]

        result = git_restore(mock_repo, files=files)

        assert "✅" in result
        assert "8 file(s)" in result
        assert "+3 more" in result

    def test_git_restore_exactly_five_files_no_suffix(self):
        """Should not add suffix when exactly 5 files."""
        mock_repo = Mock()
        files = [f"file{i}.py" for i in range(5)]

        result = git_restore(mock_repo, files=files)

        assert "✅" in result
        assert "more" not in result


class TestGitRestoreInputValidation:
    """Test input validation for git_restore."""

    def test_git_restore_rejects_empty_files_list(self):
        """Should reject an empty files list."""
        mock_repo = Mock()

        result = git_restore(mock_repo, files=[])

        assert "❌" in result
        assert "No files specified" in result
        mock_repo.git.restore.assert_not_called()

    @pytest.mark.parametrize(
        "dangerous_char",
        [";", "|", "&", "`", "$", "(", ")"],
    )
    def test_git_restore_rejects_dangerous_chars_in_source(self, dangerous_char):
        """Should reject dangerous characters in source ref."""
        mock_repo = Mock()
        malicious_source = f"HEAD{dangerous_char}rm -rf /"

        result = git_restore(mock_repo, files=["file.py"], source=malicious_source)

        assert "❌" in result
        assert "Invalid characters detected in source" in result
        mock_repo.git.restore.assert_not_called()

    def test_git_restore_accepts_valid_source_refs(self):
        """Should accept valid source refs with common characters."""
        mock_repo = Mock()

        result = git_restore(mock_repo, files=["file.py"], source="feature/my-branch_v2")

        assert "✅" in result
        mock_repo.git.restore.assert_called_once()

    def test_git_restore_accepts_commit_hash_as_source(self):
        """Should accept a full SHA commit hash as source."""
        mock_repo = Mock()

        result = git_restore(mock_repo, files=["file.py"], source="abc1234567890def")

        assert "✅" in result
        mock_repo.git.restore.assert_called_once()


class TestGitRestoreErrorHandling:
    """Test error handling for git_restore."""

    def test_git_restore_handles_git_command_error_bytes_stderr(self):
        """Should handle GitCommandError with bytes stderr gracefully."""
        mock_repo = Mock()
        mock_repo.git.restore.side_effect = GitCommandError(
            "git restore", 128, b"", b"error: pathspec 'missing.py' did not match"
        )

        result = git_restore(mock_repo, files=["missing.py"])

        assert "❌" in result
        assert "Restore failed" in result

    def test_git_restore_handles_git_command_error_string_stderr(self):
        """Should handle GitCommandError with string stderr gracefully."""
        mock_repo = Mock()
        error = GitCommandError("git restore", 128, b"", b"fatal: not a git repo")
        error.stderr = "fatal: not a git repo"
        mock_repo.git.restore.side_effect = error

        result = git_restore(mock_repo, files=["file.py"])

        assert "❌" in result
        assert "Restore failed" in result

    def test_git_restore_handles_general_exception(self):
        """Should handle unexpected exceptions gracefully."""
        mock_repo = Mock()
        mock_repo.git.restore.side_effect = Exception("Unexpected failure")

        result = git_restore(mock_repo, files=["file.py"])

        assert "❌" in result
        assert "Error during restore" in result
        assert "Unexpected failure" in result
