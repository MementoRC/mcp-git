"""
Notification interceptor for handling cancelled notifications before they reach
the MCP framework's built-in validation, which doesn't support notifications/cancelled.
"""

import logging
import json
from typing import Dict, Optional

from ..models.enhanced_validation import process_notification_safely

logger = logging.getLogger(__name__)


class NotificationInterceptor:
    """
    Intercepts and preprocesses notifications before they reach the MCP framework.
    Specifically handles 'notifications/cancelled' which is not supported by the
    standard MCP ClientNotification union.
    """

    def __init__(self):
        self.intercepted_count = 0
        self.cancelled_count = 0

    async def preprocess_message(self, raw_message: str) -> Optional[str]:
        """
        Preprocess incoming messages to handle unsupported notification types.

        Args:
            raw_message: Raw JSON message string

        Returns:
            Modified message string or None to drop the message
        """
        try:
            # Parse the message
            message_data = json.loads(raw_message)

            # Check if this is a notification
            if not isinstance(message_data, dict):
                return raw_message

            method = message_data.get("method", "")

            # Handle cancelled notifications specially
            if method == "notifications/cancelled":
                self.cancelled_count += 1
                self.intercepted_count += 1

                logger.info(
                    f"🔔 Intercepted cancelled notification #{self.cancelled_count}"
                )

                # Process the notification safely
                result = process_notification_safely(message_data)

                if result.is_valid:
                    logger.debug("✅ Cancelled notification processed successfully")
                    # Drop the message (return None) since we've handled it
                    return None
                else:
                    logger.warning(
                        f"⚠️ Cancelled notification processing failed: {result.error}"
                    )
                    # Still drop it to prevent MCP validation crash
                    return None

            # Check for other unsupported notification types
            if method.startswith("notifications/") and method not in [
                "notifications/progress",
                "notifications/initialized",
                "notifications/roots/list_changed",
            ]:
                self.intercepted_count += 1
                logger.warning(f"🔔 Intercepted unsupported notification: {method}")

                # Convert unknown notifications to cancelled notifications
                converted_data = {
                    "jsonrpc": "2.0",
                    "method": "notifications/cancelled",
                    "params": {
                        "requestId": message_data.get("params", {}).get(
                            "requestId", "unknown"
                        ),
                        "reason": f"Converted from unsupported type: {method}",
                    },
                }

                logger.debug(f"Converted {method} to cancelled notification")
                return json.dumps(converted_data)

            # For all other messages, pass through unchanged
            return raw_message

        except json.JSONDecodeError:
            # Not valid JSON, pass through
            return raw_message
        except Exception as e:
            logger.error(f"Error in message preprocessing: {e}")
            # On error, pass through to avoid breaking the protocol
            return raw_message

    def get_stats(self) -> Dict[str, int]:
        """Get interception statistics."""
        return {
            "total_intercepted": self.intercepted_count,
            "cancelled_notifications": self.cancelled_count,
        }


# Global interceptor instance
message_interceptor = NotificationInterceptor()


class InterceptingReadStream:
    """
    A wrapper around read streams that intercepts and preprocesses messages
    before they reach the MCP framework.

    This properly delegates all async context manager methods to the original stream.
    """

    def __init__(self, original_stream):
        self.original_stream = original_stream
        self.interceptor = message_interceptor

    async def readline(self) -> bytes:
        """Read and preprocess a line from the stream."""
        try:
            # Read from original stream
            line = await self.original_stream.readline()

            if not line:
                return line

            # Decode and preprocess
            raw_message = line.decode("utf-8").strip()
            if not raw_message:
                return line

            # Preprocess the message
            processed_message = await self.interceptor.preprocess_message(raw_message)

            # If message was dropped (None), return empty line
            if processed_message is None:
                logger.debug("Message dropped by interceptor")
                # Return empty line which will be ignored by JSON-RPC
                return b"\n"

            # Return processed message
            return (processed_message + "\n").encode("utf-8")

        except Exception as e:
            logger.error(f"Error in stream interception: {e}")
            # On error, return original line to avoid breaking protocol
            return line

    # Delegate async context manager methods
    async def __aenter__(self):
        """Delegate async context manager entry to original stream."""
        if hasattr(self.original_stream, "__aenter__"):
            return await self.original_stream.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Delegate async context manager exit to original stream."""
        if hasattr(self.original_stream, "__aexit__"):
            return await self.original_stream.__aexit__(exc_type, exc_val, exc_tb)
        return None

    def __getattr__(self, name):
        """Delegate all other attributes to the original stream."""
        return getattr(self.original_stream, name)


def wrap_read_stream(original_stream):
    """
    Wrap a read stream with notification interception capabilities.

    Args:
        original_stream: The original asyncio stream reader

    Returns:
        Wrapped stream with interception
    """
    return InterceptingReadStream(original_stream)


def log_interception_stats():
    """Log current interception statistics."""
    stats = message_interceptor.get_stats()
    if stats["total_intercepted"] > 0:
        logger.info(f"🔔 Notification interception stats: {stats}")
