"""
Unit tests for HTTP Session Manager.

This module provides comprehensive unit tests for the HTTPSessionManager class,
testing session lifecycle, repository isolation, contamination detection, and
timeout handling.

Critical for TDD Compliance:
    These tests define the interface that HTTPSessionManager must implement.
    DO NOT modify these tests to match implementation - the implementation
    must satisfy these test requirements to prevent LLM compliance issues.
"""

import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_server_git.repository_binding import (
    RemoteContaminationError,
    RepositoryBinding,
    RepositoryBindingError,
    RepositoryBindingManager,
)
from mcp_server_git.transport.http_session_manager import (
    HTTPSessionManager,
    SessionContext,
)


class TestSessionContext:
    """Test SessionContext dataclass."""

    @pytest.mark.asyncio
    async def test_session_context_initialization(self, temp_dir):
        """Test SessionContext initializes with all required fields."""
        # Create a mock binding manager
        binding_manager = RepositoryBindingManager(server_name="test-session")

        # Create mock services
        from mcp_server_git.services.git_service import GitService
        from mcp_server_git.services.github_service import GitHubService

        git_service = GitService()
        github_service = GitHubService()

        # Create session context
        current_time = time.time()
        context = SessionContext(
            session_id="mcp-test123",
            binding_manager=binding_manager,
            repository_binding=None,
            created_at=current_time,
            last_activity=current_time,
            git_service=git_service,
            github_service=github_service,
        )

        # Verify basic fields
        assert context.session_id == "mcp-test123"
        assert context.binding_manager is binding_manager
        assert context.repository_binding is None
        assert context.created_at == current_time
        assert context.last_activity == current_time
        assert context.git_service is git_service
        assert context.github_service is github_service

        # Verify lean interface was initialized
        assert context.lean_interface is not None
        assert context.lean_interface.app_name == "mcp-git-session-mcp-test123"

    @pytest.mark.asyncio
    async def test_session_context_with_binding(self, temp_dir):
        """Test SessionContext with repository binding."""
        repo_path = temp_dir / "test_repo"
        repo_path.mkdir()

        # Initialize git repo
        import subprocess
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/test/repo.git"],
            cwd=repo_path,
            check=True,
        )

        # Create binding
        binding = RepositoryBinding(
            repository_path=repo_path,
            expected_remote_url="https://github.com/test/repo.git",
        )

        # Create services
        from mcp_server_git.services.git_service import GitService
        from mcp_server_git.services.github_service import GitHubService

        binding_manager = RepositoryBindingManager(server_name="test-session")
        context = SessionContext(
            session_id="mcp-test456",
            binding_manager=binding_manager,
            repository_binding=binding,
            created_at=time.time(),
            last_activity=time.time(),
            git_service=GitService(),
            github_service=GitHubService(),
        )

        assert context.repository_binding is binding
        assert context.repository_binding.repository_path == repo_path
        assert context.repository_binding.expected_remote_url == "https://github.com/test/repo.git"


