"""
Test specifications for Git domain types.

These tests define the behavioral requirements for Git-related type definitions
including repository paths, operations, and validation rules.

IMPORTANT: These tests define requirements and are IMMUTABLE once complete.
Do not modify tests to match implementation - implementation must satisfy these tests.
"""

import pytest
from pathlib import Path
from typing import List, Optional, Union
from unittest.mock import Mock, patch

# Import the types we expect to be implemented
# These imports will fail initially (RED phase) - that's expected!
try:
    from mcp_server_git.types.git_types import (
        GitRepositoryPath,
        GitBranch,
        GitCommitHash,
        GitRemoteName,
        GitFileStatus,
        GitOperationResult,
        GitStatusResult,
        GitDiffResult,
        GitLogResult,
        GitCommitInfo,
        GitBranchInfo,
        GitRemoteInfo,
        GitValidationError,
        GitOperationError,
    )
    TYPES_AVAILABLE = True
except ImportError:
    TYPES_AVAILABLE = False


class TestGitRepositoryPath:
    """Test specifications for GitRepositoryPath type."""
    
    def test_should_accept_valid_git_repository_path(self):
        """GitRepositoryPath should accept valid git repository paths."""
        # ARRANGE: Valid repository path
        valid_path = "/tmp/test-repo/.git"
        
        # ACT & ASSERT: Should create GitRepositoryPath successfully
        if TYPES_AVAILABLE:
            repo_path = GitRepositoryPath(valid_path)
            assert str(repo_path) == valid_path
            assert repo_path.is_valid()
            assert repo_path.exists()
        else:
            pytest.fail("GitRepositoryPath type not implemented - this test should fail until implementation is complete")
    
    def test_should_accept_pathlib_path_objects(self):
        """GitRepositoryPath should accept pathlib.Path objects."""
        # ARRANGE: pathlib Path object
        path_obj = Path("/tmp/test-repo")
        
        # ACT & ASSERT: Should convert Path to GitRepositoryPath
        if TYPES_AVAILABLE:
            repo_path = GitRepositoryPath(path_obj)
            assert isinstance(repo_path.path, Path)
            assert str(repo_path) == str(path_obj)
    
    def test_should_reject_non_git_directories(self):
        """GitRepositoryPath should reject directories without .git."""
        # ARRANGE: Non-git directory
        non_git_path = "/tmp/not-a-repo"
        
        # ACT & ASSERT: Should raise validation error
        if TYPES_AVAILABLE:
            with pytest.raises(GitValidationError) as exc_info:
                GitRepositoryPath(non_git_path)
            assert "not a git repository" in str(exc_info.value).lower()
    
    def test_should_reject_non_existent_paths(self):
        """GitRepositoryPath should reject non-existent paths."""
        # ARRANGE: Non-existent path
        fake_path = "/does/not/exist"
        
        # ACT & ASSERT: Should raise validation error
        if TYPES_AVAILABLE:
            with pytest.raises(GitValidationError) as exc_info:
                GitRepositoryPath(fake_path)
            assert "does not exist" in str(exc_info.value).lower()
    
    def test_should_normalize_relative_paths(self):
        """GitRepositoryPath should normalize relative paths to absolute."""
        # ARRANGE: Relative path
        relative_path = "./test-repo"
        
        # ACT & ASSERT: Should convert to absolute path
        if TYPES_AVAILABLE:
            with patch('pathlib.Path.exists', return_value=True), \
                 patch('pathlib.Path.is_dir', return_value=True), \
                 patch('pathlib.Path.glob', return_value=[Path('.git')]):
                repo_path = GitRepositoryPath(relative_path)
                assert repo_path.path.is_absolute()
    
    def test_should_provide_repository_metadata(self):
        """GitRepositoryPath should provide access to repository metadata."""
        # ARRANGE: Mock git repository
        repo_path_str = "/tmp/test-repo"
        
        # ACT & ASSERT: Should provide metadata access
        if TYPES_AVAILABLE:
            with patch('pathlib.Path.exists', return_value=True), \
                 patch('pathlib.Path.is_dir', return_value=True), \
                 patch('pathlib.Path.glob', return_value=[Path('.git')]):
                repo_path = GitRepositoryPath(repo_path_str)
                
                # Should provide current branch
                assert hasattr(repo_path, 'current_branch')
                # Should provide remote info
                assert hasattr(repo_path, 'remotes')
                # Should provide status check
                assert hasattr(repo_path, 'is_clean')


