"""Tests for lean MCP interface."""

import inspect

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


import asyncio

import pytest


class TestAsyncToolExecution:
    """Test async tool execution handling - fixes issue #112."""

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

    def test_async_tool_wrapper_is_async(self):
        """Test that async tools are wrapped with async wrapper."""
        import inspect

        async def async_impl(**kwargs):
            return {"async_result": True}

        tool = ToolDefinition(
            name="async_test_tool",
            implementation=async_impl,
            description="Async test tool",
            schema={"type": "object", "properties": {}},
            domain="test",
            complexity="focused",
        )
        self.interface.register_tool(tool)

        # The registered tool should be wrapped and remain async
        registered_tool = self.interface.tool_registry["async_test_tool"]
        assert inspect.iscoroutinefunction(registered_tool.implementation)

    def test_sync_tool_wrapper_is_sync(self):
        """Test that sync tools are wrapped with sync wrapper."""
        import inspect

        def sync_impl(**kwargs):
            return {"sync_result": True}

        tool = ToolDefinition(
            name="sync_test_tool",
            implementation=sync_impl,
            description="Sync test tool",
            schema={"type": "object", "properties": {}},
            domain="test",
            complexity="focused",
        )
        self.interface.register_tool(tool)

        # The registered tool should be wrapped but remain sync
        registered_tool = self.interface.tool_registry["sync_test_tool"]
        assert not inspect.iscoroutinefunction(registered_tool.implementation)

    @pytest.mark.asyncio
    async def test_async_tool_execution_returns_value_not_coroutine(self):
        """Test that async tools return actual values, not coroutine objects.

        This is the core fix for issue #112 - async functions were returning
        unawaited coroutines that caused JSON serialization failures.
        """

        async def async_impl(**kwargs):
            await asyncio.sleep(0.01)  # Simulate async work
            return {"result": "async_value", "params": kwargs}

        tool = ToolDefinition(
            name="async_value_tool",
            implementation=async_impl,
            description="Async value test",
            schema={
                "type": "object",
                "properties": {"test_param": {"type": "string"}},
            },
            domain="test",
            complexity="focused",
        )
        self.interface.register_tool(tool)

        # Execute the wrapped async function
        registered_tool = self.interface.tool_registry["async_value_tool"]
        result = await registered_tool.implementation(test_param="hello")

        # Result should be an actual dict, not a coroutine
        assert not inspect.iscoroutine(result)
        assert isinstance(result, dict)
        # Token limiter wraps result, so check for content
        assert "result" in result or "async_value" in str(result)

    @pytest.mark.asyncio
    async def test_async_tool_error_handling(self):
        """Test that async tools handle errors correctly."""

        async def failing_async_impl(**kwargs):
            raise ValueError("Async failure!")

        tool = ToolDefinition(
            name="failing_async_tool",
            implementation=failing_async_impl,
            description="Failing async tool",
            schema={"type": "object", "properties": {}},
            domain="test",
            complexity="focused",
        )
        self.interface.register_tool(tool)

        registered_tool = self.interface.tool_registry["failing_async_tool"]
        result = await registered_tool.implementation()

        # Error should be caught and returned as dict, not raised
        assert isinstance(result, dict)
        assert "error" in result
        assert "Async failure!" in result["error"]


# TODO: Add integration tests for:
# - discover_tools functionality
# - get_tool_spec functionality
# - execute_tool with parameter validation
# - Tool wrapping and token limiting
# - Error handling in tool execution
# - FastMCP integration
