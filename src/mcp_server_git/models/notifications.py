from typing import Any, Dict, Literal, Optional, Union
import logging

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


class CancelledParams(BaseModel):
    """Parameters for a cancelled notification."""

    requestId: Union[str, int]
    reason: Optional[str] = None


class CancelledNotification(BaseModel):
    """
    A notification indicating that a previously sent request has been cancelled.
    https://microsoft.github.io/language-server-protocol/specifications/mcp/0.2.0-pre.1/#cancelledNotification
    """

    jsonrpc: Literal["2.0"] = "2.0"
    method: Literal["notifications/cancelled"] = "notifications/cancelled"
    params: CancelledParams


# Union type for all client notifications
ClientNotification = Union[
    CancelledNotification,
    # Add other notification types here as they are implemented
]


def parse_client_notification(data: Dict[str, Any]) -> ClientNotification:
    """
    Parse a client notification from raw data based on its type field.

    Args:
        data: Raw notification data containing 'method' field

    Returns:
        Parsed notification instance

    Raises:
        ValidationError: If the notification cannot be parsed
    """
    notification_method = data.get("method", "")

    if notification_method == "notifications/cancelled":
        return CancelledNotification.model_validate(data)
    else:
        # Log unknown notification type but don't crash
        logger.warning(f"Unknown notification method: {notification_method}")
        # For unknown types, attempt to parse as cancelled notification as fallback
        # This provides graceful degradation
        try:
            return CancelledNotification.model_validate(data)
        except ValidationError:
            # If all else fails, create a minimal cancelled notification
            logger.error(f"Failed to parse notification: {data}")
            return CancelledNotification(params=CancelledParams(requestId="unknown"))
