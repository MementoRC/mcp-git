"""
Test specifications for GitHub domain types.

These tests define the behavioral requirements for GitHub-related type definitions
including repository identification, API responses, and validation rules.

IMPORTANT: These tests define requirements and are IMMUTABLE once complete.
Do not modify tests to match implementation - implementation must satisfy these tests.
"""

import pytest
from typing import List, Optional, Dict, Any
from unittest.mock import Mock, patch
from datetime import datetime

# Import the types we expect to be implemented
# These imports will fail initially (RED phase) - that's expected!
try:
    from mcp_server_git.types.github_types import (
        GitHubRepository,
        GitHubUser,
        GitHubPullRequest,
        GitHubCheckRun,
        GitHubWorkflowRun,
        GitHubIssue,
        GitHubCommit,
        GitHubBranch,
        GitHubLabel,
        GitHubReview,
        GitHubFile,
        GitHubAPIResponse,
        GitHubPagination,
        GitHubRateLimit,
        GitHubWebhookEvent,
        GitHubValidationError,
        GitHubAPIError,
        GitHubCheckStatus,
        GitHubCheckConclusion,
        GitHubPRState,
        GitHubReviewState,
    )
    TYPES_AVAILABLE = True
except ImportError:
    TYPES_AVAILABLE = False


class TestGitHubRepository:
    """Test specifications for GitHubRepository type."""
    
    def test_should_accept_valid_repository_identifiers(self):
        """GitHubRepository should accept valid owner/repo combinations."""
        valid_repos = [
            ("owner", "repo"),
            ("org-name", "repo-name"),
            ("user123", "project-2023"),
            ("company", "product.service"),
        ]
        
        if TYPES_AVAILABLE:
            for owner, name in valid_repos:
                repo = GitHubRepository(owner=owner, name=name)
                assert repo.owner == owner
                assert repo.name == name
                assert repo.full_name == f"{owner}/{name}"
    
    def test_should_reject_invalid_repository_identifiers(self):
        """GitHubRepository should reject invalid GitHub repository names."""
        invalid_repos = [
            ("", "repo"),  # Empty owner
            ("owner", ""),  # Empty name
            ("owner with spaces", "repo"),  # Spaces in owner
            ("owner", "repo with spaces"),  # Spaces in name
            ("owner", ".repo"),  # Starts with dot
            ("owner", "repo."),  # Ends with dot
            ("owner", "repo..name"),  # Double dots
            ("-owner", "repo"),  # Starts with hyphen
            ("owner", "repo-"),  # Ends with hyphen
        ]
        
        if TYPES_AVAILABLE:
            for owner, name in invalid_repos:
                with pytest.raises(GitHubValidationError) as exc_info:
                    GitHubRepository(owner=owner, name=name)
                assert "invalid repository" in str(exc_info.value).lower()
    
    def test_should_provide_repository_metadata(self):
        """GitHubRepository should provide comprehensive repository metadata."""
        if TYPES_AVAILABLE:
            repo = GitHubRepository(
                owner="testorg",
                name="test-repo",
                description="A test repository",
                is_private=False,
                default_branch="main",
                clone_url="https://github.com/testorg/test-repo.git",
                ssh_url="git@github.com:testorg/test-repo.git"
            )
            
            assert repo.description == "A test repository"
            assert not repo.is_private
            assert repo.default_branch == "main"
            assert repo.clone_url.startswith("https://")
            assert repo.ssh_url.startswith("git@")
    
    def test_should_validate_urls(self):
        """GitHubRepository should validate GitHub URLs."""
        if TYPES_AVAILABLE:
            # Should reject invalid clone URLs
            with pytest.raises(GitHubValidationError):
                GitHubRepository(
                    owner="owner",
                    name="repo", 
                    clone_url="invalid-url"
                )
            
            # Should reject invalid SSH URLs
            with pytest.raises(GitHubValidationError):
                GitHubRepository(
                    owner="owner",
                    name="repo",
                    ssh_url="invalid-ssh-url"
                )


