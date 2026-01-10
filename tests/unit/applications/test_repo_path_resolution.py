"""
Tests for repository path resolution in ServerApplication.

This test file specifically validates that the fix for cross-repository contamination
works correctly. It ensures that:
1. repo_path="." is resolved to the bound repository
2. Absolute paths are used correctly
3. Operations fail gracefully when no repository can be determined
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os

from mcp_server_git.applications.server_application import (
    ServerApplication,
    ServerApplicationConfig,
    GitTools,
)


class TestRepoPathResolution:
    """Test cases for repository path resolution."""

    @pytest.fixture
    def temp_repo(self):
        """Create a temporary git repository for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir) / "test_repo"
            repo_path.mkdir()
            
            # Initialize a git repository
            import subprocess
            subprocess.run(
                ["git", "init"], 
                cwd=repo_path, 
                capture_output=True, 
                check=True
            )
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=repo_path,
                capture_output=True,
                check=True
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=repo_path,
                capture_output=True,
                check=True
            )
            
            # Create an initial commit
            test_file = repo_path / "test.txt"
            test_file.write_text("test content")
            subprocess.run(
                ["git", "add", "test.txt"],
                cwd=repo_path,
                capture_output=True,
                check=True
            )
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                cwd=repo_path,
                capture_output=True,
                check=True
            )
            
            yield repo_path

    @pytest.fixture
    def server_app_with_repo(self, temp_repo):
        """Create a ServerApplication instance bound to a test repository."""
        config = ServerApplicationConfig(
            repository_path=temp_repo,
            test_mode=True,
        )
        app = ServerApplication(config)
        return app

    @pytest.fixture
    def server_app_no_repo(self):
        """Create a ServerApplication instance without a bound repository."""
        config = ServerApplicationConfig(
            repository_path=None,
            test_mode=True,
        )
        app = ServerApplication(config)
        return app

    async def test_repo_path_dot_with_bound_repo(self, server_app_with_repo, temp_repo):
        """Test that repo_path='.' resolves to bound repository."""
        # Mock the git operations to avoid actual git calls
        with patch('mcp_server_git.git.operations.git_status') as mock_status:
            mock_status.return_value = "Mock status"
            
            with patch('mcp_server_git.utils.git_import.Repo') as mock_repo_class:
                mock_repo = MagicMock()
                mock_repo_class.return_value = mock_repo
                
                # Execute tool with repo_path="."
                result = await server_app_with_repo._execute_tool_operation(
                    GitTools.STATUS,
                    {"repo_path": "."}
                )
                
                # Verify that Repo was called with the absolute path of bound repository
                called_path = mock_repo_class.call_args[0][0]
                assert Path(called_path).resolve() == temp_repo.resolve()
                assert called_path == str(temp_repo.resolve())

    async def test_repo_path_dot_without_bound_repo(self, server_app_no_repo):
        """Test that repo_path='.' without bound repository raises error."""
        with pytest.raises(ValueError) as exc_info:
            await server_app_no_repo._execute_tool_operation(
                GitTools.STATUS,
                {"repo_path": "."}
            )
        
        assert "No repository path could be determined" in str(exc_info.value)
        assert "absolute path" in str(exc_info.value).lower()

    async def test_repo_path_absolute_path(self, server_app_with_repo, temp_repo):
        """Test that absolute path is used directly."""
        with patch('mcp_server_git.git.operations.git_status') as mock_status:
            mock_status.return_value = "Mock status"
            
            with patch('mcp_server_git.utils.git_import.Repo') as mock_repo_class:
                mock_repo = MagicMock()
                mock_repo_class.return_value = mock_repo
                
                # Execute tool with absolute path
                abs_path = str(temp_repo.resolve())
                result = await server_app_with_repo._execute_tool_operation(
                    GitTools.STATUS,
                    {"repo_path": abs_path}
                )
                
                # Verify that Repo was called with the provided absolute path
                called_path = mock_repo_class.call_args[0][0]
                assert called_path == abs_path

    async def test_repo_path_none_with_bound_repo(self, server_app_with_repo, temp_repo):
        """Test that None repo_path uses bound repository."""
        with patch('mcp_server_git.git.operations.git_status') as mock_status:
            mock_status.return_value = "Mock status"
            
            with patch('mcp_server_git.utils.git_import.Repo') as mock_repo_class:
                mock_repo = MagicMock()
                mock_repo_class.return_value = mock_repo
                
                # Execute tool without repo_path argument
                result = await server_app_with_repo._execute_tool_operation(
                    GitTools.STATUS,
                    {}  # No repo_path provided
                )
                
                # Verify that Repo was called with bound repository path
                called_path = mock_repo_class.call_args[0][0]
                assert Path(called_path).resolve() == temp_repo.resolve()

    async def test_repo_path_none_without_bound_repo(self, server_app_no_repo):
        """Test that None repo_path without bound repository raises error."""
        with pytest.raises(ValueError) as exc_info:
            await server_app_no_repo._execute_tool_operation(
                GitTools.STATUS,
                {}  # No repo_path provided
            )
        
        assert "No repository path could be determined" in str(exc_info.value)

    async def test_git_init_with_path(self, server_app_no_repo):
        """Test that git_init works with an explicit path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_repo_path = Path(tmpdir) / "new_repo"
            new_repo_path.mkdir()
            
            with patch('mcp_server_git.git.operations.git_init') as mock_init:
                mock_init.return_value = "Initialized"
                
                # Execute git_init with explicit path
                result = await server_app_no_repo._execute_tool_operation(
                    GitTools.INIT,
                    {"repo_path": str(new_repo_path)}
                )
                
                # Verify git_init was called with resolved absolute path
                called_path = mock_init.call_args[0][0]
                assert Path(called_path).resolve() == new_repo_path.resolve()

    async def test_git_init_without_path_no_bound_repo(self, server_app_no_repo):
        """Test that git_init without path and without bound repo raises error."""
        with pytest.raises(ValueError) as exc_info:
            await server_app_no_repo._execute_tool_operation(
                GitTools.INIT,
                {}  # No repo_path provided
            )
        
        assert "git_init requires a repository path" in str(exc_info.value)

    async def test_relative_path_converted_to_absolute(self, server_app_no_repo):
        """Test that relative paths are converted to absolute paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Change to temp directory
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                
                # Create a test repo in a subdirectory
                test_repo = Path(tmpdir) / "test_repo"
                test_repo.mkdir()
                import subprocess
                subprocess.run(
                    ["git", "init"], 
                    cwd=test_repo, 
                    capture_output=True, 
                    check=True
                )
                
                with patch('mcp_server_git.git.operations.git_init') as mock_init:
                    mock_init.return_value = "Initialized"
                    
                    # Execute with relative path
                    result = await server_app_no_repo._execute_tool_operation(
                        GitTools.INIT,
                        {"repo_path": "./test_repo"}
                    )
                    
                    # Verify the path was converted to absolute
                    called_path = mock_init.call_args[0][0]
                    assert Path(called_path).is_absolute()
                    assert Path(called_path).resolve() == test_repo.resolve()
            finally:
                os.chdir(old_cwd)

    async def test_repository_resolver_instance_exists(self, server_app_with_repo):
        """Test that ServerApplication has a RepositoryResolver instance."""
        assert hasattr(server_app_with_repo, '_repository_resolver')
        assert server_app_with_repo._repository_resolver is not None

    async def test_repository_resolver_bound_path(self, server_app_with_repo, temp_repo):
        """Test that RepositoryResolver is initialized with bound repository path."""
        resolver = server_app_with_repo._repository_resolver
        assert resolver.bound_repository_path is not None
        assert Path(resolver.bound_repository_path).resolve() == temp_repo.resolve()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
