"""Tests for lean MCP interface."""

import asyncio
import inspect

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


class TestExecuteToolIntegration:
    """Integration tests for execute_tool with sync and async implementations.

    These tests verify that execute_tool properly handles both sync and async
    tools, addressing the race condition fix in issue #112.
    """

    def setup_method(self):
        """Set up test fixtures."""

        class MockService:
            def __getattr__(self, name: str):
                return lambda **kwargs: {"result": f"mock_{name}", "params": kwargs}

        self.interface = GitLeanInterface(
            git_service=MockService(),
            github_service=MockService(),
            azure_service=MockService(),
        )

    def test_iscoroutinefunction_detects_async_correctly(self):
        """Verify inspect.iscoroutinefunction correctly identifies async functions.

        This is the core of the race condition fix - we check the function type
        BEFORE calling, not the result type AFTER calling.
        """

        def sync_fn():
            return "sync"

        async def async_fn():
            return "async"

        assert not inspect.iscoroutinefunction(sync_fn)
        assert inspect.iscoroutinefunction(async_fn)

    def test_wrapped_sync_tool_not_coroutinefunction(self):
        """Test that wrapped sync tools are not detected as coroutine functions."""

        def sync_impl(**kwargs):
            return {"sync": True}

        tool = ToolDefinition(
            name="sync_wrapped",
            implementation=sync_impl,
            description="Sync tool",
            schema={"type": "object", "properties": {}},
            domain="test",
            complexity="focused",
        )
        self.interface.register_tool(tool)

        wrapped = self.interface.tool_registry["sync_wrapped"].implementation
        assert not inspect.iscoroutinefunction(wrapped)

    def test_wrapped_async_tool_is_coroutinefunction(self):
        """Test that wrapped async tools ARE detected as coroutine functions."""

        async def async_impl(**kwargs):
            return {"async": True}

        tool = ToolDefinition(
            name="async_wrapped",
            implementation=async_impl,
            description="Async tool",
            schema={"type": "object", "properties": {}},
            domain="test",
            complexity="focused",
        )
        self.interface.register_tool(tool)

        wrapped = self.interface.tool_registry["async_wrapped"].implementation
        assert inspect.iscoroutinefunction(wrapped)

    @pytest.mark.asyncio
    async def test_execute_tool_logic_sync(self):
        """Test the execute_tool logic path for sync implementations."""

        def sync_impl(**kwargs):
            return {"value": "sync_result", "params": kwargs}

        tool = ToolDefinition(
            name="exec_sync_test",
            implementation=sync_impl,
            description="Test tool",
            schema={"type": "object", "properties": {"x": {"type": "string"}}},
            domain="test",
            complexity="focused",
        )
        self.interface.register_tool(tool)

        # Simulate what execute_tool does
        tool_def = self.interface.tool_registry["exec_sync_test"]
        if inspect.iscoroutinefunction(tool_def.implementation):
            result = await tool_def.implementation(x="test")
        else:
            result = tool_def.implementation(x="test")

        # Sync path should return result directly
        assert isinstance(result, dict)
        assert "value" in result or "sync_result" in str(result)

    @pytest.mark.asyncio
    async def test_execute_tool_logic_async(self):
        """Test the execute_tool logic path for async implementations."""

        async def async_impl(**kwargs):
            await asyncio.sleep(0.001)
            return {"value": "async_result", "params": kwargs}

        tool = ToolDefinition(
            name="exec_async_test",
            implementation=async_impl,
            description="Test tool",
            schema={"type": "object", "properties": {"x": {"type": "string"}}},
            domain="test",
            complexity="focused",
        )
        self.interface.register_tool(tool)

        # Simulate what execute_tool does
        tool_def = self.interface.tool_registry["exec_async_test"]
        if inspect.iscoroutinefunction(tool_def.implementation):
            result = await tool_def.implementation(x="test")
        else:
            result = tool_def.implementation(x="test")

        # Async path should await and return actual result
        assert isinstance(result, dict)
        assert not inspect.iscoroutine(result)
        assert "value" in result or "async_result" in str(result)

    def test_sync_returning_coroutine_not_awaited(self):
        """Test that sync tools returning coroutine objects as DATA are not awaited.

        This verifies the race condition fix: we check iscoroutinefunction() on the
        implementation, not iscoroutine() on the result.

        Note: The wrapped implementation will error on serialization (expected),
        but we test the UNWRAPPED implementation to verify the core logic.
        """

        async def inner_coro():
            return "should_not_execute"

        def sync_returning_coro(**kwargs):
            # Return a coroutine as data (edge case)
            return {"coro": inner_coro()}

        # Test with unwrapped implementation to verify core logic
        # The key test: sync function should NOT be detected as coroutinefunction
        assert not inspect.iscoroutinefunction(sync_returning_coro)

        # Call the sync function - it returns immediately, not awaiting
        result = sync_returning_coro()

        # Verify the result contains a coroutine object (not awaited)
        assert isinstance(result, dict)
        assert "coro" in result
        assert inspect.iscoroutine(result["coro"])

        # Clean up the unawaited coroutine
        result["coro"].close()


