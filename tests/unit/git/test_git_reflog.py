"""
Unit tests for git_reflog operation.

Verifies structured output (new_sha, label, action, message, old_sha),
max_count limiting, all=True flag, error handling, and empty-reflog edge case.
"""

from unittest.mock import Mock

import pytest

from mcp_server_git.git.operations import git_reflog
from mcp_server_git.utils.git_import import GitCommandError

# NUL separator used by the format string
SEP = "\x00"


def _make_raw(*entries: tuple) -> str:
    """Build fake reflog output for (new_sha, label, old_sha, subject) tuples."""
    lines = []
    for new_sha, label, old_sha, subject in entries:
        lines.append(f"{new_sha}{SEP}{label}{SEP}{old_sha}{SEP}{subject}")
    return "\n".join(lines)


class TestGitReflogBasic:
    """Test basic git_reflog functionality."""

    def test_git_reflog_returns_list_of_dicts(self):
        """Should return a list of dicts with required keys."""
        mock_repo = Mock()
        new_sha = "a" * 40
        mock_repo.git.reflog.return_value = _make_raw(
            (new_sha, "HEAD@{0}", "0" * 40, "commit: initial commit")
        )

        result = git_reflog(mock_repo)

        assert isinstance(result, list)
        assert len(result) == 1
        entry = result[0]
        assert entry["new_sha"] == new_sha
        assert entry["label"] == "HEAD@{0}"
        assert entry["action"] == "commit"
        assert entry["message"] == "commit: initial commit"

    def test_git_reflog_old_sha_omitted_when_zero(self):
        """Should omit old_sha when it is the all-zeros sentinel."""
        mock_repo = Mock()
        mock_repo.git.reflog.return_value = _make_raw(
            ("a" * 40, "HEAD@{0}", "0" * 40, "commit: initial")
        )

        result = git_reflog(mock_repo)

        assert "old_sha" not in result[0]

    def test_git_reflog_old_sha_present_when_non_zero(self):
        """Should include old_sha when previous position is known."""
        mock_repo = Mock()
        new_sha = "b" * 40
        old_sha = "a" * 40
        mock_repo.git.reflog.return_value = _make_raw(
            (new_sha, "HEAD@{0}", old_sha, "checkout: moving from main to feature")
        )

        result = git_reflog(mock_repo)

        assert result[0]["old_sha"] == old_sha

    def test_git_reflog_empty_returns_empty_list(self):
        """Should return empty list when reflog is empty."""
        mock_repo = Mock()
        mock_repo.git.reflog.return_value = ""

        result = git_reflog(mock_repo)

        assert result == []

    def test_git_reflog_default_ref_is_head(self):
        """Should pass HEAD as positional arg when all=False and ref='HEAD'."""
        mock_repo = Mock()
        mock_repo.git.reflog.return_value = ""

        git_reflog(mock_repo)

        args = mock_repo.git.reflog.call_args[0]
        assert "HEAD" in args

    def test_git_reflog_custom_ref_passed(self):
        """Should pass custom ref when specified."""
        mock_repo = Mock()
        mock_repo.git.reflog.return_value = ""

        git_reflog(mock_repo, ref="refs/heads/main")

        args = mock_repo.git.reflog.call_args[0]
        assert "refs/heads/main" in args


class TestGitReflogActionParsing:
    """Test action derivation from reflog subjects."""

    @pytest.mark.parametrize(
        "subject, expected_action",
        [
            ("checkout: moving from main to feature", "checkout"),
            ("commit: add new feature", "commit"),
            ("reset: moving to HEAD~1", "reset"),
            ("merge origin/main: Fast-forward", "merge"),
            ("rebase (start): checkout main", "rebase (start)"),
            ("pull: Fast-forward", "pull"),
            ("commit (amend): fixup", "commit (amend)"),
        ],
    )
    def test_git_reflog_action_parsing_returns_correct_action(
        self, subject: str, expected_action: str
    ):
        """Should parse action from reflog subject correctly."""
        mock_repo = Mock()
        mock_repo.git.reflog.return_value = _make_raw(
            ("a" * 40, "HEAD@{0}", "b" * 40, subject)
        )

        result = git_reflog(mock_repo)

        assert result[0]["action"] == expected_action

    def test_git_reflog_action_unknown_when_subject_empty(self):
        """Should set action='unknown' when subject is empty."""
        mock_repo = Mock()
        mock_repo.git.reflog.return_value = _make_raw(
            ("a" * 40, "HEAD@{0}", "b" * 40, "")
        )

        result = git_reflog(mock_repo)

        assert result[0]["action"] == "unknown"


