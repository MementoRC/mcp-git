"""
Unit tests for git_branch_list operation in mcp_server_git.git.operations module.

These tests verify the git_branch_list function that lists local and remote branches
with optional filtering capabilities.
"""

from unittest.mock import MagicMock, Mock, PropertyMock

import pytest

from mcp_server_git.git.operations import git_branch_list
from mcp_server_git.utils.git_import import GitCommandError


def _make_head(name: str, sha: str, is_active: bool = False, tracking: str | None = None) -> Mock:
    """Build a mock GitPython Head object."""
    head = Mock()
    head.name = name
    head.commit.hexsha = sha
    if tracking:
        tb = Mock()
        tb.name = tracking
        head.tracking_branch.return_value = tb
    else:
        head.tracking_branch.return_value = None
    return head


def _make_remote_ref(name: str, sha: str) -> Mock:
    ref = Mock()
    ref.name = name
    ref.commit.hexsha = sha
    return ref


def _make_repo(
    local_heads: list[Mock],
    active_name: str | None = None,
    remotes: list[list[Mock]] | None = None,
) -> Mock:
    """Build a minimal mock Repo."""
    repo = Mock()

    # repo.branches → list of local head mocks
    type(repo).branches = PropertyMock(return_value=local_heads)

    # repo.active_branch
    if active_name is not None:
        active = Mock()
        active.name = active_name
        type(repo).active_branch = PropertyMock(return_value=active)
    else:
        # Simulate detached HEAD
        active_prop = PropertyMock(side_effect=TypeError("detached HEAD"))
        type(repo).active_branch = active_prop

    # repo.remotes
    remote_mocks = []
    for ref_list in (remotes or []):
        remote = Mock()
        remote.refs = ref_list
        remote_mocks.append(remote)
    type(repo).remotes = PropertyMock(return_value=remote_mocks)

    return repo


class TestGitBranchListLocal:
    """Tests for local branch listing (default behavior)."""

    def test_lists_local_branches_returns_structured_output(self):
        """Should list local branches with sha and marker."""
        heads = [
            _make_head("develop", "aaa" * 14, is_active=False),
            _make_head("main", "bbb" * 14, is_active=True),
            _make_head("feature/new-feature", "ccc" * 14),
        ]
        repo = _make_repo(heads, active_name="main")

        result = git_branch_list(repo)

        assert "Branches:" in result
        assert "develop" in result
        assert "* main" in result
        assert "feature/new-feature" in result

    def test_lists_local_branches_with_upstream(self):
        """Should include upstream tracking info when present."""
        heads = [
            _make_head("main", "aaa" * 14, is_active=True, tracking="origin/main"),
        ]
        repo = _make_repo(heads, active_name="main")

        result = git_branch_list(repo)

        assert "-> origin/main" in result

    def test_no_branches_returns_no_branches_found(self):
        """Should return 'No branches found' when repo has no local branches."""
        repo = _make_repo([], active_name=None)

        result = git_branch_list(repo)

        assert "No branches found" in result

    def test_pattern_filters_branches(self):
        """Pattern glob should filter branch names."""
        heads = [
            _make_head("feature/task-1", "aaa" * 14),
            _make_head("feature/task-2", "bbb" * 14),
            _make_head("main", "ccc" * 14, is_active=True),
        ]
        repo = _make_repo(heads, active_name="main")

        result = git_branch_list(repo, pattern="feature/*")

        assert "feature/task-1" in result
        assert "feature/task-2" in result
        assert "main" not in result

    def test_empty_pattern_is_ignored(self):
        """Empty pattern string should not filter branches."""
        heads = [_make_head("main", "aaa" * 14, is_active=True)]
        repo = _make_repo(heads, active_name="main")

        result = git_branch_list(repo, pattern="")

        assert "main" in result

    def test_pattern_no_match_returns_no_branches_found(self):
        """Pattern that matches nothing returns 'No branches found'."""
        heads = [_make_head("main", "aaa" * 14, is_active=True)]
        repo = _make_repo(heads, active_name="main")

        result = git_branch_list(repo, pattern="nonexistent/*")

        assert "No branches found" in result


class TestGitBranchListRemote:
    """Tests for remote branch listing via branch_type='remote'."""

    def test_lists_remote_branches(self):
        """branch_type='remote' lists remote refs."""
        refs = [
            _make_remote_ref("origin/develop", "aaa" * 14),
            _make_remote_ref("origin/main", "bbb" * 14),
        ]
        repo = _make_repo([], active_name=None, remotes=[refs])

        result = git_branch_list(repo, branch_type="remote")

        assert "origin/develop" in result
        assert "origin/main" in result

    def test_remote_skips_head_ref(self):
        """Remote HEAD refs (origin/HEAD) should not appear in output."""
        refs = [
            _make_remote_ref("origin/HEAD", "aaa" * 14),
            _make_remote_ref("origin/main", "bbb" * 14),
        ]
        repo = _make_repo([], active_name=None, remotes=[refs])

        result = git_branch_list(repo, branch_type="remote")

        assert "origin/HEAD" not in result
        assert "origin/main" in result


class TestGitBranchListAll:
    """Tests for all-branches listing via branch_type='all'."""

    def test_lists_local_and_remote(self):
        """branch_type='all' includes both local and remote branches."""
        heads = [_make_head("main", "aaa" * 14, is_active=True)]
        refs = [_make_remote_ref("origin/main", "aaa" * 14)]
        repo = _make_repo(heads, active_name="main", remotes=[refs])

        result = git_branch_list(repo, branch_type="all")

        assert "* main" in result
        assert "origin/main" in result


