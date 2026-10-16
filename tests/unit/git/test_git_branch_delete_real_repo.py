"""git_branch_delete pins -d / -D semantics against a real repo (issue #283)."""

from mcp_server_git.git.operations_extended import git_branch_delete
from mcp_server_git.utils.tool_failure import ToolFailure


def _unmerged_branch(repo, name="feature"):
    repo.git.checkout("-b", name)
    repo.index.commit("work only on feature")
    repo.git.checkout("main")


def test_git_branch_delete_refuses_unmerged_branch_when_force_not_given(real_repo):
    _unmerged_branch(real_repo)

    result = git_branch_delete(real_repo, "feature")

    assert isinstance(result, ToolFailure)
    assert "not fully merged" in result
    assert "feature" in [b.name for b in real_repo.branches]


def test_git_branch_delete_deletes_unmerged_branch_when_force_true(real_repo):
    _unmerged_branch(real_repo)

    result = git_branch_delete(real_repo, "feature", force=True)

    assert result.startswith("✅")
    assert "feature" not in [b.name for b in real_repo.branches]


def test_git_branch_delete_deletes_merged_branch_when_force_not_given(real_repo):
    real_repo.create_head("done")

    result = git_branch_delete(real_repo, "done")

    assert result.startswith("✅")
    assert "done" not in [b.name for b in real_repo.branches]
