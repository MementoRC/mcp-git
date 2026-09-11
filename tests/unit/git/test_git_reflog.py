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
    """Build fake reflog output for (new_sha, label, subject) tuples."""
    lines = []
    for new_sha, label, subject in entries:
        lines.append(f"{new_sha}{SEP}{label}{SEP}{subject}")
    return "\n".join(lines)


class TestGitReflogBasic:
    """Test basic git_reflog functionality."""

    def test_git_reflog_returns_list_of_dicts(self):
        """Should return a list of dicts with required keys."""
        mock_repo = Mock()
        new_sha = "a" * 40
        mock_repo.git.reflog.return_value = _make_raw(
            (new_sha, "HEAD@{0}", "commit: initial commit")
        )

        result = git_reflog(mock_repo)

        assert isinstance(result, list)
        assert len(result) == 1
        entry = result[0]
        assert entry["new_sha"] == new_sha
        assert entry["label"] == "HEAD@{0}"
        assert entry["action"] == "commit"
        assert entry["message"] == "commit: initial commit"

    def test_git_reflog_old_sha_absent_for_single_entry(self):
        """Should omit old_sha when there is only one (oldest) entry."""
        mock_repo = Mock()
        mock_repo.git.reflog.return_value = _make_raw(
            ("a" * 40, "HEAD@{0}", "commit: initial")
        )

        result = git_reflog(mock_repo)

        assert "old_sha" not in result[0]

    def test_git_reflog_old_sha_derived_from_next_entry(self):
        """old_sha for entry[i] must equal entry[i+1].new_sha (newest-first order)."""
        mock_repo = Mock()
        sha0 = "b" * 40  # newest entry's new_sha
        sha1 = "a" * 40  # older entry's new_sha == sha0's old_sha
        mock_repo.git.reflog.return_value = _make_raw(
            (sha0, "HEAD@{0}", "checkout: moving from main to feature"),
            (sha1, "HEAD@{1}", "commit: initial"),
        )

        result = git_reflog(mock_repo)

        assert result[0]["old_sha"] == sha1
        assert "old_sha" not in result[1]

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
            # Multi-word parenthetical qualifier must be captured in full
            ("commit (initial import): first checkin", "commit (initial import)"),
        ],
    )
    def test_git_reflog_action_parsing_returns_correct_action(
        self, subject: str, expected_action: str
    ):
        """Should parse action from reflog subject correctly."""
        mock_repo = Mock()
        mock_repo.git.reflog.return_value = _make_raw(("a" * 40, "HEAD@{0}", subject))

        result = git_reflog(mock_repo)

        assert result[0]["action"] == expected_action

    def test_git_reflog_action_unknown_when_subject_empty(self):
        """Should set action='unknown' when subject is empty."""
        mock_repo = Mock()
        mock_repo.git.reflog.return_value = _make_raw(("a" * 40, "HEAD@{0}", ""))

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

    def test_git_reflog_all_true_omits_old_sha_from_every_entry(self):
        """Under all=True, no entry should contain old_sha (interleaved refs make
        adjacent-entry derivation unreliable); new_sha/label/action must still be present."""
        mock_repo = Mock()
        sha0 = "c" * 40  # HEAD@{0} — could be from refs/heads/main
        sha1 = "b" * 40  # HEAD@{1} — could be from refs/heads/feature (different ref)
        sha2 = "a" * 40  # HEAD@{2}
        mock_repo.git.reflog.return_value = _make_raw(
            (sha0, "refs/heads/main@{0}", "commit: update main"),
            (sha1, "refs/heads/feature@{0}", "commit: add feature"),
            (sha2, "refs/heads/main@{1}", "commit: initial"),
        )

        result = git_reflog(mock_repo, all=True)

        assert isinstance(result, list)
        assert len(result) == 3
        for entry in result:
            assert "old_sha" not in entry, (
                f"old_sha must be absent under all=True, got: {entry}"
            )
            assert "new_sha" in entry
            assert "label" in entry
            assert "action" in entry


class TestGitReflogMultipleEntries:
    """Test parsing of multiple reflog entries."""

    def test_git_reflog_multiple_entries_parsed_correctly(self):
        """Should parse multiple entries into correctly ordered list.

        old_sha for each entry is derived from the next entry's new_sha;
        the oldest entry has no old_sha.
        """
        mock_repo = Mock()
        sha0, sha1, sha2 = "c" * 40, "b" * 40, "a" * 40
        mock_repo.git.reflog.return_value = _make_raw(
            (sha0, "HEAD@{0}", "checkout: moving from main to feature"),
            (sha1, "HEAD@{1}", "commit: add tests"),
            (sha2, "HEAD@{2}", "commit: initial"),
        )

        result = git_reflog(mock_repo)

        assert len(result) == 3
        assert result[0]["new_sha"] == sha0
        assert result[0]["action"] == "checkout"
        assert result[0]["old_sha"] == sha1
        assert result[1]["new_sha"] == sha1
        assert result[1]["action"] == "commit"
        assert result[1]["old_sha"] == sha2
        assert result[2]["new_sha"] == sha2
        assert "old_sha" not in result[2]


