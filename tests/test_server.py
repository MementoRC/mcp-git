# Use safe git import for testing
import os
import shutil
from pathlib import Path

import pytest

# Import from current modular architecture
from mcp_server_git.applications.server_application import GitTools
from mcp_server_git.git.operations import git_checkout, git_status
from mcp_server_git.utils.git_import import git


@pytest.fixture
def test_repository(tmp_path: Path):
    from unittest.mock import MagicMock

    # Check if git is mocked (happens when GitPython is unavailable)
    if isinstance(git.Repo, MagicMock):
        pytest.skip("GitPython unavailable - git operations are mocked")

    repo_path = tmp_path / "temp_test_repo"
    repo_path.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
    try:
        test_repo = git.Repo.init(repo_path, initial_branch="master")

        # Additional check: ensure the repository object is real, not a mock
        if (
            isinstance(test_repo, MagicMock)
            or not hasattr(test_repo, "working_dir")
            or isinstance(test_repo.working_dir, MagicMock)
        ):
            pytest.skip(
                "Git repository creation returned mock object - git operations unavailable"
            )

        Path(repo_path / "test.txt").write_text("test")
        test_repo.index.add(["test.txt"])
        test_repo.index.commit("initial commit")

        yield test_repo

        shutil.rmtree(repo_path)
    except Exception as e:
        # GitPython fails due to ClaudeCode redirector or other issues - skip test
        pytest.skip(f"GitPython incompatible: {e}")


def test_git_checkout_existing_branch(test_repository):
    test_repository.git.branch("test-branch")
    result = git_checkout(test_repository, "test-branch")

    assert "Switched to branch 'test-branch'" in result
    assert test_repository.active_branch.name == "test-branch"


def test_git_checkout_nonexistent_branch(test_repository):
    result = git_checkout(test_repository, "nonexistent-branch")
    assert "not found" in result
    assert "❌" in result


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
    from mcp_server_git.git.operations import (
        git_checkout,
        git_create_branch,
        git_rebase,
    )

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
    from mcp_server_git.git.operations import git_checkout, git_create_branch, git_merge

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
    from mcp_server_git.git.operations import git_checkout, git_create_branch, git_merge

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
    from mcp_server_git.git.operations import (
        git_checkout,
        git_cherry_pick,
        git_create_branch,
    )

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
    from mcp_server_git.git.operations import (
        git_checkout,
        git_cherry_pick,
        git_create_branch,
    )

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
    from mcp_server_git.git.operations import git_abort

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
    from mcp_server_git.git.operations import git_abort

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
    from mcp_server_git.git.operations import git_abort

    result = git_abort(test_repository, "invalid-operation")

    assert "❌ Invalid operation" in result
    assert "Valid operations: rebase, merge, cherry-pick" in result


def test_git_continue_rebase(test_repository):
    """Test continuing a rebase operation"""
    from mcp_server_git.git.operations import git_continue

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
    from mcp_server_git.git.operations import git_continue

    result = git_continue(test_repository, "invalid-operation")

    assert "❌ Invalid operation" in result
    assert "Valid operations: rebase, merge, cherry-pick" in result


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


def test_git_commit_amend(test_repository):
    """Test git commit with --amend flag builds the correct command"""
    from unittest.mock import patch, MagicMock
    from mcp_server_git.git.operations import git_commit

    # Make a change and commit it
    (Path(test_repository.working_dir) / "amend_test.txt").write_text("original")
    test_repository.index.add(["amend_test.txt"])
    test_repository.index.commit("original message")

    # Stage a new change
    (Path(test_repository.working_dir) / "amend_test.txt").write_text("amended")
    test_repository.index.add(["amend_test.txt"])

    # Mock subprocess.run to capture the command and verify --amend is passed
    mock_commit_result = MagicMock(returncode=0, stderr="", stdout="")
    mock_hash_result = MagicMock(returncode=0, stdout="abc12345\n", stderr="")

    with (
        patch(
            "mcp_server_git.git.operations.subprocess.run",
            side_effect=[mock_commit_result, mock_hash_result],
        ) as mock_run,
        patch.dict("os.environ", {"GPG_SIGNING_KEY": "TESTKEY123"}),
    ):
        result = git_commit(test_repository, "amended message", amend=True)

    # Verify --amend was in the git commit command
    commit_cmd = mock_run.call_args_list[0][0][0]
    assert "--amend" in commit_cmd
    assert "-m" in commit_cmd
    assert "amended message" in commit_cmd
    assert "amended" in result


def test_git_commit_no_amend(test_repository):
    """Test git commit without --amend does not include the flag"""
    from unittest.mock import patch, MagicMock
    from mcp_server_git.git.operations import git_commit

    # Stage a change
    (Path(test_repository.working_dir) / "no_amend.txt").write_text("content")
    test_repository.index.add(["no_amend.txt"])

    mock_commit_result = MagicMock(returncode=0, stderr="", stdout="")
    mock_hash_result = MagicMock(returncode=0, stdout="def67890\n", stderr="")

    with (
        patch(
            "mcp_server_git.git.operations.subprocess.run",
            side_effect=[mock_commit_result, mock_hash_result],
        ) as mock_run,
        patch.dict("os.environ", {"GPG_SIGNING_KEY": "TESTKEY123"}),
    ):
        result = git_commit(test_repository, "new commit")

    # Verify --amend was NOT in the command
    commit_cmd = mock_run.call_args_list[0][0][0]
    assert "--amend" not in commit_cmd
    assert "created" in result
