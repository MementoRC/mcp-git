"""Tests for lean MCP interface."""

import pytest

from mcp_server_git.lean.interface import GitLeanInterface, ToolDefinition


class MockService:
    """Mock service for testing with dynamic method support."""

    def __getattr__(self, name: str):
        """Dynamic mock for any method not explicitly defined."""
        # Return a lambda that accepts any kwargs and returns a simple dict
        return lambda **kwargs: {"result": f"mock_{name}", "params": kwargs}


class TestToolDefinition:
    """Test tool definition class."""

    def test_tool_creation(self):
        """Test creating a tool definition."""

        def impl(x):
            return x * 2

        tool = ToolDefinition(
            name="test_tool",
            implementation=impl,
            description="Test tool",
            schema={"type": "object"},
            domain="test",
            complexity="focused",
        )
        assert tool.name == "test_tool"
        assert tool.domain == "test"
        assert tool.implementation(5) == 10


class TestGitLeanInterface:
    """Test Git lean MCP interface."""

    def setup_method(self):
        """Set up test fixtures."""
        self.git_service = MockService()
        self.github_service = MockService()
        self.azure_service = MockService()

        self.interface = GitLeanInterface(
            git_service=self.git_service,
            github_service=self.github_service,
            azure_service=self.azure_service,
        )

    def test_initialization(self):
        """Test interface initialization."""
        assert self.interface.git_service == self.git_service
        assert len(self.interface.tool_registry) > 0
        assert self.interface.app is not None

    def test_tool_registration(self):
        """Test registering a tool."""
        initial_count = len(self.interface.tool_registry)

        tool = ToolDefinition(
            name="custom_tool",
            implementation=lambda **kwargs: "custom result",
            description="Custom tool",
            schema={"type": "object", "properties": {"param": {"type": "string"}}},
            domain="custom",
            complexity="focused",
        )
        self.interface.register_tool(tool)

        assert len(self.interface.tool_registry) == initial_count + 1
        assert "custom_tool" in self.interface.tool_registry

    def test_parameter_validation_success(self):
        """Test successful parameter validation."""
        # Register a test tool
        tool = ToolDefinition(
            name="test_tool",
            implementation=lambda param1: f"Got: {param1}",
            description="Test tool",
            schema={
                "type": "object",
                "properties": {"param1": {"type": "string"}},
            },
            domain="test",
            complexity="focused",
        )
        self.interface.register_tool(tool)

        # This should work through the execute_tool meta-tool
        # Note: In actual usage, execute_tool would be called via FastMCP
        # Here we're testing the tool registry directly
        result = tool.implementation(param1="value")
        assert "Got: value" in result

    def test_parameter_validation_failure(self):
        """Test parameter validation rejects unexpected parameters."""
        # This would be tested through the execute_tool function
        # which validates against the schema before execution
        # TODO: Add integration test with actual FastMCP execution
        pass

    def test_health_check(self):
        """Test health check functionality."""
        health = self.interface.health_check()
        assert "interface_type" in health
        assert health["interface_type"] == "lean_mcp"
        assert "tools_registered" in health
        assert health["tools_registered"] > 0
        assert "meta_tools" in health
        assert len(health["meta_tools"]) == 3


# TODO: Add integration tests for:
# - discover_tools functionality
# - get_tool_spec functionality
# - execute_tool with parameter validation
# - Tool wrapping and token limiting
# - Error handling in tool execution
# - FastMCP integration