class TestGitReflogErrorHandling:
    """Test error handling in git_reflog."""

    def test_git_reflog_returns_error_str_on_git_command_error(self):
        """Should return a '❌ Reflog failed:' string on GitCommandError."""
        mock_repo = Mock()
        mock_repo.git.reflog.side_effect = GitCommandError("git reflog", 128, "error")

        result = git_reflog(mock_repo)

        assert isinstance(result, str)
        assert result.startswith("❌")
        assert "Reflog failed" in result

    def test_git_reflog_returns_error_str_on_general_exception(self):
        """Should return a '❌ Reflog error:' string on unexpected exception."""
        mock_repo = Mock()
        mock_repo.git.reflog.side_effect = RuntimeError("unexpected")

        result = git_reflog(mock_repo)

        assert isinstance(result, str)
        assert result.startswith("❌")
        assert "Reflog error" in result


class TestGitReflogModel:
    """Test GitReflog Pydantic model schema and field naming (FIX 1)."""

    def test_gitreflog_schema_property_is_all_not_show_all(self):
        """Schema property must be 'all', not 'show_all' — no alias indirection."""
        from mcp_server_git.git.models import GitReflog

        props = GitReflog.model_json_schema()["properties"]
        assert "all" in props, "Schema must expose 'all', not 'show_all'"
        assert "show_all" not in props, "Schema must not expose deprecated 'show_all'"

    def test_gitreflog_accepts_all_true_directly(self):
        """Model should accept {'all': True} without alias."""
        from mcp_server_git.git.models import GitReflog

        instance = GitReflog(repo_path="/tmp/repo", **{"all": True})
        assert instance.all is True  # noqa: A003

    def test_gitreflog_max_count_rejects_negative(self):
        """ge=0 constraint should reject negative max_count at validation."""
        from pydantic import ValidationError

        from mcp_server_git.git.models import GitReflog

        with pytest.raises(ValidationError):
            GitReflog(repo_path="/tmp/repo", max_count=-1)


class TestGitReflogLargeOutputWarning:
    """Test large-output warning appended for big reflogs (FIX 3)."""

    def test_git_reflog_appends_warning_when_output_exceeds_50kb(self):
        """Should append a warning dict when serialized entries exceed 50KB."""
        mock_repo = Mock()
        # Generate enough entries to exceed 50KB when serialized.
        # Each line ~100 chars; 600 entries pushes str(entries) well above 50KB.
        sha = "a" * 40
        lines = [
            f"{sha}\x00HEAD@{{{i}}}\x00checkout: moving from branch-{i} to branch-{i + 1}"
            for i in range(600)
        ]
        mock_repo.git.reflog.return_value = "\n".join(lines)

        result = git_reflog(mock_repo)

        assert isinstance(result, list)
        last = result[-1]
        assert "warning" in last, "Last entry must be a warning dict for large output"
        assert "⚠️" in last["warning"]
        assert "KB" in last["warning"]

    def test_git_reflog_no_warning_for_small_output(self):
        """Should not append a warning dict for small reflog output."""
        mock_repo = Mock()
        mock_repo.git.reflog.return_value = _make_raw(
            ("a" * 40, "HEAD@{0}", "commit: initial commit")
        )

        result = git_reflog(mock_repo)

        assert isinstance(result, list)
        assert len(result) == 1
        assert "warning" not in result[-1]


class TestGitReflogMaxCountContract:
    """Test max_count <= 0 means no limit (FIX 4)."""

    def test_git_reflog_max_count_negative_treated_as_no_limit(self):
        """max_count <= 0 must not pass -n flag (no-limit behaviour)."""
        mock_repo = Mock()
        mock_repo.git.reflog.return_value = ""

        git_reflog(mock_repo, max_count=-1)

        args = mock_repo.git.reflog.call_args[0]
        assert "-n" not in args

    def test_git_reflog_max_count_zero_treated_as_no_limit(self):
        """max_count=0 must not pass -n flag (explicit no-limit contract)."""
        mock_repo = Mock()
        mock_repo.git.reflog.return_value = ""

        git_reflog(mock_repo, max_count=0)

        args = mock_repo.git.reflog.call_args[0]
        assert "-n" not in args
