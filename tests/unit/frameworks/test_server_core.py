"""Unit tests for the MCPGitServerCore framework component."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from mcp.types import ClientCapabilities

from mcp_server_git.frameworks.server_core import MCPGitServerCore


class TestMCPGitServerCore:
    """Test suite for MCPGitServerCore."""

    @pytest.fixture
    def server_core(self):
        """Create a server core instance for testing."""
        return MCPGitServerCore("test-server")

    def test_initialization(self, server_core):
        """Test server core initialization."""
        assert server_core.server_name == "test-server"
        assert server_core.server is None
        assert server_core.repository_path is None
        assert server_core.is_running is False
        assert server_core.start_time is None
        assert server_core.error_count == 0
        assert server_core.last_error is None
        assert server_core.request_count == 0
        assert server_core.client_capabilities is None

    def test_initialize_server(self, server_core, tmp_path):
        """Test server initialization."""
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        with patch("mcp_server_git.frameworks.server_core.Server") as MockServer:
            mock_server = Mock()
            MockServer.return_value = mock_server

            result = server_core.initialize_server(repo_path)

            assert result == mock_server
            assert server_core.server == mock_server
            assert server_core.repository_path == repo_path
            assert server_core.start_time is not None
            MockServer.assert_called_once_with("test-server")

    def test_initialize_server_already_initialized(self, server_core):
        """Test server initialization when already initialized."""
        mock_server = Mock()
        server_core.server = mock_server

        result = server_core.initialize_server()

        assert result == mock_server  # Returns existing instance

    @pytest.mark.asyncio
    async def test_start_server_not_initialized(self, server_core):
        """Test starting server when not initialized."""
        with pytest.raises(RuntimeError, match="Server not initialized"):
            await server_core.start_server()

    @pytest.mark.asyncio
    async def test_start_server_test_mode(self, server_core):
        """Test starting server in test mode."""
        server_core.server = Mock()

        with patch("mcp_server_git.frameworks.server_core.stdio_server") as mock_stdio:
            with patch("asyncio.sleep") as mock_sleep:
                mock_stdio.return_value.__aenter__.return_value = (Mock(), Mock())

                await server_core.start_server(test_mode=True)

                assert server_core.is_running is False  # Should stop after test
                # In test mode, asyncio.sleep(60) is called for timeout
                mock_sleep.assert_called_with(60)

    def test_get_server_instance(self, server_core):
        """Test getting server instance."""
        assert server_core.get_server_instance() is None

        mock_server = Mock()
        server_core.server = mock_server

        assert server_core.get_server_instance() == mock_server

    def test_increment_request_count(self, server_core):
        """Test request count incrementation."""
        assert server_core.request_count == 0

        server_core.increment_request_count()
        assert server_core.request_count == 1

        server_core.increment_request_count()
        assert server_core.request_count == 2

    def test_set_client_capabilities(self, server_core):
        """Test setting client capabilities."""
        capabilities = ClientCapabilities()

        server_core.set_client_capabilities(capabilities)

        assert server_core.client_capabilities == capabilities

    def test_get_component_state(self, server_core):
        """Test getting component state."""
        state = server_core.get_component_state()

        assert state.component_id == "server-core-test-server"
        assert state.component_type == "MCPGitServerCore"
        assert isinstance(state.state_data, dict)
        assert state.state_data["server_name"] == "test-server"
        assert state.state_data["is_running"] is False
        assert state.state_data["error_count"] == 0
        assert isinstance(state.last_updated, datetime)

    def test_validate_component(self, server_core, tmp_path):
        """Test component validation."""
        # Test uninitialized server
        result = server_core.validate_component()
        assert result.is_valid is False
        assert "Server not initialized" in result.validation_errors

        # Test with initialized server
        server_core.server = Mock()
        result = server_core.validate_component()
        assert result.is_valid is True
        assert len(result.validation_errors) == 0

        # Test with non-existent repository path
        server_core.repository_path = tmp_path / "non-existent"
        result = server_core.validate_component()
        assert result.is_valid is False
        assert any(
            "Repository path does not exist" in e for e in result.validation_errors
        )

        # Test high error count
        server_core.repository_path = None
        server_core.error_count = 150
        result = server_core.validate_component()
        assert result.is_valid is True  # Still valid, just warning
        assert any("High error count" in w for w in result.validation_warnings)

    def test_get_debug_info(self, server_core):
        """Test getting debug information."""
        server_core.request_count = 10
        server_core.error_count = 2
        server_core.start_time = datetime.now()

        debug_info = server_core.get_debug_info()

        assert debug_info.debug_level == "INFO"
        assert isinstance(debug_info.debug_data, dict)
        assert isinstance(debug_info.performance_metrics, dict)
        assert debug_info.performance_metrics["request_count"] == 10
        assert debug_info.performance_metrics["error_count"] == 2
        assert debug_info.performance_metrics["uptime_seconds"] >= 0

    def test_inspect_state(self, server_core):
        """Test state inspection."""
        server_core.server_name = "test-server"
        server_core.error_count = 5

        # Test full state
        full_state = server_core.inspect_state()
        assert isinstance(full_state, dict)
        assert full_state["server_name"] == "test-server"
        assert full_state["error_count"] == 5

        # Test specific path
        specific = server_core.inspect_state("error_count")
        assert specific == {"error_count": 5}

        # Test invalid path
        with pytest.raises(KeyError):
            server_core.inspect_state("invalid.path")

    def test_get_component_dependencies(self, server_core):
        """Test getting component dependencies."""
        deps = server_core.get_component_dependencies()

        assert isinstance(deps, list)
        assert "mcp.server" in deps
        assert "mcp.server.stdio" in deps
        assert "logging" in deps
        assert "asyncio" in deps

    def test_export_state_json(self, server_core):
        """Test exporting state as JSON."""
        server_core.server = Mock()
        server_core.request_count = 5

        json_str = server_core.export_state_json()

        # Verify it's valid JSON
        data = json.loads(json_str)
        assert isinstance(data, dict)
        assert data["component_type"] == "MCPGitServerCore"
        assert data["state_data"]["request_count"] == 5
        assert "validation" in data
        assert "debug_info" in data

    def test_health_check(self, server_core):
        """Test health check functionality."""
        # Uninitialized server
        health = server_core.health_check()
        assert health["healthy"] is False
        assert health["status"] == "not_initialized"
        assert health["error_count"] == 0

        # Initialized but not running
        server_core.server = Mock()
        health = server_core.health_check()
        assert health["healthy"] is False
        assert health["status"] == "stopped"

        # Running server
        server_core.is_running = True
        server_core.start_time = datetime.now()
        health = server_core.health_check()
        assert health["healthy"] is True
        assert health["status"] == "running"
        assert health["uptime"] >= 0

    def test_state_history(self, server_core):
        """Test state history tracking."""
        # Perform actions that update state
        server_core.initialize_server()
        server_core.increment_request_count()
        server_core.increment_request_count()

        # Get state history
        history = server_core.get_state_history(limit=5)

        assert isinstance(history, list)
        assert len(history) > 0
        assert all(hasattr(state, "component_id") for state in history)

        # Verify newest first
        if len(history) > 1:
            assert history[0].last_updated >= history[1].last_updated

    @pytest.mark.asyncio
    async def test_error_handling(self, server_core):
        """Test error handling during server operation."""
        server_core.server = Mock()
        server_core.server.run = AsyncMock(
            side_effect=Exception("Test transport error closed")
        )

        with patch("mcp_server_git.frameworks.server_core.stdio_server") as mock_stdio:
            mock_stdio.return_value.__aenter__.return_value = (Mock(), Mock())

            # Should not raise, but increment error count
            await server_core.start_server()

            assert server_core.error_count == 1
            assert "transport error closed" in server_core.last_error.lower()
            assert server_core.is_running is False
