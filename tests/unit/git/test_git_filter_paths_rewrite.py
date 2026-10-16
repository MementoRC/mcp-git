"""git_filter_paths real rewrites against real repositories (issue #283).

Signing uses the ``signing_repo`` stub gpg.program; tests that do not care
about signing use ``signing_not_enforced``.
"""

from pathlib import Path

import pytest

from mcp_server_git.git._bundle_ops import git_bundle_verify
from mcp_server_git.git._filter_ops import git_filter_paths
from mcp_server_git.utils.tool_failure import ToolFailure

from ._filter_repo_helpers import (
    SECRETS,
    add_bare_remote,
    all_commits,
    build_283_history,
    bundles_near,
    commit,
    dates_by_subject,
    is_signed,
    isolated_git_home,
    ref_shas,
    tree_paths,
)

_SECRET_PREFIXES = (".mcp.json", ".claude/", ".serena/")


def _secret_paths(repo, sha):
    return [p for p in tree_paths(repo, sha) if p.startswith(_SECRET_PREFIXES)]


@pytest.fixture
def repo(real_repo, signing_not_enforced):
    commit(real_repo, {"src/a.py": "1", ".mcp.json": "{}"}, "add config", 1)
    commit(real_repo, {"src/a.py": "2"}, "edit src", 2)
    return real_repo


def test_git_filter_paths_returns_signed_history_without_secrets_when_283_reproduced(
    signing_repo,
):
    repo = signing_repo
    build_283_history(repo)
    # The fixture's root commit has an empty tree, so prune_empty drops it
    # (as native --prune-empty does); every other commit survives.
    dates_before = dates_by_subject(repo)
    del dates_before["initial commit"]
    count_before = len(all_commits(repo)) - 1

    result = git_filter_paths(repo, SECRETS, all_refs=True)

    assert not isinstance(result, ToolFailure), result
    commits = all_commits(repo)
    assert len(commits) == count_before
    assert all(_secret_paths(repo, sha) == [] for sha in commits)
    assert repo.git.rev_list("--merges", "--count", "main") == "1"
    assert dates_by_subject(repo) == dates_before
    assert all(is_signed(repo, sha) for sha in commits)
    assert "Signed: yes" in result
    # The working copies of the removed files are kept (untracked).
    root = Path(repo.working_tree_dir)
    assert (root / ".mcp.json").is_file()
    assert (root / ".claude" / "settings.json").is_file()


def test_git_filter_paths_returns_verified_default_bundle_when_run_completes(repo):
    result = git_filter_paths(repo, [".mcp.json"])

    bundles = bundles_near(repo)
    assert len(bundles) == 1
    assert bundles[0].name.startswith("repo-pre-filter-")
    assert str(bundles[0]) in result
    assert not isinstance(git_bundle_verify(repo, str(bundles[0])), ToolFailure)


def test_git_filter_paths_returns_no_refs_original_when_run_completes(repo):
    git_filter_paths(repo, [".mcp.json"])

    assert repo.git.for_each_ref("refs/original/") == ""


def test_git_filter_paths_returns_old_and_new_shas_when_run_completes(repo):
    old = repo.head.commit.hexsha

    result = git_filter_paths(repo, [".mcp.json"])

    new = repo.head.commit.hexsha
    assert new != old
    assert f"{old[:8]} -> {new[:8]}" in result
    assert "Signed: no" in result
    assert "pushed" in result
    assert not is_signed(repo, new)


def test_git_filter_paths_returns_custom_backup_when_backup_path_given(repo, tmp_path):
    backup = tmp_path / "custom.bundle"

    result = git_filter_paths(repo, [".mcp.json"], backup_path=str(backup))

    assert not isinstance(result, ToolFailure), result
    assert backup.is_file()


def test_git_filter_paths_keeps_only_listed_paths_when_invert(repo):
    commit(repo, {"docs/readme.md": "only docs"}, "docs only", 3)

    result = git_filter_paths(repo, ["src"], invert=True)

    assert not isinstance(result, ToolFailure), result
    commits = all_commits(repo)
    assert all(p.startswith("src/") for sha in commits for p in tree_paths(repo, sha))
    subjects = repo.git.log("--format=%s").splitlines()
    assert "docs only" not in subjects
    assert "edit src" in subjects


def test_git_filter_paths_drops_commit_that_only_touched_removed_path_when_prune(
    repo,
):
    commit(repo, {".mcp.json": "{changed}"}, "config only", 3)

    git_filter_paths(repo, [".mcp.json"])

    subjects = repo.git.log("--format=%s").splitlines()
    assert "config only" not in subjects
    assert {"add config", "edit src"} <= set(subjects)


