"""git_checkout(orphan=True) creates an unborn branch (issue #283)."""

from mcp_server_git.git._branch_ops import git_checkout
from mcp_server_git.utils.tool_failure import ToolFailure


def test_git_checkout_creates_unborn_branch_when_orphan_true(real_repo):
    result = git_checkout(real_repo, "fresh-root", orphan=True)

    assert result.startswith("✅")
    assert not isinstance(result, ToolFailure)
    assert real_repo.active_branch.name == "fresh-root"
    assert not real_repo.head.is_valid()


def test_git_checkout_root_commit_has_no_parent_when_committed_on_orphan(real_repo):
    git_checkout(real_repo, "fresh-root", orphan=True)

    real_repo.index.commit("new root")

    assert real_repo.head.commit.parents == ()


def test_git_checkout_fails_when_orphan_branch_name_exists(real_repo):
    result = git_checkout(real_repo, "main", orphan=True)

    assert isinstance(result, ToolFailure)
    assert "already exists" in result
    assert real_repo.head.is_valid()
