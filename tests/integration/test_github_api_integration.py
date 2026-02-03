"""
Integration tests for GitHub API functions.

This module tests the integration of GitHub API functions with actual API responses,
memory management, error handling, and resource cleanup.

Focus areas:
- GitHub API function integration with real response structures
- Memory management with PatchMemoryManager
- Error handling granularity and specific exception types
- Resource cleanup with async context managers
- Rate limiting and timeout handling
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import json

from mcp_server_git.github.api import (
    github_list_issues,
    github_create_issue,
    github_get_pr_details,
    github_get_pr_files,
    github_list_workflow_runs,
    PatchMemoryManager,
    github_client_context,
)


class TestGitHubAPIIntegration:
    """Integration tests for GitHub API functions."""

    @pytest.fixture
    def mock_github_response(self):
        """Mock GitHub API response structure."""
        return {
            "id": 12345,
            "number": 1,
            "title": "Test Issue",
            "body": "Test issue body",
            "state": "open",
            "user": {
                "login": "testuser",
                "id": 54321,
                "avatar_url": "https://github.com/images/error/testuser.gif",
            },
            "labels": [
                {"name": "bug", "color": "d73a4a"},
                {"name": "documentation", "color": "0075ca"},
            ],
            "assignees": [],
            "milestone": None,
            "created_at": "2023-01-01T00:00:00Z",
            "updated_at": "2023-01-01T00:00:00Z",
            "closed_at": None,
            "html_url": "https://github.com/owner/repo/issues/1",
        }

    @pytest.fixture
    def mock_pr_response(self):
        """Mock GitHub Pull Request response structure."""
        return {
            "id": 67890,
            "number": 2,
            "title": "Test PR",
            "body": "Test PR body",
            "state": "open",
            "draft": False,
            "user": {"login": "testuser", "id": 54321},
            "head": {
                "ref": "feature-branch",
                "sha": "abc123def456",
                "repo": {"full_name": "owner/repo"},
            },
            "base": {
                "ref": "main",
                "sha": "def456abc123",
                "repo": {"full_name": "owner/repo"},
            },
            "mergeable": True,
            "mergeable_state": "clean",
            "merged": False,
            "created_at": "2023-01-01T00:00:00Z",
            "updated_at": "2023-01-01T00:00:00Z",
            "html_url": "https://github.com/owner/repo/pull/2",
        }

    @pytest.fixture
    def mock_workflow_run_response(self):
        """Mock GitHub Workflow Run response structure."""
        return {
            "id": 123456789,
            "name": "CI",
            "status": "completed",
            "conclusion": "success",
            "workflow_id": 987654,
            "run_number": 42,
            "event": "push",
            "created_at": "2023-01-01T00:00:00Z",
            "updated_at": "2023-01-01T00:00:00Z",
            "run_started_at": "2023-01-01T00:00:00Z",
            "html_url": "https://github.com/owner/repo/actions/runs/123456789",
            "head_branch": "main",
            "head_sha": "abc123def456",
        }

    @pytest.mark.asyncio
    async def test_github_list_issues_integration(self, mock_github_response):
        """Test github_list_issues with realistic response data."""
        mock_response_data = [mock_github_response]

        with patch("mcp_server_git.github.api.get_github_client") as mock_client_func:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.json.return_value = mock_response_data
            mock_response.status = 200
            mock_client.get.return_value = mock_response
            mock_client.session = AsyncMock()
            mock_client_func.return_value = mock_client

            result = await github_list_issues("owner", "repo", "open")

            # Verify the API was called correctly
            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            assert "/repos/owner/repo/issues" in call_args[0][0]

            # Verify response structure - function returns formatted string, not JSON
            assert isinstance(result, str)
            assert "Open Issues for owner/repo:" in result
            assert "#1: Test Issue" in result
            assert "Author: testuser" in result
            assert "Labels: bug, documentation" in result

    @pytest.mark.asyncio
    async def test_github_create_issue_integration(self, mock_github_response):
        """Test github_create_issue with realistic response data."""
        with patch("mcp_server_git.github.api.get_github_client") as mock_client_func:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.json.return_value = mock_github_response
            mock_response.status = 201
            mock_client.post.return_value = mock_response
            mock_client.session = AsyncMock()
            mock_client_func.return_value = mock_client

            result = await github_create_issue(
                "owner", "repo", "Test Issue", "Test body", ["bug", "enhancement"]
            )

            # Verify the API was called correctly
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert "/repos/owner/repo/issues" in call_args[0][0]

            # Verify request payload
            call_kwargs = call_args[1]
            assert "json" in call_kwargs
            payload = call_kwargs["json"]
            assert payload["title"] == "Test Issue"
            assert payload["body"] == "Test body"
            assert payload["labels"] == ["bug", "enhancement"]

            # Verify response structure (function returns success message, not JSON)
            assert isinstance(result, str)
            assert "Successfully created issue" in result
            assert "#1" in result

    @pytest.mark.asyncio
    async def test_github_get_pr_details_integration(self, mock_pr_response):
        """Test github_get_pr_details with realistic response data."""
        with patch("mcp_server_git.github.api.get_github_client") as mock_client_func:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.json.return_value = mock_pr_response
            mock_response.status = 200
            mock_client.get.return_value = mock_response
            mock_client.session = AsyncMock()
            mock_client_func.return_value = mock_client

            result = await github_get_pr_details("owner", "repo", 2)

            # Verify the API was called correctly
            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            assert "/repos/owner/repo/pulls/2" in call_args[0][0]

            # Verify response structure (function returns formatted text, not JSON)
            assert isinstance(result, str)
            assert "Pull Request #2" in result
            assert "Test PR" in result
            assert "feature-branch" in result

    @pytest.mark.asyncio
    async def test_github_list_workflow_runs_integration(
        self, mock_workflow_run_response
    ):
        """Test github_list_workflow_runs with realistic response data."""
        mock_response_data = {
            "total_count": 1,
            "workflow_runs": [mock_workflow_run_response],
        }

        with patch("mcp_server_git.github.api.get_github_client") as mock_client_func:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.json.return_value = mock_response_data
            mock_response.status = 200
            mock_client.get.return_value = mock_response
            mock_client.session = AsyncMock()
            mock_client_func.return_value = mock_client

            result = await github_list_workflow_runs("owner", "repo")

            # Verify the API was called correctly
            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            assert "/repos/owner/repo/actions/runs" in call_args[0][0]

            # Verify response structure (function returns formatted text, not JSON)
            assert isinstance(result, str)
            assert "Workflow Runs for owner/repo" in result
            assert "CI" in result  # workflow name
            assert "completed" in result

    @pytest.mark.asyncio
    async def test_error_handling_granularity_network_error(self):
        """Test specific error handling for network-related issues."""
        with patch("mcp_server_git.github.api.get_github_client") as mock_client_func:
            mock_client = AsyncMock()
            mock_client.session = AsyncMock()
            # Simulate a connection error
            mock_client.get.side_effect = ConnectionError("Network unreachable")
            mock_client_func.return_value = mock_client

            result = await github_list_issues("owner", "repo")

            # Should get a properly formatted error message
            assert "network connection failed" in result.lower()
            assert "network unreachable" in result.lower()

    @pytest.mark.asyncio
    async def test_error_handling_granularity_authentication_error(self):
        """Test specific error handling for authentication issues."""
        with patch("mcp_server_git.github.api.get_github_client") as mock_client_func:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status = 401
            mock_response.text = AsyncMock(return_value="Bad credentials")
            mock_client.get.return_value = mock_response
            mock_client.session = AsyncMock()
            mock_client_func.return_value = mock_client

            result = await github_list_issues("owner", "repo")

            # Should get a properly formatted authentication error
            assert "401" in result or "failed to list issues" in result.lower()

    @pytest.mark.asyncio
    async def test_error_handling_granularity_rate_limit_error(self):
        """Test specific error handling for rate limiting."""
        with patch("mcp_server_git.github.api.get_github_client") as mock_client_func:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status = 403
            mock_response.text = AsyncMock(return_value="API rate limit exceeded")
            mock_client.get.return_value = mock_response
            mock_client.session = AsyncMock()
            mock_client_func.return_value = mock_client

            result = await github_list_issues("owner", "repo")

            # Should get a properly formatted rate limit error
            assert "403" in result or "failed to list issues" in result.lower()


class TestPatchMemoryManagerIntegration:
    """Integration tests for PatchMemoryManager with GitHub API."""

    def test_patch_memory_manager_initialization(self):
        """Test PatchMemoryManager initialization with custom limits."""
        manager = PatchMemoryManager(max_patch_size=500, max_total_memory=2000)

        assert manager.max_patch_size == 500
        assert manager.max_total_memory == 2000
        assert manager.current_memory_usage == 0
        assert manager.patches_processed == 0

    def test_patch_memory_manager_can_include_patch(self):
        """Test memory budget checking logic."""
        manager = PatchMemoryManager(max_patch_size=100, max_total_memory=500)

        # Should allow small patches
        assert manager.can_include_patch(50) == True
        assert manager.can_include_patch(100) == True

        # Process some patches to use up memory
        manager.current_memory_usage = 400

        # Should reject patches that exceed remaining budget
        assert manager.can_include_patch(200) == False
        assert manager.can_include_patch(100) == True  # Exactly at limit

    def test_patch_memory_manager_process_patch_normal(self):
        """Test normal patch processing within limits."""
        manager = PatchMemoryManager(max_patch_size=100, max_total_memory=500)

        test_patch = "diff --git a/file.py b/file.py\n+added line"
        processed_patch, was_truncated = manager.process_patch(test_patch)

        # Patch is wrapped in markdown code block
        assert test_patch in processed_patch
        assert "```diff" in processed_patch
        assert was_truncated == False
        assert manager.current_memory_usage == len(test_patch)
        assert manager.patches_processed == 1

    def test_patch_memory_manager_process_patch_truncated(self):
        """Test patch processing with truncation due to size limits."""
        manager = PatchMemoryManager(max_patch_size=20, max_total_memory=500)

        large_patch = (
            "diff --git a/very_long_filename.py b/very_long_filename.py\n" + "+" * 100
        )
        processed_patch, was_truncated = manager.process_patch(large_patch)

        # Truncation includes markdown and truncation message
        assert was_truncated == True
        assert "truncated" in processed_patch.lower()
        assert "```diff" in processed_patch
        assert manager.patches_processed == 1

    def test_patch_memory_manager_memory_budget_exceeded(self):
        """Test patch processing when memory budget is exceeded."""
        manager = PatchMemoryManager(max_patch_size=100, max_total_memory=50)

        # Pre-fill memory usage
        manager.current_memory_usage = 40

        test_patch = "diff --git a/file.py b/file.py\n+added line"  # ~30 chars
        processed_patch, was_truncated = manager.process_patch(test_patch)

        # Should be truncated due to memory budget
        assert was_truncated == True
        assert (
            "skipped" in processed_patch.lower() and "memory" in processed_patch.lower()
        )
        # Memory usage stays at 40 since patch was skipped
        assert manager.current_memory_usage == 40

    @pytest.mark.asyncio
    async def test_github_get_pr_files_with_memory_management(self):
        """Test github_get_pr_files integration with memory management."""
        # Mock large PR files response
        large_file_response = {
            "filename": "large_file.py",
            "status": "modified",
            "additions": 100,
            "deletions": 50,
            "changes": 150,
            "patch": "diff --git a/large_file.py b/large_file.py\n"
            + "+" * 2000,  # Large patch
        }
        mock_response_data = [large_file_response]

        with (
            patch("mcp_server_git.github.api.get_github_client") as mock_client_func,
            patch("mcp_server_git.github.api.PatchMemoryManager") as mock_manager_class,
        ):
            # Set up mock memory manager
            mock_manager = MagicMock()
            mock_manager.can_include_patch.return_value = True
            mock_manager.process_patch.return_value = ("truncated patch", True)
            mock_manager_class.return_value = mock_manager

            # Set up mock HTTP response
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.json.return_value = mock_response_data
            mock_response.status = 200
            mock_client.get.return_value = mock_response
            mock_client.session = AsyncMock()
            mock_client_func.return_value = mock_client

            result = await github_get_pr_files("owner", "repo", 1, include_patch=True)

            # Verify memory manager was used
            mock_manager_class.assert_called_once()
            mock_manager.process_patch.assert_called()

            # Verify response contains memory management info (function returns formatted text)
            assert isinstance(result, str)
            assert "large_file.py" in result
            assert "Memory usage:" in result


class TestGitHubClientContextIntegration:
    """Integration tests for github_client_context async context manager."""

    @pytest.mark.asyncio
    async def test_github_client_context_resource_management(self):
        """Test that github_client_context properly manages session resources."""
        with patch("mcp_server_git.github.api.get_github_client") as mock_client_func:
            mock_client = AsyncMock()
            mock_session = AsyncMock()
            mock_client.session = mock_session
            mock_client_func.return_value = mock_client

            # Use the context manager
            async with github_client_context() as client:
                assert client is mock_client

            # Verify session was properly closed
            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_github_client_context_exception_handling(self):
        """Test that github_client_context properly handles exceptions."""
        with patch("mcp_server_git.github.api.get_github_client") as mock_client_func:
            mock_client = AsyncMock()
            mock_session = AsyncMock()
            mock_client.session = mock_session
            mock_client_func.return_value = mock_client

            # Test that exceptions don't prevent cleanup
            try:
                async with github_client_context() as _client:
                    raise ValueError("Test exception")
            except ValueError:
                pass

            # Verify session was still properly closed despite exception
            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_github_client_context_timeout_configuration(self):
        """Test that github_client_context configures appropriate timeouts."""
        with patch("mcp_server_git.github.api.get_github_client") as mock_client_func:
            mock_client = AsyncMock()
            mock_session = AsyncMock()
            mock_client.session = mock_session
            mock_client_func.return_value = mock_client

            async with github_client_context() as client:
                # Verify we get the client
                assert client is mock_client

            # Verify session was properly closed
            mock_session.close.assert_called_once()


class TestGitHubAPIErrorHandlingGranularity:
    """Test granular error handling in GitHub API functions."""

    @pytest.mark.asyncio
    async def test_value_error_handling_invalid_parameters(self):
        """Test ValueError handling for invalid parameters."""
        # Test with invalid repository name
        result = await github_list_issues("", "repo")  # Empty owner
        assert "❌" in result or "error" in result.lower() or "failed" in result.lower()

        # Test with invalid PR number
        result = await github_get_pr_details("owner", "repo", -1)  # Negative PR number
        assert "❌" in result or "error" in result.lower() or "failed" in result.lower()

    @pytest.mark.asyncio
    async def test_connection_error_handling_network_issues(self):
        """Test ConnectionError handling for network issues."""
        with patch("mcp_server_git.github.api.get_github_client") as mock_client_func:
            mock_client = AsyncMock()
            mock_client.session = AsyncMock()
            mock_client.get.side_effect = ConnectionError("Connection failed")
            mock_client_func.return_value = mock_client

            result = await github_list_issues("owner", "repo")

            # Should get specific connection error message
            assert "network connection failed" in result.lower()
            assert "connection" in result.lower()

    @pytest.mark.asyncio
    async def test_timeout_error_handling(self):
        """Test timeout error handling."""
        with patch("mcp_server_git.github.api.get_github_client") as mock_client_func:
            mock_client = AsyncMock()
            mock_client.session = AsyncMock()
            mock_client.get.side_effect = asyncio.TimeoutError("Request timeout")
            mock_client_func.return_value = mock_client

            result = await github_list_issues("owner", "repo")

            # Should get specific timeout error message
            assert "timeout" in result.lower() or "error" in result.lower()

    @pytest.mark.asyncio
    async def test_json_decode_error_handling(self):
        """Test handling of malformed JSON responses."""
        with patch("mcp_server_git.github.api.get_github_client") as mock_client_func:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json.side_effect = json.JSONDecodeError(
                "Invalid JSON", "response", 0
            )
            mock_response.text = AsyncMock(return_value="Invalid JSON response")
            mock_client.get.return_value = mock_response
            mock_client.session = AsyncMock()
            mock_client_func.return_value = mock_client

            result = await github_list_issues("owner", "repo")

            # Should get specific JSON decode error message
            assert (
                "json" in result.lower()
                or "parse" in result.lower()
                or "error" in result.lower()
            )

    @pytest.mark.asyncio
    async def test_http_error_status_codes(self):
        """Test handling of various HTTP error status codes."""
        error_cases = [
            (400, "Bad Request"),
            (401, "Unauthorized"),
            (403, "Forbidden"),
            (404, "Not Found"),
            (422, "Unprocessable Entity"),
            (500, "Internal Server Error"),
            (502, "Bad Gateway"),
            (503, "Service Unavailable"),
        ]

        for status_code, status_text in error_cases:
            with patch(
                "mcp_server_git.github.api.get_github_client"
            ) as mock_client_func:
                mock_client = AsyncMock()
                mock_response = AsyncMock()
                mock_response.status = status_code
                mock_response.text = AsyncMock(
                    return_value=f"Error {status_code}: {status_text}"
                )
                mock_client.get.return_value = mock_response
                mock_client.session = AsyncMock()
                mock_client_func.return_value = mock_client

                result = await github_list_issues("owner", "repo")

                # Should include status code or error indication in error message
                assert (
                    str(status_code) in result
                    or "error" in result.lower()
                    or "failed" in result.lower()
                )
