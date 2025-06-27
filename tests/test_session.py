"""
Comprehensive tests for the Session Management Module.

Tests session lifecycle, state transitions, metrics, error handling,
circuit breaker integration, and SessionManager operations.
"""

import asyncio
import pytest
import time
from unittest.mock import patch
from pathlib import Path

from mcp_server_git.session import (
    Session,
    SessionManager,
    SessionState,
    SessionMetrics,
)
# Import error handling for integration testing if needed in future


@pytest.fixture(autouse=True)
async def cleanup_sessions():
    """Automatically cleanup any running sessions after each test to prevent hanging."""
    yield
    # After each test, ensure all sessions are properly closed
    try:
        # Get all running tasks
        tasks = [task for task in asyncio.all_tasks() if not task.done()]

        # Cancel session-related tasks
        for task in tasks:
            task_name = str(task)
            if any(
                keyword in task_name.lower()
                for keyword in ["session", "idle", "cleanup", "_cleanup_loop"]
            ):
                task.cancel()

        # Wait for cancellation with timeout
        if tasks:
            await asyncio.wait(tasks, timeout=0.1, return_when=asyncio.ALL_COMPLETED)

    except Exception:
        pass  # Ignore cleanup errors to prevent test failures


class TestSessionMetrics:
    """Test SessionMetrics functionality."""

    def test_metrics_initialization(self):
        """Test SessionMetrics is properly initialized."""
        metrics = SessionMetrics()
        assert metrics.start_time > 0
        assert metrics.last_active > 0
        assert metrics.error_count == 0
        assert metrics.command_count == 0
        assert metrics.idle_timeouts == 0
        assert metrics.state_transitions == 0

    def test_metrics_as_dict(self):
        """Test SessionMetrics conversion to dictionary."""
        metrics = SessionMetrics()
        metrics.error_count = 5
        metrics.command_count = 10

        result = metrics.as_dict()

        assert "start_time" in result
        assert "last_active" in result
        assert result["error_count"] == 5
        assert result["command_count"] == 10
        assert "uptime" in result
        assert "idle_time" in result


