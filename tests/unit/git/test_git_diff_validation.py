"""
Unit tests for Git diff validation functions.

These tests verify the validation functions for git diff operations,
including commit range validation, parameter conflict detection, and
security checks for command injection prevention.

Critical for TDD Compliance:
    These tests define the behavior that the implementation must satisfy.
    DO NOT modify these tests to match a broken implementation - the
    implementation must be fixed to pass these tests.
"""

import pytest
from unittest.mock import Mock, patch

from mcp_server_git.git.operations import (
    _validate_commit_range,
    _validate_diff_parameters,
    _apply_diff_size_limiting,
    git_diff,
    git_diff_staged,
    git_diff_unstaged,
)
from mcp_server_git.utils.git_import import GitCommandError, Repo


class TestValidateCommitRange:
    """Test commit range validation function."""

    def test_valid_hash_ranges(self):
        """Should accept valid commit hash ranges."""
        test_cases = [
            "abc123..def456",
            "abc123...def456",
            "a1b2c3d4e5f6..f6e5d4c3b2a1",
            "1234567890abcdef..fedcba0987654321",
        ]
        
        for commit_range in test_cases:
            is_valid, message = _validate_commit_range(commit_range)
            assert is_valid is True
            assert message == ""

    def test_valid_branch_ranges(self):
        """Should accept valid branch name ranges."""
        test_cases = [
            "main..develop",
            "feature/new-feature..main",
            "main...feature/hotfix",
            "release-v1.0..develop",
            "feature/user-auth..release/v2.0",
        ]
        
        for commit_range in test_cases:
            is_valid, message = _validate_commit_range(commit_range)
            assert is_valid is True
            assert message == ""

    def test_valid_head_ranges(self):
        """Should accept valid HEAD reference ranges."""
        test_cases = [
            "HEAD~1..HEAD",
            "HEAD~5..HEAD~2",
            "HEAD..HEAD~1",
            "HEAD~10...HEAD",
            "HEAD~..HEAD",
        ]
        
        for commit_range in test_cases:
            is_valid, message = _validate_commit_range(commit_range)
            assert is_valid is True
            assert message == ""

    def test_valid_mixed_ranges(self):
        """Should accept valid mixed hash/branch/HEAD ranges."""
        test_cases = [
            "abc123..main",
            "main..def456",
            "HEAD~1..main",
            "feature/test..HEAD",
            "abc123...HEAD~5",
        ]
        
        for commit_range in test_cases:
            is_valid, message = _validate_commit_range(commit_range)
            assert is_valid is True
            assert message == ""

    def test_empty_or_whitespace_ranges(self):
        """Should reject empty or whitespace-only ranges."""
        test_cases = [
            "",
            "   ",
            "\t",
            "\n",
            None,
        ]
        
        for commit_range in test_cases:
            is_valid, message = _validate_commit_range(commit_range)
            assert is_valid is False
            assert "cannot be empty" in message

    def test_injection_attack_prevention(self):
        """Should reject commit ranges with dangerous characters."""
        test_cases = [
            "main; rm -rf /",
            "HEAD~1..HEAD | cat /etc/passwd",
            "main && echo 'hacked'",
            "HEAD`whoami`..main",
            "main$(id)..develop",
            "HEAD(ls -la)..main",
            "main)..develop",
        ]
        
        for commit_range in test_cases:
            is_valid, message = _validate_commit_range(commit_range)
            assert is_valid is False
            assert "Invalid characters detected" in message
            assert commit_range in message

    def test_unusual_but_potentially_valid_formats(self):
        """Should warn about unusual but potentially valid commit ranges."""
        test_cases = [
            "weird-format..another",
            "123..456",  # Too short for typical hashes but might be valid
            "a..b",      # Very short but could be valid tags
        ]
        
        for commit_range in test_cases:
            is_valid, message = _validate_commit_range(commit_range)
            assert is_valid is True
            assert "Warning: Unusual commit range format" in message
            assert "proceed with caution" in message


