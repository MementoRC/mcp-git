"""
GitHub API response fixtures for testing.

Provides mock responses for GitHub API calls to enable testing
without actual API requests.
"""

from typing import Dict, Any
import pytest
from unittest.mock import MagicMock


class GitHubResponseFactory:
    """Factory for creating mock GitHub API responses."""
    
    @staticmethod
    def user_response(login: str = "testuser") -> Dict[str, Any]:
        """Create a mock user response."""
        return {
            "login": login,
            "id": 12345,
            "name": "Test User",
            "email": f"{login}@example.com",
            "avatar_url": f"https://github.com/{login}.png",
            "type": "User",
            "public_repos": 10,
            "followers": 5,
            "following": 3
        }
    
    @staticmethod
    def repository_response(name: str = "test-repo", owner: str = "testuser") -> Dict[str, Any]:
        """Create a mock repository response."""
        return {
            "id": 67890,
            "name": name,
            "full_name": f"{owner}/{name}",
            "owner": GitHubResponseFactory.user_response(owner),
            "private": False,
            "description": f"Test repository {name}",
            "default_branch": "main",
            "clone_url": f"https://github.com/{owner}/{name}.git",
            "ssh_url": f"git@github.com:{owner}/{name}.git",
            "created_at": "2023-01-01T00:00:00Z",
            "updated_at": "2023-12-01T00:00:00Z",
            "language": "Python",
            "size": 1024,
            "stargazers_count": 42,
            "watchers_count": 15,
            "forks_count": 7
        }
    
    @staticmethod
    def pull_request_response(number: int = 1, state: str = "open") -> Dict[str, Any]:
        """Create a mock pull request response."""
        return {
            "id": 123456,
            "number": number,
            "state": state,
            "title": f"Test Pull Request #{number}",
            "body": "This is a test pull request",
            "user": GitHubResponseFactory.user_response(),
            "head": {
                "ref": "feature-branch",
                "sha": "abc123def456"
            },
            "base": {
                "ref": "main",
                "sha": "def456abc123"
            },
            "created_at": "2023-11-01T00:00:00Z",
            "updated_at": "2023-12-01T00:00:00Z",
            "mergeable": True,
            "mergeable_state": "clean"
        }
    
    @staticmethod
    def check_run_response(status: str = "completed", conclusion: str = "success") -> Dict[str, Any]:
        """Create a mock check run response."""
        return {
            "id": 789012,
            "name": "CI Tests",
            "status": status,
            "conclusion": conclusion,
            "started_at": "2023-12-01T10:00:00Z",
            "completed_at": "2023-12-01T10:05:00Z" if status == "completed" else None,
            "output": {
                "title": "Test Results",
                "summary": "All tests passed" if conclusion == "success" else "Some tests failed"
            }
        }
    
    @staticmethod
    def commit_response(sha: str = "abc123def456") -> Dict[str, Any]:
        """Create a mock commit response."""
        return {
            "sha": sha,
            "commit": {
                "message": "Test commit message",
                "author": {
                    "name": "Test User",
                    "email": "test@example.com",
                    "date": "2023-12-01T12:00:00Z"
                },
                "committer": {
                    "name": "Test User", 
                    "email": "test@example.com",
                    "date": "2023-12-01T12:00:00Z"
                }
            },
            "author": GitHubResponseFactory.user_response(),
            "committer": GitHubResponseFactory.user_response()
        }


@pytest.fixture
def github_response_factory():
    """Provide access to GitHubResponseFactory."""
    return GitHubResponseFactory


@pytest.fixture
def mock_github_client():
    """Create a mock GitHub client."""
    client = MagicMock()
    
    # Configure common responses
    client.get_user.return_value = GitHubResponseFactory.user_response()
    client.get_repo.return_value = GitHubResponseFactory.repository_response()
    client.get_pulls.return_value = [GitHubResponseFactory.pull_request_response()]
    client.get_check_runs.return_value = [GitHubResponseFactory.check_run_response()]
    
    return client


@pytest.fixture
def github_api_responses():
    """Common GitHub API response patterns."""
    return {
        "success": {
            "status_code": 200,
            "headers": {"content-type": "application/json"},
        },
        "not_found": {
            "status_code": 404,
            "json": {"message": "Not Found"},
        },
        "rate_limited": {
            "status_code": 403,
            "json": {"message": "API rate limit exceeded"},
        },
        "server_error": {
            "status_code": 500,
            "json": {"message": "Internal Server Error"},
        }
    }