def test_git_filter_paths_keeps_empty_commit_when_prune_empty_false(repo):
    commit(repo, {".mcp.json": "{changed}"}, "config only", 3)
    before = len(all_commits(repo))

    git_filter_paths(repo, [".mcp.json"], prune_empty=False)

    assert len(all_commits(repo)) == before
    assert "config only" in repo.git.log("--format=%s")


def test_git_filter_paths_proceeds_without_pushing_when_allow_with_remote(
    repo, tmp_path
):
    bare = add_bare_remote(repo, tmp_path)
    remote_before = ref_shas(bare)

    result = git_filter_paths(repo, [".mcp.json"], allow_with_remote=True)

    assert not isinstance(result, ToolFailure), result
    assert "origin" in result
    assert "divergent" in result
    assert ref_shas(bare) == remote_before
    assert all(_secret_paths(repo, sha) == [] for sha in all_commits(repo, "main"))


def test_git_filter_paths_leaves_remote_tracking_refs_when_all_refs_with_remote(
    repo, tmp_path
):
    add_bare_remote(repo, tmp_path)
    tracking = {
        r: s for r, s in ref_shas(repo).items() if r.startswith("refs/remotes/")
    }
    assert "refs/remotes/origin/main" in tracking

    result = git_filter_paths(
        repo, [".mcp.json"], all_refs=True, allow_with_remote=True
    )

    assert not isinstance(result, ToolFailure), result
    after = ref_shas(repo)
    assert {r: after.get(r) for r in tracking} == tracking
    assert after["refs/heads/main"] != tracking["refs/remotes/origin/main"]
    assert "refs/remotes/" not in result


def test_git_filter_paths_leaves_stash_untouched_when_all_refs(repo):
    (Path(repo.working_tree_dir) / ".mcp.json").write_text("{stashed}")
    repo.git.stash("push", "-m", "wip")
    stash_before = repo.git.rev_parse("refs/stash")

    result = git_filter_paths(repo, [".mcp.json"], all_refs=True)

    assert not isinstance(result, ToolFailure), result
    assert repo.git.rev_parse("refs/stash") == stash_before
    assert "refs/stash" not in result


def test_git_filter_paths_reports_files_left_untracked_when_remove_mode(repo):
    result = git_filter_paths(repo, [".mcp.json"])

    assert "left on disk as untracked files" in result
    assert ".gitignore" in result
    assert (Path(repo.working_tree_dir) / ".mcp.json").is_file()
    assert ".mcp.json" in repo.git.status("--porcelain", "--untracked-files=all")


def test_git_filter_paths_treats_shell_metacharacters_literally_when_path_injected(
    repo, tmp_path
):
    nasty = ["a; touch pwned", "$(id)", "`touch pwned2`"]
    commit(repo, dict.fromkeys(nasty, "x"), "add nasty names", 3)

    result = git_filter_paths(repo, nasty)

    assert not isinstance(result, ToolFailure), result
    for sha in all_commits(repo):
        assert not set(nasty) & set(tree_paths(repo, sha))
    assert not list(tmp_path.rglob("pwned*"))
    assert not list(Path.cwd().glob("pwned*"))


def test_git_filter_paths_leaves_other_branches_untouched_when_all_refs_false(repo):
    repo.git.branch("other")
    other_before = repo.git.rev_parse("refs/heads/other")

    git_filter_paths(repo, [".mcp.json"])

    assert repo.git.rev_parse("refs/heads/other") == other_before
    assert _secret_paths(repo, other_before) == [".mcp.json"]
    assert repo.git.rev_parse("refs/heads/main") != other_before


def test_git_filter_paths_rewrites_named_branch_only_when_branch_given(repo):
    repo.git.branch("other")
    main_before = repo.git.rev_parse("refs/heads/main")

    result = git_filter_paths(repo, [".mcp.json"], branch="other")

    assert not isinstance(result, ToolFailure), result
    assert repo.git.rev_parse("refs/heads/main") == main_before
    assert _secret_paths(repo, "refs/heads/other") == []


def test_git_filter_paths_rewrites_branches_and_tags_when_all_refs(repo):
    repo.git.branch("other")
    repo.git.tag("v1")

    git_filter_paths(repo, [".mcp.json"], all_refs=True)

    for ref in ("refs/heads/main", "refs/heads/other", "refs/tags/v1"):
        assert _secret_paths(repo, ref) == []