class TestGitBranch:
    """Test specifications for GitBranch type."""
    
    def test_should_accept_valid_branch_names(self):
        """GitBranch should accept valid git branch names."""
        valid_names = [
            "main",
            "feature/new-component", 
            "bugfix-123",
            "release/v1.0.0",
            "user/john/experimental"
        ]
        
        if TYPES_AVAILABLE:
            for name in valid_names:
                branch = GitBranch(name)
                assert str(branch) == name
                assert branch.is_valid()
    
    def test_should_reject_invalid_branch_names(self):
        """GitBranch should reject invalid git branch names."""
        invalid_names = [
            "",  # Empty
            " ",  # Whitespace only
            "feature..double-dot",  # Double dots
            "~invalid",  # Tilde at start
            "branch^name",  # Caret character
            "branch:name",  # Colon character
            ".hidden",  # Starts with dot
            "branch/",  # Ends with slash
        ]
        
        if TYPES_AVAILABLE:
            for name in invalid_names:
                with pytest.raises(GitValidationError) as exc_info:
                    GitBranch(name)
                assert "invalid branch name" in str(exc_info.value).lower()
    
    def test_should_provide_branch_metadata(self):
        """GitBranch should provide branch metadata and operations."""
        if TYPES_AVAILABLE:
            branch = GitBranch("feature/new-component")
            
            # Should provide branch type classification
            assert hasattr(branch, 'is_feature_branch')
            assert hasattr(branch, 'is_main_branch')
            assert hasattr(branch, 'is_release_branch')
            
            # Should provide branch hierarchy
            assert hasattr(branch, 'parent_branch')
            assert hasattr(branch, 'namespace')


class TestGitCommitHash:
    """Test specifications for GitCommitHash type."""
    
    def test_should_accept_valid_commit_hashes(self):
        """GitCommitHash should accept valid git commit hashes."""
        valid_hashes = [
            "a1b2c3d4e5f6789012345678901234567890abcd",  # Full SHA-1
            "a1b2c3d",  # Short SHA-1 (7 chars)
            "a1b2c3d4e5f",  # Medium SHA-1 (11 chars)
        ]
        
        if TYPES_AVAILABLE:
            for hash_val in valid_hashes:
                commit_hash = GitCommitHash(hash_val)
                assert str(commit_hash) == hash_val
                assert commit_hash.is_valid()
    
    def test_should_reject_invalid_commit_hashes(self):
        """GitCommitHash should reject invalid commit hashes."""
        invalid_hashes = [
            "",  # Empty
            "123",  # Too short
            "g1b2c3d4e5f6789012345678901234567890abcd",  # Invalid character
            "a1b2c3d4e5f6789012345678901234567890abcde",  # Too long
        ]
        
        if TYPES_AVAILABLE:
            for hash_val in invalid_hashes:
                with pytest.raises(GitValidationError) as exc_info:
                    GitCommitHash(hash_val)
                assert "invalid commit hash" in str(exc_info.value).lower()
    
    def test_should_provide_hash_utilities(self):
        """GitCommitHash should provide hash utility methods."""
        if TYPES_AVAILABLE:
            commit_hash = GitCommitHash("a1b2c3d4e5f6789012345678901234567890abcd")
            
            # Should provide short hash
            assert hasattr(commit_hash, 'short')
            assert len(commit_hash.short()) >= 7
            
            # Should provide full hash
            assert hasattr(commit_hash, 'full')
            assert len(commit_hash.full()) == 40


