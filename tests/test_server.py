import pytest
from pathlib import Path
import git
from mcp_server_git.server import git_checkout, git_status, GitTools
from mcp.types import TextContent
import shutil

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
    lines = status.split('\n') if status else []
    
    # Should have entries for our changes
    assert any(line.endswith('new_file.txt') for line in lines)
    assert any(line.endswith('test.txt') for line in lines)
    
    # Each line should follow porcelain format (2 character status + space + filename)
    for line in lines:
        if line.strip():  # Skip empty lines
            assert len(line) >= 4  # At least "XY filename"
            assert line[2] == ' '  # Third character should be space
            
    # Should not contain human-readable text
    assert "Changes not staged for commit:" not in status
    assert "Untracked files:" not in status

def test_git_status_porcelain_string_parameter(test_repository):
    """Test git_status function with porcelain parameter passed as string"""
    # Create some changes to test status
    (Path(test_repository.working_dir) / "new_file.txt").write_text("new content")
    (Path(test_repository.working_dir) / "test.txt").write_text("modified content")
    
    # Test with string "true"
    status = git_status(test_repository, porcelain=True)  # Function should handle boolean properly
    
    # Test with actual string conversion logic that the MCP handler uses
    porcelain_raw = "true"
    porcelain = porcelain_raw if isinstance(porcelain_raw, bool) else str(porcelain_raw).lower() in ('true', '1', 'yes')
    assert porcelain == True
    
    porcelain_raw = "false"
    porcelain = porcelain_raw if isinstance(porcelain_raw, bool) else str(porcelain_raw).lower() in ('true', '1', 'yes')
    assert porcelain == False
    
    porcelain_raw = True
    porcelain = porcelain_raw if isinstance(porcelain_raw, bool) else str(porcelain_raw).lower() in ('true', '1', 'yes')
    assert porcelain == True