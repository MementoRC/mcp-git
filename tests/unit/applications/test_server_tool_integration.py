"""Unit tests for server application tool integration."""

from unittest.mock import MagicMock, patch

import pytest

from mcp_server_git.applications.server_application import (
    AzureTools,
    GitHubTools,
    GitTools,
    ServerApplication,
)


class TestServerToolIntegration:
    """Test that tools are properly integrated in the active server application."""

    def test_git_tools_enum_exists(self):
        """Test that GitTools enum defines all expected Git tools."""
        # Verify Git tools
        assert hasattr(GitTools, "STATUS")
        assert hasattr(GitTools, "LOG")
        assert hasattr(GitTools, "DIFF_UNSTAGED")
        assert hasattr(GitTools, "COMMIT")
        assert hasattr(GitTools, "PUSH")
        assert hasattr(GitTools, "PULL")

    def test_azure_tools_defined(self):
        """Test that Azure tools are properly defined."""
        azure_tools = [
            AzureTools.GET_BUILD_STATUS.value,
            AzureTools.GET_BUILD_LOGS.value,
            AzureTools.GET_FAILING_JOBS.value,
            AzureTools.LIST_BUILDS.value,
        ]

        expected_names = [
            "azure_get_build_status",
            "azure_get_build_logs",
            "azure_get_failing_jobs",
            "azure_list_builds",
        ]

        assert azure_tools == expected_names

    @pytest.mark.asyncio
    async def test_server_application_initializes(self):
        """Test that ServerApplication can be initialized."""
        # This test ensures the server structure is valid
        # We don't run it fully, just verify it can be created
        app = ServerApplication()
        assert app is not None
        assert hasattr(app, "_execute_tool_operation")

    @pytest.mark.asyncio
    async def test_server_has_tool_execution_method(self):
        """Test that the server has the tool execution method."""
        app = ServerApplication()

        # Verify the method exists and is callable
        assert hasattr(app, "_execute_tool_operation")
        assert callable(app._execute_tool_operation)

    def test_github_tools_registered(self):
        """Test that GitHub tools are properly defined in GitHubTools enum."""
        # Sample of GitHub tools that should exist
        github_tools = [
            "LIST_PULL_REQUESTS",
            "GET_PR_DETAILS",
            "GET_PR_STATUS",
            "CREATE_PR",
            "UPDATE_PR",
        ]

        for tool_name in github_tools:
            assert hasattr(GitHubTools, tool_name), f"GitHub tool {tool_name} not found"

    def test_git_tools_registered(self):
        """Test that Git tools are properly defined in GitTools enum."""
        # Core Git tools that should exist
        git_tools = [
            "STATUS",
            "LOG",
            "DIFF_UNSTAGED",
            "DIFF_STAGED",
            "COMMIT",
            "ADD",
            "PUSH",
            "PULL",
        ]

        for tool_name in git_tools:
            assert hasattr(GitTools, tool_name), f"Git tool {tool_name} not found"
