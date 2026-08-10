"""
Unit tests for git_worktree_list and git_worktree_remove operations.

These tests verify the worktree management functions added to operations_extended.py.
"""

from unittest.mock import Mock

import pytest

from mcp_server_git.git.operations_extended import (
    git_worktree_add,
    git_worktree_list,
    git_worktree_remove,
)
from mcp_server_git.utils.git_import import GitCommandError


PORCELAIN_TWO_WORKTREES = """\
worktree /home/user/project
HEAD abc12345def67890abc12345def67890abc12345
branch refs/heads/main

worktree /home/user/project-feature
HEAD 11223344556677889900aabbccddeeff00112233
branch refs/heads/feature/my-work
"""

PORCELAIN_ONE_WORKTREE = """\
worktree /home/user/project
HEAD abc12345def67890abc12345def67890abc12345
branch refs/heads/main
"""

PORCELAIN_DETACHED = """\
worktree /home/user/project
HEAD abc12345def67890abc12345def67890abc12345
detached
"""


class TestGitWorktreeListSuccess:
    """Test successful git_worktree_list scenarios."""

    def test_git_worktree_list_parses_two_worktrees_correctly(self):
        """Should parse porcelain output with two worktrees and return formatted list."""
        mock_repo = Mock()
        mock_repo.git.worktree.return_value = PORCELAIN_TWO_WORKTREES

        result = git_worktree_list(mock_repo)

        assert "Worktrees (2):" in result
        assert "/home/user/project" in result
        assert "main" in result
        assert "/home/user/project-feature" in result
        assert "feature/my-work" in result
        mock_repo.git.worktree.assert_called_once_with("list", "--porcelain")

    def test_git_worktree_list_parses_single_worktree(self):
        """Should parse a single worktree and return correct count."""
        mock_repo = Mock()
        mock_repo.git.worktree.return_value = PORCELAIN_ONE_WORKTREE

        result = git_worktree_list(mock_repo)

        assert "Worktrees (1):" in result
        assert "/home/user/project" in result
        assert "main" in result

    def test_git_worktree_list_returns_no_worktrees_message_when_empty(self):
        """Should return descriptive message when output is empty."""
        mock_repo = Mock()
        mock_repo.git.worktree.return_value = ""

        result = git_worktree_list(mock_repo)

        assert "No worktrees found" in result

    def test_git_worktree_list_handles_detached_head_worktree(self):
        """Should show 'detached' as branch for detached HEAD worktrees."""
        mock_repo = Mock()
        mock_repo.git.worktree.return_value = PORCELAIN_DETACHED

        result = git_worktree_list(mock_repo)

        assert "Worktrees (1):" in result
        assert "detached" in result

    def test_git_worktree_list_strips_refs_heads_prefix_from_branch(self):
        """Should strip refs/heads/ prefix from branch names."""
        mock_repo = Mock()
        mock_repo.git.worktree.return_value = PORCELAIN_TWO_WORKTREES

        result = git_worktree_list(mock_repo)

        assert "refs/heads/" not in result

    def test_git_worktree_list_includes_short_sha_in_output(self):
        """Should include short (8-char) SHA in output."""
        mock_repo = Mock()
        mock_repo.git.worktree.return_value = PORCELAIN_ONE_WORKTREE

        result = git_worktree_list(mock_repo)

        # Short SHA is first 8 chars: "abc12345"
        assert "abc12345" in result


class TestGitWorktreeListErrorHandling:
    """Test error handling for git_worktree_list."""

    def test_git_worktree_list_handles_git_command_error_bytes_stderr(self):
        """Should handle GitCommandError with bytes stderr gracefully."""
        mock_repo = Mock()
        mock_repo.git.worktree.side_effect = GitCommandError(
            "git worktree", 128, b"", b"fatal: not a git repository"
        )

        result = git_worktree_list(mock_repo)

        assert "❌" in result
        assert "Failed to list worktrees" in result

    def test_git_worktree_list_handles_git_command_error_string_stderr(self):
        """Should handle GitCommandError with string stderr gracefully."""
        mock_repo = Mock()
        error = GitCommandError("git worktree", 128, b"", b"fatal: error")
        error.stderr = "fatal: error"
        mock_repo.git.worktree.side_effect = error

        result = git_worktree_list(mock_repo)

        assert "❌" in result
        assert "Failed to list worktrees" in result

    def test_git_worktree_list_handles_general_exception(self):
        """Should handle unexpected exceptions gracefully."""
        mock_repo = Mock()
        mock_repo.git.worktree.side_effect = Exception("Unexpected failure")

        result = git_worktree_list(mock_repo)

        assert "❌" in result
        assert "Error listing worktrees" in result
        assert "Unexpected failure" in result


