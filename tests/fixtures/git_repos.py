"""
Git repository fixtures for testing.

Provides factory functions and fixtures for creating test git repositories
with various states and configurations.
"""

import subprocess
from pathlib import Path
from typing import List, Optional
import pytest


class GitRepositoryFactory:
    """Factory for creating test git repositories."""
    
    @staticmethod
    def create_clean_repo(path: Path) -> Path:
        """Create a clean git repository with initial commit."""
        path.mkdir(parents=True, exist_ok=True)
        
        # Initialize repository
        subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
        
        # Create initial commit
        (path / "README.md").write_text("# Test Repository")
        subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=path, check=True)
        
        return path
    
    @staticmethod
    def create_dirty_repo(path: Path, modified_files: Optional[List[str]] = None) -> Path:
        """Create a git repository with uncommitted changes."""
        GitRepositoryFactory.create_clean_repo(path)
        
        if modified_files is None:
            modified_files = ["modified.txt", "new_file.txt"]
        
        for file_name in modified_files:
            (path / file_name).write_text(f"Content of {file_name}")
        
        return path
    
    @staticmethod
    def create_repo_with_branches(path: Path, branches: List[str]) -> Path:
        """Create a git repository with multiple branches."""
        GitRepositoryFactory.create_clean_repo(path)
        
        for branch in branches:
            subprocess.run(["git", "checkout", "-b", branch], cwd=path, check=True, capture_output=True)
            
            # Create a commit on this branch
            branch_file = path / f"{branch}_file.txt"
            branch_file.write_text(f"Content from {branch} branch")
            subprocess.run(["git", "add", branch_file.name], cwd=path, check=True)
            subprocess.run(["git", "commit", "-m", f"Add {branch} file"], cwd=path, check=True)
        
        # Return to main branch
        subprocess.run(["git", "checkout", "main"], cwd=path, check=True, capture_output=True)
        
        return path
    
    @staticmethod
    def create_repo_with_history(path: Path, commit_count: int = 5) -> Path:
        """Create a git repository with specified number of commits."""
        GitRepositoryFactory.create_clean_repo(path)
        
        for i in range(1, commit_count):
            file_path = path / f"file_{i}.txt"
            file_path.write_text(f"Content for commit {i}")
            subprocess.run(["git", "add", file_path.name], cwd=path, check=True)
            subprocess.run(["git", "commit", "-m", f"Commit {i}"], cwd=path, check=True)
        
        return path


@pytest.fixture
def git_repo_factory():
    """Provide access to GitRepositoryFactory."""
    return GitRepositoryFactory


@pytest.fixture
def clean_git_repo(temp_dir: Path) -> Path:
    """Create a clean git repository for testing."""
    return GitRepositoryFactory.create_clean_repo(temp_dir / "clean_repo")


@pytest.fixture
def dirty_git_repo(temp_dir: Path) -> Path:
    """Create a git repository with uncommitted changes."""
    return GitRepositoryFactory.create_dirty_repo(temp_dir / "dirty_repo")


@pytest.fixture
def multi_branch_repo(temp_dir: Path) -> Path:
    """Create a git repository with multiple branches."""
    return GitRepositoryFactory.create_repo_with_branches(
        temp_dir / "multi_branch_repo", 
        ["feature-1", "feature-2", "bugfix"]
    )