"""Tests for git_merge_tree operation (dry-run conflict detection)."""

import pytest
from unittest.mock import MagicMock

from git.exc import GitCommandError

from mcp_server_git.git.operations_extended import git_merge_tree


@pytest.fixture
def mock_repo():
    """Provide a mock Repo object."""
    repo = MagicMock()
    repo.git = MagicMock()
    return repo


class TestGitMergeTreeCleanMerge:
    """Tests for clean merge (exit 0) scenarios."""

    def test_git_merge_tree_returns_success_message_when_no_conflicts(self, mock_repo):
        tree_hash = "abc1234def5678901234567890abcdef12345678"
        mock_repo.git.merge_tree.return_value = tree_hash

        result = git_merge_tree(mock_repo, "main", "feature")

        assert "✅" in result
        assert "main" in result
        assert "feature" in result
        assert "no conflicts" in result

    def test_git_merge_tree_includes_tree_hash_in_output_when_clean(self, mock_repo):
        tree_hash = "abc1234def5678"
        mock_repo.git.merge_tree.return_value = tree_hash

        result = git_merge_tree(mock_repo, "main", "feature")

        assert tree_hash in result

    def test_git_merge_tree_calls_merge_tree_with_write_tree_flag(self, mock_repo):
        mock_repo.git.merge_tree.return_value = "abc1234"

        git_merge_tree(mock_repo, "main", "feature")

        mock_repo.git.merge_tree.assert_called_once_with("--write-tree", "main", "feature")


class TestGitMergeTreeConflicts:
    """Tests for conflict detection (exit 1) scenarios."""

    def test_git_merge_tree_returns_warning_when_conflicts_detected(self, mock_repo):
        # GitCommandError(command, status, stderr, stdout) — stdout is 4th arg
        mock_repo.git.merge_tree.side_effect = GitCommandError(
            "git merge-tree", 1, b"", b"CONFLICT (content): Merge conflict in file.py"
        )

        result = git_merge_tree(mock_repo, "main", "feature")

        assert "⚠️" in result
        assert "Conflicts detected" in result
        assert "main" in result
        assert "feature" in result

    def test_git_merge_tree_lists_conflict_files_when_conflicts_in_stdout(self, mock_repo):
        # GitCommandError(command, status, stderr, stdout) — stdout is 4th arg
        mock_repo.git.merge_tree.side_effect = GitCommandError(
            "git merge-tree", 1, b"", b"CONFLICT (content): Merge conflict in src/app.py"
        )

        result = git_merge_tree(mock_repo, "main", "feature")

        assert "src/app.py" in result

    def test_git_merge_tree_lists_multiple_conflict_files_when_multiple_conflicts(self, mock_repo):
        stdout = (
            b"CONFLICT (content): Merge conflict in src/app.py\n"
            b"CONFLICT (modify/delete): foo.txt deleted in feature\n"
            b"Auto-merging bar.txt"
        )
        # GitCommandError(command, status, stderr, stdout) — stdout is 4th arg
        mock_repo.git.merge_tree.side_effect = GitCommandError(
            "git merge-tree", 1, b"", stdout
        )

        result = git_merge_tree(mock_repo, "main", "feature")

        assert "src/app.py" in result
        assert "foo.txt" in result
        # Non-conflict line should not appear as a conflict item
        assert result.count("  -") == 2

    def test_git_merge_tree_returns_warning_with_stdout_when_exit1_no_conflict_lines(self, mock_repo):
        # GitCommandError(command, status, stderr, stdout) — stdout is 4th arg
        mock_repo.git.merge_tree.side_effect = GitCommandError(
            "git merge-tree", 1, b"", b"some other output without conflict markers"
        )

        result = git_merge_tree(mock_repo, "main", "feature")

        assert "⚠️" in result
        assert "some other output" in result


class TestGitMergeTreeValidation:
    """Tests for input validation (dangerous characters)."""

    @pytest.mark.parametrize("char", [";", "|", "&", "`", "$"])
    def test_git_merge_tree_rejects_dangerous_chars_in_branch1(self, mock_repo, char):
        result = git_merge_tree(mock_repo, f"main{char}evil", "feature")

        assert "❌" in result
        assert "branch1" in result
        mock_repo.git.merge_tree.assert_not_called()

    @pytest.mark.parametrize("char", [";", "|", "&", "`", "$"])
    def test_git_merge_tree_rejects_dangerous_chars_in_branch2(self, mock_repo, char):
        result = git_merge_tree(mock_repo, "main", f"feature{char}evil")

        assert "❌" in result
        assert "branch2" in result
        mock_repo.git.merge_tree.assert_not_called()


class TestGitMergeTreeErrors:
    """Tests for error handling scenarios."""

    def test_git_merge_tree_returns_error_when_exit_code_128(self, mock_repo):
        stderr = b"fatal: Not a valid object name: 'nonexistent'"
        mock_repo.git.merge_tree.side_effect = GitCommandError(
            "git merge-tree", 128, b"", stderr
        )

        result = git_merge_tree(mock_repo, "main", "nonexistent")

        assert "❌" in result
        assert "Merge-tree failed" in result

    def test_git_merge_tree_returns_error_on_general_exception(self, mock_repo):
        mock_repo.git.merge_tree.side_effect = RuntimeError("unexpected git error")

        result = git_merge_tree(mock_repo, "main", "feature")

        assert "❌" in result
        assert "Error during merge-tree" in result
        assert "unexpected git error" in result
