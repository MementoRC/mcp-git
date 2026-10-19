"""git_reflog_expire and git_gc against real repositories (issue #283)."""

import re
from pathlib import Path
from unittest.mock import Mock

import pytest
from git import GitCommandError, Repo

from mcp_server_git.git._maintenance_ops import git_gc, git_reflog_expire
from mcp_server_git.utils.tool_failure import ToolFailure

from ._filter_repo_helpers import commit, isolated_git_home  # noqa: F401

_BAD = ["--foo", "now; rm", "", "yesterday", "2020-1-1", "now\n", "-1.day.ago"]
_GOOD = [
    "now",
    "never",
    "all",
    "2020-01-01",
    "2020-01-01 10:30",
    "2020-01-01T10:30:15",
    "2.weeks.ago",
    "1.day.ago",
]


def _reflog_count(repo: Repo, ref: str) -> int:
    return len(repo.git.reflog("show", "--format=%H", ref).split())


def _counts(repo: Repo) -> dict[str, int]:
    refs = ["HEAD", "refs/heads/main", "refs/stash"]
    return {r: _reflog_count(repo, r) for r in refs if _has_reflog(repo, r)}


def _has_reflog(repo: Repo, ref: str) -> bool:
    status, _, _ = repo.git.reflog(
        "exists", ref, with_extended_output=True, with_exceptions=False
    )
    return status == 0


def _scrubbable_blob(repo: Repo) -> str:
    """Commit a secret on a side branch, then delete the branch; return the blob."""
    commit(repo, {"base.txt": "base"}, "base", 1)
    repo.git.checkout("-b", "side")
    commit(repo, {"secret.txt": "top secret"}, "add secret", 2)
    blob = repo.git.rev_parse("HEAD:secret.txt")
    repo.git.checkout("main")
    repo.git.branch("-D", "side")
    return blob


def _with_stash(repo: Repo) -> None:
    commit(repo, {"base.txt": "base"}, "base", 1)
    (Path(repo.working_tree_dir) / "base.txt").write_text("changed")
    repo.git.stash("push", "-m", "wip")


def _exists(repo: Repo, sha: str) -> bool:
    try:
        repo.git.cat_file("-e", sha)
    except GitCommandError:
        return False
    return True


def _would_prune(result: str) -> int:
    return int(re.search(r"would prune (\d+) loose", result).group(1))


def test_git_reflog_expire_returns_prediction_and_changes_nothing_when_dry_run(
    real_repo,
):
    _scrubbable_blob(real_repo)
    before = _counts(real_repo)
    objects = real_repo.git.count_objects("-v")

    result = git_reflog_expire(real_repo)

    assert not isinstance(result, ToolFailure)
    assert "DRY RUN" in result
    assert re.search(r"would remove [1-9]\d* of", result)
    assert "Stash: none" in result
    assert _counts(real_repo) == before
    assert real_repo.git.count_objects("-v") == objects


def test_git_reflog_expire_empties_reflogs_and_keeps_stash_when_not_included(
    real_repo,
):
    _with_stash(real_repo)
    assert _counts(real_repo)["HEAD"] > 0

    result = git_reflog_expire(real_repo, dry_run=False)

    after = _counts(real_repo)
    assert result.startswith("✅ Reflog expire: removed")
    assert "Stash: skipped (1 entries kept" in result
    assert "refs/stash" not in result.split("Command:")[1].split("\n")[0]
    assert after == {"HEAD": 0, "refs/heads/main": 0, "refs/stash": 1}


def test_git_reflog_expire_expires_stash_when_include_stash_true(real_repo):
    _with_stash(real_repo)

    result = git_reflog_expire(real_repo, include_stash=True, dry_run=False)

    assert "Stash: expired too" in result
    assert set(_counts(real_repo).values()) == {0}
    assert "refs/stash" in _counts(real_repo)


def test_git_reflog_expire_leaves_stash_when_dry_run_includes_stash(real_repo):
    _with_stash(real_repo)
    before = _counts(real_repo)

    result = git_reflog_expire(real_repo, include_stash=True)

    assert "DRY RUN" in result
    assert _counts(real_repo) == before


def test_git_reflog_expire_returns_failure_when_unit_unknown(real_repo):
    _scrubbable_blob(real_repo)

    result = git_reflog_expire(real_repo, expire_unreachable="2.fortnights.ago")

    assert isinstance(result, ToolFailure)
    assert result.startswith("❌ Invalid expire_unreachable value")


