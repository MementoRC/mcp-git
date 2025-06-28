import asyncio
import json
import pytest

from mcp_server_git.session import SessionManager, SessionState
from mcp_server_git.core.notification_interceptor import NotificationInterceptor


@pytest.mark.asyncio
async def test_long_running_session_lifecycle():
    """Test that a session remains active and then times out as expected."""
    manager = SessionManager(idle_timeout=1.5, heartbeat_timeout=1.0)
    session = await manager.create_session("longrun", user="eve")
    assert session.state == SessionState.ACTIVE
    # Wait for idle timeout to trigger
    await asyncio.sleep(2.0)
    assert session.state == SessionState.CLOSED


@pytest.mark.asyncio
async def test_heartbeat_prevents_idle_timeout():
    """Test that heartbeats keep the session alive."""
    manager = SessionManager(idle_timeout=2.0, heartbeat_timeout=1.0)
    session = await manager.create_session("heartbeat", user="bob")
    for _ in range(3):
        await session.handle_heartbeat()
        await asyncio.sleep(0.5)
    # Should still be active
    assert session.state == SessionState.ACTIVE
    await session.close()


@pytest.mark.asyncio
async def test_stress_many_notifications(sample_cancelled_notification):
    """Stress test: send many notifications through the interceptor."""
    interceptor = NotificationInterceptor()
    raw_message = json.dumps(sample_cancelled_notification)
    count = 1000
    dropped = 0
    for _ in range(count):
        result = await interceptor.preprocess_message(raw_message)
        if result is None:
            dropped += 1
    assert dropped == count


@pytest.mark.asyncio
async def test_concurrent_sessions_and_notifications(sample_cancelled_notification):
    """Test concurrent session creation and notification interception."""
    manager = SessionManager(idle_timeout=2.0, heartbeat_timeout=1.0)
    interceptor = NotificationInterceptor()
    raw_message = json.dumps(sample_cancelled_notification)

    async def create_and_run_session(sid):
        session = await manager.create_session(sid)
        await session.handle_heartbeat()
        await asyncio.sleep(0.2)
        await session.close()

    async def send_notifications():
        for _ in range(100):
            await interceptor.preprocess_message(raw_message)

    tasks = [
        asyncio.create_task(create_and_run_session(f"sess-{i}")) for i in range(10)
    ] + [asyncio.create_task(send_notifications()) for _ in range(5)]

    await asyncio.gather(*tasks)


@pytest.mark.asyncio
async def test_malformed_message_handling(malformed_notification):
    """Test that malformed notifications do not crash the interceptor."""
    interceptor = NotificationInterceptor()
    raw_message = json.dumps(malformed_notification)
    # Should not raise, should be dropped
    result = await interceptor.preprocess_message(raw_message)
    assert result is None