class TestGitBranchListContains:
    """Tests for 'contains' commit-ish filter."""

    def test_contains_filters_to_matching_branches(self):
        """Only branches containing the given commit should appear."""
        heads = [
            _make_head("feature/x", "aaa" * 14),
            _make_head("main", "bbb" * 14, is_active=True),
        ]
        repo = _make_repo(heads, active_name="main")
        # git branch --contains abc123 returns only 'feature/x'
        repo.git.branch.return_value = "  feature/x"

        result = git_branch_list(repo, contains="abc123")

        assert "feature/x" in result
        assert "main" not in result
        repo.git.branch.assert_called_once_with("--contains", "abc123")

    def test_contains_no_match_returns_no_branches_found(self):
        """If no branches contain the commit, return 'No branches found'."""
        heads = [_make_head("main", "aaa" * 14, is_active=True)]
        repo = _make_repo(heads, active_name="main")
        repo.git.branch.return_value = ""

        result = git_branch_list(repo, contains="deadbeef")

        assert "No branches found" in result


class TestGitBranchListMerged:
    """Tests for 'merged' filter."""

    def test_merged_true_filters_to_merged_branches(self):
        """merged=True should keep only branches in --merged output."""
        heads = [
            _make_head("merged-feat", "aaa" * 14),
            _make_head("main", "bbb" * 14, is_active=True),
        ]
        repo = _make_repo(heads, active_name="main")
        repo.git.branch.return_value = "  merged-feat\n* main"

        result = git_branch_list(repo, merged=True)

        assert "merged-feat" in result
        assert "* main" in result
        repo.git.branch.assert_called_once_with("--merged")

    def test_merged_false_filters_to_unmerged_branches(self):
        """merged=False should keep only branches in --no-merged output."""
        heads = [
            _make_head("unmerged-feat", "aaa" * 14),
            _make_head("main", "bbb" * 14, is_active=True),
        ]
        repo = _make_repo(heads, active_name="main")
        repo.git.branch.return_value = "  unmerged-feat"

        result = git_branch_list(repo, merged=False)

        assert "unmerged-feat" in result
        assert "main" not in result
        repo.git.branch.assert_called_once_with("--no-merged")

    def test_merged_none_does_not_filter(self):
        """merged=None (default) should not call --merged/--no-merged."""
        heads = [_make_head("main", "aaa" * 14, is_active=True)]
        repo = _make_repo(heads, active_name="main")

        git_branch_list(repo, merged=None)

        repo.git.branch.assert_not_called()


class TestGitBranchListBackCompat:
    """Tests for deprecated remote/all bool aliases (back-compat)."""

    def test_legacy_remote_true_maps_to_branch_type_remote(self):
        """remote=True should behave like branch_type='remote'."""
        refs = [_make_remote_ref("origin/main", "aaa" * 14)]
        repo = _make_repo([], active_name=None, remotes=[refs])

        result = git_branch_list(repo, remote=True)

        assert "origin/main" in result

    def test_legacy_all_true_maps_to_branch_type_all(self):
        """all=True should behave like branch_type='all'."""
        heads = [_make_head("main", "aaa" * 14, is_active=True)]
        refs = [_make_remote_ref("origin/main", "aaa" * 14)]
        repo = _make_repo(heads, active_name="main", remotes=[refs])

        result = git_branch_list(repo, all=True)

        assert "main" in result
        assert "origin/main" in result

    def test_legacy_all_takes_precedence_over_remote(self):
        """When both all=True and remote=True, all wins."""
        heads = [_make_head("main", "aaa" * 14, is_active=True)]
        refs = [_make_remote_ref("origin/main", "aaa" * 14)]
        repo = _make_repo(heads, active_name="main", remotes=[refs])

        result = git_branch_list(repo, all=True, remote=True)

        assert "main" in result
        assert "origin/main" in result

    def test_branch_type_conflicts_with_legacy_remote_raises_error(self):
        """Mixing branch_type (non-default) with remote=True → ❌ error."""
        repo = _make_repo([], active_name=None)

        result = git_branch_list(repo, branch_type="remote", remote=True)

        assert "❌ Branch list error:" in result
        assert "Cannot combine" in result

    def test_branch_type_conflicts_with_legacy_all_raises_error(self):
        """Mixing branch_type (non-default) with all=True → ❌ error."""
        repo = _make_repo([], active_name=None)

        result = git_branch_list(repo, branch_type="all", all=True)

        assert "❌ Branch list error:" in result
        assert "Cannot combine" in result


class TestGitBranchListErrors:
    """Tests for error handling."""

    def test_handles_git_command_error(self):
        """GitCommandError during branch listing returns ❌ message."""
        repo = Mock()
        type(repo).branches = PropertyMock(
            side_effect=GitCommandError("branch", "fatal: not a git repository")
        )
        type(repo).active_branch = PropertyMock(return_value=Mock(name="main"))
        type(repo).remotes = PropertyMock(return_value=[])

        result = git_branch_list(repo)

        assert "❌ Branch list failed:" in result

    def test_handles_generic_exception(self):
        """Unexpected exceptions return ❌ message."""
        repo = Mock()
        type(repo).branches = PropertyMock(side_effect=Exception("Unexpected error"))
        type(repo).active_branch = PropertyMock(return_value=Mock(name="main"))
        type(repo).remotes = PropertyMock(return_value=[])

        result = git_branch_list(repo)

        assert "❌ Branch list error:" in result
        assert "Unexpected error" in result