def test_git_gc_returns_nothing_pruned_and_unchanged_when_dry_run(real_repo):
    blob = _scrubbable_blob(real_repo)
    objects = real_repo.git.count_objects("-v")

    result = git_gc(real_repo)

    assert result.startswith("✅ GC DRY RUN")
    assert "git_reflog_expire first" in result
    assert real_repo.git.count_objects("-v") == objects
    assert _exists(real_repo, blob)


def test_git_gc_reports_prunable_objects_when_reflog_expired_and_dry_run(real_repo):
    blob = _scrubbable_blob(real_repo)
    git_reflog_expire(real_repo, dry_run=False)

    result = git_gc(real_repo, prune="now")

    assert _would_prune(result) > 0
    assert "git_reflog_expire first" not in result
    assert "Command: git prune --dry-run --expire=now" in result
    assert _exists(real_repo, blob)


def test_git_gc_reports_before_and_after_when_run_for_real(real_repo):
    _scrubbable_blob(real_repo)
    git_reflog_expire(real_repo, dry_run=False)

    result = git_gc(real_repo, prune="now", aggressive=True, dry_run=False)

    assert result.startswith("✅ git gc --prune=now --aggressive completed")
    assert "Before: count=" in result
    assert "After: count=0" in result


def test_scrub_makes_blob_unreachable_when_reflog_expire_then_gc_run(real_repo):
    blob = _scrubbable_blob(real_repo)
    assert _exists(real_repo, blob)

    git_gc(real_repo, prune="now", dry_run=False)
    assert _exists(real_repo, blob), "reflogs still keep the blob alive"

    git_reflog_expire(real_repo, dry_run=False)
    assert _exists(real_repo, blob), "expiring reflogs alone does not delete objects"

    git_gc(real_repo, prune="now", dry_run=False)
    assert not _exists(real_repo, blob)


def test_git_gc_keeps_reflog_entries_when_config_says_expire_now(real_repo):
    _with_stash(real_repo)
    commit(real_repo, {"more.txt": "x"}, "more", 3)
    with real_repo.config_writer() as config:
        config.set_value("gc", "reflogExpire", "now")
        config.set_value("gc", "reflogExpireUnreachable", "now")
    before = _counts(real_repo)
    assert before["refs/stash"] == 1
    assert before["refs/heads/main"] > 0

    git_gc(real_repo, prune="now", dry_run=False)

    assert _counts(real_repo) == before


def test_git_gc_omits_reflog_note_when_only_stash_has_reflog(real_repo):
    _with_stash(real_repo)
    git_reflog_expire(real_repo, dry_run=False)

    result = git_gc(real_repo)

    assert "git_reflog_expire first" not in result


@pytest.mark.parametrize("tool", ["expire", "gc"])
def test_tools_note_untouched_head_reflogs_when_linked_worktree_exists(
    real_repo, tmp_path, tool
):
    real_repo.git.worktree("add", str(tmp_path / "wt"), "-b", "wt-branch")

    result = git_reflog_expire(real_repo) if tool == "expire" else git_gc(real_repo)

    assert "other linked worktrees exist" in result
    assert "HEAD reflogs were not touched" in result


@pytest.mark.parametrize("tool", ["expire", "gc"])
def test_tools_omit_worktree_note_when_no_linked_worktree(real_repo, tool):
    result = git_reflog_expire(real_repo) if tool == "expire" else git_gc(real_repo)

    assert "linked worktrees" not in result


@pytest.mark.parametrize("value", _BAD)
@pytest.mark.parametrize("param", ["expire", "expire_unreachable"])
def test_git_reflog_expire_returns_failure_without_calling_git_when_value_invalid(
    param, value
):
    repo = Mock()

    result = git_reflog_expire(repo, **{param: value})

    assert isinstance(result, ToolFailure)
    assert result.startswith(f"❌ Invalid {param} value")
    assert repo.mock_calls == []


@pytest.mark.parametrize("value", _BAD)
def test_git_gc_returns_failure_without_calling_git_when_prune_invalid(value):
    repo = Mock()

    result = git_gc(repo, prune=value, dry_run=False)

    assert isinstance(result, ToolFailure)
    assert result.startswith("❌ Invalid prune value")
    assert repo.mock_calls == []


@pytest.mark.parametrize("value", _GOOD)
def test_git_reflog_expire_accepts_value_when_form_allowed(real_repo, value):
    _scrubbable_blob(real_repo)

    result = git_reflog_expire(real_repo, expire=value, expire_unreachable=value)

    assert not isinstance(result, ToolFailure), result


@pytest.mark.parametrize("value", _GOOD)
def test_git_gc_accepts_value_when_form_allowed(real_repo, value):
    result = git_gc(real_repo, prune=value)

    assert not isinstance(result, ToolFailure), result