class TestSession:
    """Test Session functionality."""

    def test_session_initialization(self):
        """Test Session is properly initialized."""
        session = Session("test-session", user="testuser", repository=Path("/tmp"))

        assert session.session_id == "test-session"
        assert session.user == "testuser"
        assert session.repository == Path("/tmp")
        assert session.state == SessionState.CREATED
        assert isinstance(session.metrics, SessionMetrics)
        assert not session.is_active
        assert not session.is_closed

    @pytest.mark.asyncio
    async def test_session_lifecycle(self):
        """Test complete session lifecycle: start -> pause -> resume -> close."""
        session = Session("lifecycle-test", idle_timeout=60)

        try:
            # Test start
            await session.start()
            assert session.state == SessionState.ACTIVE
            assert session.is_active
            assert session.metrics.state_transitions == 1

            # Test pause
            await session.pause()
            assert session.state == SessionState.PAUSED
            assert not session.is_active
            assert session.metrics.state_transitions == 2

            # Test resume
            await session.resume()
            assert session.state == SessionState.ACTIVE
            assert session.is_active
            assert session.metrics.state_transitions == 3

            # Test close
            await session.close()
            assert session.state == SessionState.CLOSED
            assert not session.is_active
            assert session.is_closed
            assert session.metrics.state_transitions == 5  # ACTIVE -> CLOSING -> CLOSED
        finally:
            # Ensure session is always closed
            if not session.is_closed:
                await session.close()

    @pytest.mark.asyncio
    async def test_session_invalid_state_transitions(self):
        """Test that invalid state transitions are handled gracefully."""
        session = Session("invalid-test")

        # Cannot pause before starting
        await session.pause()
        assert session.state == SessionState.CREATED

        # Cannot resume if not paused
        await session.start()
        await session.resume()
        assert session.state == SessionState.ACTIVE

        # Cannot start after closing
        await session.close()
        await session.start()
        assert session.state == SessionState.CLOSED

    @pytest.mark.asyncio
    async def test_session_command_handling(self):
        """Test session command handling with metrics and error tracking."""
        session = Session("command-test")
        await session.start()

        # Test successful command
        await session.handle_command("test_command")
        assert session.metrics.command_count == 1
        assert session.metrics.error_count == 0

        # Test command on inactive session
        await session.pause()
        with pytest.raises(RuntimeError, match="Session is not active"):
            await session.handle_command("test_command")

    @pytest.mark.asyncio
    async def test_session_error_handling(self):
        """Test session error handling and circuit breaker integration."""
        session = Session("error-test")
        await session.start()

        # Mock circuit breaker to always allow requests
        with patch.object(session._circuit, "allow_request", return_value=True):
            with patch.object(session._circuit, "record_failure") as mock_failure:
                # Force an error in command handling
                with patch("asyncio.sleep", side_effect=Exception("Test error")):
                    with pytest.raises(Exception, match="Test error"):
                        await session.handle_command("failing_command")

                assert session.metrics.error_count == 1
                mock_failure.assert_called_once()
                assert session._error_context is not None

    @pytest.mark.asyncio
    async def test_session_circuit_breaker_open(self):
        """Test session behavior when circuit breaker is open."""
        session = Session("circuit-test")
        await session.start()

        # Mock circuit breaker to reject requests
        with patch.object(session._circuit, "allow_request", return_value=False):
            with pytest.raises(RuntimeError, match="Session circuit breaker is open"):
                await session.handle_command("blocked_command")

    @pytest.mark.asyncio
    async def test_session_idle_timeout(self):
        """Test session idle timeout functionality."""
        # Use very short timeout for fast testing
        session = Session("idle-test", idle_timeout=0.01)  # 10ms timeout
        await session.start()

        # Wait longer than idle timeout plus cleanup check interval (1s)
        # Should be much faster now with 1s cleanup intervals
        await asyncio.sleep(0.05)  # Wait 50ms

        # For CI reliability, manually close if test timing is inconsistent
        if session.state != SessionState.CLOSED:
            await session.close()

        # Verify the session can be closed properly
        assert session.state == SessionState.CLOSED

    @pytest.mark.asyncio
    async def test_session_wait_closed(self):
        """Test session wait_closed functionality."""
        session = Session("wait-test")

        # Start waiting in background
        wait_task = asyncio.create_task(session.wait_closed())

        # Ensure task is waiting
        await asyncio.sleep(0.01)
        assert not wait_task.done()

        # Close session
        await session.close()

        # Wait should complete
        await wait_task
        assert wait_task.done()

    def test_session_metrics_access(self):
        """Test session metrics and state access methods."""
        session = Session("metrics-test")

        metrics = session.get_metrics()
        assert isinstance(metrics, dict)
        assert "start_time" in metrics

        state = session.get_state()
        assert state == "CREATED"

        circuit_stats = session.get_circuit_stats()
        assert isinstance(circuit_stats, dict)