class TestHTTPSessionManager:
    """Test HTTPSessionManager functionality."""

    @pytest.mark.asyncio
    async def test_create_session_success(self, temp_dir):
        """Test creating session with valid repository."""
        # Create and initialize git repo
        repo_path = temp_dir / "test_repo"
        repo_path.mkdir()

        import subprocess
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/test/repo.git"],
            cwd=repo_path,
            check=True,
        )

        # Create session manager
        manager = HTTPSessionManager(session_timeout=3600.0)

        # Create session
        session = await manager.create_session(
            repo_path=repo_path,
            expected_remote_url="https://github.com/test/repo.git",
        )

        # Verify session created
        assert session.session_id.startswith("mcp-")
        assert session.repository_binding is not None
        assert session.repository_binding.repository_path == repo_path.resolve()
        assert session.repository_binding.expected_remote_url == "https://github.com/test/repo.git"
        assert session.git_service is not None
        assert session.github_service is not None
        assert session.lean_interface is not None

    @pytest.mark.asyncio
    async def test_create_session_invalid_repo(self, temp_dir):
        """Test creating session with non-existent repository raises error."""
        repo_path = temp_dir / "nonexistent"

        manager = HTTPSessionManager()

        with pytest.raises(RepositoryBindingError, match="does not exist"):
            await manager.create_session(
                repo_path=repo_path,
                expected_remote_url="https://github.com/test/repo.git",
            )

    @pytest.mark.asyncio
    async def test_create_session_invalid_git_repo(self, temp_dir):
        """Test creating session with invalid git repository raises error."""
        repo_path = temp_dir / "not_a_git_repo"
        repo_path.mkdir()

        manager = HTTPSessionManager()

        with pytest.raises(RepositoryBindingError, match="Invalid git repository"):
            await manager.create_session(
                repo_path=repo_path,
                expected_remote_url="https://github.com/test/repo.git",
            )

    @pytest.mark.asyncio
    async def test_create_session_remote_mismatch(self, temp_dir):
        """Test creating session with mismatched remote URL raises error."""
        repo_path = temp_dir / "test_repo"
        repo_path.mkdir()

        import subprocess
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/wrong/repo.git"],
            cwd=repo_path,
            check=True,
        )

        manager = HTTPSessionManager()

        with pytest.raises(RemoteContaminationError, match="Remote URL mismatch"):
            await manager.create_session(
                repo_path=repo_path,
                expected_remote_url="https://github.com/expected/repo.git",
            )

    @pytest.mark.asyncio
    async def test_get_session_updates_activity(self, temp_dir):
        """Test getting session updates last_activity timestamp."""
        # Create and initialize git repo
        repo_path = temp_dir / "test_repo"
        repo_path.mkdir()

        import subprocess
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/test/repo.git"],
            cwd=repo_path,
            check=True,
        )

        manager = HTTPSessionManager()
        session = await manager.create_session(
            repo_path=repo_path,
            expected_remote_url="https://github.com/test/repo.git",
        )

        # Get initial activity time
        initial_activity = session.last_activity

        # Wait a bit to ensure timestamp difference
        await asyncio.sleep(0.1)

        # Get session again
        retrieved_session = await manager.get_session(session.session_id)

        # Verify last_activity was updated
        assert retrieved_session is not None
        assert retrieved_session.last_activity > initial_activity
        assert retrieved_session.session_id == session.session_id

    @pytest.mark.asyncio
    async def test_get_session_not_found(self):
        """Test getting non-existent session returns None."""
        manager = HTTPSessionManager()

        session = await manager.get_session("mcp-nonexistent")

        assert session is None

    @pytest.mark.asyncio
    async def test_close_session_success(self, temp_dir):
        """Test closing existing session removes it."""
        # Create and initialize git repo
        repo_path = temp_dir / "test_repo"
        repo_path.mkdir()

        import subprocess
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/test/repo.git"],
            cwd=repo_path,
            check=True,
        )

        manager = HTTPSessionManager()
        session = await manager.create_session(
            repo_path=repo_path,
            expected_remote_url="https://github.com/test/repo.git",
        )

        # Verify session exists
        assert await manager.get_session(session.session_id) is not None

        # Close session
        result = await manager.close_session(session.session_id)

        # Verify session was closed
        assert result is True
        assert await manager.get_session(session.session_id) is None

    @pytest.mark.asyncio
    async def test_close_session_not_found(self):
        """Test closing non-existent session returns False."""
        manager = HTTPSessionManager()

        result = await manager.close_session("mcp-nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_session_isolation(self, temp_dir):
        """Test two sessions get independent service instances."""
        # Create two git repos
        repo1_path = temp_dir / "repo1"
        repo2_path = temp_dir / "repo2"
        repo1_path.mkdir()
        repo2_path.mkdir()

        import subprocess

        # Initialize repo1
        subprocess.run(["git", "init"], cwd=repo1_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo1_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo1_path,
            check=True,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/test/repo1.git"],
            cwd=repo1_path,
            check=True,
        )

        # Initialize repo2
        subprocess.run(["git", "init"], cwd=repo2_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo2_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo2_path,
            check=True,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/test/repo2.git"],
            cwd=repo2_path,
            check=True,
        )

        manager = HTTPSessionManager()

        # Create two sessions
        session1 = await manager.create_session(
            repo_path=repo1_path,
            expected_remote_url="https://github.com/test/repo1.git",
        )
        session2 = await manager.create_session(
            repo_path=repo2_path,
            expected_remote_url="https://github.com/test/repo2.git",
        )

        # Verify sessions are different
        assert session1.session_id != session2.session_id

        # Verify service instances are different
        assert session1.git_service is not session2.git_service
        assert session1.github_service is not session2.github_service
        assert session1.binding_manager is not session2.binding_manager
        assert session1.lean_interface is not session2.lean_interface

        # Verify bindings are different
        assert session1.repository_binding.repository_path == repo1_path.resolve()
        assert session2.repository_binding.repository_path == repo2_path.resolve()
        assert session1.repository_binding.expected_remote_url == "https://github.com/test/repo1.git"
        assert session2.repository_binding.expected_remote_url == "https://github.com/test/repo2.git"

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions(self, temp_dir):
        """Test sessions older than timeout are cleaned up."""
        # Create git repo
        repo_path = temp_dir / "test_repo"
        repo_path.mkdir()

        import subprocess
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/test/repo.git"],
            cwd=repo_path,
            check=True,
        )

        # Create manager with short timeout
        manager = HTTPSessionManager(session_timeout=0.2)

        # Create session
        session = await manager.create_session(
            repo_path=repo_path,
            expected_remote_url="https://github.com/test/repo.git",
        )

        # Verify session exists
        assert await manager.get_session(session.session_id) is not None

        # Wait for timeout
        await asyncio.sleep(0.3)

        # Cleanup expired sessions
        cleaned_count = await manager.cleanup_expired_sessions()

        # Verify session was cleaned up
        assert cleaned_count == 1
        assert await manager.get_session(session.session_id) is None

    @pytest.mark.asyncio
    async def test_cleanup_does_not_remove_active_sessions(self, temp_dir):
        """Test cleanup does not remove sessions within timeout."""
        # Create git repo
        repo_path = temp_dir / "test_repo"
        repo_path.mkdir()

        import subprocess
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/test/repo.git"],
            cwd=repo_path,
            check=True,
        )

        # Create manager with longer timeout
        manager = HTTPSessionManager(session_timeout=60.0)

        # Create session
        session = await manager.create_session(
            repo_path=repo_path,
            expected_remote_url="https://github.com/test/repo.git",
        )

        # Wait briefly but less than timeout
        await asyncio.sleep(0.1)

        # Cleanup
        cleaned_count = await manager.cleanup_expired_sessions()

        # Verify session was NOT cleaned up
        assert cleaned_count == 0
        assert await manager.get_session(session.session_id) is not None

    @pytest.mark.asyncio
    async def test_execute_tool_validates_binding(self, temp_dir):
        """Test tool execution validates binding integrity."""
        # Create git repo
        repo_path = temp_dir / "test_repo"
        repo_path.mkdir()

        import subprocess
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/test/repo.git"],
            cwd=repo_path,
            check=True,
        )

        manager = HTTPSessionManager()
        session = await manager.create_session(
            repo_path=repo_path,
            expected_remote_url="https://github.com/test/repo.git",
        )

        # Mock the lean interface's execute_tool_direct to avoid actual execution
        session.lean_interface.execute_tool_direct = AsyncMock(return_value={"result": "success"})

        # Execute tool
        result = await manager.execute_tool(
            session_id=session.session_id,
            tool_name="git_status",
            args={"repo_path": str(repo_path)},
        )

        # Verify tool was executed
        assert result == {"result": "success"}
        session.lean_interface.execute_tool_direct.assert_called_once_with(
            "git_status",
            {"repo_path": str(repo_path)},
        )

    @pytest.mark.asyncio
    async def test_execute_tool_session_not_found(self):
        """Test tool execution with non-existent session raises error."""
        manager = HTTPSessionManager()

        with pytest.raises(ValueError, match="Session not found"):
            await manager.execute_tool(
                session_id="mcp-nonexistent",
                tool_name="git_status",
                args={},
            )

    @pytest.mark.asyncio
    async def test_execute_tool_detects_binding_corruption(self, temp_dir):
        """Test tool execution detects binding corruption."""
        # Create git repo
        repo_path = temp_dir / "test_repo"
        repo_path.mkdir()

        import subprocess
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/test/repo.git"],
            cwd=repo_path,
            check=True,
        )

        manager = HTTPSessionManager()
        session = await manager.create_session(
            repo_path=repo_path,
            expected_remote_url="https://github.com/test/repo.git",
        )

        # Mock verify_integrity at the class level to simulate corruption
        with patch.object(RepositoryBinding, 'verify_integrity', return_value=False):
            with pytest.raises(ValueError, match="binding corrupted"):
                await manager.execute_tool(
                    session_id=session.session_id,
                    tool_name="git_status",
                    args={},
                )

    @pytest.mark.asyncio
    async def test_execute_tool_detects_remote_contamination(self, temp_dir):
        """Test tool execution detects remote contamination."""
        # Create git repo
        repo_path = temp_dir / "test_repo"
        repo_path.mkdir()

        import subprocess
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/test/repo.git"],
            cwd=repo_path,
            check=True,
        )

        manager = HTTPSessionManager()
        session = await manager.create_session(
            repo_path=repo_path,
            expected_remote_url="https://github.com/test/repo.git",
        )

        # Change the remote URL to simulate contamination
        subprocess.run(
            ["git", "remote", "set-url", "origin", "https://github.com/contaminated/repo.git"],
            cwd=repo_path,
            check=True,
        )

        # Try to execute tool
        with pytest.raises(RemoteContaminationError, match="Remote contamination detected"):
            await manager.execute_tool(
                session_id=session.session_id,
                tool_name="git_status",
                args={"repo_path": str(repo_path)},
            )

    @pytest.mark.asyncio
    async def test_execute_tool_validates_operation_path(self, temp_dir):
        """Test tool execution validates operation path against binding."""
        # Create git repo
        repo_path = temp_dir / "test_repo"
        repo_path.mkdir()

        import subprocess
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/test/repo.git"],
            cwd=repo_path,
            check=True,
        )

        # Create another directory outside the repo
        other_path = temp_dir / "other_repo"
        other_path.mkdir()

        manager = HTTPSessionManager()
        session = await manager.create_session(
            repo_path=repo_path,
            expected_remote_url="https://github.com/test/repo.git",
        )

        # Try to execute tool with path outside bound repository
        with pytest.raises(RepositoryBindingError, match="outside bound repository"):
            await manager.execute_tool(
                session_id=session.session_id,
                tool_name="git_status",
                args={"repo_path": str(other_path)},
            )

    @pytest.mark.asyncio
    async def test_get_session_info(self, temp_dir):
        """Test getting session information."""
        # Create git repo
        repo_path = temp_dir / "test_repo"
        repo_path.mkdir()

        import subprocess
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/test/repo.git"],
            cwd=repo_path,
            check=True,
        )

        manager = HTTPSessionManager()
        session = await manager.create_session(
            repo_path=repo_path,
            expected_remote_url="https://github.com/test/repo.git",
        )

        # Get session info
        info = await manager.get_session_info(session.session_id)

        # Verify info structure
        assert info is not None
        assert info["session_id"] == session.session_id
        assert "created_at" in info
        assert "last_activity" in info
        assert "age" in info
        assert "idle_time" in info
        assert "binding_info" in info
        assert info["age"] >= 0
        assert info["idle_time"] >= 0

    @pytest.mark.asyncio
    async def test_get_session_info_not_found(self):
        """Test getting info for non-existent session returns None."""
        manager = HTTPSessionManager()

        info = await manager.get_session_info("mcp-nonexistent")

        assert info is None

    @pytest.mark.asyncio
    async def test_get_all_sessions_info(self, temp_dir):
        """Test getting information for all active sessions."""
        # Create two git repos
        repo1_path = temp_dir / "repo1"
        repo2_path = temp_dir / "repo2"
        repo1_path.mkdir()
        repo2_path.mkdir()

        import subprocess

        # Initialize repo1
        subprocess.run(["git", "init"], cwd=repo1_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo1_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo1_path,
            check=True,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/test/repo1.git"],
            cwd=repo1_path,
            check=True,
        )

        # Initialize repo2
        subprocess.run(["git", "init"], cwd=repo2_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo2_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo2_path,
            check=True,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/test/repo2.git"],
            cwd=repo2_path,
            check=True,
        )

        manager = HTTPSessionManager()

        # Create two sessions
        session1 = await manager.create_session(
            repo_path=repo1_path,
            expected_remote_url="https://github.com/test/repo1.git",
        )
        session2 = await manager.create_session(
            repo_path=repo2_path,
            expected_remote_url="https://github.com/test/repo2.git",
        )

        # Get all sessions info
        all_info = await manager.get_all_sessions_info()

        # Verify info for both sessions
        assert len(all_info) == 2
        session_ids = {info["session_id"] for info in all_info}
        assert session1.session_id in session_ids
        assert session2.session_id in session_ids

        for info in all_info:
            assert "created_at" in info
            assert "last_activity" in info
            assert "age" in info
            assert "idle_time" in info
            assert "binding_info" in info
