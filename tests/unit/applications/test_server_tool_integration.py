"""Unit tests for server application tool integration."""

import pytest
from unittest.mock import MagicMock, patch

from mcp_server_git.applications.server_application import GitTools, ServerApplication


class TestServerToolIntegration:
    """Test that tools are properly integrated in the active server application."""

    def test_git_tools_enum_exists(self):
        """Test that GitTools enum defines all expected tool categories."""
        # Verify Git tools
        assert hasattr(GitTools, 'STATUS')
        assert hasattr(GitTools, 'LOG')
        assert hasattr(GitTools, 'DIFF_UNSTAGED')
        
        # Verify GitHub tools exist (sampled)
        assert hasattr(GitTools, 'GITHUB_LIST_PULL_REQUESTS')
        assert hasattr(GitTools, 'GITHUB_GET_PR_DETAILS')
        
        # Verify Azure tools exist
        assert hasattr(GitTools, 'AZURE_GET_BUILD_STATUS')
        assert hasattr(GitTools, 'AZURE_GET_BUILD_LOGS')
        assert hasattr(GitTools, 'AZURE_GET_FAILING_JOBS')
        assert hasattr(GitTools, 'AZURE_LIST_BUILDS')

    def test_azure_tools_defined(self):
        """Test that Azure tools are properly defined."""
        azure_tools = [
            GitTools.AZURE_GET_BUILD_STATUS.value,
            GitTools.AZURE_GET_BUILD_LOGS.value,
            GitTools.AZURE_GET_FAILING_JOBS.value,
            GitTools.AZURE_LIST_BUILDS.value,
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
        assert hasattr(app, '_execute_tool_operation')

    @pytest.mark.asyncio
    async def test_server_has_tool_execution_method(self):
        """Test that the server has the tool execution method."""
        app = ServerApplication()
        
        # Verify the method exists and is callable
        assert hasattr(app, '_execute_tool_operation')
        assert callable(getattr(app, '_execute_tool_operation'))

    def test_github_tools_registered(self):
        """Test that GitHub tools are properly defined in GitTools enum."""
        # Sample of GitHub tools that should exist
        github_tools = [
            'GITHUB_LIST_PULL_REQUESTS',
            'GITHUB_GET_PR_DETAILS',
            'GITHUB_GET_PR_STATUS',
            'GITHUB_CREATE_PULL_REQUEST',
            'GITHUB_UPDATE_PULL_REQUEST',
        ]
        
        for tool_name in github_tools:
            assert hasattr(GitTools, tool_name), f"GitHub tool {tool_name} not found"

    def test_git_tools_registered(self):
        """Test that Git tools are properly defined in GitTools enum."""
        # Core Git tools that should exist
        git_tools = [
            'STATUS',
            'LOG',
            'DIFF_UNSTAGED',
            'DIFF_STAGED',
            'COMMIT',
            'ADD',
            'PUSH',
            'PULL',
        ]
        
        for tool_name in git_tools:
            assert hasattr(GitTools, tool_name), f"Git tool {tool_name} not found"

    def test_security_tools_registered(self):
        """Test that Security tools are properly defined in GitTools enum."""
        # Security tools that should exist
        assert hasattr(GitTools, 'SECURITY_VALIDATE')
