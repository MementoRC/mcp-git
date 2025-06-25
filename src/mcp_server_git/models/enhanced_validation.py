"""
Enhanced validation system for MCP Git Server with robust notification handling.
This module provides comprehensive validation that can handle unexpected or malformed messages
without crashing the server.
"""

import logging
import json
from typing import Dict, Any, Optional, Union
from dataclasses import dataclass


from .notifications import CancelledNotification
from .validation import ValidationResult, safe_parse_notification

logger = logging.getLogger(__name__)


@dataclass
class NotificationInfo:
    """Information about a notification for logging and debugging."""

    method: str
    has_params: bool
    request_id: Optional[Union[str, int]] = None
    raw_size: int = 0


class RobustNotificationHandler:
    """
    A robust notification handler that can process various notification types
    without crashing when encountering unknown or malformed messages.
    """

    def __init__(self):
        self.processed_count = 0
        self.error_count = 0
        self.unknown_count = 0

    def extract_notification_info(self, data: Dict[str, Any]) -> NotificationInfo:
        """Extract basic information from notification data for logging."""
        try:
            method = data.get("method", "unknown")
            params = data.get("params", {})
            has_params = bool(params)
            request_id = None

            if isinstance(params, dict):
                request_id = params.get("requestId")

            raw_size = len(json.dumps(data)) if data else 0

            return NotificationInfo(
                method=method,
                has_params=has_params,
                request_id=request_id,
                raw_size=raw_size,
            )
        except Exception as e:
            logger.error(f"Failed to extract notification info: {e}")
            return NotificationInfo(method="error", has_params=False)

    def handle_notification(self, data: Dict[str, Any]) -> ValidationResult:
        """
        Handle a notification with comprehensive error handling and fallback logic.

        Args:
            data: Raw notification data

        Returns:
            ValidationResult with model or error information
        """
        try:
            # Extract basic info for logging
            info = self.extract_notification_info(data)
            logger.debug(
                f"Processing notification: {info.method} (request_id: {info.request_id})"
            )

            # Attempt to parse the notification
            result = safe_parse_notification(data)

            if result.is_valid:
                self.processed_count += 1
                logger.debug(f"Successfully parsed {info.method} notification")
                return result
            else:
                # Handle parsing failure
                self.error_count += 1
                logger.warning(
                    f"Failed to parse {info.method} notification: {result.error}"
                )

                # Attempt fallback handling
                return self._handle_parsing_failure(data, info, result.error)

        except Exception as e:
            self.error_count += 1
            logger.error(f"Unexpected error in notification handling: {e}")
            return ValidationResult(error=e, raw_data=data)

    def _handle_parsing_failure(
        self,
        data: Dict[str, Any],
        info: NotificationInfo,
        original_error: Optional[Exception],
    ) -> ValidationResult:
        """Handle cases where notification parsing fails."""

        # Check if this is a cancelled notification that we can handle specially
        if info.method == "notifications/cancelled":
            try:
                # Try to create a minimal valid cancelled notification
                fallback_data = {
                    "jsonrpc": "2.0",
                    "method": "notifications/cancelled",
                    "params": {
                        "requestId": info.request_id or "unknown",
                        "reason": "Recovered from parsing failure",
                    },
                }
                model = CancelledNotification.model_validate(fallback_data)
                logger.info(
                    f"Recovered cancelled notification for request {info.request_id}"
                )
                return ValidationResult(model=model, raw_data=data)
            except Exception as fallback_error:
                logger.error(f"Fallback handling failed: {fallback_error}")

        # For unknown notification types, log and continue gracefully
        if info.method not in [
            "notifications/cancelled",
            "notifications/progress",
            "notifications/initialized",
            "notifications/roots/list_changed",
        ]:
            self.unknown_count += 1
            logger.warning(
                f"Unknown notification type: {info.method} - ignoring gracefully"
            )

            # Create a "silent" cancelled notification to represent the unknown type
            try:
                silent_data = {
                    "jsonrpc": "2.0",
                    "method": "notifications/cancelled",
                    "params": {
                        "requestId": info.request_id or f"unknown_{self.unknown_count}",
                        "reason": f"Unknown notification type: {info.method}",
                    },
                }
                model = CancelledNotification.model_validate(silent_data)
                logger.debug(
                    f"Created silent cancelled notification for unknown type: {info.method}"
                )
                return ValidationResult(model=model, raw_data=data)
            except Exception as e:
                logger.error(f"Failed to create silent notification: {e}")

        # Final fallback - return error result but don't crash
        return ValidationResult(error=original_error, raw_data=data)

    def get_stats(self) -> Dict[str, int]:
        """Get processing statistics."""
        return {
            "processed": self.processed_count,
            "errors": self.error_count,
            "unknown": self.unknown_count,
            "total": self.processed_count + self.error_count,
        }


# Global handler instance
notification_handler = RobustNotificationHandler()


def process_notification_safely(data: Dict[str, Any]) -> ValidationResult:
    """
    Main entry point for safe notification processing.

    This function provides a safe way to process notifications that won't
    crash the server even when encountering malformed or unknown message types.
    """
    return notification_handler.handle_notification(data)


def log_notification_stats() -> None:
    """Log current notification processing statistics."""
    stats = notification_handler.get_stats()
    logger.info(f"Notification stats: {stats}")
