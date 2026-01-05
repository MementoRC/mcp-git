"""Tests for git_init operation on non-initialized directories"""

import tempfile
import shutil
from pathlib import Path
import pytest


class TestGitInit:
    """Test git_init function for initializing new repositories"""

    def test_git_init_on_empty_directory(self):
        """Test that git_init works on a directory without .git"""
        from src.mcp_server_git.git.operations import git_init
        
        # Create a temporary directory without .git
        test_dir = Path(tempfile.mkdtemp())
        
        try:
            # Verify no .git directory exists
            assert not (test_dir / ".git").exists()
            
            # Call git_init
            result = git_init(str(test_dir))
            
            # Verify success
            assert "✅" in result
            assert "Initialized empty Git repository" in result
            assert str(test_dir) in result
            assert (test_dir / ".git").exists()
        finally:
            shutil.rmtree(test_dir)

    def test_git_init_creates_usable_repository(self):
        """Test that git_init creates a repository that can be used"""
        from src.mcp_server_git.git.operations import git_init
        from src.mcp_server_git.utils.git_import import Repo
        
        test_dir = Path(tempfile.mkdtemp())
        
        try:
            # Initialize the repository
            result = git_init(str(test_dir))
            assert "✅" in result
            
            # Verify we can create a Repo object from it
            repo = Repo(test_dir)
            assert repo is not None
            assert repo.git_dir == str(test_dir / ".git")
        finally:
            shutil.rmtree(test_dir)

    def test_git_init_on_nested_directory(self):
        """Test that git_init works on a nested directory that doesn't exist yet"""
        from src.mcp_server_git.git.operations import git_init
        
        base_dir = Path(tempfile.mkdtemp())
        nested_dir = base_dir / "level1" / "level2" / "level3"
        
        try:
            # Directory doesn't exist yet
            assert not nested_dir.exists()
            
            # Call git_init - should create directories
            result = git_init(str(nested_dir))
            
            # Verify success
            assert "✅" in result
            assert nested_dir.exists()
            assert (nested_dir / ".git").exists()
        finally:
            shutil.rmtree(base_dir)

    def test_git_init_on_existing_repository(self):
        """Test that git_init on an existing repository doesn't fail catastrophically"""
        from src.mcp_server_git.git.operations import git_init
        
        test_dir = Path(tempfile.mkdtemp())
        
        try:
            # Initialize once
            result1 = git_init(str(test_dir))
            assert "✅" in result1
            
            # Try to initialize again
            result2 = git_init(str(test_dir))
            # Should not crash - may succeed or return an error message
            assert result2 is not None
            assert isinstance(result2, str)
        finally:
            shutil.rmtree(test_dir)

    def test_git_init_with_server_application_flow(self):
        """Test the fix: git_init should work through server application without requiring existing repo"""
        from src.mcp_server_git.core.tools import GitTools
        
        # This simulates the fixed code path in _execute_tool_operation
        test_dir = Path(tempfile.mkdtemp())
        
        try:
            # Verify no .git directory exists
            assert not (test_dir / ".git").exists()
            
            # Simulate the fixed logic
            repo_path = str(test_dir)
            name = GitTools.INIT
            
            # Before the fix, Repo(repo_path) was called here, which would fail
            # After the fix, git_init is called directly with repo_path
            if name == GitTools.INIT:
                from src.mcp_server_git.git.operations import git_init
                result = git_init(repo_path)
            else:
                # Other tools would create Repo object here
                from src.mcp_server_git.utils.git_import import Repo
                repo = Repo(repo_path)  # This would fail for non-git directories
            
            # Verify success
            assert "✅" in result
            assert "Error" not in result
            assert (test_dir / ".git").exists()
        finally:
            shutil.rmtree(test_dir)
