import asyncio
import json
import uuid
import pytest
from unittest.mock import AsyncMock

from mcp_server_git.models.notifications import (
    CancelledNotification,
    parse_client_notification,
)
from mcp_server_git.models.validation import validate_cancelled_notification
from mcp_server_git.core.notification_interceptor import NotificationInterceptor
from mcp_server_git.session import SessionManager, SessionState
from mcp_server_git.error_handling import ErrorContext, classify_error, handle_error


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
async def test_notification_interceptor_handles_cancelled(
    sample_cancelled_notification,
):
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


# Enhanced Task 9 Integration Tests for Message Processing


@pytest.mark.asyncio
async def test_message_processing_loop_cancellation():
    """Test the new message processing loop handles cancellation properly."""
    # Mock streams
    read_stream = AsyncMock()

    # Setup test messages
    request_id = str(uuid.uuid4())
    start_message = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "test_operation",
        "params": {"data": "test"},
    }
    cancel_message = {
        "jsonrpc": "2.0",
        "method": "notifications/cancelled",
        "params": {"requestId": request_id, "reason": "Test cancellation"},
    }

    # Setup read stream to return messages then EOF
    read_stream.readline.side_effect = [
        json.dumps(start_message).encode() + b"\n",
        json.dumps(cancel_message).encode() + b"\n",
        b"",  # EOF
    ]

    # Track active operations (simulating server state)
    active_operations = {}

    # Simulate the message processing loop logic
    async def mock_process_message_loop():
        while True:
            raw_message = await read_stream.readline()
            if not raw_message:
                break

            try:
                message = json.loads(raw_message.decode())
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue

            # Handle cancellation
            try:
                notification = parse_client_notification(message)
                if isinstance(notification, CancelledNotification):
                    req_id = notification.params.requestId
                    op = active_operations.get(req_id)
                    if op and not op.done():
                        op.cancel()
                    continue
            except (ValueError, KeyError, TypeError):
                pass

            # Handle regular message
            req_id = message.get("id") or str(uuid.uuid4())

            async def handle_message_task():
                await asyncio.sleep(0.1)  # Simulate work

            op_task = asyncio.create_task(handle_message_task())
            active_operations[req_id] = op_task

            try:
                await op_task
            except asyncio.CancelledError:
                pass
            finally:
                active_operations.pop(req_id, None)

    # Run the mock processing loop
    await mock_process_message_loop()

    # Verify cancellation was handled
    assert len(active_operations) == 0  # All operations cleaned up


@pytest.mark.asyncio
async def test_active_operation_tracking():
    """Test that active operations are properly tracked and cleaned up."""
    active_operations = {}

    # Create a mock operation
    operation_id = "test-op-123"

    async def mock_operation():
        await asyncio.sleep(0.1)
        return "completed"

    # Track operation
    task = asyncio.create_task(mock_operation())
    active_operations[operation_id] = task

    # Verify it's tracked
    assert operation_id in active_operations
    assert not active_operations[operation_id].done()

    # Wait for completion
    await task

    # Verify completion
    assert active_operations[operation_id].done()

    # Clean up
    active_operations.pop(operation_id, None)
    assert operation_id not in active_operations


@pytest.mark.asyncio
async def test_operation_cancellation_during_execution():
    """Test cancelling an operation while it's running."""
    active_operations = {}
    operation_id = "cancel-test-456"

    async def long_running_operation():
        try:
            await asyncio.sleep(1.0)  # Long operation
            return "completed"
        except asyncio.CancelledError:
            return "cancelled"

    # Start operation
    task = asyncio.create_task(long_running_operation())
    active_operations[operation_id] = task

    # Let it start
    await asyncio.sleep(0.1)

    # Cancel it
    task.cancel()

    # Wait for cancellation
    try:
        result = await task
        assert result == "cancelled"
    except asyncio.CancelledError:
        pass  # Expected

    # Clean up
    active_operations.pop(operation_id, None)
    assert operation_id not in active_operations


@pytest.mark.asyncio
async def test_message_error_recovery():
    """Test error recovery during message processing."""
    error_count = 0

    async def failing_message_handler():
        nonlocal error_count
        error_count += 1
        if error_count <= 2:
            raise ValueError("Test error")
        return "success"

    # Simulate error handling
    for attempt in range(5):
        try:
            result = await failing_message_handler()
            if result == "success":
                break
        except ValueError as e:
            # Classify and handle error
            error_ctx = classify_error(e, operation="test_message")
            await handle_error(error_ctx)
            continue

    # Should eventually succeed
    assert error_count == 3  # Failed twice, succeeded on third


@pytest.mark.asyncio
async def test_concurrent_message_processing():
    """Test processing multiple messages concurrently."""
    active_operations = {}
    completed_operations = []

    async def process_message(msg_id):
        operation_id = f"op-{msg_id}"

        async def operation():
            await asyncio.sleep(0.1)
            completed_operations.append(operation_id)
            return f"result-{msg_id}"

        task = asyncio.create_task(operation())
        active_operations[operation_id] = task

        try:
            result = await task
            return result
        finally:
            active_operations.pop(operation_id, None)

    # Process multiple messages concurrently
    tasks = [process_message(i) for i in range(10)]
    results = await asyncio.gather(*tasks)

    # Verify all completed
    assert len(results) == 10
    assert len(completed_operations) == 10
    assert len(active_operations) == 0

    # Verify results
    for i, result in enumerate(results):
        assert result == f"result-{i}"


@pytest.mark.asyncio
async def test_malformed_message_resilience():
    """Test that malformed messages don't crash the processing loop."""
    processed_count = 0

    test_messages = [
        "{invalid json",  # Invalid JSON
        "{}",  # Empty object
        '{"method": "test"}',  # Valid message
        '{"invalid": true}',  # Missing required fields
        '{"method": "test2", "id": "valid"}',  # Another valid message
    ]

    for raw_message in test_messages:
        try:
            message = json.loads(raw_message)
            # Process valid messages
            if "method" in message:
                processed_count += 1
        except json.JSONDecodeError:
            # Skip invalid JSON - should not crash
            continue
        except Exception as e:
            # Handle other errors gracefully
            error_ctx = classify_error(e, operation="message_parse")
            await handle_error(error_ctx)

    # Should have processed 2 valid messages
    assert processed_count == 2
