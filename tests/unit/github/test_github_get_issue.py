"""
Unit tests for github_get_issue function.

Tests the GitHub issue retrieval functionality including:
- Successful issue retrieval with all fields
- 404 error handling with helpful suggestions
- Pull request rejection logic (when issue is actually a PR)
- Authentication error handling
- Body truncation logic (>2000 chars)
- Connection error handling
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp_server_git.github.api import github_get_issue


class TestGitHubGetIssue:
    """Test github_get_issue function."""

    @pytest.mark.asyncio
    async def test_successful_issue_retrieval(self):
        """Test retrieving a complete issue with all fields."""
        mock_client = MagicMock()

        # Mock successful issue response with all fields
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "number": 42,
                "title": "Fix bug in authentication",
                "state": "open",
                "user": {"login": "alice"},
                "created_at": "2023-01-15T10:30:00Z",
                "updated_at": "2023-01-16T14:20:00Z",
                "closed_at": None,
                "labels": [
                    {"name": "bug"},
                    {"name": "priority-high"},
                ],
                "assignees": [
                    {"login": "bob"},
                    {"login": "charlie"},
                ],
                "milestone": {"title": "v1.0.0"},
                "comments": 5,
                "html_url": "https://github.com/owner/repo/issues/42",
                "body": "This is a detailed issue description about the bug we found.",
                "pull_request": None,
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.issues.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_issue(
                repo_owner="owner",
                repo_name="repo",
                issue_number=42,
            )

            # Verify the response contains all expected fields
            assert "Issue #42:" in result
            assert "Fix bug in authentication" in result
            assert "State: 🟢 open" in result
            assert "Author: alice" in result
            assert "Created: 2023-01-15T10:30:00Z" in result
            assert "Updated: 2023-01-16T14:20:00Z" in result
            assert "Labels: bug, priority-high" in result
            assert "Assignees: bob, charlie" in result
            assert "Milestone: v1.0.0" in result
            assert "Comments: 5" in result
            assert "https://github.com/owner/repo/issues/42" in result
            assert (
                "This is a detailed issue description about the bug we found." in result
            )

    @pytest.mark.asyncio
    async def test_closed_issue_retrieval(self):
        """Test retrieving a closed issue with closed_at timestamp."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "number": 123,
                "title": "Issue that was fixed",
                "state": "closed",
                "user": {"login": "alice"},
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2023-01-10T00:00:00Z",
                "closed_at": "2023-01-10T12:00:00Z",
                "labels": [],
                "assignees": [],
                "milestone": None,
                "comments": 0,
                "html_url": "https://github.com/owner/repo/issues/123",
                "body": "Simple issue",
                "pull_request": None,
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.issues.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_issue(
                repo_owner="owner",
                repo_name="repo",
                issue_number=123,
            )

            assert "State: 🔴 closed" in result
            assert "Closed: 2023-01-10T12:00:00Z" in result
            assert "Issue #123:" in result

    @pytest.mark.asyncio
    async def test_issue_not_found_404_error(self):
        """Test that 404 error is handled with helpful suggestion."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 404
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.issues.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_issue(
                repo_owner="owner",
                repo_name="repo",
                issue_number=999,
            )

            assert "Issue #999 not found" in result
            assert "owner/repo" in result
            # Check for helpful suggestion about checking issue number and repo access
            assert "Check issue number and repository access" in result

    @pytest.mark.asyncio
    async def test_pull_request_rejection(self):
        """Test that pull requests are rejected when queried as issues."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "number": 456,
                "title": "Add new feature",
                "state": "open",
                "user": {"login": "alice"},
                "created_at": "2023-01-15T10:30:00Z",
                "updated_at": "2023-01-16T14:20:00Z",
                "closed_at": None,
                "labels": [],
                "assignees": [],
                "milestone": None,
                "comments": 2,
                "html_url": "https://github.com/owner/repo/pull/456",
                "body": "This is a PR description",
                "pull_request": {
                    "url": "https://api.github.com/repos/owner/repo/pulls/456"
                },
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.issues.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_issue(
                repo_owner="owner",
                repo_name="repo",
                issue_number=456,
            )

            assert "pull request" in result
            assert "not an issue" in result
            assert "#456" in result

    @pytest.mark.asyncio
    async def test_authentication_error(self):
        """Test that authentication errors are handled properly."""
        with patch(
            "src.mcp_server_git.github.issues.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ValueError(
                "GitHub token not configured"
            )

            result = await github_get_issue(
                repo_owner="owner",
                repo_name="repo",
                issue_number=42,
            )

            assert "GitHub token not configured" in result
            assert "❌" in result

    @pytest.mark.asyncio
    async def test_connection_error(self):
        """Test that connection errors are handled gracefully."""
        with patch(
            "src.mcp_server_git.github.issues.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = ConnectionError(
                "Network timeout"
            )

            result = await github_get_issue(
                repo_owner="owner",
                repo_name="repo",
                issue_number=42,
            )

            assert "Network connection failed" in result
            assert "Network timeout" in result

    @pytest.mark.asyncio
    async def test_body_truncation_long_description(self):
        """Test that very long issue bodies are truncated at 2000 chars."""
        mock_client = MagicMock()

        # Create a long body > 2000 characters
        long_body = "A" * 2500

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "number": 99,
                "title": "Issue with long description",
                "state": "open",
                "user": {"login": "alice"},
                "created_at": "2023-01-15T10:30:00Z",
                "updated_at": "2023-01-16T14:20:00Z",
                "closed_at": None,
                "labels": [],
                "assignees": [],
                "milestone": None,
                "comments": 0,
                "html_url": "https://github.com/owner/repo/issues/99",
                "body": long_body,
                "pull_request": None,
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.issues.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_issue(
                repo_owner="owner",
                repo_name="repo",
                issue_number=99,
            )

            # Verify truncation message appears
            assert "... (truncated)" in result
            # Verify that body truncation occurred (contains 2000 A's but not all 2500)
            assert result.count("A") >= 2000
            # Verify it doesn't contain the full 2500 characters
            assert long_body not in result

    @pytest.mark.asyncio
    async def test_body_not_truncated_short_description(self):
        """Test that short issue bodies are not truncated."""
        mock_client = MagicMock()

        short_body = "This is a short description"

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "number": 88,
                "title": "Simple issue",
                "state": "open",
                "user": {"login": "alice"},
                "created_at": "2023-01-15T10:30:00Z",
                "updated_at": "2023-01-16T14:20:00Z",
                "closed_at": None,
                "labels": [],
                "assignees": [],
                "milestone": None,
                "comments": 0,
                "html_url": "https://github.com/owner/repo/issues/88",
                "body": short_body,
                "pull_request": None,
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.issues.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_issue(
                repo_owner="owner",
                repo_name="repo",
                issue_number=88,
            )

            # Verify no truncation message
            assert "... (truncated)" not in result
            # Verify full body is included
            assert short_body in result

    @pytest.mark.asyncio
    async def test_empty_body_handling(self):
        """Test that issues with no body are handled gracefully."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "number": 77,
                "title": "Issue with no description",
                "state": "open",
                "user": {"login": "alice"},
                "created_at": "2023-01-15T10:30:00Z",
                "updated_at": "2023-01-16T14:20:00Z",
                "closed_at": None,
                "labels": [],
                "assignees": [],
                "milestone": None,
                "comments": 0,
                "html_url": "https://github.com/owner/repo/issues/77",
                "body": None,
                "pull_request": None,
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.issues.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_issue(
                repo_owner="owner",
                repo_name="repo",
                issue_number=77,
            )

            assert "(No description provided)" in result

    @pytest.mark.asyncio
    async def test_generic_api_error(self):
        """Test that other API errors are reported properly."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal Server Error")
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.issues.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_issue(
                repo_owner="owner",
                repo_name="repo",
                issue_number=42,
            )

            assert "Failed to get issue" in result
            assert "500" in result
            assert "Internal Server Error" in result

    @pytest.mark.asyncio
    async def test_unexpected_error_handling(self):
        """Test that unexpected errors are caught and reported."""
        with patch(
            "src.mcp_server_git.github.issues.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.side_effect = RuntimeError(
                "Unexpected database error"
            )

            result = await github_get_issue(
                repo_owner="owner",
                repo_name="repo",
                issue_number=42,
            )

            assert "Error getting issue" in result
            assert "Unexpected database error" in result

    @pytest.mark.asyncio
    async def test_minimal_issue_fields(self):
        """Test handling of issues with minimal fields (no optional data)."""
        mock_client = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "number": 50,
                "title": "Minimal issue",
                "state": "open",
                "user": None,
                "created_at": "2023-01-15T10:30:00Z",
                "updated_at": "2023-01-16T14:20:00Z",
                "closed_at": None,
                "labels": [],
                "assignees": [],
                "milestone": None,
                "comments": 0,
                "html_url": None,
                "body": None,
                "pull_request": None,
            }
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "src.mcp_server_git.github.issues.github_client_context"
        ) as mock_context:
            mock_context.return_value.__aenter__.return_value = mock_client

            result = await github_get_issue(
                repo_owner="owner",
                repo_name="repo",
                issue_number=50,
            )

            # Should still return valid output even with minimal data
            assert "Issue #50:" in result
            assert "Minimal issue" in result
            assert "Author: N/A" in result
            # URL is None since we explicitly set it to None in the mock
            assert "URL:" in result
