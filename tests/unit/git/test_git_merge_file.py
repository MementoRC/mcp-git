"""Tests for git_merge_file operation (issue #210, Gap 2)."""

from unittest.mock import MagicMock

import pytest
from git.exc import GitCommandError

from mcp_server_git.git.merge_ops import git_merge_file


@pytest.fixture
def mock_repo():
    """Provide a mock Repo object."""
    repo = MagicMock()
    repo.git = MagicMock()
    repo.git.show.return_value = "some file content\n"
    repo.git.merge_file.return_value = "merged content clean\n"
    return repo


class TestGitMergeFileCleanMerge:
    """Tests for clean merge (no conflicts) scenarios."""

    def test_git_merge_file_returns_success_message_when_no_conflicts(self, mock_repo):
        result = git_merge_file(mock_repo, "src/app.py", "base", "ours", "theirs")

        assert "✅ Clean merge (0 conflicts)" in result
        assert "merged content clean" in result
        assert "📄 Merged content (ours / base / theirs)" in result

    def test_git_merge_file_calls_merge_file_with_labels_and_three_paths(
        self, mock_repo
    ):
        git_merge_file(mock_repo, "src/app.py", "base", "ours", "theirs")

        args = mock_repo.git.merge_file.call_args.args
        assert args[0] == "-L"
        assert args[1] == "ours"
        assert args[2] == "-L"
        assert args[3] == "base"
        assert args[4] == "-L"
        assert args[5] == "theirs"
        assert args[6] == "-p"
        assert args[7].endswith("ours")
        assert args[8].endswith("base")
        assert args[9].endswith("theirs")

    def test_git_merge_file_passes_custom_labels_through_to_dash_l_flags(
        self, mock_repo
    ):
        git_merge_file(
            mock_repo,
            "src/app.py",
            "base",
            "ours",
            "theirs",
            labels=["mine", "common", "yours"],
        )

        args = mock_repo.git.merge_file.call_args.args
        assert args[0] == "-L"
        assert args[1] == "mine"
        assert args[2] == "-L"
        assert args[3] == "common"
        assert args[4] == "-L"
        assert args[5] == "yours"


class TestGitMergeFileConflicts:
    """Tests for conflicting merge scenarios."""

    def test_git_merge_file_returns_warning_with_markers_when_conflicts(
        self, mock_repo
    ):
        mock_repo.git.merge_file.side_effect = GitCommandError(
            "git merge-file", 2, b"", b"<merged with markers>"
        )

        result = git_merge_file(mock_repo, "src/app.py", "base", "ours", "theirs")

        assert "⚠️ 2 conflict region(s)" in result
        assert "<merged with markers>" in result

    def test_git_merge_file_returns_merge_file_failed_on_out_of_range_exit_status(
        self, mock_repo
    ):
        mock_repo.git.merge_file.side_effect = GitCommandError(
            "git merge-file", 255, b"fatal error", b""
        )

        result = git_merge_file(mock_repo, "src/app.py", "base", "ours", "theirs")

        assert "❌" in result
        assert "Merge-file failed" in result


class TestGitMergeFileMissingSides:
    """Tests for missing-file-on-one-or-more-sides scenarios."""

    def test_git_merge_file_marks_absent_side_when_missing_on_one_side(self, mock_repo):
        def show_side_effect(spec):
            if spec.startswith("theirs:"):
                raise GitCommandError("git show", 128, b"", b"fatal: path not found")
            return "content\n"

        mock_repo.git.show.side_effect = show_side_effect

        result = git_merge_file(mock_repo, "src/app.py", "base", "ours", "theirs")

        assert "theirs: theirs  (absent)" in result
        mock_repo.git.merge_file.assert_called_once()

    def test_git_merge_file_returns_error_when_missing_on_all_sides(self, mock_repo):
        mock_repo.git.show.side_effect = GitCommandError(
            "git show", 128, b"", b"fatal: path not found"
        )

        result = git_merge_file(mock_repo, "src/app.py", "base", "ours", "theirs")

        assert "does not exist in any of" in result
        mock_repo.git.merge_file.assert_not_called()


class TestGitMergeFileOutputPath:
    """Tests for the output_path (write-to-disk) mode."""

    def test_git_merge_file_writes_full_result_to_disk_when_output_path_given(
        self, mock_repo, tmp_path
    ):
        mock_repo.git.merge_file.return_value = "UNIQUE_MERGED_BODY_MARKER\n"
        output_path = str(tmp_path / "merged.txt")

        result = git_merge_file(
            mock_repo, "src/app.py", "base", "ours", "theirs", output_path=output_path
        )

        assert (tmp_path / "merged.txt").read_text() == "UNIQUE_MERGED_BODY_MARKER\n"
        assert "💾 Full merge result written to" in result
        assert "UNIQUE_MERGED_BODY_MARKER" not in result

    def test_git_merge_file_rejects_relative_output_path(self, mock_repo):
        result = git_merge_file(
            mock_repo,
            "src/app.py",
            "base",
            "ours",
            "theirs",
            output_path="relative/path.txt",
        )

        assert "output_path must be an absolute path" in result


class TestGitMergeFileValidation:
    """Tests for input validation (dangerous characters, label count)."""

    def test_git_merge_file_rejects_dangerous_chars_in_ours_rev(self, mock_repo):
        result = git_merge_file(mock_repo, "src/app.py", "base", "ours;evil", "theirs")

        assert "❌" in result
        assert "ours_rev" in result
        mock_repo.git.merge_file.assert_not_called()

    def test_git_merge_file_rejects_dangerous_chars_in_path(self, mock_repo):
        result = git_merge_file(mock_repo, "src/app.py;evil", "base", "ours", "theirs")

        assert "❌" in result
        assert "path" in result
        mock_repo.git.merge_file.assert_not_called()

    def test_git_merge_file_rejects_labels_of_wrong_length(self, mock_repo):
        result = git_merge_file(
            mock_repo, "src/app.py", "base", "ours", "theirs", labels=["only-one"]
        )

        assert "labels must be exactly three entries" in result
        mock_repo.git.merge_file.assert_not_called()
