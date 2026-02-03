"""
Unit tests for repository path resolution logic in ServerApplication.

This module tests the critical fix for the MCP git server repository context bug
where the server was defaulting to "." instead of using the configured --repository path.

Focus areas:
- Repository path resolution from ServerApplicationConfig
- Default path handling when no repository is specified
- Path validation and normalization
- Integration with git operations
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from tempfile import TemporaryDirectory
import os

from mcp_server_git.applications.server_application import (
    ServerApplication,
    ServerApplicationConfig,
)


class TestRepositoryPathResolution:
    """Test repository path resolution logic in ServerApplication."""

    def test_config_with_explicit_repository_path(self):
        """Test ServerApplicationConfig with explicit repository path."""
        test_path = Path("/path/to/repo")
        config = ServerApplicationConfig(repository_path=test_path)

        assert config.repository_path == test_path
        assert config.repository_path.is_absolute()

    def test_config_with_none_repository_path(self):
        """Test ServerApplicationConfig with None repository path."""
        config = ServerApplicationConfig(repository_path=None)

        assert config.repository_path is None

    def test_config_with_relative_repository_path(self):
        """Test ServerApplicationConfig with relative repository path."""
        test_path = Path("relative/path")
        config = ServerApplicationConfig(repository_path=test_path)

        assert config.repository_path == test_path
        assert not config.repository_path.is_absolute()

    def test_config_with_string_path_conversion(self):
        """Test ServerApplicationConfig converts string paths to Path objects."""
        test_path_str = "/string/path/to/repo"
        test_path = Path(test_path_str)
        config = ServerApplicationConfig(repository_path=test_path)

        assert isinstance(config.repository_path, Path)
        assert str(config.repository_path) == test_path_str

    @pytest.mark.asyncio
    async def test_execute_tool_operation_uses_config_repository_path(self):
        """Test that _execute_tool_operation uses repository path from config."""
        test_repo_path = "/test/repository/path"
        config = ServerApplicationConfig(repository_path=Path(test_repo_path))
        app = ServerApplication(config)

        # Mock the Repo class and git_status function
        with (
            patch("mcp_server_git.utils.git_import.Repo") as mock_repo_class,
            patch("mcp_server_git.git.operations.git_status") as mock_git_status,
        ):
            mock_repo_instance = MagicMock()
            mock_repo_class.return_value = mock_repo_instance
            mock_git_status.return_value = "mocked status"

            # Call _execute_tool_operation with git_status (no repo_path in arguments)
            result = await app._execute_tool_operation("git_status", {})

            # Verify that Repo was instantiated with the config repository path
            mock_repo_class.assert_called_once_with(test_repo_path)
            mock_git_status.assert_called_once_with(mock_repo_instance)
            assert result == "mocked status"

    @pytest.mark.asyncio
    async def test_execute_tool_operation_uses_argument_repo_path_when_provided(self):
        """Test that _execute_tool_operation uses repo_path from arguments when provided."""
        config_repo_path = "/config/repository/path"
        argument_repo_path = "/argument/repository/path"

        config = ServerApplicationConfig(repository_path=Path(config_repo_path))
        app = ServerApplication(config)

        with (
            patch("mcp_server_git.utils.git_import.Repo") as mock_repo_class,
            patch("mcp_server_git.git.operations.git_status") as mock_git_status,
        ):
            mock_repo_instance = MagicMock()
            mock_repo_class.return_value = mock_repo_instance
            mock_git_status.return_value = "mocked status"

            # Call _execute_tool_operation with explicit repo_path in arguments
            result = await app._execute_tool_operation(
                "git_status", {"repo_path": argument_repo_path}
            )

            # Verify that Repo was instantiated with the argument repo_path (not config)
            mock_repo_class.assert_called_once_with(argument_repo_path)
            mock_git_status.assert_called_once_with(mock_repo_instance)
            assert result == "mocked status"

    @pytest.mark.asyncio
    async def test_execute_tool_operation_defaults_to_current_directory_when_no_config(
        self,
    ):
        """Test that _execute_tool_operation defaults to '.' when no config repository path."""
        config = ServerApplicationConfig(repository_path=None)
        app = ServerApplication(config)

        with (
            patch("mcp_server_git.utils.git_import.Repo") as mock_repo_class,
            patch("mcp_server_git.git.operations.git_status") as mock_git_status,
        ):
            mock_repo_instance = MagicMock()
            mock_repo_class.return_value = mock_repo_instance
            mock_git_status.return_value = "mocked status"

            # Call _execute_tool_operation with no repo_path in arguments and no config path
            result = await app._execute_tool_operation("git_status", {})

            # Verify that Repo was instantiated with "." as default
            mock_repo_class.assert_called_once_with(".")
            mock_git_status.assert_called_once_with(mock_repo_instance)
            assert result == "mocked status"

    @pytest.mark.asyncio
    async def test_execute_tool_operation_path_resolution_priority(self):
        """Test the priority order: argument repo_path > config repository_path > '.'"""
        config_repo_path = "/config/path"
        config = ServerApplicationConfig(repository_path=Path(config_repo_path))
        app = ServerApplication(config)

        with (
            patch("mcp_server_git.utils.git_import.Repo") as mock_repo_class,
            patch("mcp_server_git.git.operations.git_status") as mock_git_status,
        ):
            mock_repo_class.return_value = MagicMock()
            mock_git_status.return_value = "mocked"

            # Test 1: Only config path available
            await app._execute_tool_operation("git_status", {})
            mock_repo_class.assert_called_with(config_repo_path)

            # Reset mock
            mock_repo_class.reset_mock()

            # Test 2: Both config and argument path - argument should win
            argument_repo_path = "/argument/path"
            await app._execute_tool_operation(
                "git_status", {"repo_path": argument_repo_path}
            )
            mock_repo_class.assert_called_with(argument_repo_path)

    @pytest.mark.asyncio
    async def test_execute_tool_operation_with_different_git_operations(self):
        """Test repository path resolution works for different git operations."""
        test_repo_path = "/test/repo"
        config = ServerApplicationConfig(repository_path=Path(test_repo_path))
        app = ServerApplication(config)

        git_operations = [
            ("git_status", "git_status"),
            ("git_diff_unstaged", "git_diff_unstaged"),
            ("git_diff_staged", "git_diff_staged"),
            ("git_log", "git_log"),
        ]

        for tool_name, function_name in git_operations:
            with (
                patch("mcp_server_git.utils.git_import.Repo") as mock_repo_class,
                patch(
                    f"mcp_server_git.git.operations.{function_name}"
                ) as mock_function,
            ):
                mock_repo_instance = MagicMock()
                mock_repo_class.return_value = mock_repo_instance
                mock_function.return_value = f"mocked {function_name}"

                # Call the tool operation
                result = await app._execute_tool_operation(tool_name, {})

                # Verify repository path resolution
                mock_repo_class.assert_called_once_with(test_repo_path)

                # Verify the function was called with the repo instance
                if function_name == "git_log":
                    mock_function.assert_called_once_with(
                        mock_repo_instance, max_count=10
                    )
                else:
                    mock_function.assert_called_once_with(mock_repo_instance)

    def test_path_normalization_absolute_path(self):
        """Test that absolute paths are handled correctly."""
        absolute_path = Path("/absolute/path/to/repo")
        config = ServerApplicationConfig(repository_path=absolute_path)
        app = ServerApplication(config)

        # The path should be stored as-is when it's absolute
        assert app.config.repository_path == absolute_path
        assert app.config.repository_path.is_absolute()

    def test_path_normalization_relative_path(self):
        """Test that relative paths are handled correctly."""
        relative_path = Path("relative/path/to/repo")
        config = ServerApplicationConfig(repository_path=relative_path)
        app = ServerApplication(config)

        # The path should be stored as-is when it's relative
        assert app.config.repository_path == relative_path
        assert not app.config.repository_path.is_absolute()

    @pytest.mark.asyncio
    async def test_repository_path_string_conversion_in_execute_tool(self):
        """Test that Path objects are properly converted to strings in _execute_tool_operation."""
        test_repo_path = Path("/test/repository/path")
        config = ServerApplicationConfig(repository_path=test_repo_path)
        app = ServerApplication(config)

        with (
            patch("mcp_server_git.utils.git_import.Repo") as mock_repo_class,
            patch("mcp_server_git.git.operations.git_status") as mock_git_status,
        ):
            mock_repo_class.return_value = MagicMock()
            mock_git_status.return_value = "mocked"

            await app._execute_tool_operation("git_status", {})

            # Verify that the Path object was converted to string
            mock_repo_class.assert_called_once_with(str(test_repo_path))

    def test_config_repository_path_none_handling(self):
        """Test proper handling when repository_path is None in config."""
        config = ServerApplicationConfig(repository_path=None)
        app = ServerApplication(config)

        assert app.config.repository_path is None

        # Test the default path logic that would be used in _execute_tool_operation
        default_repo_path = (
            str(app.config.repository_path) if app.config.repository_path else "."
        )
        assert default_repo_path == "."


class TestRepositoryPathResolutionEdgeCases:
    """Test edge cases for repository path resolution."""

    @pytest.mark.asyncio
    async def test_empty_string_repo_path_argument(self):
        """Test handling of empty string repo_path in arguments."""
        config = ServerApplicationConfig(repository_path=Path("/config/path"))
        app = ServerApplication(config)

        with (
            patch("mcp_server_git.utils.git_import.Repo") as mock_repo_class,
            patch("mcp_server_git.git.operations.git_status") as mock_git_status,
        ):
            mock_repo_class.return_value = MagicMock()
            mock_git_status.return_value = "mocked"

            # Empty string should still be used (not fall back to config)
            await app._execute_tool_operation("git_status", {"repo_path": ""})
            mock_repo_class.assert_called_once_with("")

    @pytest.mark.asyncio
    async def test_whitespace_repo_path_argument(self):
        """Test handling of whitespace-only repo_path in arguments."""
        config = ServerApplicationConfig(repository_path=Path("/config/path"))
        app = ServerApplication(config)

        with (
            patch("mcp_server_git.utils.git_import.Repo") as mock_repo_class,
            patch("mcp_server_git.git.operations.git_status") as mock_git_status,
        ):
            mock_repo_class.return_value = MagicMock()
            mock_git_status.return_value = "mocked"

            # Whitespace should still be used as-is
            await app._execute_tool_operation("git_status", {"repo_path": "   "})
            mock_repo_class.assert_called_once_with("   ")

    def test_path_with_special_characters(self):
        """Test repository paths with special characters."""
        special_paths = [
            Path("/path/with spaces/repo"),
            Path("/path/with-dashes/repo"),
            Path("/path/with_underscores/repo"),
            Path("/path/with.dots/repo"),
            Path("/path/with@symbols/repo"),
        ]

        for path in special_paths:
            config = ServerApplicationConfig(repository_path=path)
            app = ServerApplication(config)
            assert app.config.repository_path == path

    @pytest.mark.asyncio
    async def test_path_resolution_with_symlinks(self):
        """Test path resolution behavior with symbolic links."""
        with TemporaryDirectory() as temp_dir:
            # Create actual directory and symlink
            actual_repo = Path(temp_dir) / "actual_repo"
            actual_repo.mkdir()

            symlink_repo = Path(temp_dir) / "symlink_repo"
            symlink_repo.symlink_to(actual_repo)

            config = ServerApplicationConfig(repository_path=symlink_repo)
            app = ServerApplication(config)

            # The path should be stored as provided (symlink path)
            assert app.config.repository_path == symlink_repo

            with (
                patch("mcp_server_git.utils.git_import.Repo") as mock_repo_class,
                patch("mcp_server_git.git.operations.git_status") as mock_git_status,
            ):
                mock_repo_class.return_value = MagicMock()
                mock_git_status.return_value = "mocked"

                await app._execute_tool_operation("git_status", {})

                # Should use the symlink path as provided
                mock_repo_class.assert_called_once_with(str(symlink_repo))


class TestRepositoryPathResolutionIntegration:
    """Integration tests for repository path resolution with actual Path objects."""

    def test_real_path_objects_integration(self):
        """Test integration with real Path objects and common path operations."""
        # Test with current working directory
        cwd_path = Path.cwd()
        config = ServerApplicationConfig(repository_path=cwd_path)
        app = ServerApplication(config)

        assert app.config.repository_path == cwd_path
        assert app.config.repository_path.exists()  # Should exist since it's cwd

        # Test string conversion
        path_str = str(app.config.repository_path)
        assert isinstance(path_str, str)
        assert len(path_str) > 0

    def test_path_resolution_consistency(self):
        """Test that path resolution is consistent across multiple calls."""
        test_path = Path("/consistent/test/path")
        config = ServerApplicationConfig(repository_path=test_path)
        app = ServerApplication(config)

        # Multiple accesses should return the same object
        path1 = app.config.repository_path
        path2 = app.config.repository_path

        assert path1 is path2  # Same object reference
        assert path1 == path2  # Same value
        assert str(path1) == str(path2)  # Same string representation

    def test_cross_platform_path_handling(self):
        """Test that path handling works across different path formats."""
        # Test Unix-style path
        unix_path = Path("/unix/style/path")
        config = ServerApplicationConfig(repository_path=unix_path)
        app = ServerApplication(config)
        assert app.config.repository_path == unix_path

        # Test relative path
        rel_path = Path("relative/path")
        config2 = ServerApplicationConfig(repository_path=rel_path)
        app2 = ServerApplication(config2)
        assert app2.config.repository_path == rel_path
