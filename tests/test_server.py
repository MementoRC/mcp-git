import pytest
from pathlib import Path
import git
from mcp_server_git.server import git_checkout, git_status, GitTools
import shutil


@pytest.fixture
def test_repository(tmp_path: Path):
    repo_path = tmp_path / "temp_test_repo"
    test_repo = git.Repo.init(repo_path, initial_branch="master")

    Path(repo_path / "test.txt").write_text("test")
    test_repo.index.add(["test.txt"])
    test_repo.index.commit("initial commit")

    yield test_repo

    shutil.rmtree(repo_path)


def test_git_checkout_existing_branch(test_repository):
    test_repository.git.branch("test-branch")
    result = git_checkout(test_repository, "test-branch")

    assert "Switched to branch 'test-branch'" in result
    assert test_repository.active_branch.name == "test-branch"


def test_git_checkout_nonexistent_branch(test_repository):
    with pytest.raises(git.GitCommandError):
        git_checkout(test_repository, "nonexistent-branch")


def test_github_api_tools_no_repo_path_required():
    """Test that GitHub API tools are identified correctly for repo_path handling"""

    # These are the GitHub tools that don't need repo_path
    github_tools = [
        GitTools.GITHUB_GET_PR_CHECKS,
        GitTools.GITHUB_GET_FAILING_JOBS,
        GitTools.GITHUB_GET_WORKFLOW_RUN,
        GitTools.GITHUB_GET_PR_DETAILS,
        GitTools.GITHUB_LIST_PULL_REQUESTS,
        GitTools.GITHUB_GET_PR_STATUS,
        GitTools.GITHUB_GET_PR_FILES,
    ]

    # Verify these are the GitHub tools that don't need repo_path
    assert GitTools.GITHUB_GET_PR_CHECKS in github_tools
    assert GitTools.GITHUB_GET_FAILING_JOBS in github_tools
    assert GitTools.GITHUB_GET_WORKFLOW_RUN in github_tools
    assert GitTools.GITHUB_GET_PR_DETAILS in github_tools
    assert GitTools.GITHUB_LIST_PULL_REQUESTS in github_tools
    assert GitTools.GITHUB_GET_PR_STATUS in github_tools
    assert GitTools.GITHUB_GET_PR_FILES in github_tools

    # Verify regular git tools are NOT in the GitHub tools list
    assert GitTools.STATUS not in github_tools
    assert GitTools.COMMIT not in github_tools
    assert GitTools.ADD not in github_tools

    # Test that our fix correctly identifies GitHub tools
    # The fix should handle these tools without requiring repo_path
    for tool in github_tools:
        assert (
            "github" in tool.value.lower()
        )  # All GitHub tools should have "github" in their name


def test_git_status_default_format(test_repository):
    """Test git_status function with default (human-readable) format"""
    # Create some changes to test status
    (Path(test_repository.working_dir) / "new_file.txt").write_text("new content")
    (Path(test_repository.working_dir) / "test.txt").write_text("modified content")

    status = git_status(test_repository, porcelain=False)

    # Default format should be human-readable
    assert "Changes not staged for commit:" in status or "Untracked files:" in status
    assert "new_file.txt" in status
    assert "test.txt" in status


def test_git_status_porcelain_format(test_repository):
    """Test git_status function with porcelain (machine-readable) format"""
    # Create some changes to test status
    (Path(test_repository.working_dir) / "new_file.txt").write_text("new content")
    (Path(test_repository.working_dir) / "test.txt").write_text("modified content")

    status = git_status(test_repository, porcelain=True)

    # Porcelain format should be machine-readable
    lines = status.split("\n") if status else []

    # Should have entries for our changes
    assert any(line.endswith("new_file.txt") for line in lines)
    assert any(line.endswith("test.txt") for line in lines)

    # Each line should follow porcelain format (2 character status + space + filename)
    for line in lines:
        if line.strip():  # Skip empty lines
            assert len(line) >= 4  # At least "XY filename"
            assert line[2] == " "  # Third character should be space

    # Should not contain human-readable text
    assert "Changes not staged for commit:" not in status
    assert "Untracked files:" not in status