class TestGitWorktreeRemoveSuccess:
    """Test successful git_worktree_remove scenarios."""

    def test_git_worktree_remove_normal_removal_returns_success(self):
        """Should call worktree remove and return success message."""
        mock_repo = Mock()

        result = git_worktree_remove(mock_repo, worktree_path="/home/user/project-feature")

        assert "✅" in result
        assert "/home/user/project-feature" in result
        mock_repo.git.worktree.assert_called_once_with("remove", "/home/user/project-feature")

    def test_git_worktree_remove_force_removal_passes_force_flag(self):
        """Should pass --force flag when force=True."""
        mock_repo = Mock()

        result = git_worktree_remove(
            mock_repo, worktree_path="/home/user/project-feature", force=True
        )

        assert "✅" in result
        assert "/home/user/project-feature" in result
        mock_repo.git.worktree.assert_called_once_with(
            "remove", "--force", "/home/user/project-feature"
        )

    def test_git_worktree_remove_without_force_does_not_pass_force_flag(self):
        """Should not pass --force flag when force=False (default)."""
        mock_repo = Mock()

        git_worktree_remove(mock_repo, worktree_path="/tmp/wt")

        call_args = mock_repo.git.worktree.call_args[0]
        assert "--force" not in call_args


class TestGitWorktreeRemoveInputValidation:
    """Test input validation for git_worktree_remove."""

    @pytest.mark.parametrize("dangerous_char", [";", "|", "&", "`", "$"])
    def test_git_worktree_remove_rejects_dangerous_chars_in_path(self, dangerous_char):
        """Should reject dangerous characters in worktree_path."""
        mock_repo = Mock()
        malicious_path = f"/tmp/wt{dangerous_char}rm -rf /"

        result = git_worktree_remove(mock_repo, worktree_path=malicious_path)

        assert "❌" in result
        assert "Invalid characters in worktree path" in result
        mock_repo.git.worktree.assert_not_called()

    def test_git_worktree_remove_accepts_valid_absolute_path(self):
        """Should accept valid absolute paths with slashes and hyphens."""
        mock_repo = Mock()

        result = git_worktree_remove(mock_repo, worktree_path="/home/user/my-worktree_v2")

        assert "✅" in result
        mock_repo.git.worktree.assert_called_once()


class TestGitWorktreeRemoveErrorHandling:
    """Test error handling for git_worktree_remove."""

    def test_git_worktree_remove_handles_git_command_error_bytes_stderr(self):
        """Should handle GitCommandError with bytes stderr gracefully."""
        mock_repo = Mock()
        mock_repo.git.worktree.side_effect = GitCommandError(
            "git worktree", 128, b"", b"fatal: '/tmp/wt' is not a working tree"
        )

        result = git_worktree_remove(mock_repo, worktree_path="/tmp/wt")

        assert "❌" in result
        assert "Failed to remove worktree" in result

    def test_git_worktree_remove_handles_git_command_error_string_stderr(self):
        """Should handle GitCommandError with string stderr gracefully."""
        mock_repo = Mock()
        error = GitCommandError("git worktree", 128, b"", b"fatal: error")
        error.stderr = "fatal: error"
        mock_repo.git.worktree.side_effect = error

        result = git_worktree_remove(mock_repo, worktree_path="/tmp/wt")

        assert "❌" in result
        assert "Failed to remove worktree" in result

    def test_git_worktree_remove_handles_general_exception(self):
        """Should handle unexpected exceptions gracefully."""
        mock_repo = Mock()
        mock_repo.git.worktree.side_effect = Exception("Unexpected failure")

        result = git_worktree_remove(mock_repo, worktree_path="/tmp/wt")

        assert "❌" in result
        assert "Error removing worktree" in result
        assert "Unexpected failure" in result


