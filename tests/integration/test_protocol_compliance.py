import asyncio
import json
import pytest

from src.mcp_server_git.models.notifications import (
    CancelledNotification,
    parse_client_notification,
)
from src.mcp_server_git.models.validation import validate_cancelled_notification
from src.mcp_server_git.core.notification_interceptor import NotificationInterceptor
from src.mcp_server_git.session import Session, SessionManager, SessionState
from src.mcp_server_git.error_handling import classify_error, ErrorContext

@pytest.mark.asyncio
async def test_cancelled_notification_parsing(sample_cancelled_notification):
    """Test that a valid cancelled notification is parsed correctly."""
    notification = parse_client_notification(sample_cancelled_notification)
    assert isinstance(notification, CancelledNotification)
    assert notification.params.requestId == "test-req-1"
    assert notification.params.reason == "User cancelled"

@pytest.mark.asyncio
async def test_cancelled_notification_validation(sample_cancelled_notification):
    """Test that a valid cancelled notification passes validation."""
    notification = validate_cancelled_notification(sample_cancelled_notification)
    assert notification.params.requestId == "test-req-1"

@pytest.mark.asyncio
async def test_malformed_cancelled_notification(malformed_notification):
    """Test that a malformed cancelled notification raises ValueError."""
    with pytest.raises(ValueError):
        validate_cancelled_notification(malformed_notification)

@pytest.mark.asyncio
async def test_notification_interceptor_handles_cancelled(sample_cancelled_notification):
    """Test that the notification interceptor processes cancelled notifications."""
    interceptor = NotificationInterceptor()
    raw_message = json.dumps(sample_cancelled_notification)
    result = await interceptor.preprocess_message(raw_message)
    # Should return None (message dropped after processing)
    assert result is None

@pytest.mark.asyncio
async def test_notification_interceptor_handles_malformed(malformed_notification):
    """Test that the notification interceptor drops malformed notifications."""
    interceptor = NotificationInterceptor()
    raw_message = json.dumps(malformed_notification)
    result = await interceptor.preprocess_message(raw_message)
    # Should return None (message dropped)
    assert result is None

@pytest.mark.asyncio
async def test_session_lifecycle_integration():
    """Test session creation, activation, pausing, and closing."""
    manager = SessionManager(idle_timeout=2, heartbeat_timeout=1)
    session = await manager.create_session("sess-1", user="alice")
    assert session.state == SessionState.ACTIVE
    await session.pause()
    assert session.state == SessionState.PAUSED
    await session.resume()
    assert session.state == SessionState.ACTIVE
    await session.close(reason="test done")
    assert session.state == SessionState.CLOSED

@pytest.mark.asyncio
async def test_session_error_handling():
    """Test error context integration with session command handling."""
    manager = SessionManager()
    session = await manager.create_session("sess-err", user="bob")
    # Simulate a command that raises an error
    with pytest.raises(RuntimeError):
        await session.handle_command("bad_command")
    ctx = session.get_error_context()
    assert isinstance(ctx, ErrorContext)
    assert ctx.operation == "bad_command"
    await session.close()

@pytest.mark.asyncio
async def test_protocol_compliance_with_unknown_notification():
    """Test that unknown notification types are converted or dropped."""
    interceptor = NotificationInterceptor()
    unknown_notification = {
        "jsonrpc": "2.0",
        "method": "notifications/unknown_type",
        "params": {"foo": "bar"},
    }
    raw_message = json.dumps(unknown_notification)
    result = await interceptor.preprocess_message(raw_message)
    # Should convert to a cancelled notification
    assert result is not None
    data = json.loads(result)
    assert data["method"] == "notifications/cancelled"
    assert "requestId" in data["params"]

@pytest.mark.asyncio
async def test_protocol_compliance_with_non_notification():
    """Test that non-notification messages pass through unchanged."""
    interceptor = NotificationInterceptor()
    request_message = {
        "jsonrpc": "2.0",
        "id": 42,
        "method": "tools/call",
        "params": {"name": "git_status", "arguments": {}},
    }
    raw_message = json.dumps(request_message)
    result = await interceptor.preprocess_message(raw_message)
    assert result == raw_message