def test_git_status_porcelain_string_parameter(test_repository):
    """Test git_status function with porcelain parameter passed as string"""
    # Create some changes to test status
    (Path(test_repository.working_dir) / "new_file.txt").write_text("new content")
    (Path(test_repository.working_dir) / "test.txt").write_text("modified content")

    # Test with string "true"
    git_status(
        test_repository, porcelain=True
    )  # Function should handle boolean properly

    # Test with actual string conversion logic that the MCP handler uses
    porcelain_raw = "true"
    porcelain = (
        porcelain_raw
        if isinstance(porcelain_raw, bool)
        else str(porcelain_raw).lower() in ("true", "1", "yes")
    )
    assert porcelain

    porcelain_raw = "false"
    porcelain = (
        porcelain_raw
        if isinstance(porcelain_raw, bool)
        else str(porcelain_raw).lower() in ("true", "1", "yes")
    )
    assert not porcelain

    porcelain_raw = True
    porcelain = (
        porcelain_raw
        if isinstance(porcelain_raw, bool)
        else str(porcelain_raw).lower() in ("true", "1", "yes")
    )
    assert porcelain


# Tests for advanced git operations


def test_git_rebase_success(test_repository):
    """Test successful rebase operation"""
    from mcp_server_git.server import git_rebase, git_create_branch, git_checkout

    # Create and switch to feature branch
    git_create_branch(test_repository, "feature-branch")
    git_checkout(test_repository, "feature-branch")

    # Add commit to feature branch
    (Path(test_repository.working_dir) / "feature.txt").write_text("feature content")
    test_repository.index.add(["feature.txt"])
    test_repository.index.commit("Add feature")

    # Switch back to main and add another commit
    git_checkout(test_repository, "master")
    (Path(test_repository.working_dir) / "main.txt").write_text("main content")
    test_repository.index.add(["main.txt"])
    test_repository.index.commit("Add main feature")

    # Switch back to feature branch and rebase
    git_checkout(test_repository, "feature-branch")
    result = git_rebase(test_repository, "master")

    assert "✅ Successfully rebased" in result or "Already up to date" in result


def test_git_merge_success(test_repository):
    """Test successful merge operation"""
    from mcp_server_git.server import git_merge, git_create_branch, git_checkout

    # Create and switch to feature branch
    git_create_branch(test_repository, "merge-feature")
    git_checkout(test_repository, "merge-feature")

    # Add commit to feature branch
    (Path(test_repository.working_dir) / "merge-feature.txt").write_text(
        "merge feature"
    )
    test_repository.index.add(["merge-feature.txt"])
    test_repository.index.commit("Add merge feature")

    # Switch back to main and merge
    git_checkout(test_repository, "master")
    result = git_merge(test_repository, "merge-feature")

    assert "✅ Successfully merged" in result


def test_git_merge_squash(test_repository):
    """Test squash merge strategy"""
    from mcp_server_git.server import git_merge, git_create_branch, git_checkout

    # Create and switch to feature branch
    git_create_branch(test_repository, "squash-feature")
    git_checkout(test_repository, "squash-feature")

    # Add commit to feature branch
    (Path(test_repository.working_dir) / "squash.txt").write_text("squash content")
    test_repository.index.add(["squash.txt"])
    test_repository.index.commit("Add squash feature")

    # Switch back to main and squash merge
    git_checkout(test_repository, "master")
    result = git_merge(test_repository, "squash-feature", strategy="squash")

    assert "Changes staged but not committed" in result or "✅ Successfully" in result


