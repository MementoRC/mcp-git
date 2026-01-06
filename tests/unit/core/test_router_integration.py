"""Unit tests for router integration with Azure and GitHub async tools."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.mcp_server_git.core.tools import GitToolRouter, ToolRegistry, ToolCategory, GitTools


class TestRouterIntegration:
    """Test router integration for async Azure and GitHub tools."""

    @pytest.fixture
    def router_with_mocks(self):
        """Create a router with mocked handlers for testing."""
        registry = ToolRegistry()
        registry.initialize_default_tools()
        router = GitToolRouter(registry)
        
        # Create mock handlers
        mock_git_handlers = {
            "git_status": MagicMock(return_value="On branch main")
        }
        
        mock_github_handlers = {
            "github_get_pr_details": AsyncMock(return_value="PR #123 details")
        }
        
        mock_security_handlers = {
            "git_security_validate": MagicMock(return_value="Security check passed")
        }
        
        mock_azure_handlers = {
            "azure_get_build_status": AsyncMock(return_value="Build #456 status"),
            "azure_get_build_logs": AsyncMock(return_value="Build logs content"),
            "azure_get_failing_jobs": AsyncMock(return_value="No failing jobs"),
            "azure_list_builds": AsyncMock(return_value="Builds list")
        }
        
        router.set_handlers(
            mock_git_handlers,
            mock_github_handlers, 
            mock_security_handlers,
            mock_azure_handlers
        )
        
        return router, {
            "git": mock_git_handlers,
            "github": mock_github_handlers,
            "security": mock_security_handlers,
            "azure": mock_azure_handlers
        }

    @pytest.mark.asyncio
    async def test_azure_tools_routed_as_async(self, router_with_mocks):
        """Test that Azure tools are properly routed as async functions."""
        router, handlers = router_with_mocks
        
        # Test azure_get_build_status
        result = await router.route_tool_call(
            GitTools.AZURE_GET_BUILD_STATUS.value,
            {"project": "test-project", "build_id": 456}
        )
        
        assert len(result) == 1
        assert result[0].text == "Build #456 status"
        handlers["azure"]["azure_get_build_status"].assert_called_once_with("test-project", 456)

    @pytest.mark.asyncio
    async def test_azure_get_build_logs_async_routing(self, router_with_mocks):
        """Test azure_get_build_logs async routing."""
        router, handlers = router_with_mocks
        
        result = await router.route_tool_call(
            GitTools.AZURE_GET_BUILD_LOGS.value,
            {"project": "test-project", "build_id": 456, "log_id": 789}
        )
        
        assert len(result) == 1
        assert result[0].text == "Build logs content"
        handlers["azure"]["azure_get_build_logs"].assert_called_once_with("test-project", 456, 789)

    @pytest.mark.asyncio
    async def test_azure_get_failing_jobs_async_routing(self, router_with_mocks):
        """Test azure_get_failing_jobs async routing."""
        router, handlers = router_with_mocks
        
        result = await router.route_tool_call(
            GitTools.AZURE_GET_FAILING_JOBS.value,
            {"project": "test-project", "build_id": 456, "include_logs": True}
        )
        
        assert len(result) == 1
        assert result[0].text == "No failing jobs"
        handlers["azure"]["azure_get_failing_jobs"].assert_called_once_with("test-project", 456, True)

    @pytest.mark.asyncio
    async def test_azure_list_builds_async_routing(self, router_with_mocks):
        """Test azure_list_builds async routing."""
        router, handlers = router_with_mocks
        
        result = await router.route_tool_call(
            GitTools.AZURE_LIST_BUILDS.value,
            {
                "project": "test-project",
                "repository_id": "repo123", 
                "branch_name": "refs/heads/main",
                "status": "completed",
                "result": "succeeded",
                "top": 50,
                "continuation_token": "token123"
            }
        )
        
        assert len(result) == 1
        assert result[0].text == "Builds list"
        handlers["azure"]["azure_list_builds"].assert_called_once_with(
            "test-project", "repo123", "refs/heads/main", "completed", "succeeded", 50, "token123"
        )

    @pytest.mark.asyncio
    async def test_github_tools_routed_as_async(self, router_with_mocks):
        """Test that GitHub tools are properly routed as async functions."""
        router, handlers = router_with_mocks
        
        result = await router.route_tool_call(
            GitTools.GITHUB_GET_PR_DETAILS.value,
            {"repo_owner": "testorg", "repo_name": "testrepo", "pr_number": 123}
        )
        
        assert len(result) == 1
        assert result[0].text == "PR #123 details"
        handlers["github"]["github_get_pr_details"].assert_called_once()

    @pytest.mark.asyncio
    async def test_git_tools_routed_as_sync(self, router_with_mocks):
        """Test that Git tools are routed as synchronous functions."""
        router, handlers = router_with_mocks
        
        result = await router.route_tool_call(
            GitTools.STATUS.value,
            {"repo_path": "/tmp/test-repo"}
        )
        
        assert len(result) == 1
        assert result[0].text == "On branch main"
        handlers["git"]["git_status"].assert_called_once()

    @pytest.mark.asyncio
    async def test_router_validation_azure_tools_no_repo_required(self, router_with_mocks):
        """Test that Azure tools don't require repo_path parameter."""
        router, handlers = router_with_mocks
        
        # Azure tools should work without repo_path
        result = await router.route_tool_call(
            GitTools.AZURE_GET_BUILD_STATUS.value,
            {"project": "test-project", "build_id": 456}
        )
        
        assert len(result) == 1
        assert result[0].text == "Build #456 status"

    @pytest.mark.asyncio
    async def test_router_validation_git_tools_require_repo(self, router_with_mocks):
        """Test that Git tools require repo_path parameter."""
        router, handlers = router_with_mocks
        
        # Git tools should fail without repo_path
        result = await router.route_tool_call(
            GitTools.STATUS.value,
            {}  # Missing repo_path
        )
        
        assert len(result) == 1
        assert "repo_path parameter required" in result[0].text

    @pytest.mark.asyncio
    async def test_router_validation_github_tools_require_owner_name(self, router_with_mocks):
        """Test that GitHub tools require repo_owner and repo_name parameters."""
        router, handlers = router_with_mocks
        
        # GitHub tools should fail without repo_owner and repo_name
        result = await router.route_tool_call(
            GitTools.GITHUB_GET_PR_DETAILS.value,
            {"pr_number": 123}  # Missing repo_owner and repo_name
        )
        
        assert len(result) == 1
        assert "repo_owner and repo_name parameters required" in result[0].text

    @pytest.mark.asyncio
    async def test_router_unknown_tool_handling(self, router_with_mocks):
        """Test router handling of unknown tools."""
        router, handlers = router_with_mocks
        
        result = await router.route_tool_call(
            "unknown_tool",
            {"param": "value"}
        )
        
        assert len(result) == 1
        assert "Unknown tool: unknown_tool" in result[0].text

    @pytest.mark.asyncio
    async def test_router_error_handling(self, router_with_mocks):
        """Test router error handling for tool execution failures."""
        router, handlers = router_with_mocks
        
        # Make the Azure handler raise an exception
        handlers["azure"]["azure_get_build_status"].side_effect = Exception("Test error")
        
        result = await router.route_tool_call(
            GitTools.AZURE_GET_BUILD_STATUS.value,
            {"project": "test-project", "build_id": 456}
        )
        
        assert len(result) == 1
        assert "Tool execution failed" in result[0].text
        assert "Test error" in result[0].text

    def test_router_handlers_initialization(self):
        """Test router handlers initialization."""
        registry = ToolRegistry()
        registry.initialize_default_tools()
        router = GitToolRouter(registry)
        
        # Router should not be initialized yet
        assert not router._handlers_initialized
        
        # Set empty handlers
        router.set_handlers({}, {}, {}, {})
        
        # Router should now be initialized
        assert router._handlers_initialized

    @pytest.mark.asyncio
    async def test_router_uninitialized_handlers(self):
        """Test router behavior with uninitialized handlers."""
        registry = ToolRegistry()
        registry.initialize_default_tools()
        router = GitToolRouter(registry)
        
        # Don't initialize handlers
        result = await router.route_tool_call(
            GitTools.AZURE_GET_BUILD_STATUS.value,
            {"project": "test", "build_id": 123}
        )
        
        assert len(result) == 1
        assert "Tool handlers not initialized" in result[0].text