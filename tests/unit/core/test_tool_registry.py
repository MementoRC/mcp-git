"""Unit tests for tool registry integration."""

import pytest

from src.mcp_server_git.core.tools import GitTools, ToolCategory, ToolRegistry


class TestToolRegistryIntegration:
    """Test tool registry integration for all tool categories."""

    def test_azure_tools_registered(self):
        """Test that Azure tools are properly registered in the tool registry."""
        registry = ToolRegistry()
        registry.initialize_default_tools()
        
        azure_tools = registry.get_tools_by_category(ToolCategory.AZURE)
        assert len(azure_tools) == 4
        
        # Verify specific Azure tools are registered
        azure_tool_names = {tool.name for tool in azure_tools}
        expected_azure_tools = {
            GitTools.AZURE_GET_BUILD_STATUS.value,
            GitTools.AZURE_GET_BUILD_LOGS.value,
            GitTools.AZURE_GET_FAILING_JOBS.value,
            GitTools.AZURE_LIST_BUILDS.value,
        }
        assert azure_tool_names == expected_azure_tools
        
        # Verify each tool has proper configuration
        for tool in azure_tools:
            assert tool.category == ToolCategory.AZURE
            assert tool.handler is not None
            assert not tool.requires_repo  # Azure tools don't require repo
            assert not tool.requires_github_token
            assert tool.description
            assert tool.schema

    def test_github_tools_registered(self):
        """Test that GitHub tools are properly registered in the tool registry."""
        registry = ToolRegistry()
        registry.initialize_default_tools()
        
        github_tools = registry.get_tools_by_category(ToolCategory.GITHUB)
        assert len(github_tools) == 15  # Expected GitHub tools count
        
        # Verify all GitHub tools require GitHub token
        for tool in github_tools:
            assert tool.category == ToolCategory.GITHUB
            assert not tool.requires_repo
            assert tool.requires_github_token
            assert tool.description
            assert tool.schema

    def test_git_tools_registered(self):
        """Test that Git tools are properly registered in the tool registry."""
        registry = ToolRegistry()
        registry.initialize_default_tools()
        
        git_tools = registry.get_tools_by_category(ToolCategory.GIT)
        assert len(git_tools) > 0  # Should have Git tools
        
        # Verify most Git tools require repo (except git_init)
        for tool in git_tools:
            assert tool.category == ToolCategory.GIT
            if tool.name != GitTools.INIT.value:
                assert tool.requires_repo
            assert not tool.requires_github_token
            assert tool.description
            assert tool.schema

    def test_security_tools_registered(self):
        """Test that Security tools are properly registered in the tool registry."""
        registry = ToolRegistry()
        registry.initialize_default_tools()
        
        security_tools = registry.get_tools_by_category(ToolCategory.SECURITY)
        assert len(security_tools) == 2  # Expected security tools count
        
        # Verify security tools configuration
        for tool in security_tools:
            assert tool.category == ToolCategory.SECURITY
            assert tool.requires_repo
            assert not tool.requires_github_token
            assert tool.description
            assert tool.schema

    def test_get_tool_by_name(self):
        """Test retrieving specific tools by name."""
        registry = ToolRegistry()
        registry.initialize_default_tools()
        
        # Test Azure tool retrieval
        azure_status_tool = registry.get_tool(GitTools.AZURE_GET_BUILD_STATUS.value)
        assert azure_status_tool is not None
        assert azure_status_tool.name == GitTools.AZURE_GET_BUILD_STATUS.value
        assert azure_status_tool.category == ToolCategory.AZURE
        
        # Test non-existent tool
        non_existent = registry.get_tool("non_existent_tool")
        assert non_existent is None

    def test_list_all_tools(self):
        """Test listing all tools in MCP format."""
        registry = ToolRegistry()
        registry.initialize_default_tools()
        
        all_tools = registry.list_tools()
        assert len(all_tools) > 0
        
        # Verify MCP Tool format
        for tool in all_tools:
            assert hasattr(tool, 'name')
            assert hasattr(tool, 'description')
            assert hasattr(tool, 'inputSchema')
            assert tool.inputSchema is not None

    def test_registry_initialization_idempotent(self):
        """Test that registry initialization can be called multiple times safely."""
        registry = ToolRegistry()
        
        # First initialization
        registry.initialize_default_tools()
        first_count = len(registry.tools)
        
        # Second initialization should not add duplicate tools
        registry.initialize_default_tools()
        second_count = len(registry.tools)
        
        assert first_count == second_count
        assert first_count > 0

    def test_tool_categories_complete(self):
        """Test that all expected tool categories are represented."""
        registry = ToolRegistry()
        registry.initialize_default_tools()
        
        # Get all categories present in registry
        present_categories = {tool.category for tool in registry.tools.values()}
        
        # Verify all expected categories are present
        expected_categories = {
            ToolCategory.GIT,
            ToolCategory.GITHUB, 
            ToolCategory.AZURE,
            ToolCategory.SECURITY,
        }
        assert present_categories == expected_categories