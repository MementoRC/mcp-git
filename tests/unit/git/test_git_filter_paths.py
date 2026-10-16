"""git_filter_paths guards and dry runs against real repositories (issue #283).

Every refusal must leave refs untouched and write no bundle. Rewrites are
covered in test_git_filter_paths_rewrite.py.
"""

from pathlib import Path

import pytest

from mcp_server_git.git._filter_ops import git_filter_paths
from mcp_server_git.utils.tool_failure import ToolFailure

from ._filter_repo_helpers import (
    add_bare_remote,
    bundles_near,
    commit,
    isolated_git_home,
    ref_shas,
    write,
)


@pytest.fixture
def repo(real_repo, signing_not_enforced):
    commit(real_repo, {"src/a.py": "1", ".mcp.json": "{}"}, "add config", 1)
    commit(real_repo, {"src/a.py": "2"}, "edit src", 2)
    return real_repo


def _assert_refused_unchanged(repo, result, before, needle):
    assert isinstance(result, ToolFailure)
    assert needle in result
    assert ref_shas(repo) == before
    assert bundles_near(repo) == []


@pytest.mark.parametrize(
    ("paths", "needle"),
    [
        ([], "at least one"),
        (["-rf"], "'-'"),
        (["/etc/passwd"], "absolute"),
        (["a/../b"], "'..'"),
        (["."], "whole repository"),
        ([""], "empty"),
    ],
)
def test_git_filter_paths_returns_failure_unchanged_when_path_invalid(
    repo, paths, needle
):
    before = ref_shas(repo)

    result = git_filter_paths(repo, paths)

    _assert_refused_unchanged(repo, result, before, needle)


def test_git_filter_paths_returns_failure_when_branch_combined_with_all_refs(repo):
    before = ref_shas(repo)

    result = git_filter_paths(repo, [".mcp.json"], all_refs=True, branch="main")

    _assert_refused_unchanged(repo, result, before, "all_refs")


def test_git_filter_paths_returns_failure_when_branch_starts_with_dash(repo):
    before = ref_shas(repo)

    result = git_filter_paths(repo, [".mcp.json"], branch="--all")

    _assert_refused_unchanged(repo, result, before, "branch")


def test_git_filter_paths_returns_failure_when_branch_missing(repo):
    before = ref_shas(repo)

    result = git_filter_paths(repo, [".mcp.json"], branch="nope")

    _assert_refused_unchanged(repo, result, before, "nope")


def test_git_filter_paths_returns_failure_listing_file_when_tree_has_unstaged_change(
    repo,
):
    write(repo, {"src/a.py": "dirty"})
    before = ref_shas(repo)

    result = git_filter_paths(repo, [".mcp.json"])

    _assert_refused_unchanged(repo, result, before, "src/a.py")


def test_git_filter_paths_returns_failure_listing_file_when_change_is_staged(repo):
    write(repo, {"staged.txt": "x"})
    repo.git.add("staged.txt")
    before = ref_shas(repo)

    result = git_filter_paths(repo, [".mcp.json"])

    _assert_refused_unchanged(repo, result, before, "staged.txt")


def test_git_filter_paths_returns_failure_listing_file_when_file_untracked(repo):
    write(repo, {"notes/todo.txt": "x"})
    before = ref_shas(repo)

    result = git_filter_paths(repo, [".mcp.json"])

    _assert_refused_unchanged(repo, result, before, "notes/todo.txt")


def test_git_filter_paths_returns_dry_run_when_only_ignored_files_present(repo):
    commit(repo, {".gitignore": "*.log\n"}, "ignore logs", 3)
    write(repo, {"debug.log": "noise"})

    result = git_filter_paths(repo, [".mcp.json"], dry_run=True)

    assert not isinstance(result, ToolFailure)
    assert "Dry run" in result


def test_git_filter_paths_returns_failure_naming_remote_when_remote_configured(
    repo, tmp_path
):
    add_bare_remote(repo, tmp_path)
    before = ref_shas(repo)

    result = git_filter_paths(repo, [".mcp.json"])

    _assert_refused_unchanged(repo, result, before, "origin")
    assert "allow_with_remote" in result


def test_git_filter_paths_returns_failure_when_rebase_in_progress(repo):
    with repo.git.custom_environment(GIT_SEQUENCE_EDITOR="sed -i -e s/^pick/edit/"):
        repo.git.rebase("-i", "HEAD~1")
    assert (Path(repo.git_dir) / "rebase-merge").is_dir()
    before = ref_shas(repo)

    result = git_filter_paths(repo, [".mcp.json"])

    _assert_refused_unchanged(repo, result, before, "rebase")