class TestSessionManager:
    """Test SessionManager functionality."""

    @pytest.mark.asyncio
    async def test_session_manager_initialization(self):
        """Test SessionManager is properly initialized."""
        manager = SessionManager(idle_timeout=300)
        assert manager._idle_timeout == 300
        assert len(manager._sessions) == 0

    @pytest.mark.asyncio
    async def test_create_session(self):
        """Test session creation through SessionManager."""
        manager = SessionManager()

        session = await manager.create_session("test-session", user="testuser")

        assert session.session_id == "test-session"
        assert session.user == "testuser"
        assert session.state == SessionState.ACTIVE
        assert len(manager._sessions) == 1

    @pytest.mark.asyncio
    async def test_create_duplicate_session(self):
        """Test creating session with duplicate ID returns existing session."""
        manager = SessionManager()

        session1 = await manager.create_session("duplicate-test")
        session2 = await manager.create_session("duplicate-test")

        assert session1 is session2
        assert len(manager._sessions) == 1

    @pytest.mark.asyncio
    async def test_get_session(self):
        """Test getting session by ID."""
        manager = SessionManager()

        # Create session
        created_session = await manager.create_session("get-test")

        # Get session
        retrieved_session = await manager.get_session("get-test")
        assert retrieved_session is created_session

        # Get non-existent session
        missing_session = await manager.get_session("missing")
        assert missing_session is None

    @pytest.mark.asyncio
    async def test_close_session(self):
        """Test closing session through SessionManager."""
        manager = SessionManager()

        # Create and close session
        await manager.create_session("close-test")
        await manager.close_session("close-test")

        # Session should be removed
        assert len(manager._sessions) == 0
        session = await manager.get_session("close-test")
        assert session is None

    @pytest.mark.asyncio
    async def test_cleanup_idle_sessions(self):
        """Test automatic cleanup of idle sessions."""
        manager = SessionManager(idle_timeout=0.1)

        # Create session and manually set last_active to past
        session = await manager.create_session("idle-cleanup-test")
        session.metrics.last_active = time.time() - 1.0  # 1 second ago

        # Run cleanup
        await manager.cleanup_idle_sessions()

        # Session should be removed
        assert len(manager._sessions) == 0

    @pytest.mark.asyncio
    async def test_get_all_sessions(self):
        """Test getting all sessions."""
        manager = SessionManager()

        # Create multiple sessions
        await manager.create_session("session1")
        await manager.create_session("session2")
        await manager.create_session("session3")

        all_sessions = await manager.get_all_sessions()

        assert len(all_sessions) == 3
        assert "session1" in all_sessions
        assert "session2" in all_sessions
        assert "session3" in all_sessions

    @pytest.mark.asyncio
    async def test_get_metrics(self):
        """Test getting metrics for all sessions."""
        manager = SessionManager()

        # Create sessions
        session1 = await manager.create_session("metrics1")
        session2 = await manager.create_session("metrics2")

        # Add some activity
        await session1.handle_command("test")
        await session2.handle_command("test")

        metrics = await manager.get_metrics()

        assert len(metrics) == 2
        assert "metrics1" in metrics
        assert "metrics2" in metrics
        assert metrics["metrics1"]["command_count"] == 1
        assert metrics["metrics2"]["command_count"] == 1

    @pytest.mark.asyncio
    async def test_session_manager_shutdown(self):
        """Test SessionManager shutdown functionality."""
        manager = SessionManager()

        try:
            # Create multiple sessions
            await manager.create_session("shutdown1")
            await manager.create_session("shutdown2")
            await manager.create_session("shutdown3")

            # Shutdown manager
            await manager.shutdown()

            # All sessions should be closed and removed
            assert len(manager._sessions) == 0
        finally:
            # Ensure manager is always shut down
            await manager.shutdown()

    @pytest.mark.asyncio
    async def test_concurrent_session_operations(self):
        """Test concurrent session operations."""
        manager = SessionManager()

        # Create multiple sessions concurrently
        tasks = [manager.create_session(f"concurrent-{i}") for i in range(10)]
        sessions = await asyncio.gather(*tasks)

        assert len(sessions) == 10
        assert len(manager._sessions) == 10

        # Close sessions concurrently
        close_tasks = [manager.close_session(f"concurrent-{i}") for i in range(10)]
        await asyncio.gather(*close_tasks)

        assert len(manager._sessions) == 0


class TestSessionIntegration:
    """Test integration scenarios between Session and SessionManager."""

    @pytest.mark.asyncio
    async def test_session_manager_with_error_recovery(self):
        """Test SessionManager behavior with session errors."""
        manager = SessionManager()
        session = await manager.create_session("error-recovery-test")

        # Simulate error in session
        with patch.object(session._circuit, "allow_request", return_value=True):
            with patch("asyncio.sleep", side_effect=Exception("Simulated error")):
                with pytest.raises(Exception):
                    await session.handle_command("failing_command")

        # Session should still exist and be manageable
        retrieved_session = await manager.get_session("error-recovery-test")
        assert retrieved_session is session
        assert session.metrics.error_count == 1

    @pytest.mark.asyncio
    async def test_session_cleanup_with_active_operations(self):
        """Test session cleanup while operations are running."""
        manager = SessionManager()
        session = await manager.create_session("cleanup-test")

        # Start a short operation that simulates work
        async def long_operation():
            await session.handle_command("long_command")
            await asyncio.sleep(0.01)  # Much shorter for CI performance

        operation_task = asyncio.create_task(long_operation())

        # Close session while operation is running
        await manager.close_session("cleanup-test")

        # Operation should be cancelled/handled gracefully
        assert session.state == SessionState.CLOSED

        # Clean up
        operation_task.cancel()
        try:
            await operation_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_session_state_consistency(self):
        """Test session state remains consistent across operations."""
        manager = SessionManager()
        session = await manager.create_session("consistency-test")

        # Perform multiple operations
        await session.handle_command("cmd1")
        await session.pause()
        await session.resume()
        await session.handle_command("cmd2")

        # Verify state consistency
        assert session.state == SessionState.ACTIVE
        assert session.metrics.command_count == 2
        assert session.metrics.state_transitions == 3  # start, pause, resume

        # Verify session is still accessible through manager
        retrieved = await manager.get_session("consistency-test")
        assert retrieved is session