class TestGitReflogMaxCount:
    """Test max_count limiting."""

    def test_git_reflog_max_count_passes_n_flag(self):
        """Should pass -n <max_count> when max_count is set."""
        mock_repo = Mock()
        mock_repo.git.reflog.return_value = ""

        git_reflog(mock_repo, max_count=3)

        args = mock_repo.git.reflog.call_args[0]
        assert "-n" in args
        assert "3" in args

    def test_git_reflog_no_n_flag_when_max_count_none(self):
        """Should not pass -n flag when max_count is None."""
        mock_repo = Mock()
        mock_repo.git.reflog.return_value = ""

        git_reflog(mock_repo, max_count=None)

        args = mock_repo.git.reflog.call_args[0]
        assert "-n" not in args

    def test_git_reflog_no_n_flag_when_max_count_zero(self):
        """Should not pass -n flag when max_count is 0."""
        mock_repo = Mock()
        mock_repo.git.reflog.return_value = ""

        git_reflog(mock_repo, max_count=0)

        args = mock_repo.git.reflog.call_args[0]
        assert "-n" not in args


class TestGitReflogAllFlag:
    """Test --all flag behaviour."""

    def test_git_reflog_all_true_passes_all_flag(self):
        """Should pass --all and omit ref when all=True."""
        mock_repo = Mock()
        mock_repo.git.reflog.return_value = ""

        git_reflog(mock_repo, all=True)

        args = mock_repo.git.reflog.call_args[0]
        assert "--all" in args
        assert "HEAD" not in args

    def test_git_reflog_all_false_does_not_pass_all_flag(self):
        """Should not pass --all when all=False."""
        mock_repo = Mock()
        mock_repo.git.reflog.return_value = ""

        git_reflog(mock_repo, all=False)

        args = mock_repo.git.reflog.call_args[0]
        assert "--all" not in args


class TestGitReflogMultipleEntries:
    """Test parsing of multiple reflog entries."""

    def test_git_reflog_multiple_entries_parsed_correctly(self):
        """Should parse multiple entries into correctly ordered list."""
        mock_repo = Mock()
        sha0, sha1, sha2 = "c" * 40, "b" * 40, "a" * 40
        mock_repo.git.reflog.return_value = _make_raw(
            (sha0, "HEAD@{0}", sha1, "checkout: moving from main to feature"),
            (sha1, "HEAD@{1}", sha2, "commit: add tests"),
            (sha2, "HEAD@{2}", "0" * 40, "commit: initial"),
        )

        result = git_reflog(mock_repo)

        assert len(result) == 3
        assert result[0]["new_sha"] == sha0
        assert result[0]["action"] == "checkout"
        assert result[1]["new_sha"] == sha1
        assert result[1]["action"] == "commit"
        assert result[2]["new_sha"] == sha2
        assert "old_sha" not in result[2]


class TestGitReflogErrorHandling:
    """Test error handling in git_reflog."""

    def test_git_reflog_returns_error_dict_on_git_command_error(self):
        """Should return list with error dict on GitCommandError."""
        mock_repo = Mock()
        mock_repo.git.reflog.side_effect = GitCommandError("git reflog", 128, "error")

        result = git_reflog(mock_repo)

        assert len(result) == 1
        assert "error" in result[0]
        assert "Reflog failed" in result[0]["error"]

    def test_git_reflog_returns_error_dict_on_general_exception(self):
        """Should return list with error dict on unexpected exception."""
        mock_repo = Mock()
        mock_repo.git.reflog.side_effect = RuntimeError("unexpected")

        result = git_reflog(mock_repo)

        assert len(result) == 1
        assert "error" in result[0]
        assert "Reflog error" in result[0]["error"]