class TestValidateDiffParameters:
    """Test diff parameter conflict validation."""

    def test_single_target_parameter(self):
        """Should accept single target parameter."""
        is_valid, message = _validate_diff_parameters(target="main")
        assert is_valid is True
        assert message == ""

    def test_single_commit_range_parameter(self):
        """Should accept single commit_range parameter."""
        is_valid, message = _validate_diff_parameters(commit_range="HEAD~1..HEAD")
        assert is_valid is True
        assert message == ""

    def test_both_base_and_target_commit(self):
        """Should accept both base_commit and target_commit together."""
        is_valid, message = _validate_diff_parameters(
            base_commit="main", 
            target_commit="develop"
        )
        assert is_valid is True
        assert message == ""

    def test_conflicting_target_and_commit_range(self):
        """Should reject conflicting target and commit_range."""
        is_valid, message = _validate_diff_parameters(
            target="main", 
            commit_range="HEAD~1..HEAD"
        )
        assert is_valid is False
        assert "Conflicting diff parameters" in message
        assert "target, commit_range" in message

    def test_conflicting_target_and_commit_pair(self):
        """Should reject conflicting target and base/target commit pair."""
        is_valid, message = _validate_diff_parameters(
            target="main",
            base_commit="develop", 
            target_commit="feature"
        )
        assert is_valid is False
        assert "Conflicting diff parameters" in message
        assert "target, base_commit + target_commit" in message

    def test_conflicting_commit_range_and_commit_pair(self):
        """Should reject conflicting commit_range and base/target commit pair."""
        is_valid, message = _validate_diff_parameters(
            commit_range="HEAD~1..HEAD",
            base_commit="develop",
            target_commit="main"
        )
        assert is_valid is False
        assert "Conflicting diff parameters" in message
        assert "commit_range, base_commit + target_commit" in message

    def test_partial_commit_pair_base_only(self):
        """Should reject base_commit without target_commit."""
        is_valid, message = _validate_diff_parameters(base_commit="main")
        assert is_valid is False
        assert "Both base_commit and target_commit must be provided together" in message

    def test_partial_commit_pair_target_only(self):
        """Should reject target_commit without base_commit."""
        is_valid, message = _validate_diff_parameters(target_commit="develop")
        assert is_valid is False
        assert "Both base_commit and target_commit must be provided together" in message

    def test_all_parameters_conflicting(self):
        """Should reject when all parameter types are provided."""
        is_valid, message = _validate_diff_parameters(
            target="main",
            commit_range="HEAD~1..HEAD",
            base_commit="develop",
            target_commit="feature"
        )
        assert is_valid is False
        assert "Conflicting diff parameters" in message
        
    def test_no_parameters(self):
        """Should accept no parameters (uses defaults)."""
        is_valid, message = _validate_diff_parameters()
        assert is_valid is True
        assert message == ""

    def test_invalid_commit_range_format(self):
        """Should reject invalid commit_range format."""
        is_valid, message = _validate_diff_parameters(
            commit_range="main; rm -rf /"
        )
        assert is_valid is False
        assert "Invalid commit_range" in message
        assert "Invalid characters detected" in message

    def test_commit_range_with_warning(self):
        """Should pass through warnings from commit_range validation."""
        is_valid, message = _validate_diff_parameters(
            commit_range="a..b"  # Unusual format that triggers warning
        )
        assert is_valid is True
        assert "Warning: Unusual commit range format" in message


