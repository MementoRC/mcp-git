"""git_filter_paths dry run must count merges and every rewritten commit (#283).

History simplification hides merges that are TREESAME to a parent, yet the
real run rewrites them (and every descendant). The report is checked against
the sha changes of a real run on the same repository.
"""

import re

import pytest

from mcp_server_git.git._filter_ops import git_filter_paths
from mcp_server_git.utils.tool_failure import ToolFailure

from ._filter_repo_helpers import all_commits, commit, isolated_git_home, merge


@pytest.fixture
def repo(real_repo, signing_not_enforced):
    """The path is in the tree on both sides; the merge equals its first parent."""
    commit(real_repo, {"README.md": "r"}, "c0 readme", 1)
    commit(real_repo, {".mcp.json": "{a}", "src/app.py": "1"}, "c1 add config", 2)
    real_repo.git.checkout("-b", "side")
    commit(real_repo, {"src/side.py": "s"}, "s1 side", 3)
    real_repo.git.checkout("main")
    commit(real_repo, {".mcp.json": "{b}"}, "c2 edit config", 4)
    merge(real_repo, "side", "m1 merge side", 5)
    commit(real_repo, {"src/app.py": "2"}, "c3 after merge", 6)
    return real_repo


def _count(result: str, label: str) -> int:
    match = re.search(rf"{re.escape(label)}[^\d\n]*(\d+)", result)
    assert match, result
    return int(match.group(1))


def _sha_changes(repo, **kwargs) -> int:
    before = set(all_commits(repo, "main"))
    result = git_filter_paths(repo, **kwargs)
    assert not isinstance(result, ToolFailure), result
    return len(before - set(all_commits(repo, "main")))


def test_git_filter_paths_lists_merge_when_dry_run_and_merge_is_treesame(repo):
    result = git_filter_paths(repo, [".mcp.json"], dry_run=True)

    assert "m1 merge side" in result
    assert "c0 readme" not in result


def test_git_filter_paths_reports_rewritten_count_equal_to_sha_changes_when_removing(
    repo,
):
    result = git_filter_paths(repo, [".mcp.json"], dry_run=True, prune_empty=False)
    reported = _count(result, "Commits that will be rewritten (new sha)")

    changed = _sha_changes(repo, paths=[".mcp.json"], prune_empty=False)

    assert reported == changed == 5


def test_git_filter_paths_reports_dropped_empty_count_when_prune_empty_on(repo):
    commit(repo, {".mcp.json": "{c}"}, "c4 only config", 7)
    result = git_filter_paths(repo, [".mcp.json"], dry_run=True)
    reported = _count(result, "Commits that would be dropped as empty")
    rewritten = _count(result, "Commits that will be rewritten (new sha)")

    before = all_commits(repo, "main")
    git_filter_paths(repo, [".mcp.json"])
    after = all_commits(repo, "main")

    # c2 edit config, c4 only config and the empty initial commit
    assert reported == 3
    assert len(after) == len(before) - reported
    assert len(set(before) - set(after)) == rewritten


def test_git_filter_paths_omits_dropped_line_when_prune_empty_off(repo):
    result = git_filter_paths(repo, [".mcp.json"], dry_run=True, prune_empty=False)

    assert "dropped as empty" not in result


def test_git_filter_paths_reports_rewritten_count_equal_to_sha_changes_when_inverted(
    repo,
):
    result = git_filter_paths(
        repo, ["src"], invert=True, dry_run=True, prune_empty=False
    )
    reported = _count(result, "Commits that will be rewritten (new sha)")

    assert "m1 merge side" in result
    assert "c0 readme" in result
    assert reported == _sha_changes(repo, paths=["src"], invert=True, prune_empty=False)


def test_git_filter_paths_refuses_when_no_commit_tree_has_path(repo):
    result = git_filter_paths(repo, ["nowhere.txt"], dry_run=True)

    assert isinstance(result, ToolFailure)
    assert "nowhere.txt" in result
