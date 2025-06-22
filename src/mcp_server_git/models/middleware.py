import logging
from typing import Any, Dict, Optional

from .notifications import CancelledNotification
from .validation import validate_cancelled_notification

logger = logging.getLogger(__name__)


def notification_validator_middleware(
    message: Dict[str, Any],
) -> Optional[CancelledNotification]:
    """
    A middleware that validates incoming notifications.
    It specifically looks for and validates "notifications/cancelled".
    Other notifications are passed through (by returning None).
    """
    if message.get("method") == "notifications/cancelled":
        try:
            validated_notification = validate_cancelled_notification(message)
            logger.info(
                "Validated CancelledNotification for requestId: "
                f"{validated_notification.params.requestId}"
            )
            return validated_notification
        except ValueError as e:
            logger.error(f"Failed to validate CancelledNotification: {e}")
            # In a real server, you might drop the message or send an error response
            # For this middleware, we'll just log and return None.
            return None
    return None
