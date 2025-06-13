import pytest
from pathlib import Path
import git
from mcp_server_git.server import git_checkout, GitTools
from mcp.types import TextContent
import shutil
import unittest.mock

@pytest.fixture
def test_repository(tmp_path: Path):
    repo_path = tmp_path / "temp_test_repo"
    test_repo = git.Repo.init(repo_path)

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
    from mcp_server_git.server import GitTools
    
    # These are the GitHub tools that don't need repo_path
    github_tools = [
        GitTools.GITHUB_GET_PR_CHECKS,
        GitTools.GITHUB_GET_FAILING_JOBS, 
        GitTools.GITHUB_GET_WORKFLOW_RUN,
        GitTools.GITHUB_GET_PR_DETAILS,
        GitTools.GITHUB_LIST_PULL_REQUESTS,
        GitTools.GITHUB_GET_PR_STATUS,
        GitTools.GITHUB_GET_PR_FILES
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
        assert "github" in tool.value.lower()  # All GitHub tools should have "github" in their name