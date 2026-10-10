"""Characterization tests for git_diff_branches outcome branches, real repo."""

import git
import pytest

from mcp_server_git.git.operations import git_diff_branches


@pytest.fixture
def repo(tmp_path):
    r = git.Repo.init(tmp_path)
    with r.config_writer() as cw:
        cw.set_value("user", "name", "Test")
        cw.set_value("user", "email", "test@example.com")
        cw.set_value("commit", "gpgsign", "false")
    (tmp_path / "a.txt").write_text("one\n")
    r.index.add(["a.txt"])
    r.index.commit("first")
    r.create_head("feature").checkout()
    return r


def _commit_on_feature(repo, text):
    from pathlib import Path

    (Path(repo.working_tree_dir) / "a.txt").write_text(text)
    repo.index.add(["a.txt"])
    repo.index.commit("feature change")
    repo.git.checkout("-")
    return repo.active_branch.name


def test_git_diff_branches_returns_error_when_base_branch_missing(repo):
    assert (
        git_diff_branches(repo, "nope", "feature") == "❌ Base branch 'nope' not found"
    )


def test_git_diff_branches_returns_error_when_compare_branch_missing(repo):
    assert (
        git_diff_branches(repo, "feature", "nope")
        == "❌ Compare branch 'nope' not found"
    )


def test_git_diff_branches_returns_no_differences_when_branches_equal(repo):
    base = _commit_on_feature(repo, "one\n")
    assert (
        git_diff_branches(repo, base, "feature")
        == f"No differences between {base} and feature"
    )


def test_git_diff_branches_returns_no_differences_when_stat_only_and_equal(repo):
    base = _commit_on_feature(repo, "one\n")
    assert (
        git_diff_branches(repo, base, "feature", stat_only=True)
        == f"No differences between {base} and feature"
    )


def test_git_diff_branches_returns_diff_when_branches_differ(repo):
    base = _commit_on_feature(repo, "one\ntwo\n")
    assert "+two" in git_diff_branches(repo, base, "feature")


def test_git_diff_branches_accepts_special_ref_when_head_given(repo):
    base = _commit_on_feature(repo, "one\ntwo\n")
    assert git_diff_branches(repo, "HEAD", "feature").startswith("diff --git")


def test_git_diff_branches_returns_stats_when_stat_only_and_differ(repo):
    base = _commit_on_feature(repo, "one\ntwo\n")
    result = git_diff_branches(repo, base, "feature", stat_only=True)
    assert result.startswith(f"Diff statistics between {base} and feature:\n")
    assert "a.txt" in result


def test_git_diff_branches_truncates_when_max_lines_exceeded(repo):
    base = _commit_on_feature(repo, "x\n" * 30)
    result = git_diff_branches(repo, base, "feature", max_lines=5)
    assert "... [Truncated: showing 5 of " in result
    assert result.endswith(
        "\nUse --stat flag for summary or increase max_lines for more content"
    )


def test_git_diff_branches_returns_full_diff_when_max_lines_not_exceeded(repo):
    base = _commit_on_feature(repo, "one\ntwo\n")
    assert "Truncated" not in git_diff_branches(repo, base, "feature", max_lines=1000)


def test_git_diff_branches_ignores_limit_when_max_lines_not_positive(repo):
    base = _commit_on_feature(repo, "one\ntwo\n")
    assert "Truncated" not in git_diff_branches(repo, base, "feature", max_lines=0)


def test_git_diff_branches_warns_when_output_is_large(repo):
    base = _commit_on_feature(repo, ("y" * 99 + "\n") * 600)
    result = git_diff_branches(repo, base, "feature")
    assert result.startswith("⚠️  Large diff detected (")
    assert "Consider using stat_only=true" in result


def test_git_diff_branches_returns_error_message_when_unexpected_exception():
    class Boom:
        @property
        def branches(self):
            raise RuntimeError("boom")

    assert git_diff_branches(Boom(), "a", "b") == "❌ Diff error: boom"