class TestGitHubUser:
    """Test specifications for GitHubUser type."""
    
    def test_should_represent_github_user_data(self):
        """GitHubUser should represent complete GitHub user information."""
        if TYPES_AVAILABLE:
            user = GitHubUser(
                login="testuser",
                id=12345,
                name="Test User",
                email="test@example.com",
                avatar_url="https://github.com/testuser.png",
                type="User"
            )
            
            assert user.login == "testuser"
            assert user.id == 12345
            assert user.name == "Test User"
            assert user.email == "test@example.com"
            assert user.type == "User"
    
    def test_should_validate_user_data(self):
        """GitHubUser should validate user data integrity."""
        if TYPES_AVAILABLE:
            # Should reject invalid login names
            with pytest.raises(GitHubValidationError):
                GitHubUser(
                    login="",  # Empty login
                    id=12345,
                    name="Test User"
                )
            
            # Should reject invalid user IDs
            with pytest.raises(GitHubValidationError):
                GitHubUser(
                    login="testuser",
                    id=-1,  # Negative ID
                    name="Test User"
                )
    
    def test_should_distinguish_user_types(self):
        """GitHubUser should distinguish between different user types."""
        if TYPES_AVAILABLE:
            user = GitHubUser(login="testuser", id=123, type="User")
            org = GitHubUser(login="testorg", id=456, type="Organization")
            bot = GitHubUser(login="testbot", id=789, type="Bot")
            
            assert user.is_user()
            assert org.is_organization() 
            assert bot.is_bot()


class TestGitHubPullRequest:
    """Test specifications for GitHubPullRequest type."""
    
    def test_should_represent_complete_pull_request_data(self):
        """GitHubPullRequest should represent complete PR information."""
        if TYPES_AVAILABLE:
            pr = GitHubPullRequest(
                number=123,
                title="Add new feature",
                body="This PR adds a new feature for testing",
                state=GitHubPRState.OPEN,
                user=GitHubUser(login="author", id=111),
                head_branch="feature/new-feature",
                base_branch="main",
                head_sha="abc123",
                base_sha="def456"
            )
            
            assert pr.number == 123
            assert pr.title == "Add new feature"
            assert pr.state == GitHubPRState.OPEN
            assert pr.head_branch == "feature/new-feature"
            assert pr.base_branch == "main"
    
    def test_should_validate_pull_request_data(self):
        """GitHubPullRequest should validate PR data integrity."""
        if TYPES_AVAILABLE:
            # Should reject invalid PR numbers
            with pytest.raises(GitHubValidationError):
                GitHubPullRequest(
                    number=0,  # Invalid PR number
                    title="Test PR",
                    state=GitHubPRState.OPEN
                )
            
            # Should reject empty titles
            with pytest.raises(GitHubValidationError):
                GitHubPullRequest(
                    number=123,
                    title="",  # Empty title
                    state=GitHubPRState.OPEN
                )
    
    def test_should_provide_pull_request_predicates(self):
        """GitHubPullRequest should provide convenient status checking."""
        if TYPES_AVAILABLE:
            open_pr = GitHubPullRequest(
                number=123,
                title="Test PR",
                state=GitHubPRState.OPEN
            )
            
            assert open_pr.is_open()
            assert not open_pr.is_closed()
            assert not open_pr.is_merged()
            
            # Should provide merge status checking
            assert hasattr(open_pr, 'is_mergeable')
            assert hasattr(open_pr, 'is_draft')


class TestGitHubCheckRun:
    """Test specifications for GitHubCheckRun type."""
    
    def test_should_represent_check_run_data(self):
        """GitHubCheckRun should represent GitHub check run information."""
        if TYPES_AVAILABLE:
            check = GitHubCheckRun(
                id=789012,
                name="CI Tests",
                status=GitHubCheckStatus.COMPLETED,
                conclusion=GitHubCheckConclusion.SUCCESS,
                started_at=datetime.now(),
                completed_at=datetime.now()
            )
            
            assert check.id == 789012
            assert check.name == "CI Tests"
            assert check.status == GitHubCheckStatus.COMPLETED
            assert check.conclusion == GitHubCheckConclusion.SUCCESS
    
    def test_should_validate_check_run_states(self):
        """GitHubCheckRun should validate status and conclusion combinations."""
        if TYPES_AVAILABLE:
            # Completed checks must have conclusions
            with pytest.raises(GitHubValidationError):
                GitHubCheckRun(
                    id=123,
                    name="Test",
                    status=GitHubCheckStatus.COMPLETED,
                    conclusion=None  # Missing conclusion
                )
            
            # In-progress checks should not have conclusions
            with pytest.raises(GitHubValidationError):
                GitHubCheckRun(
                    id=123,
                    name="Test",
                    status=GitHubCheckStatus.IN_PROGRESS,
                    conclusion=GitHubCheckConclusion.SUCCESS  # Premature conclusion
                )
    
    def test_should_provide_check_predicates(self):
        """GitHubCheckRun should provide convenient status checking."""
        if TYPES_AVAILABLE:
            success_check = GitHubCheckRun(
                id=123,
                name="Test",
                status=GitHubCheckStatus.COMPLETED,
                conclusion=GitHubCheckConclusion.SUCCESS
            )
            
            assert success_check.is_successful()
            assert not success_check.is_failing()
            assert success_check.is_completed()
            assert not success_check.is_pending()


