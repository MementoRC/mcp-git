"""Characterization tests for git_log against a real temporary repository."""

from pathlib import Path

import pytest

from mcp_server_git.git.operations import git_log
from mcp_server_git.utils.git_import import Repo


def _commit(repo: Repo, root: Path, name: str, text: str, msg: str, date: str) -> None:
    (root / name).write_text(text)
    repo.git.add(name)
    with repo.git.custom_environment(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date):
        repo.git.commit("-m", msg)


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    r = Repo.init(tmp_path, initial_branch="main")
    with r.config_writer() as cw:
        cw.set_value("user", "name", "Alice")
        cw.set_value("user", "email", "alice@example.com")
        cw.set_value("commit", "gpgsign", "false")
    _commit(r, tmp_path, "a.txt", "alpha\n", "first alpha", "2020-01-01T00:00:00")
    _commit(r, tmp_path, "b.txt", "needle\n", "second beta", "2021-01-01T00:00:00")
    r.git.checkout("-b", "feature")
    _commit(r, tmp_path, "c.txt", "gamma\n", "feature gamma", "2022-01-01T00:00:00")
    r.git.checkout("main")
    with r.git.custom_environment(
        GIT_AUTHOR_DATE="2023-01-01T00:00:00", GIT_COMMITTER_DATE="2023-01-01T00:00:00"
    ):
        r.git.merge("--no-ff", "-m", "merge feature", "feature")
    r.git.commit("--amend", "--author=Bob <bob@example.com>", "--no-edit")
    return r


def _subjects(out: str) -> list[str]:
    return [ln for ln in out.splitlines() if ln]


def test_git_log_returns_error_when_both_pickaxe_options_given(repo: Repo):
    out = git_log(repo, search_content="a", search_content_regex="b")
    assert (
        out == "❌ Specify only one of search_content (-S) or search_content_regex (-G)"
    )


def test_git_log_returns_full_log_when_defaults_used(repo: Repo):
    out = git_log(repo)
    assert out.startswith("commit ")
    assert "first alpha" in out and "merge feature" in out


def test_git_log_limits_entries_when_max_count_given(repo: Repo):
    out = git_log(repo, max_count=1, oneline=True)
    assert len(_subjects(out)) == 1
    assert "merge feature" in out


def test_git_log_ignores_limit_when_max_count_zero(repo: Repo):
    out = git_log(repo, max_count=0, oneline=True)
    assert len(_subjects(out)) == 4


def test_git_log_ignores_limit_when_max_count_none(repo: Repo):
    out = git_log(repo, max_count=None, oneline=True)  # type: ignore[arg-type]
    assert len(_subjects(out)) == 4


def test_git_log_uses_oneline_when_oneline_and_format_both_given(repo: Repo):
    out = git_log(repo, oneline=True, format_str="%s", max_count=1)
    assert out.endswith(" merge feature")
    assert len(out.split()[0]) >= 7


def test_git_log_uses_format_str_when_format_given(repo: Repo):
    out = git_log(repo, format_str="%s|%an", max_count=2)
    assert out == "merge feature|Bob\nfeature gamma|Alice"


def test_git_log_uses_signature_format_when_show_signature_given(repo: Repo):
    out = git_log(repo, show_signature=True, max_count=1)
    parts = out.split(" ", 3)
    assert parts[1] == "N"
    assert out.endswith("merge feature")


def test_git_log_prefers_format_str_over_show_signature(repo: Repo):
    out = git_log(repo, format_str="%s", show_signature=True, max_count=1)
    assert out == "merge feature"


def test_git_log_draws_graph_when_graph_given(repo: Repo):
    out = git_log(repo, graph=True, oneline=True)
    assert "*" in out and "|" in out


def test_git_log_filters_by_since_when_since_given(repo: Repo):
    out = git_log(repo, since="2021-06-01", format_str="%s")
    assert out == "merge feature\nfeature gamma"


def test_git_log_filters_by_until_when_until_given(repo: Repo):
    out = git_log(repo, until="2021-06-01", format_str="%s")
    assert out == "second beta\nfirst alpha"


def test_git_log_filters_by_author_when_author_given(repo: Repo):
    assert git_log(repo, author="Bob", format_str="%s") == "merge feature"


def test_git_log_filters_by_message_when_grep_given(repo: Repo):
    assert git_log(repo, grep="beta", format_str="%s") == "second beta"


def test_git_log_filters_by_pickaxe_when_search_content_given(repo: Repo):
    assert git_log(repo, search_content="needle", format_str="%s") == "second beta"


def test_git_log_filters_by_pickaxe_regex_when_search_content_regex_given(repo: Repo):
    out = git_log(repo, search_content_regex="gam+a", format_str="%s")
    assert out == "feature gamma"


def test_git_log_accepts_dash_prefixed_pickaxe_when_search_starts_with_dash(repo: Repo):
    out = git_log(repo, search_content="-x")
    assert out == "No commits found matching the specified criteria"


def test_git_log_pickaxe_all_shows_whole_commit_when_search_content_all_given(
    repo: Repo,
):
    out = git_log(
        repo, search_content="needle", search_content_all=True, format_str="%s"
    )
    assert out == "second beta"


def test_git_log_ignores_pickaxe_all_when_no_pickaxe_given(repo: Repo):
    out = git_log(repo, search_content_all=True, oneline=True)
    assert len(_subjects(out)) == 4


def test_git_log_pickaxe_all_applies_when_only_regex_given(repo: Repo):
    out = git_log(
        repo, search_content_regex="needle", search_content_all=True, format_str="%s"
    )
    assert out == "second beta"


def test_git_log_shows_only_merges_when_merges_true(repo: Repo):
    assert git_log(repo, merges=True, format_str="%s") == "merge feature"


def test_git_log_hides_merges_when_merges_false(repo: Repo):
    out = git_log(repo, merges=False, format_str="%s")
    assert out == "feature gamma\nsecond beta\nfirst alpha"


def test_git_log_shows_all_when_merges_none(repo: Repo):
    assert len(_subjects(git_log(repo, merges=None, oneline=True))) == 4


def test_git_log_reverses_order_when_reverse_given(repo: Repo):
    out = git_log(repo, reverse=True, format_str="%s")
    assert out == "first alpha\nsecond beta\nfeature gamma\nmerge feature"


def test_git_log_restricts_to_files_when_files_given(repo: Repo):
    assert git_log(repo, files=["b.txt"], format_str="%s") == "second beta"


def test_git_log_uses_branch_when_branch_given(repo: Repo):
    out = git_log(repo, branch="feature", format_str="%s")
    assert out == "feature gamma\nsecond beta\nfirst alpha"


def test_git_log_returns_no_commits_message_when_filter_matches_nothing(repo: Repo):
    out = git_log(repo, grep="no-such-message")
    assert out == "No commits found matching the specified criteria"


def test_git_log_returns_failed_message_when_branch_unknown(repo: Repo):
    out = git_log(repo, branch="nonexistent-branch")
    assert out.startswith("❌ Log failed: ")
    assert "nonexistent-branch" in out


def test_git_log_returns_error_message_when_unexpected_exception(repo: Repo):
    out = git_log(None)  # type: ignore[arg-type]
    assert out.startswith("❌ Log error: ")
