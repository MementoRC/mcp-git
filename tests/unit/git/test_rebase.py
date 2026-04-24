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
