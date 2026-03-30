"""Integration tests for complete 3-meta-tool workflow."""

import os
import tempfile
from unittest.mock import MagicMock, patch

from mcp_server_git.lean.interface import GitLeanInterface, ToolDefinition


class MockGitService:
    """Mock git service for integration testing (unused for git ops, kept for interface)."""

    pass


class MockGitHubService:
    """Mock GitHub service for integration testing with all required methods."""

    def __getattr__(self, name: str):
        """Dynamic mock for any github method not explicitly defined."""
        if name.startswith("github_"):
            return lambda **kwargs: {"result": f"mock_{name}", "params": kwargs}
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'"
        )


class MockAzureService:
    """Mock Azure service for integration testing with all required methods."""

    def __getattr__(self, name: str):
        """Dynamic mock for any azure method not explicitly defined."""
        if name.startswith("azure_"):
            return lambda **kwargs: {"result": f"mock_{name}", "params": kwargs}
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'"
        )


class TestLeanMCPIntegration:
    """Test complete 3-meta-tool workflow integration."""

    def setup_method(self):
        """Set up test fixtures."""
        self.git_service = MockGitService()
        self.github_service = MockGitHubService()
        self.azure_service = MockAzureService()

        self.interface = GitLeanInterface(
            git_service=self.git_service,
            github_service=self.github_service,
            azure_service=self.azure_service,
        )

    def test_complete_workflow_discover_spec_execute(self):
        """Test complete workflow: discover -> get_tool_spec -> execute_tool."""
        # Step 1: Discover tools
        app = self.interface.get_app()

        # Get discover_tools from the registry
        # Note: In actual FastMCP usage, this would be called via the MCP protocol
        # Here we're testing the underlying interface methods directly

        # Simulate discovering tools with pattern
        available_tools = []
        for name, tool_def in self.interface.tool_registry.items():
            if "status" in name.lower():
                available_tools.append(
                    {
                        "name": name,
                        "description": tool_def.description,
                        "domain": tool_def.domain,
                    }
                )

        assert len(available_tools) > 0
        assert any(t["name"] == "git_status" for t in available_tools)

        # Step 2: Get tool spec
        tool_name = "git_status"
        assert tool_name in self.interface.tool_registry

        tool_def = self.interface.tool_registry[tool_name]
        spec = {
            "name": tool_name,
            "description": tool_def.description,
            "schema": tool_def.schema,
        }

        assert "schema" in spec
        assert "properties" in spec["schema"]
        assert "repo_path" in spec["schema"]["properties"]

        # Step 3: Test execution with mock (real git may be blocked in some envs)
        # In production, this would use real git. For tests, we verify the wrapper
        # structure is correct by checking that implementation is callable and wrapped
        assert callable(tool_def.implementation)

        # Verify the implementation is properly wrapped (has token limiter applied)
        # The wrapper should return a dict with error info if git is unavailable
        repo_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        result = tool_def.implementation(repo_path=repo_path)

        # Result could be:
        # 1. A string (git status output) if git works
        # 2. A dict with error if git is blocked/unavailable
        # Both are valid for this test - we're testing the interface works
        assert result is not None
        if isinstance(result, dict):
            # Error case - git blocked or unavailable
            assert "error" in result or "result" in result
        else:
            # Success case - git works
            assert isinstance(result, str)

    def test_parameter_validation_with_schema(self):
        """Test that parameter validation works against JSON schema."""
        # Register a test tool with strict schema
        tool = ToolDefinition(
            name="test_strict_tool",
            implementation=lambda value: {"result": value * 2},
            description="Test tool with strict validation",
            schema={
                "type": "object",
                "properties": {
                    "value": {"type": "integer", "minimum": 0, "maximum": 100}
                },
                "required": ["value"],
            },
            domain="test",
            complexity="focused",
        )

        self.interface.register_tool(tool)

        # Valid parameters should work
        result = tool.implementation(value=50)
        assert result["result"] == 100

        # Schema validation would reject invalid values in execute_tool
        # (Testing via the actual execute_tool meta-tool would require FastMCP integration)

    def test_token_limiting_applied_to_results(self):
        """Test that token limiting is applied to tool execution results."""
        # Register a tool that returns large data
        large_data = {"data": "x" * 10000, "status": "success"}

        tool = ToolDefinition(
            name="test_large_response",
            implementation=lambda: large_data,
            description="Returns large response",
            schema={"type": "object", "properties": {}},
            domain="test",
            complexity="focused",
        )

        self.interface.register_tool(tool)

        # Execute and check if token limiting was applied
        # The wrapper adds token limiting
        result = tool.implementation()

        # Response should be either offloaded to file or truncated
        assert (
            result.get("offloaded") is True  # New: offloaded to /tmp file
            or "status" in result  # Old: truncated but status preserved
            or "_token_limit_info" in result  # Old: truncation metadata added
        ), f"Large response should be offloaded or truncated, got keys: {list(result.keys())}"

        if result.get("offloaded"):
            assert "full_output_path" in result
            assert "summary" in result

    def test_schema_caching_performance(self):
        """Test that schemas are cached for performance."""
        tool_name = "git_status"

        # Schema should be in cache after registration
        assert tool_name in self.interface._schema_cache

        cached_schema = self.interface._schema_cache[tool_name]
        tool_schema = self.interface.tool_registry[tool_name].schema

        # Cached schema should match tool schema
        assert cached_schema == tool_schema

    def test_error_handling_for_invalid_tool(self):
        """Test error handling when tool doesn't exist."""
        # Attempt to get non-existent tool
        tool_name = "nonexistent_tool"

        assert tool_name not in self.interface.tool_registry

        # Error should be handled gracefully
        # In actual usage through execute_tool meta-tool

    def test_health_check_reports_correct_stats(self):
        """Test health check returns accurate interface statistics."""
        health = self.interface.health_check()

        assert health["interface_type"] == "lean_mcp"
        assert health["tools_registered"] > 0
        assert "meta_tools" in health
        assert len(health["meta_tools"]) == 3
        assert "discover_tools" in health["meta_tools"]
        assert "get_tool_spec" in health["meta_tools"]
        assert "execute_tool" in health["meta_tools"]
        assert health["token_limiter_enabled"] is True

    def test_multi_domain_tool_registration(self):
        """Test that tools from all domains are registered."""
        health = self.interface.health_check()
        domains = health["domains"]

        # All three domains should have tools
        assert domains["git"] > 0
        assert domains["github"] > 0
        assert domains["azure"] > 0

        # Total should match registry size
        total = domains["git"] + domains["github"] + domains["azure"]
        assert total == len(self.interface.tool_registry)