class TestGitFileStatus:
    """Test specifications for GitFileStatus type."""
    
    def test_should_define_all_git_file_statuses(self):
        """GitFileStatus should define all possible git file statuses."""
        expected_statuses = [
            "untracked",
            "modified", 
            "added",
            "deleted",
            "renamed",
            "copied",
            "unmerged",
            "ignored"
        ]
        
        if TYPES_AVAILABLE:
            for status in expected_statuses:
                file_status = GitFileStatus(status)
                assert str(file_status) == status
                assert file_status.is_valid()
    
    def test_should_reject_invalid_file_statuses(self):
        """GitFileStatus should reject invalid file statuses."""
        invalid_statuses = ["unknown", "invalid", "", "123"]
        
        if TYPES_AVAILABLE:
            for status in invalid_statuses:
                with pytest.raises(GitValidationError) as exc_info:
                    GitFileStatus(status)
                assert "invalid file status" in str(exc_info.value).lower()
    
    def test_should_provide_status_predicates(self):
        """GitFileStatus should provide convenient status checking methods."""
        if TYPES_AVAILABLE:
            modified_status = GitFileStatus("modified")
            
            # Should provide status checking predicates
            assert hasattr(modified_status, 'is_modified')
            assert hasattr(modified_status, 'is_staged')
            assert hasattr(modified_status, 'is_untracked')
            assert hasattr(modified_status, 'needs_commit')


class TestGitOperationResult:
    """Test specifications for GitOperationResult type."""
    
    def test_should_represent_successful_operations(self):
        """GitOperationResult should represent successful git operations."""
        if TYPES_AVAILABLE:
            result = GitOperationResult.success(
                output="Operation completed successfully",
                operation="git status"
            )
            
            assert result.is_success()
            assert not result.is_error()
            assert result.output == "Operation completed successfully"
            assert result.operation == "git status"
    
    def test_should_represent_failed_operations(self):
        """GitOperationResult should represent failed git operations."""
        if TYPES_AVAILABLE:
            result = GitOperationResult.error(
                error="Repository not found",
                operation="git status",
                error_code="REPO_NOT_FOUND"
            )
            
            assert not result.is_success()
            assert result.is_error()
            assert result.error == "Repository not found"
            assert result.error_code == "REPO_NOT_FOUND"
    
    def test_should_provide_result_chaining(self):
        """GitOperationResult should support operation chaining."""
        if TYPES_AVAILABLE:
            success_result = GitOperationResult.success("Success", "git add")
            
            # Should support transformation of successful results
            assert hasattr(success_result, 'then')
            assert hasattr(success_result, 'map')
            
            # Should short-circuit on errors
            error_result = GitOperationResult.error("Error", "git add")
            chained = error_result.then(lambda x: x)
            assert chained.is_error()


class TestGitStatusResult:
    """Test specifications for GitStatusResult type."""
    
    def test_should_represent_repository_status(self):
        """GitStatusResult should represent complete repository status."""
        if TYPES_AVAILABLE:
            status = GitStatusResult(
                is_clean=False,
                current_branch=GitBranch("main"),
                modified_files=["file1.py", "file2.py"],
                untracked_files=["new_file.py"],
                staged_files=["staged.py"]
            )
            
            assert not status.is_clean
            assert str(status.current_branch) == "main"
            assert len(status.modified_files) == 2
            assert len(status.untracked_files) == 1
            assert len(status.staged_files) == 1
    
    def test_should_detect_clean_repositories(self):
        """GitStatusResult should correctly identify clean repositories."""
        if TYPES_AVAILABLE:
            clean_status = GitStatusResult(
                is_clean=True,
                current_branch=GitBranch("main"),
                modified_files=[],
                untracked_files=[],
                staged_files=[]
            )
            
            assert clean_status.is_clean
            assert clean_status.has_no_changes()
            assert not clean_status.needs_commit()
    
    def test_should_provide_status_summary(self):
        """GitStatusResult should provide human-readable status summary."""
        if TYPES_AVAILABLE:
            status = GitStatusResult(
                is_clean=False,
                current_branch=GitBranch("feature/test"),
                modified_files=["file1.py"],
                untracked_files=["file2.py"],
                staged_files=["file3.py"]
            )
            
            # Should provide summary methods
            assert hasattr(status, 'summary')
            assert hasattr(status, 'file_count')
            assert hasattr(status, 'needs_attention')