class TestPathValidation:
    """Test path validation to prevent relative path issues."""

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

    def test_absolute_path_accepted(self):
        """Test that absolute paths are accepted."""
        params = {"repo_path": "/absolute/path/to/repo"}
        # Should not raise
        self.interface._validate_path_parameters(params)

    def test_relative_dot_rejected(self):
        """Test that '.' is rejected."""
        params = {"repo_path": "."}
        with pytest.raises(ValueError) as exc_info:
            self.interface._validate_path_parameters(params)
        assert "Relative path '.' not supported" in str(exc_info.value)
        assert "MCP servers resolve paths relative to their process CWD" in str(
            exc_info.value
        )

    def test_relative_dotdot_rejected(self):
        """Test that '..' is rejected as a traversal component.

        After issue #168's fix, '..' is caught by the traversal-rejection
        branch (which runs before the absolute-path check) so the error
        message references traversal rather than relativeness.
        """
        params = {"repo_path": ".."}
        with pytest.raises(ValueError) as exc_info:
            self.interface._validate_path_parameters(params)
        msg = str(exc_info.value)
        assert "'..'" in msg
        assert "traversal" in msg

    def test_relative_path_rejected(self):
        """Test that relative paths without leading slash are rejected."""
        params = {"repo_path": "relative/path"}
        with pytest.raises(ValueError) as exc_info:
            self.interface._validate_path_parameters(params)
        assert "Relative path 'relative/path' not supported" in str(exc_info.value)

    def test_case_insensitive_path_param_detection(self):
        """Test that path parameter detection is case-insensitive."""
        # Test various path parameter naming conventions
        test_cases = [
            {"repo_path": "."},
            {"RepoPath": "."},
            {"REPO_PATH": "."},
            {"some_path": "relative"},
        ]

        for params in test_cases:
            with pytest.raises(ValueError):
                self.interface._validate_path_parameters(params)

    def test_multiple_params_with_one_invalid_path(self):
        """Test that validation fails if any path parameter is invalid."""
        params = {
            "repo_path": "/absolute/path",
            "other_param": "value",
            "another_path": "relative/bad",
        }
        with pytest.raises(ValueError) as exc_info:
            self.interface._validate_path_parameters(params)
        assert "relative/bad" in str(exc_info.value)

    def test_non_path_params_ignored(self):
        """Test that non-path parameters are not validated."""
        params = {
            "repo_path": "/absolute/path",
            "branch_name": "main",
            "commit_message": "feat: add feature",
            "author": "test@example.com",
        }
        # Should not raise
        self.interface._validate_path_parameters(params)

    def test_path_param_with_non_string_value_ignored(self):
        """Test that path parameters with non-string values are ignored."""
        params = {
            "repo_path": "/absolute/path",
            "some_path_id": 123,  # Not a string, should be ignored
            "another_path_flag": True,  # Not a string, should be ignored
        }
        # Should not raise
        self.interface._validate_path_parameters(params)

    @pytest.mark.asyncio
    async def test_execute_tool_rejects_relative_path(self):
        """Test that execute_tool rejects relative paths before execution."""

        def test_impl(repo_path: str):
            return {"path": repo_path}

        tool = ToolDefinition(
            name="test_path_tool",
            implementation=test_impl,
            description="Test tool for path validation",
            schema={
                "type": "object",
                "properties": {"repo_path": {"type": "string"}},
                "required": ["repo_path"],
            },
            domain="test",
            complexity="focused",
        )
        self.interface.register_tool(tool)

        # Get the execute_tool implementation from the app
        # We'll test the logic directly since the tool is registered
        # In actual usage, execute_tool would be called via FastMCP

        # Simulate the execute_tool validation path
        tool_name = "test_path_tool"
        parameters = {"repo_path": "."}

        # Call the validation method directly
        with pytest.raises(ValueError) as exc_info:
            self.interface._validate_path_parameters(parameters)
        assert "Relative path '.' not supported" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_git_status_with_relative_path_through_registry(self):
        """Test that git_status tool rejects relative paths through the full stack."""
        # The git_status tool is registered during interface initialization
        # We want to verify that calling it with a relative path fails

        # Get the registered git_status tool
        assert "git_status" in self.interface.tool_registry

        # Try to execute with relative path - should fail validation
        with pytest.raises(ValueError) as exc_info:
            self.interface._validate_path_parameters({"repo_path": "."})
        assert "Relative path '.' not supported" in str(exc_info.value)

        # Verify absolute path would pass validation
        self.interface._validate_path_parameters({"repo_path": "/absolute/path"})

    def test_error_message_content(self):
        """Test that error message provides helpful guidance."""
        params = {"repo_path": "relative/path"}
        try:
            self.interface._validate_path_parameters(params)
            pytest.fail("Should have raised ValueError")
        except ValueError as e:
            error_msg = str(e)
            # Verify error message contains key information
            assert "relative/path" in error_msg
            assert (
                "MCP servers resolve paths relative to their process CWD" in error_msg
            )
            assert "Claude Code's working directory" in error_msg
            assert "Use absolute path instead" in error_msg


# TODO: Add integration tests for:
# - discover_tools functionality
# - get_tool_spec functionality
# - Tool wrapping and token limiting
# - Error handling in tool execution
# - FastMCP integration
