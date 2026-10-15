"""Characterization tests for git_diff outcome branches, run on a real repo."""

from pathlib import Path

import git
import pytest

from mcp_server_git.git.operations import git_diff


@pytest.fixture
def repo(tmp_path):
    r = git.Repo.init(tmp_path)
    with r.config_writer() as cw:
        cw.set_value("user", "name", "Test")
        cw.set_value("user", "email", "test@example.com")
        cw.set_value("commit", "gpgsign", "false")
    (tmp_path / "a.txt").write_text("one\n")
    (tmp_path / "b.txt").write_text("bee\n")
    r.index.add(["a.txt", "b.txt"])
    r.index.commit("first")
    (tmp_path / "a.txt").write_text("one\ntwo\n")
    r.index.add(["a.txt"])
    r.index.commit("second")
    return r


def _dirty(repo, text="changed\n"):
    (Path(repo.working_tree_dir) / "a.txt").write_text(text)


def test_git_diff_returns_no_changes_message_when_tree_clean(repo):
    assert git_diff(repo) == "No changes detected in diff against HEAD"


def test_git_diff_returns_diff_against_head_when_tree_dirty(repo):
    _dirty(repo)
    result = git_diff(repo)
    assert "+changed" in result
    assert not result.startswith("⚠️")


def test_git_diff_returns_diff_against_target_when_target_given(repo):
    result = git_diff(repo, target="HEAD~1")
    assert "+two" in result


def test_git_diff_returns_changed_files_when_name_only_with_changes(repo):
    _dirty(repo)
    assert git_diff(repo, name_only=True) == "Changed files against HEAD:\na.txt"


def test_git_diff_returns_no_changes_when_name_only_and_tree_clean(repo):
    assert git_diff(repo, name_only=True) == "No changes against HEAD"


def test_git_diff_returns_summary_when_stat_only_with_changes(repo):
    _dirty(repo)
    result = git_diff(repo, stat_only=True)
    assert result.startswith("Diff against HEAD summary:\n")
    assert "a.txt" in result


def test_git_diff_returns_no_differences_when_stat_only_and_tree_clean(repo):
    assert git_diff(repo, stat_only=True) == "No differences against HEAD"


def test_git_diff_name_only_wins_when_both_name_only_and_stat_only(repo):
    _dirty(repo)
    assert git_diff(repo, name_only=True, stat_only=True).startswith("Changed files")


def test_git_diff_filters_output_when_paths_given(repo, tmp_path):
    _dirty(repo)
    (tmp_path / "b.txt").write_text("other\n")
    result = git_diff(repo, name_only=True, paths=["b.txt"])
    assert result == "Changed files against HEAD:\nb.txt"


def test_git_diff_truncates_output_when_max_lines_exceeded(repo):
    _dirty(repo, "x\n" * 30)
    result = git_diff(repo, max_lines=5)
    assert "... [Truncated: showing 5 of " in result
    assert result.endswith(
        "\nUse stat_only=true for summary or increase max_lines for more content"
    )


def test_git_diff_returns_full_output_when_max_lines_not_exceeded(repo):
    _dirty(repo)
    assert "Truncated" not in git_diff(repo, max_lines=1000)


def test_git_diff_warns_when_output_is_large(repo):
    _dirty(repo, ("y" * 99 + "\n") * 600)
    result = git_diff(repo)
    assert result.startswith("⚠️  Large diff detected (")
    assert "Consider using stat_only=true" in result


def test_git_diff_returns_range_diff_when_commit_range_given(repo):
    result = git_diff(repo, commit_range="HEAD~1..HEAD")
    assert "+two" in result


def test_git_diff_returns_no_changes_message_when_range_empty(repo):
    assert (
        git_diff(repo, commit_range="HEAD..HEAD")
        == "No changes detected in diff commit range HEAD..HEAD"
    )


def test_git_diff_returns_commit_diff_when_base_and_target_commit_given(repo):
    result = git_diff(repo, base_commit="HEAD~1", target_commit="HEAD", name_only=True)
    assert result == "Changed files HEAD~1...HEAD:\na.txt"


def test_git_diff_returns_error_when_conflicting_parameters(repo):
    result = git_diff(repo, target="main", commit_range="HEAD~1..HEAD")
    assert result.startswith("❌ Parameter validation failed: Conflicting diff")


def test_git_diff_returns_error_when_only_base_commit_given(repo):
    assert git_diff(repo, base_commit="HEAD") == (
        "❌ Parameter validation failed: "
        "Both base_commit and target_commit must be provided together"
    )


def test_git_diff_returns_error_when_range_has_dangerous_chars(repo):
    result = git_diff(repo, commit_range="HEAD;rm..HEAD")
    assert result.startswith("❌ Parameter validation failed: Invalid commit_range:")


def test_git_diff_prefixes_warning_when_range_format_unusual(repo):
    result = git_diff(repo, commit_range="HEAD^..HEAD")
    assert result.startswith("⚠️ Warning: Unusual commit range format 'HEAD^..HEAD'")
    assert "+two" in result


@pytest.mark.parametrize(
    "kwargs, body",
    [
        ({"name_only": True}, "Changed files commit range HEAD^..HEAD:\na.txt"),
        ({"stat_only": True}, "Diff commit range HEAD^..HEAD summary:\n a.txt"),
    ],
)
def test_git_diff_prefixes_warning_when_unusual_range_and_option(repo, kwargs, body):
    result = git_diff(repo, commit_range="HEAD^..HEAD", **kwargs)
    warning, _, rest = result.partition("\n\n")
    assert warning.startswith("⚠️ Warning: Unusual")
    assert rest.startswith(body)


def test_git_diff_returns_failure_message_when_git_command_fails(repo):
    result = git_diff(repo, commit_range="nosuchref..HEAD")
    assert result.startswith("❌ Diff failed: ")


def test_git_diff_returns_error_message_when_unexpected_exception(repo):
    class Boom:
        class git:  # noqa: N801
            @staticmethod
            def diff(*_args, **_kwargs):
                raise RuntimeError("boom")

    assert git_diff(Boom) == "❌ Diff error: boom"