class TestGitCommitInfo:
    """Test specifications for GitCommitInfo type."""
    
    def test_should_represent_complete_commit_information(self):
        """GitCommitInfo should represent complete git commit information."""
        if TYPES_AVAILABLE:
            commit = GitCommitInfo(
                hash=GitCommitHash("a1b2c3d4e5f6789012345678901234567890abcd"),
                author_name="John Doe",
                author_email="john@example.com",
                message="Fix critical bug in authentication",
                timestamp="2023-12-01T10:00:00Z",
                parent_hashes=[GitCommitHash("b2c3d4e5f6789012345678901234567890abcde1")]
            )
            
            assert str(commit.hash) == "a1b2c3d4e5f6789012345678901234567890abcd"
            assert commit.author_name == "John Doe"
            assert commit.author_email == "john@example.com"
            assert commit.message == "Fix critical bug in authentication"
            assert len(commit.parent_hashes) == 1
    
    def test_should_validate_commit_data(self):
        """GitCommitInfo should validate commit data integrity."""
        if TYPES_AVAILABLE:
            # Should reject invalid email addresses
            with pytest.raises(GitValidationError):
                GitCommitInfo(
                    hash=GitCommitHash("a1b2c3d"),
                    author_name="John Doe",
                    author_email="invalid-email",  # Invalid email
                    message="Test commit",
                    timestamp="2023-12-01T10:00:00Z"
                )
            
            # Should reject empty commit messages
            with pytest.raises(GitValidationError):
                GitCommitInfo(
                    hash=GitCommitHash("a1b2c3d"),
                    author_name="John Doe", 
                    author_email="john@example.com",
                    message="",  # Empty message
                    timestamp="2023-12-01T10:00:00Z"
                )
    
    def test_should_provide_commit_utilities(self):
        """GitCommitInfo should provide commit utility methods."""
        if TYPES_AVAILABLE:
            commit = GitCommitInfo(
                hash=GitCommitHash("a1b2c3d4e5f6789012345678901234567890abcd"),
                author_name="John Doe",
                author_email="john@example.com", 
                message="feat: add new authentication system",
                timestamp="2023-12-01T10:00:00Z"
            )
            
            # Should categorize commit types
            assert hasattr(commit, 'is_feature')
            assert hasattr(commit, 'is_bugfix')
            assert hasattr(commit, 'is_breaking_change')
            
            # Should provide formatting options
            assert hasattr(commit, 'one_line_summary')
            assert hasattr(commit, 'detailed_summary')


# Integration tests between types
class TestGitTypeIntegration:
    """Test specifications for integration between Git types."""
    
    def test_git_types_should_work_together(self):
        """Different Git types should integrate seamlessly."""
        if TYPES_AVAILABLE:
            # ARRANGE: Create integrated git objects
            repo_path = GitRepositoryPath("/tmp/test-repo")
            branch = GitBranch("feature/integration-test")
            commit_hash = GitCommitHash("a1b2c3d4e5f")
            
            # ACT: Use them together in status result
            status = GitStatusResult(
                is_clean=True,
                current_branch=branch,
                modified_files=[],
                untracked_files=[],
                staged_files=[]
            )
            
            # ASSERT: Should work seamlessly together
            assert status.current_branch == branch
            assert str(status.current_branch) == "feature/integration-test"
    
    def test_type_conversions_should_be_safe(self):
        """Type conversions between Git types should be type-safe."""
        if TYPES_AVAILABLE:
            # String to GitBranch conversion
            branch_str = "main"
            branch = GitBranch(branch_str)
            assert str(branch) == branch_str
            
            # Path to GitRepositoryPath conversion
            path_str = "/tmp/repo"
            with patch('pathlib.Path.exists', return_value=True), \
                 patch('pathlib.Path.is_dir', return_value=True), \
                 patch('pathlib.Path.glob', return_value=[Path('.git')]):
                repo_path = GitRepositoryPath(path_str)
                assert str(repo_path) == path_str


@pytest.mark.unit
class TestGitValidationError:
    """Test specifications for GitValidationError exception."""
    
    def test_should_provide_detailed_error_context(self):
        """GitValidationError should provide detailed error context."""
        if TYPES_AVAILABLE:
            try:
                GitBranch("invalid..branch")
            except GitValidationError as e:
                assert hasattr(e, 'field_name')
                assert hasattr(e, 'invalid_value')
                assert hasattr(e, 'validation_rule')
                assert hasattr(e, 'suggested_fix')
    
    def test_should_support_error_chaining(self):
        """GitValidationError should support proper error chaining."""
        if TYPES_AVAILABLE:
            try:
                # This should raise a validation error
                GitRepositoryPath("/invalid/path")
            except GitValidationError as e:
                assert e.__cause__ is not None or e.__context__ is not None


# Mark all tests that will initially fail
pytestmark = pytest.mark.unit