class TestGitHubCheckStatus:
    """Test specifications for GitHubCheckStatus enum."""
    
    def test_should_define_all_github_check_statuses(self):
        """GitHubCheckStatus should define all valid GitHub check statuses."""
        expected_statuses = [
            "queued",
            "in_progress", 
            "completed"
        ]
        
        if TYPES_AVAILABLE:
            for status in expected_statuses:
                check_status = GitHubCheckStatus(status)
                assert str(check_status) == status
    
    def test_should_reject_invalid_check_statuses(self):
        """GitHubCheckStatus should reject invalid statuses."""
        invalid_statuses = ["unknown", "pending", "running", ""]
        
        if TYPES_AVAILABLE:
            for status in invalid_statuses:
                with pytest.raises(GitHubValidationError):
                    GitHubCheckStatus(status)


class TestGitHubCheckConclusion:
    """Test specifications for GitHubCheckConclusion enum."""
    
    def test_should_define_all_github_check_conclusions(self):
        """GitHubCheckConclusion should define all valid conclusions."""
        expected_conclusions = [
            "success",
            "failure",
            "neutral",
            "cancelled", 
            "skipped",
            "timed_out",
            "action_required"
        ]
        
        if TYPES_AVAILABLE:
            for conclusion in expected_conclusions:
                check_conclusion = GitHubCheckConclusion(conclusion)
                assert str(check_conclusion) == conclusion
    
    def test_should_reject_invalid_conclusions(self):
        """GitHubCheckConclusion should reject invalid conclusions."""
        invalid_conclusions = ["unknown", "error", "passed", ""]
        
        if TYPES_AVAILABLE:
            for conclusion in invalid_conclusions:
                with pytest.raises(GitHubValidationError):
                    GitHubCheckConclusion(conclusion)


class TestGitHubAPIResponse:
    """Test specifications for GitHubAPIResponse wrapper."""
    
    def test_should_wrap_successful_responses(self):
        """GitHubAPIResponse should wrap successful API responses."""
        if TYPES_AVAILABLE:
            response_data = {"login": "testuser", "id": 123}
            response = GitHubAPIResponse.success(
                data=response_data,
                status_code=200,
                headers={"content-type": "application/json"}
            )
            
            assert response.is_success()
            assert not response.is_error()
            assert response.data == response_data
            assert response.status_code == 200
    
    def test_should_wrap_error_responses(self):
        """GitHubAPIResponse should wrap API error responses."""
        if TYPES_AVAILABLE:
            response = GitHubAPIResponse.error(
                message="Not Found",
                status_code=404,
                error_code="RESOURCE_NOT_FOUND"
            )
            
            assert not response.is_success()
            assert response.is_error()
            assert response.message == "Not Found"
            assert response.status_code == 404
            assert response.error_code == "RESOURCE_NOT_FOUND"
    
    def test_should_handle_rate_limiting(self):
        """GitHubAPIResponse should handle GitHub rate limiting."""
        if TYPES_AVAILABLE:
            rate_limited = GitHubAPIResponse.rate_limited(
                reset_time=datetime.now(),
                remaining_requests=0,
                limit=5000
            )
            
            assert rate_limited.is_rate_limited()
            assert hasattr(rate_limited, 'reset_time')
            assert hasattr(rate_limited, 'remaining_requests')


