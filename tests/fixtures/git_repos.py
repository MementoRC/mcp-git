"""Git repository fixtures for testing.

Provides factory functions and fixtures for creating test git repositories
with various states and configurations.
"""

import os
import subprocess
from pathlib import Path
from typing import Optional

import pytest


def _run_git_command(cmd: list[str], cwd: Path, **kwargs):
    """Run git command with clean PATH environment (no ClaudeCode redirectors)."""
    env = os.environ.copy()

    # Remove ClaudeCode's modified PATH to avoid git redirectors
    if "PATH" in env:
        path_entries = env["PATH"].split(os.pathsep)
        clean_path = [
            p
            for p in path_entries
            if not any(
                redirect in p
                for redirect in [
                    "claude-code",
                    "ClaudeCode",
                    ".claude",
                    "redirector",
                    "mcp",
                ]
            )
        ]
        env["PATH"] = os.pathsep.join(clean_path)

    return subprocess.run(cmd, cwd=cwd, env=env, **kwargs)


class GitRepositoryFactory:
    """Factory for creating test git repositories."""

    @staticmethod
    def create_clean_repo(path: Path) -> Path:
        """Create a clean git repository with initial commit."""
        path.mkdir(parents=True, exist_ok=True)

        # Initialize repository
        _run_git_command(["git", "init"], cwd=path, check=True, capture_output=True)
        _run_git_command(
            ["git", "config", "user.name", "Test User"], cwd=path, check=True
        )
        _run_git_command(
            ["git", "config", "user.email", "test@example.com"], cwd=path, check=True
        )

        # Create initial commit
        (path / "README.md").write_text("# Test Repository")
        _run_git_command(["git", "add", "README.md"], cwd=path, check=True)
        _run_git_command(
            ["git", "commit", "-m", "Initial commit"], cwd=path, check=True
        )

        return path

    @staticmethod
    def create_dirty_repo(path: Path, modified_files: list[str] | None = None) -> Path:
        """Create a git repository with uncommitted changes."""
        GitRepositoryFactory.create_clean_repo(path)

        if modified_files is None:
            modified_files = ["modified.txt", "new_file.txt"]

        for file_name in modified_files:
            (path / file_name).write_text(f"Content of {file_name}")

        return path

    @staticmethod
    def create_repo_with_branches(path: Path, branches: list[str]) -> Path:
        """Create a git repository with multiple branches."""
        GitRepositoryFactory.create_clean_repo(path)

        for branch in branches:
            _run_git_command(
                ["git", "checkout", "-b", branch],
                cwd=path,
                check=True,
                capture_output=True,
            )

            # Create a commit on this branch
            branch_file = path / f"{branch}_file.txt"
            branch_file.write_text(f"Content from {branch} branch")
            _run_git_command(["git", "add", branch_file.name], cwd=path, check=True)
            _run_git_command(
                ["git", "commit", "-m", f"Add {branch} file"], cwd=path, check=True
            )

        # Return to main branch
        _run_git_command(
            ["git", "checkout", "main"], cwd=path, check=True, capture_output=True
        )

        return path

    @staticmethod
    def create_repo_with_history(path: Path, commit_count: int = 5) -> Path:
        """Create a git repository with specified number of commits."""
        GitRepositoryFactory.create_clean_repo(path)

        for i in range(1, commit_count):
            file_path = path / f"file_{i}.txt"
            file_path.write_text(f"Content for commit {i}")
            _run_git_command(["git", "add", file_path.name], cwd=path, check=True)
            _run_git_command(
                ["git", "commit", "-m", f"Commit {i}"], cwd=path, check=True
            )

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
        temp_dir / "multi_branch_repo", ["feature-1", "feature-2", "bugfix"]
    )
