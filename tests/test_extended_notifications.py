from typing import Any, Dict

import pytest
from pydantic import ValidationError

from mcp_server_git.models.middleware import notification_validator_middleware
from mcp_server_git.models.notifications import CancelledNotification
from mcp_server_git.models.validation import validate_cancelled_notification


# 1. Test cases for direct model validation
def test_cancelled_notification_valid_string_request_id():
    """Tests a valid CancelledNotification with a string requestId."""
    data = {
        "jsonrpc": "2.0",
        "method": "notifications/cancelled",
        "params": {"requestId": "abc-123"},
    }
    notification = CancelledNotification(**data)
    assert notification.jsonrpc == "2.0"
    assert notification.method == "notifications/cancelled"
    assert notification.params.requestId == "abc-123"
    assert notification.params.reason is None


def test_cancelled_notification_valid_int_request_id():
    """Tests a valid CancelledNotification with an integer requestId."""
    data = {
        "jsonrpc": "2.0",
        "method": "notifications/cancelled",
        "params": {"requestId": 123},
    }
    notification = CancelledNotification(**data)
    assert notification.params.requestId == 123


def test_cancelled_notification_with_reason():
    """Tests a valid CancelledNotification with an optional reason."""
    data = {
        "jsonrpc": "2.0",
        "method": "notifications/cancelled",
        "params": {"requestId": "abc-123", "reason": "User cancelled"},
    }
    notification = CancelledNotification(**data)
    assert notification.params.requestId == "abc-123"
    assert notification.params.reason == "User cancelled"


def test_cancelled_notification_invalid_method():
    """Tests that an incorrect method raises a validation error."""
    data = {
        "jsonrpc": "2.0",
        "method": "$/progress/cancel",  # Incorrect method
        "params": {"requestId": "abc-123"},
    }
    with pytest.raises(ValidationError):
        CancelledNotification(**data)


def test_cancelled_notification_missing_jsonrpc():
    """Tests that a missing jsonrpc field gets defaulted to '2.0'."""
    data = {
        "method": "notifications/cancelled",
        "params": {"requestId": "abc-123"},
    }
    notification = CancelledNotification(**data)
    assert notification.jsonrpc == "2.0"  # Should default to "2.0"


def test_cancelled_notification_missing_request_id():
    """Tests that missing requestId in params raises a validation error."""
    data = {
        "jsonrpc": "2.0",
        "method": "notifications/cancelled",
        "params": {},  # Missing requestId
    }
    with pytest.raises(ValidationError):
        CancelledNotification(**data)


# 2. Test cases for the validation function
def test_validate_cancelled_notification_success():
    """Tests the validation function with valid data."""
    valid_data = {
        "jsonrpc": "2.0",
        "method": "notifications/cancelled",
        "params": {"requestId": 456},
    }
    notification = validate_cancelled_notification(valid_data)
    assert isinstance(notification, CancelledNotification)
    assert notification.params.requestId == 456


def test_validate_cancelled_notification_failure():
    """Tests that the validation function raises ValueError for invalid data."""
    invalid_data = {
        "jsonrpc": "2.0",
        "method": "notifications/cancelled",
        "params": {"id": 456},  # 'id' instead of 'requestId'
    }
    with pytest.raises(
        ValueError, match="Invalid notification format for CancelledNotification"
    ):
        validate_cancelled_notification(invalid_data)


# 3. Test cases for the middleware
def test_middleware_with_valid_cancelled_notification():
    """Tests the middleware with a valid notification."""
    message = {
        "jsonrpc": "2.0",
        "method": "notifications/cancelled",
        "params": {"requestId": "xyz-789", "reason": "Timeout"},
    }
    result = notification_validator_middleware(message)
    assert isinstance(result, CancelledNotification)
    assert result.params.requestId == "xyz-789"
    assert result.params.reason == "Timeout"


def test_middleware_with_invalid_cancelled_notification(caplog):
    """Tests the middleware with an invalid notification, expecting None."""
    message = {
        "jsonrpc": "2.0",
        "method": "notifications/cancelled",
        "params": {},  # Missing requestId
    }
    result = notification_validator_middleware(message)
    assert result is None
    assert "Failed to validate CancelledNotification" in caplog.text


def test_middleware_with_other_notification():
    """Tests that the middleware ignores other notifications."""
    message: Dict[str, Any] = {
        "jsonrpc": "2.0",
        "method": "textDocument/didChange",
        "params": {},
    }
    result = notification_validator_middleware(message)
    assert result is None


def test_middleware_with_non_notification_message():
    """Tests that the middleware ignores messages without a 'method' field."""
    message: Dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": "some result",
    }
    result = notification_validator_middleware(message)
    assert result is None
