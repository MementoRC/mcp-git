"""Unit tests for git_rebase --onto and fork-point support (#159)."""

import pytest
from pydantic import ValidationError

from mcp_server_git.git.models import GitRebase


class TestGitRebaseModel:
    """Tests for GitRebase Pydantic model."""

    def test_model_accepts_target_branch_only(self):
        """Existing behavior: just repo_path + target_branch."""
        m = GitRebase(repo_path="/tmp/repo", target_branch="main")
        assert m.target_branch == "main"
        assert m.onto is None
        assert m.fork_point is None
        assert m.branch is None

    def test_model_accepts_onto_with_fork_point(self):
        m = GitRebase(
            repo_path="/tmp/repo",
            target_branch="main",
            onto="new-base",
            fork_point="old-base",
        )
        assert m.onto == "new-base"
        assert m.fork_point == "old-base"

    def test_model_accepts_branch_param(self):
        m = GitRebase(
            repo_path="/tmp/repo",
            target_branch="main",
            branch="feature",
        )
        assert m.branch == "feature"

    def test_model_accepts_all_params(self):
        m = GitRebase(
            repo_path="/tmp/repo",
            target_branch="main",
            onto="new-base",
            fork_point="old-base",
            branch="feature",
        )
        assert m.onto == "new-base"
        assert m.fork_point == "old-base"
        assert m.branch == "feature"


from unittest.mock import MagicMock, PropertyMock, patch

from git import GitCommandError

from mcp_server_git.git.operations import git_rebase


def _make_repo(
    branch_name: str = "feature",
    branches: list[str] | None = None,
    remotes: bool = False,
):
    """Create a mock Repo with configurable branches."""
    repo = MagicMock()
    type(repo.active_branch).name = PropertyMock(return_value=branch_name)

    if branches is None:
        branches = ["main", "feature", "development"]
    mock_branches = []
    for b in branches:
        mb = MagicMock()
        mb.name = b
        mock_branches.append(mb)
    repo.branches = mock_branches

    if not remotes:
        repo.remotes = []

    return repo


class TestGitRebaseOnto:
    """Tests for git_rebase with --onto parameter."""

    def test_rebase_simple_returns_success(self):
        """Existing behavior preserved: simple rebase onto target."""
        repo = _make_repo()
        repo.git.rebase.return_value = ""
        result = git_rebase(repo, "main")
        assert "✅" in result
        assert "feature" in result
        repo.git.rebase.assert_called_once_with("main")

    def test_rebase_onto_calls_git_with_onto_flag(self):
        """--onto new-base old-base should pass correct args."""
        repo = _make_repo()
        repo.git.rebase.return_value = ""
        result = git_rebase(repo, "main", onto="new-base", fork_point="old-base")
        assert "✅" in result
        repo.git.rebase.assert_called_once_with("--onto", "new-base", "old-base")

    def test_rebase_onto_with_branch_passes_branch_arg(self):
        """--onto new-base old-base feature should include branch."""
        repo = _make_repo()
        repo.git.rebase.return_value = ""
        result = git_rebase(
            repo, "main", onto="new-base", fork_point="old-base", branch="feature"
        )
        assert "✅" in result
        repo.git.rebase.assert_called_once_with(
            "--onto", "new-base", "old-base", "feature"
        )

    def test_rebase_branch_without_onto_passes_target_and_branch(self):
        """branch param without --onto: git rebase target branch."""
        repo = _make_repo()
        repo.git.rebase.return_value = ""
        result = git_rebase(repo, "main", branch="feature")
        assert "✅" in result
        repo.git.rebase.assert_called_once_with("main", "feature")

    def test_rebase_onto_without_fork_point_returns_error(self):
        """--onto without fork_point is invalid."""
        repo = _make_repo()
        result = git_rebase(repo, "main", onto="new-base")
        assert "❌" in result
        assert "fork_point" in result.lower()

    def test_rebase_fork_point_without_onto_returns_error(self):
        """fork_point without --onto is invalid."""
        repo = _make_repo()
        result = git_rebase(repo, "main", fork_point="old-base")
        assert "❌" in result
        assert "onto" in result.lower()

    def test_rebase_onto_conflict_returns_conflict_msg(self):
        """Conflict during --onto rebase returns conflict message."""
        repo = _make_repo()
        repo.git.rebase.side_effect = GitCommandError("rebase", 128, stderr="conflict")
        result = git_rebase(repo, "main", onto="new-base", fork_point="old-base")
        assert "conflict" in result.lower()

    def test_rebase_onto_git_error_returns_error_msg(self):
        """Non-conflict git error returns error message."""
        repo = _make_repo()
        repo.git.rebase.side_effect = GitCommandError("rebase", 128, stderr="fatal")
        result = git_rebase(repo, "main", onto="new-base", fork_point="old-base")
        assert "❌" in result


class TestGitRebaseRefValidation:
    """Tests for ref parameter validation in git_rebase."""

    @pytest.mark.parametrize(
        "param_name,kwargs",
        [
            ("onto", {"onto": "base;rm -rf", "fork_point": "old"}),
            ("fork_point", {"onto": "base", "fork_point": "old|bad"}),
            ("branch", {"branch": "feat&bad"}),
            ("onto", {"onto": "$(cmd)", "fork_point": "old"}),
            ("fork_point", {"onto": "base", "fork_point": "old`inject`"}),
        ],
    )
    def test_rebase_rejects_dangerous_chars_in_ref(self, param_name, kwargs):
        repo = _make_repo()
        result = git_rebase(repo, "main", **kwargs)
        assert "❌" in result
        assert "Invalid characters" in result
        assert param_name in result

    def test_rebase_allows_valid_ref_chars(self):
        """Refs with slashes, dots, hyphens are valid."""
        repo = _make_repo()
        repo.git.rebase.return_value = ""
        result = git_rebase(
            repo,
            "main",
            onto="origin/feature-branch.v2",
            fork_point="refs/heads/old-base",
        )
        assert "✅" in result
