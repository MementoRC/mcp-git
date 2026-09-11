"""
Unit tests for git_rm operation.

These tests verify the git_rm function that removes a single, explicitly-named
file from the working tree and/or index with safety guards against wildcards,
directories, and shell injection.
"""

from unittest.mock import Mock

import pytest

from mcp_server_git.git.operations_extended import git_rm
from mcp_server_git.utils.git_import import GitCommandError


class TestGitRmSuccess:
    """Test successful git_rm scenarios."""

    def test_git_rm_returns_success_for_tracked_file(self):
        """Should remove file from working tree and index."""
        mock_repo = Mock()
        mock_repo.git.rm.return_value = "rm 'src/old.py'"

        result = git_rm(mock_repo, file="src/old.py")

        assert "✅" in result
        assert "src/old.py" in result
        assert "working tree and index" in result
        mock_repo.git.rm.assert_called_once_with("--", "src/old.py")

    def test_git_rm_cached_returns_index_only_message(self):
        """Should remove from index only when cached=True."""
        mock_repo = Mock()
        mock_repo.git.rm.return_value = "rm 'config.yaml'"

        result = git_rm(mock_repo, file="config.yaml", cached=True)

        assert "✅" in result
        assert "from index (kept on disk)" in result
        mock_repo.git.rm.assert_called_once_with("--cached", "--", "config.yaml")

    def test_git_rm_dry_run_returns_preview(self):
        """Should show what would be removed without doing it."""
        mock_repo = Mock()
        mock_repo.git.rm.return_value = "rm 'temp.txt'"

        result = git_rm(mock_repo, file="temp.txt", dry_run=True)

        assert "🔍" in result
        assert "Dry-run" in result
        assert "temp.txt" in result
        mock_repo.git.rm.assert_called_once_with("--dry-run", "--", "temp.txt")

    def test_git_rm_cached_and_dry_run_combined(self):
        """Should combine --cached and --dry-run flags."""
        mock_repo = Mock()
        mock_repo.git.rm.return_value = "rm 'data.json'"

        result = git_rm(mock_repo, file="data.json", cached=True, dry_run=True)

        assert "🔍" in result
        mock_repo.git.rm.assert_called_once_with(
            "--cached", "--dry-run", "--", "data.json"
        )

    def test_git_rm_accepts_nested_path(self):
        """Should accept deeply nested file paths."""
        mock_repo = Mock()
        mock_repo.git.rm.return_value = "rm 'src/core/utils/helper.py'"

        result = git_rm(mock_repo, file="src/core/utils/helper.py")

        assert "✅" in result
        mock_repo.git.rm.assert_called_once_with("--", "src/core/utils/helper.py")

    def test_git_rm_strips_whitespace_from_file(self):
        """Should strip leading/trailing whitespace from file path."""
        mock_repo = Mock()
        mock_repo.git.rm.return_value = "rm 'file.py'"

        result = git_rm(mock_repo, file="  file.py  ")

        assert "✅" in result
        mock_repo.git.rm.assert_called_once_with("--", "file.py")

    @pytest.mark.parametrize(
        "filename",
        [
            "docs/résumé.txt",
            "data/日本語.csv",
            "notes/über-file.md",
            "src/café.py",
        ],
    )
    def test_git_rm_accepts_unicode_filenames(self, filename):
        """Should accept non-ASCII filenames without error."""
        mock_repo = Mock()
        mock_repo.git.rm.return_value = f"rm '{filename}'"

        result = git_rm(mock_repo, file=filename)

        assert "✅" in result
        mock_repo.git.rm.assert_called_once_with("--", filename)