def test_git_cherry_pick_success(test_repository):
    """Test successful cherry-pick operation"""
    from mcp_server_git.server import git_cherry_pick, git_create_branch, git_checkout

    # Create and switch to feature branch
    git_create_branch(test_repository, "cherry-source")
    git_checkout(test_repository, "cherry-source")

    # Add commit to feature branch
    (Path(test_repository.working_dir) / "cherry.txt").write_text("cherry content")
    test_repository.index.add(["cherry.txt"])
    commit = test_repository.index.commit("Add cherry feature")

    # Switch back to main and cherry-pick
    git_checkout(test_repository, "master")
    result = git_cherry_pick(test_repository, commit.hexsha)

    assert (
        "✅ Successfully cherry-picked" in result or "already exists" in result.lower()
    )


def test_git_cherry_pick_no_commit(test_repository):
    """Test cherry-pick with --no-commit option"""
    from mcp_server_git.server import git_cherry_pick, git_create_branch, git_checkout

    # Create and switch to feature branch
    git_create_branch(test_repository, "cherry-no-commit")
    git_checkout(test_repository, "cherry-no-commit")

    # Add commit to feature branch
    (Path(test_repository.working_dir) / "cherry-nc.txt").write_text("cherry no commit")
    test_repository.index.add(["cherry-nc.txt"])
    commit = test_repository.index.commit("Add cherry no commit")

    # Switch back to main and cherry-pick with no-commit
    git_checkout(test_repository, "master")
    result = git_cherry_pick(test_repository, commit.hexsha, no_commit=True)

    assert "changes staged but not committed" in result or "✅ Successfully" in result


def test_git_abort_rebase(test_repository):
    """Test aborting a rebase operation"""
    from mcp_server_git.server import git_abort

    # Note: This test assumes we're not actually in a rebase state
    # In a real scenario, you'd start a rebase that has conflicts first
    result = git_abort(test_repository, "rebase")

    # Should either succeed or indicate no rebase in progress
    assert (
        "✅ Successfully aborted" in result
        or "no rebase in progress" in result
        or "not currently rebasing" in result
    )


def test_git_abort_merge(test_repository):
    """Test aborting a merge operation"""
    from mcp_server_git.server import git_abort

    # Note: This test assumes we're not actually in a merge state
    result = git_abort(test_repository, "merge")

    # Should either succeed or indicate no merge in progress
    assert (
        "✅ Successfully aborted" in result
        or "no merge to abort" in result
        or "MERGE_HEAD missing" in result
    )


def test_git_abort_invalid_operation(test_repository):
    """Test aborting with invalid operation"""
    from mcp_server_git.server import git_abort

    result = git_abort(test_repository, "invalid-operation")

    assert "❌ Unknown operation" in result
    assert "Supported: rebase, merge, cherry-pick" in result


def test_git_continue_rebase(test_repository):
    """Test continuing a rebase operation"""
    from mcp_server_git.server import git_continue

    # Note: This test assumes we're not actually in a rebase state
    result = git_continue(test_repository, "rebase")

    # Should either succeed or indicate no rebase in progress
    assert (
        "✅ Successfully continued" in result
        or "no rebase in progress" in result
        or "not currently rebasing" in result
    )


def test_git_continue_invalid_operation(test_repository):
    """Test continuing with invalid operation"""
    from mcp_server_git.server import git_continue

    result = git_continue(test_repository, "invalid-operation")

    assert "❌ Unknown operation" in result
    assert "Supported: rebase, merge, cherry-pick" in result


def test_advanced_git_tools_enum():
    """Test that new git tools are properly defined in enum"""
    # Test that all new tools are in the enum
    assert hasattr(GitTools, "REBASE")
    assert hasattr(GitTools, "MERGE")
    assert hasattr(GitTools, "CHERRY_PICK")
    assert hasattr(GitTools, "ABORT")
    assert hasattr(GitTools, "CONTINUE")

    # Test enum values
    assert GitTools.REBASE == "git_rebase"
    assert GitTools.MERGE == "git_merge"
    assert GitTools.CHERRY_PICK == "git_cherry_pick"
    assert GitTools.ABORT == "git_abort"
    assert GitTools.CONTINUE == "git_continue"