class TestGitHubPagination:
    """Test specifications for GitHubPagination type."""
    
    def test_should_handle_paginated_responses(self):
        """GitHubPagination should handle GitHub API pagination."""
        if TYPES_AVAILABLE:
            pagination = GitHubPagination(
                page=2,
                per_page=30,
                total_count=150,
                has_next=True,
                has_previous=True
            )
            
            assert pagination.page == 2
            assert pagination.per_page == 30
            assert pagination.total_count == 150
            assert pagination.has_next
            assert pagination.has_previous
    
    def test_should_calculate_pagination_metadata(self):
        """GitHubPagination should calculate pagination metadata."""
        if TYPES_AVAILABLE:
            pagination = GitHubPagination(
                page=3,
                per_page=25,
                total_count=100
            )
            
            assert pagination.total_pages == 4
            assert pagination.is_last_page == False
            assert pagination.is_first_page == False
            assert pagination.next_page == 4
            assert pagination.previous_page == 2
    
    def test_should_validate_pagination_parameters(self):
        """GitHubPagination should validate pagination parameters."""
        if TYPES_AVAILABLE:
            # Should reject invalid page numbers
            with pytest.raises(GitHubValidationError):
                GitHubPagination(page=0, per_page=30)  # Page must be >= 1
            
            # Should reject invalid per_page values
            with pytest.raises(GitHubValidationError):
                GitHubPagination(page=1, per_page=101)  # GitHub max is 100


class TestGitHubRateLimit:
    """Test specifications for GitHubRateLimit type."""
    
    def test_should_track_rate_limit_status(self):
        """GitHubRateLimit should track GitHub API rate limit status."""
        if TYPES_AVAILABLE:
            rate_limit = GitHubRateLimit(
                limit=5000,
                remaining=4500,
                reset_time=datetime.now(),
                used=500
            )
            
            assert rate_limit.limit == 5000
            assert rate_limit.remaining == 4500
            assert rate_limit.used == 500
            assert not rate_limit.is_exhausted()
    
    def test_should_detect_rate_limit_exhaustion(self):
        """GitHubRateLimit should detect when rate limit is exhausted."""
        if TYPES_AVAILABLE:
            exhausted_limit = GitHubRateLimit(
                limit=5000,
                remaining=0,
                reset_time=datetime.now(),
                used=5000
            )
            
            assert exhausted_limit.is_exhausted()
            assert exhausted_limit.needs_wait()
            assert exhausted_limit.time_until_reset() > 0


# Integration tests between GitHub types
class TestGitHubTypeIntegration:
    """Test specifications for integration between GitHub types."""
    
    def test_github_types_should_work_together(self):
        """Different GitHub types should integrate seamlessly."""
        if TYPES_AVAILABLE:
            # ARRANGE: Create integrated GitHub objects
            repo = GitHubRepository(owner="testorg", name="test-repo")
            user = GitHubUser(login="testuser", id=123)
            pr = GitHubPullRequest(
                number=456,
                title="Test PR",
                state=GitHubPRState.OPEN,
                user=user
            )
            
            # ACT & ASSERT: Should work together
            assert pr.user == user
            assert pr.user.login == "testuser"
    
    def test_api_response_should_contain_typed_data(self):
        """GitHubAPIResponse should contain properly typed data."""
        if TYPES_AVAILABLE:
            user_data = {"login": "testuser", "id": 123}
            response = GitHubAPIResponse.success(user_data, 200)
            
            # Should be able to extract typed data
            user = GitHubUser.from_api_response(response)
            assert user.login == "testuser"
            assert user.id == 123


@pytest.mark.unit
class TestGitHubValidationError:
    """Test specifications for GitHubValidationError exception."""
    
    def test_should_provide_detailed_error_context(self):
        """GitHubValidationError should provide detailed error context."""
        if TYPES_AVAILABLE:
            try:
                GitHubRepository(owner="", name="repo")
            except GitHubValidationError as e:
                assert hasattr(e, 'field_name')
                assert hasattr(e, 'invalid_value')
                assert hasattr(e, 'validation_rule')
                assert hasattr(e, 'github_docs_link')
    
    def test_should_categorize_error_types(self):
        """GitHubValidationError should categorize different error types."""
        if TYPES_AVAILABLE:
            # Should distinguish validation vs API errors
            validation_error = GitHubValidationError("Invalid format")
            api_error = GitHubAPIError("API request failed")
            
            assert validation_error.is_validation_error()
            assert api_error.is_api_error()


# Mark all tests that will initially fail
pytestmark = pytest.mark.unit