class TestGitRmInputValidation:
    """Test safety guards for git_rm."""

    def test_git_rm_rejects_empty_string(self):
        """Should reject empty file path."""
        mock_repo = Mock()

        result = git_rm(mock_repo, file="")

        assert "❌" in result
        assert "No file specified" in result
        mock_repo.git.rm.assert_not_called()

    def test_git_rm_rejects_whitespace_only(self):
        """Should reject whitespace-only file path."""
        mock_repo = Mock()

        result = git_rm(mock_repo, file="   ")

        assert "❌" in result
        assert "No file specified" in result
        mock_repo.git.rm.assert_not_called()

    def test_git_rm_rejects_dot(self):
        """Should reject '.' as file path."""
        mock_repo = Mock()

        result = git_rm(mock_repo, file=".")

        assert "❌" in result
        assert "Refusing" in result
        mock_repo.git.rm.assert_not_called()

    def test_git_rm_rejects_dotdot(self):
        """Should reject '..' as file path."""
        mock_repo = Mock()

        result = git_rm(mock_repo, file="..")

        assert "❌" in result
        assert "Refusing" in result
        mock_repo.git.rm.assert_not_called()

    def test_git_rm_rejects_trailing_slash(self):
        """Should reject directory-style paths ending in '/'."""
        mock_repo = Mock()

        result = git_rm(mock_repo, file="src/")

        assert "❌" in result
        assert "Directory removal not supported" in result
        mock_repo.git.rm.assert_not_called()

    @pytest.mark.parametrize(
        "path",
        [
            "./",  # trailing slash caught first
            "dir/../",  # trailing slash caught first
        ],
    )
    def test_git_rm_rejects_trailing_slash_variants(self, path):
        """Should reject paths ending in '/' before normalization."""
        mock_repo = Mock()

        result = git_rm(mock_repo, file=path)

        assert "❌" in result
        assert "Directory removal not supported" in result
        mock_repo.git.rm.assert_not_called()

    @pytest.mark.parametrize(
        "path",
        [
            "/etc/passwd",
            "/home/user/file.py",
            "/tmp/test.txt",
        ],
    )
    def test_git_rm_rejects_absolute_paths(self, path):
        """Should reject absolute paths to prevent system file removal."""
        mock_repo = Mock()

        result = git_rm(mock_repo, file=path)

        assert "❌" in result
        assert "Absolute paths not allowed" in result
        mock_repo.git.rm.assert_not_called()

    @pytest.mark.parametrize(
        "path",
        [
            "dir/..",  # normpath collapses to .
            "a/b/../..",  # normpath collapses to .
        ],
    )
    def test_git_rm_rejects_normalized_dot_paths(self, path):
        """Should reject paths that normalize to '.' or '..'."""
        mock_repo = Mock()

        result = git_rm(mock_repo, file=path)

        assert "❌" in result
        assert "Refusing" in result
        mock_repo.git.rm.assert_not_called()

    def test_git_rm_normalizes_redundant_separators(self):
        """Should normalize path before passing to git."""
        mock_repo = Mock()
        mock_repo.git.rm.return_value = "rm 'src/file.py'"

        result = git_rm(mock_repo, file="src//file.py")

        assert "✅" in result
        mock_repo.git.rm.assert_called_once_with("--", "src/file.py")

    def test_git_rm_normalizes_dot_segments(self):
        """Should normalize ./src/../src/file.py to src/file.py."""
        mock_repo = Mock()
        mock_repo.git.rm.return_value = "rm 'src/file.py'"

        result = git_rm(mock_repo, file="./src/../src/file.py")

        assert "✅" in result
        mock_repo.git.rm.assert_called_once_with("--", "src/file.py")

    @pytest.mark.parametrize("wildcard", ["*", "?", "[", "]", "{", "}"])
    def test_git_rm_rejects_wildcards(self, wildcard):
        """Should reject any wildcard/glob characters."""
        mock_repo = Mock()

        result = git_rm(mock_repo, file=f"src/{wildcard}.py")

        assert "❌" in result
        assert "Wildcards" in result
        mock_repo.git.rm.assert_not_called()

    @pytest.mark.parametrize(
        "dangerous_char",
        [";", "|", "&", "`", "$", "(", ")"],
    )
    def test_git_rm_rejects_dangerous_chars(self, dangerous_char):
        """Should reject shell injection characters."""
        mock_repo = Mock()

        result = git_rm(mock_repo, file=f"file{dangerous_char}evil")

        assert "❌" in result
        assert "Invalid characters detected" in result
        mock_repo.git.rm.assert_not_called()


class TestGitRmErrorHandling:
    """Test error handling for git_rm."""

    def test_git_rm_returns_file_not_found_when_pathspec_unmatched(self):
        """Should return specific 'not tracked' message for missing files."""
        mock_repo = Mock()
        mock_repo.git.rm.side_effect = GitCommandError(
            "git rm", 128, b"fatal: pathspec 'missing.py' did not match any files"
        )

        result = git_rm(mock_repo, file="missing.py")

        assert "❌" in result
        assert "File not found" in result
        assert "not tracked" in result

    def test_git_rm_returns_uncommitted_changes_when_locally_modified(self):
        """Should return specific message when file has local modifications."""
        mock_repo = Mock()
        mock_repo.git.rm.side_effect = GitCommandError(
            "git rm",
            1,
            b"error: the following file has local modifications:\n  file.py",
        )

        result = git_rm(mock_repo, file="file.py")

        assert "❌" in result
        assert "uncommitted changes" in result

    def test_git_rm_returns_uncommitted_changes_when_staged(self):
        """Should return specific message when file has staged changes."""
        mock_repo = Mock()
        mock_repo.git.rm.side_effect = GitCommandError(
            "git rm",
            1,
            b"error: the following file has changes staged in the index:\n  file.py",
        )

        result = git_rm(mock_repo, file="file.py")

        assert "❌" in result
        assert "uncommitted changes" in result

    def test_git_rm_handles_git_command_error_string_stderr(self):
        """Should handle GitCommandError with string stderr."""
        mock_repo = Mock()
        error = GitCommandError("git rm", 128, b"", b"fatal: not a git repo")
        error.stderr = "fatal: not a git repo"
        mock_repo.git.rm.side_effect = error

        result = git_rm(mock_repo, file="file.py")

        assert "❌" in result
        assert "git rm failed" in result

    def test_git_rm_handles_general_exception(self):
        """Should handle unexpected exceptions gracefully."""
        mock_repo = Mock()
        mock_repo.git.rm.side_effect = Exception("Unexpected failure")

        result = git_rm(mock_repo, file="file.py")

        assert "❌" in result
        assert "Error during git rm" in result
        assert "Unexpected failure" in result