class TestGitWorktreeAdd:
    """Test git_worktree_add: all behavior paths from the issue #167 matrix."""

    def test_worktree_add_detached_head(self):
        """No branch, no new_branch: detached HEAD at current HEAD."""
        mock_repo = Mock()

        result = git_worktree_add(mock_repo, worktree_path="/tmp/wt-detached")

        assert "✅" in result
        assert "/tmp/wt-detached" in result
        assert "detached HEAD" in result
        mock_repo.git.worktree.assert_called_once_with("add", "/tmp/wt-detached")

    def test_worktree_add_existing_branch(self):
        """branch='main', no new_branch: checks out existing branch."""
        mock_repo = Mock()

        result = git_worktree_add(mock_repo, worktree_path="/tmp/wt-main", branch="main")

        assert "✅" in result
        assert "branch main" in result
        mock_repo.git.worktree.assert_called_once_with("add", "/tmp/wt-main", "main")

    def test_worktree_add_new_branch(self):
        """new_branch='feature', no branch: creates branch from HEAD using -b."""
        mock_repo = Mock()

        result = git_worktree_add(mock_repo, worktree_path="/tmp/wt-feature", new_branch="feature")

        assert "✅" in result
        assert "new branch feature" in result
        call_args = mock_repo.git.worktree.call_args[0]
        assert "-b" in call_args
        assert "-B" not in call_args
        assert "feature" in call_args
        assert "/tmp/wt-feature" in call_args

    def test_worktree_add_force_new_branch_uses_B(self):
        """new_branch + force=True: uses -B (force-create) and --force."""
        mock_repo = Mock()

        result = git_worktree_add(
            mock_repo, worktree_path="/tmp/wt-force", new_branch="feature", force=True
        )

        assert "✅" in result
        call_args = mock_repo.git.worktree.call_args[0]
        assert "--force" in call_args
        assert "-B" in call_args
        assert "-b" not in call_args

    def test_worktree_add_new_branch_with_start_point(self):
        """new_branch + branch: creates new_branch from given start-point."""
        mock_repo = Mock()

        result = git_worktree_add(
            mock_repo, worktree_path="/tmp/wt-nb", new_branch="feat/x", branch="main"
        )

        assert "✅" in result
        call_args = mock_repo.git.worktree.call_args[0]
        assert "-b" in call_args
        assert "feat/x" in call_args
        assert "/tmp/wt-nb" in call_args
        assert "main" in call_args

    def test_worktree_add_creates_new_branch_from_commit_ish_when_both_given(self):
        """new_branch + commit_ish: creates new_branch from the given commit-ish."""
        mock_repo = Mock()

        result = git_worktree_add(
            mock_repo,
            worktree_path="/tmp/wt",
            new_branch="feature",
            commit_ish="development",
        )

        assert "✅" in result
        assert "from development" in result
        call_args = mock_repo.git.worktree.call_args[0]
        assert call_args == ("add", "-b", "feature", "/tmp/wt", "development")

    def test_worktree_add_uses_branch_as_start_point_when_new_branch_set(self):
        """Legacy form: new_branch + branch still works as the start point."""
        mock_repo = Mock()

        result = git_worktree_add(
            mock_repo,
            worktree_path="/tmp/wt",
            new_branch="feature",
            branch="development",
        )

        assert "✅" in result
        call_args = mock_repo.git.worktree.call_args[0]
        assert call_args == ("add", "-b", "feature", "/tmp/wt", "development")

    def test_worktree_add_prefers_commit_ish_over_branch_when_new_branch_set(self):
        """When both branch and commit_ish are set, commit_ish wins."""
        mock_repo = Mock()

        result = git_worktree_add(
            mock_repo,
            worktree_path="/tmp/wt",
            new_branch="feature",
            branch="development",
            commit_ish="v1.2.3",
        )

        assert "✅" in result
        call_args = mock_repo.git.worktree.call_args[0]
        assert call_args[-1] == "v1.2.3"
        assert "development" not in call_args

    def test_worktree_add_creates_detached_worktree_when_only_commit_ish_given(self):
        """commit_ish only: detached HEAD at that commit-ish."""
        mock_repo = Mock()

        result = git_worktree_add(mock_repo, worktree_path="/tmp/wt", commit_ish="abc1234")

        assert "✅" in result
        assert "detached HEAD at abc1234" in result
        call_args = mock_repo.git.worktree.call_args[0]
        assert call_args == ("add", "/tmp/wt", "abc1234")

    def test_worktree_add_returns_error_when_commit_ish_and_branch_without_new_branch(self):
        """commit_ish + branch without new_branch is rejected as ambiguous."""
        mock_repo = Mock()

        result = git_worktree_add(
            mock_repo,
            worktree_path="/tmp/wt",
            branch="development",
            commit_ish="abc1234",
        )

        assert "❌" in result
        assert "mutually exclusive" in result
        mock_repo.git.worktree.assert_not_called()

    def test_worktree_add_returns_error_when_commit_ish_has_dangerous_chars(self):
        """Should reject dangerous characters in commit_ish."""
        mock_repo = Mock()

        result = git_worktree_add(mock_repo, worktree_path="/tmp/wt", commit_ish="abc; rm -rf /")

        assert "❌" in result
        assert "Invalid characters in commit_ish" in result
        mock_repo.git.worktree.assert_not_called()

    def test_worktree_add_rejects_dangerous_chars_in_worktree_path(self):
        """Should reject dangerous characters in worktree_path."""
        mock_repo = Mock()

        result = git_worktree_add(mock_repo, worktree_path="/tmp/wt;rm -rf /")

        assert "❌" in result
        assert "Invalid characters in worktree path" in result
        mock_repo.git.worktree.assert_not_called()

    def test_worktree_add_handles_git_command_error(self):
        """Should handle GitCommandError gracefully."""
        mock_repo = Mock()
        mock_repo.git.worktree.side_effect = GitCommandError(
            "git worktree", 128, b"", b"fatal: already checked out"
        )

        result = git_worktree_add(mock_repo, worktree_path="/tmp/wt")

        assert "❌" in result
        assert "Failed to add worktree" in result

    def test_worktree_add_handles_general_exception(self):
        """Should handle unexpected exceptions gracefully."""
        mock_repo = Mock()
        mock_repo.git.worktree.side_effect = Exception("Disk full")

        result = git_worktree_add(mock_repo, worktree_path="/tmp/wt")

        assert "❌" in result
        assert "Error adding worktree" in result
        assert "Disk full" in result
