"""
Global pytest configuration and fixtures for TDD test suite with intelligent status tracking.

This file provides:
1. Shared fixtures and configuration for all test levels
2. Automatic marking of tests based on implementation status
3. Clear distinction between intentional vs unintentional failures
4. Progress tracking across development phases
5. Enhanced reporting of test status
"""

import pytest
import tempfile
import shutil
import json
import fnmatch
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


# Test Status Tracking System
def load_test_status() -> Dict[str, Any]:
    """Load test status configuration from .taskmaster/test-status.json"""
    status_file = Path(__file__).parent.parent / ".taskmaster" / "test-status.json"
    if status_file.exists():
        with open(status_file, 'r') as f:
            return json.load(f)
    return {"current_phase": "unknown", "test_phases": {}}


def should_test_fail(test_nodeid: str, test_status: Dict[str, Any]) -> bool:
    """Check if a test is expected to fail in the current phase"""
    current_phase = test_status.get("current_phase", "")
    if not current_phase or current_phase not in test_status.get("test_phases", {}):
        return False
    
    phase_info = test_status["test_phases"][current_phase]
    expected_failing = phase_info.get("expected_failing", [])
    
    for pattern in expected_failing:
        if fnmatch.fnmatch(test_nodeid, pattern):
            return True
    return False


def should_test_pass(test_nodeid: str, test_status: Dict[str, Any]) -> bool:
    """Check if a test is expected to pass in the current phase"""
    current_phase = test_status.get("current_phase", "")
    if not current_phase or current_phase not in test_status.get("test_phases", {}):
        return False
    
    phase_info = test_status["test_phases"][current_phase]
    expected_passing = phase_info.get("expected_passing", [])
    
    for pattern in expected_passing:
        if fnmatch.fnmatch(test_nodeid, pattern):
            return True
    return False


@pytest.fixture(scope="session")
def test_status():
    """Provide test status information to tests"""
    return load_test_status()


@pytest.fixture(scope="session")
def current_phase(test_status):
    """Provide current development phase to tests"""
    return test_status.get("current_phase", "unknown")


# Markers for test categorization
pytest_plugins = []

def pytest_configure(config):
    """Configure pytest markers including test status tracking."""
    # Original markers
    config.addinivalue_line("markers", "unit: Unit tests for individual components")
    config.addinivalue_line("markers", "integration: Integration tests between components")
    config.addinivalue_line("markers", "system: End-to-end system tests")
    config.addinivalue_line("markers", "slow: Tests that take more than 1 second")
    config.addinivalue_line("markers", "requires_git: Tests that require git repository setup")
    config.addinivalue_line("markers", "requires_github: Tests that require GitHub API access")
    
    # Test status tracking markers
    config.addinivalue_line("markers", "expected_fail: Test expected to fail (TDD red phase)")
    config.addinivalue_line("markers", "implementation_pending: Test waiting for implementation")
    config.addinivalue_line("markers", "phase_1: Test part of phase 1 (foundation)")
    config.addinivalue_line("markers", "phase_2: Test part of phase 2 (implementation)")
    config.addinivalue_line("markers", "phase_3: Test part of phase 3 (integration)")
    config.addinivalue_line("markers", "critical: Test critical for current phase")


def pytest_collection_modifyitems(config, items):
    """Automatically mark tests based on their location and implementation status."""
    test_status = load_test_status()
    current_phase = test_status.get("current_phase", "")
    
    for item in items:
        test_nodeid = item.nodeid
        
        # Auto-mark based on test file location (original functionality)
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
        
        # Apply phase-specific markers based on current development phase
        if "types/" in test_nodeid:
            if current_phase == "phase_1_foundation":
                item.add_marker(pytest.mark.phase_1)
            elif current_phase == "phase_2_implementation":
                item.add_marker(pytest.mark.phase_2)
            elif current_phase == "phase_3_integration":
                item.add_marker(pytest.mark.phase_3)
        
        # Mark tests as expected to fail or pass based on test status
        if should_test_fail(test_nodeid, test_status):
            item.add_marker(pytest.mark.expected_fail)
            item.add_marker(pytest.mark.implementation_pending)
            item.add_marker(pytest.mark.xfail(
                reason=f"Expected to fail in {current_phase} - implementation pending",
                strict=False,
                run=True
            ))
        elif should_test_pass(test_nodeid, test_status):
            item.add_marker(pytest.mark.critical)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Enhanced terminal summary with phase information and failure analysis."""
    test_status = load_test_status()
    current_phase = test_status.get("current_phase", "unknown")
    
    # Add phase summary
    terminalreporter.write_sep("=", "DEVELOPMENT PHASE SUMMARY")
    terminalreporter.write_line(f"Current Phase: {current_phase}")
    
    if current_phase in test_status.get("test_phases", {}):
        phase_info = test_status["test_phases"][current_phase]
        terminalreporter.write_line(f"Description: {phase_info.get('description', 'N/A')}")
        terminalreporter.write_line(f"Status: {phase_info.get('status', 'unknown')}")
    
    # Count expected vs unexpected failures
    failed_reports = terminalreporter.stats.get('failed', [])
    expected_failures = 0
    unexpected_failures = 0
    unexpected_failure_tests = []
    
    for report in failed_reports:
        test_nodeid = report.nodeid
        if should_test_fail(test_nodeid, test_status):
            expected_failures += 1
        else:
            unexpected_failures += 1
            unexpected_failure_tests.append(test_nodeid)
    
    # Summary with color coding
    terminalreporter.write_line("")
    terminalreporter.write_line(f"Expected Failures (TDD Red Phase): {expected_failures}", green=True)
    
    if unexpected_failures > 0:
        terminalreporter.write_line(f"Unexpected Failures: {unexpected_failures}", red=True)
    else:
        terminalreporter.write_line(f"Unexpected Failures: {unexpected_failures}", green=True)
    
    if unexpected_failures == 0:
        terminalreporter.write_line("✅ ALL FAILURES ARE EXPECTED (TDD Red Phase)", green=True)
        terminalreporter.write_line("   No action required - continue with implementation", green=True)
    else:
        terminalreporter.write_line(f"❌ {unexpected_failures} UNEXPECTED FAILURES DETECTED", red=True)
        terminalreporter.write_line("   These require immediate attention:", red=True)
        
        for test_nodeid in unexpected_failure_tests:
            terminalreporter.write_line(f"     - {test_nodeid}", red=True)
        
        terminalreporter.write_line("")
        terminalreporter.write_line("🚨 NEXT ACTIONS:", yellow=True)
        terminalreporter.write_line("   1. Fix unexpected failures before proceeding", yellow=True)
        terminalreporter.write_line("   2. Update .taskmaster/test-status.json if failures are intentional", yellow=True)
        terminalreporter.write_line("   3. Commit fixes and re-run tests", yellow=True)