class TestApplyDiffSizeLimiting:
    """Test diff size limiting function."""

    def test_empty_diff_output(self):
        """Should handle empty diff output."""
        result = _apply_diff_size_limiting("", "test operation")
        assert result == "No changes detected in test operation"
        
        result = _apply_diff_size_limiting("   \n\t  ", "test operation")
        assert result == "No changes detected in test operation"

    def test_stat_only_passthrough(self):
        """Should pass through stat-only output without modification."""
        diff_output = "file1.py | 5 ++---\nfile2.py | 2 ++\n2 files changed"
        result = _apply_diff_size_limiting(diff_output, "test", stat_only=True)
        assert result == diff_output

    def test_max_lines_limiting(self):
        """Should limit output to max_lines when specified."""
        diff_output = "\n".join([f"Line {i}" for i in range(1, 11)])  # 10 lines
        result = _apply_diff_size_limiting(diff_output, "test", max_lines=5)
        
        assert "Line 1" in result
        assert "Line 5" in result
        assert "Line 6" not in result
        assert "Line 10" not in result
        assert "[Truncated: showing 5 of 10 lines]" in result
        assert "Use stat_only=true for summary" in result

    def test_max_lines_no_truncation_needed(self):
        """Should not truncate when content is within max_lines."""
        diff_output = "Line 1\nLine 2\nLine 3"
        result = _apply_diff_size_limiting(diff_output, "test", max_lines=5)
        assert result == diff_output

    def test_max_lines_zero_or_negative(self):
        """Should ignore max_lines when zero or negative."""
        diff_output = "Line 1\nLine 2\nLine 3"
        
        result = _apply_diff_size_limiting(diff_output, "test", max_lines=0)
        assert result == diff_output
        
        result = _apply_diff_size_limiting(diff_output, "test", max_lines=-5)
        assert result == diff_output

    def test_large_diff_warning(self):
        """Should add warning for large diffs over 50KB."""
        # Create a diff larger than 50KB
        large_diff = "A" * 60000  # 60KB of content
        result = _apply_diff_size_limiting(large_diff, "test operation")
        
        assert result.startswith("⚠️  Large diff detected")
        assert "Consider using stat_only=true" in result
        assert "max_lines parameter" in result
        assert large_diff in result

    def test_normal_size_diff(self):
        """Should return normal diffs without modification."""
        normal_diff = "Some normal diff content\n+Added line\n-Removed line"
        result = _apply_diff_size_limiting(normal_diff, "test operation")
        assert result == normal_diff


class TestGitDiffValidationIntegration:
    """Test integration of validation with git diff functions."""

    @patch('mcp_server_git.git.operations._validate_diff_parameters')
    def test_git_diff_calls_parameter_validation(self, mock_validate):
        """Should call parameter validation in git_diff function."""
        mock_repo = Mock(spec=Repo)
        mock_repo.git.diff.return_value = "test output"
        mock_validate.return_value = (True, "")
        
        # Call with conflicting parameters to trigger validation
        git_diff(
            mock_repo, 
            target="main", 
            commit_range="HEAD~1..HEAD"
        )
        
        # Verify validation was called with the parameters
        mock_validate.assert_called_once()
        call_args = mock_validate.call_args
        assert call_args[1]['target'] == "main"
        assert call_args[1]['commit_range'] == "HEAD~1..HEAD"

    @patch('mcp_server_git.git.operations._validate_diff_parameters')
    def test_git_diff_handles_validation_failure(self, mock_validate):
        """Should return error message when parameter validation fails."""
        mock_repo = Mock(spec=Repo)
        mock_validate.return_value = (False, "Conflicting parameters detected")
        
        result = git_diff(
            mock_repo,
            target="main",
            commit_range="HEAD~1..HEAD"
        )
        
        assert "❌ Parameter validation failed: Conflicting parameters detected" in result

    @patch('mcp_server_git.git.operations._validate_diff_parameters')
    def test_git_diff_shows_validation_warnings(self, mock_validate):
        """Should include warnings from parameter validation."""
        mock_repo = Mock(spec=Repo)
        mock_repo.git.diff.return_value = "test diff output"
        mock_validate.return_value = (True, "Warning: Unusual format detected")
        
        result = git_diff(mock_repo, commit_range="a..b")
        
        assert "⚠️ Warning: Unusual format detected" in result
        assert "test diff output" in result

    def test_commit_range_used_in_git_command(self):
        """Should properly use commit_range in git diff command."""
        mock_repo = Mock(spec=Repo)
        mock_repo.git.diff.return_value = "diff output"
        
        git_diff(mock_repo, commit_range="HEAD~1..HEAD")
        
        # Verify commit_range was passed to git diff
        mock_repo.git.diff.assert_called_once()
        args = mock_repo.git.diff.call_args[0]
        assert "HEAD~1..HEAD" in args


# Test fixtures for validation testing
@pytest.fixture
def sample_large_diff():
    """Create a sample large diff for size limiting tests."""
    lines = [f"+Line {i}: This is a long line of added content" for i in range(1000)]
    return "\n".join(lines)


# Mark for test organization
pytestmark = [pytest.mark.unit, pytest.mark.git_operations, pytest.mark.validation]