def test_git_filter_paths_returns_failure_with_cleanup_hint_when_refs_original_exists(
    repo,
):
    repo.git.update_ref("refs/original/refs/heads/main", "HEAD")
    before = ref_shas(repo)

    result = git_filter_paths(repo, [".mcp.json"])

    _assert_refused_unchanged(repo, result, before, "update-ref -d")


def test_git_filter_paths_returns_failure_when_paths_match_no_commit(repo):
    before = ref_shas(repo)

    result = git_filter_paths(repo, ["never-committed.txt"])

    _assert_refused_unchanged(repo, result, before, "never-committed.txt")


def test_git_filter_paths_returns_failure_unchanged_when_backup_file_exists(
    repo, tmp_path
):
    backup = tmp_path / "taken.bundle"
    backup.write_text("precious")
    before = ref_shas(repo)

    result = git_filter_paths(repo, [".mcp.json"], backup_path=str(backup))

    assert isinstance(result, ToolFailure)
    assert "already exists" in result
    assert backup.read_text() == "precious"
    assert ref_shas(repo) == before


def test_git_filter_paths_returns_failure_unchanged_when_signing_key_missing(
    real_repo,
):
    commit(real_repo, {".mcp.json": "{}"}, "add config", 1)
    before = ref_shas(real_repo)

    result = git_filter_paths(real_repo, [".mcp.json"])

    _assert_refused_unchanged(real_repo, result, before, "GPG")


def test_git_filter_paths_returns_report_with_warning_when_dry_run_without_key(
    real_repo,
):
    commit(real_repo, {".mcp.json": "{}"}, "add config", 1)
    before = ref_shas(real_repo)

    result = git_filter_paths(real_repo, [".mcp.json"], dry_run=True)

    assert not isinstance(result, ToolFailure), result
    assert "Dry run" in result
    assert "add config" in result
    assert "WARNING: a real run would refuse" in result
    assert "GPG" in result
    assert ref_shas(real_repo) == before
    assert bundles_near(real_repo) == []


def test_git_filter_paths_returns_branches_and_tags_only_when_dry_run_all_refs(
    repo, tmp_path
):
    add_bare_remote(repo, tmp_path)
    repo.git.tag("v1")

    result = git_filter_paths(
        repo, [".mcp.json"], all_refs=True, allow_with_remote=True, dry_run=True
    )

    assert "refs/heads/main" in result
    assert "refs/tags/v1" in result
    assert "refs/remotes/" not in result


def test_git_filter_paths_returns_commits_and_files_unchanged_when_dry_run(repo):
    commit(repo, {".claude/a.json": "1", ".claude/b.json": "2"}, "add claude", 3)
    before = ref_shas(repo)

    result = git_filter_paths(repo, [".mcp.json", ".claude/"], dry_run=True)

    assert not isinstance(result, ToolFailure)
    assert "add config" in result
    assert "add claude" in result
    assert "edit src" not in result
    for name in (".mcp.json", ".claude/a.json", ".claude/b.json"):
        assert name in result
    assert "src/a.py" not in result
    assert "refs/heads/main" in result
    assert ref_shas(repo) == before
    assert bundles_near(repo) == []


def test_git_filter_paths_returns_files_outside_kept_paths_when_dry_run_inverted(
    repo,
):
    before = ref_shas(repo)

    result = git_filter_paths(repo, ["src"], invert=True, dry_run=True)

    assert "add config" in result
    assert ".mcp.json" in result
    assert "src/a.py" not in result
    assert ref_shas(repo) == before


def test_git_filter_paths_returns_capped_file_list_when_dry_run_matches_many(repo):
    many = {f"secrets/f{i:03d}.txt": str(i) for i in range(60)}
    commit(repo, many, "add many secrets", 3)

    result = git_filter_paths(repo, ["secrets"], dry_run=True)

    assert "secrets/f000.txt" in result
    assert "...and 10 more" in result


def test_git_filter_paths_returns_scope_of_one_branch_when_dry_run_on_branch(repo):
    repo.git.branch("other")

    result = git_filter_paths(repo, [".mcp.json"], branch="other", dry_run=True)

    assert "refs/heads/other" in result
    assert "refs/heads/main" not in result
