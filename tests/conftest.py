"""
Global pytest configuration and fixtures for TDD test suite.

This file provides shared fixtures and configuration for all test levels.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from typing import Generator, Dict, Any
from unittest.mock import MagicMock

# Test environment setup
@pytest.fixture(scope="session")
def test_environment():
    """Set up test environment variables and configuration."""
    import os
    original_env = os.environ.copy()
    
    # Set test-specific environment variables
    os.environ["LOG_LEVEL"] = "DEBUG"
    os.environ["TESTING"] = "true"
    
    yield
    
    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files."""
    temp_path = Path(tempfile.mkdtemp())
    try:
        yield temp_path
    finally:
        shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def mock_git_repo(temp_dir: Path) -> Path:
    """Create a mock git repository for testing."""
    repo_path = temp_dir / "test_repo"
    repo_path.mkdir()
    
    # Initialize git repo
    import subprocess
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True)
    
    # Create initial commit
    (repo_path / "README.md").write_text("# Test Repository")
    subprocess.run(["git", "add", "README.md"], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True)
    
    return repo_path


@pytest.fixture
def mock_github_responses() -> Dict[str, Any]:
    """Mock GitHub API responses for testing."""
    return {
        "user": {
            "login": "testuser",
            "id": 12345,
            "name": "Test User",
            "email": "test@example.com"
        },
        "repo": {
            "id": 67890,
            "name": "test-repo",
            "full_name": "testuser/test-repo",
            "private": False,
            "default_branch": "main"
        },
        "pulls": [
            {
                "number": 1,
                "title": "Test Pull Request",
                "state": "open",
                "base": {"ref": "main"},
                "head": {"ref": "feature-branch"}
            }
        ]
    }


@pytest.fixture
def mock_mcp_client():
    """Mock MCP client for protocol testing."""
    client = MagicMock()
    client.connect = MagicMock()
    client.disconnect = MagicMock()
    client.send_message = MagicMock()
    client.receive_message = MagicMock()
    return client


# Markers for test categorization
pytest_plugins = []

def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line("markers", "unit: Unit tests for individual components")
    config.addinivalue_line("markers", "integration: Integration tests between components")
    config.addinivalue_line("markers", "system: End-to-end system tests")
    config.addinivalue_line("markers", "slow: Tests that take more than 1 second")
    config.addinivalue_line("markers", "requires_git: Tests that require git repository setup")
    config.addinivalue_line("markers", "requires_github: Tests that require GitHub API access")


def pytest_collection_modifyitems(config, items):
    """Automatically mark tests based on their location."""
    for item in items:
        # Auto-mark based on test file location
        if "tests/unit/" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "tests/integration/" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "tests/system/" in str(item.fspath):
            item.add_marker(pytest.mark.system)
            
        # Mark tests that use git fixtures
        if "mock_git_repo" in item.fixturenames:
            item.add_marker(pytest.mark.requires_git)
            
        # Mark tests that use GitHub fixtures
        if "mock_github_responses" in item.fixturenames:
            item.add_marker(pytest.mark.requires_github)