"""Server-level notification operations for the MCP Git server.

This module provides the NotificationOperations class that serves as the primary interface
for managing notifications, events, and messaging within the MCP Git server. It integrates
with existing notification infrastructure and provides server-level coordination.
"""

import logging
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Any

from ..configuration.server_config import GitServerConfig
from ..core.notification_interceptor import message_interceptor
from ..models.notifications import (
    CancelledNotification,
    parse_client_notification,
)
from ..protocols.debugging_protocol import DebuggableComponent
from ..protocols.notification_protocol import (
    EventSubscriber,
    NotificationChannel,
    NotificationEvent,
    NotificationLevel,
)

logger = logging.getLogger(__name__)


@dataclass
class NotificationStats:
    """Statistics about notification operations."""

    total_events_published: int = 0
    total_messages_broadcast: int = 0
    total_errors_reported: int = 0
    total_status_updates: int = 0
    total_cancelled_notifications: int = 0
    active_subscriptions: int = 0
    intercepted_notifications: int = 0
    last_activity: datetime = field(default_factory=datetime.now)


@dataclass
class SubscriptionRecord:
    """Internal record for event subscriptions."""

    subscription_id: str
    subscriber: EventSubscriber
    filters: dict[str, Any]
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)


class NotificationOperations(DebuggableComponent):
    """Server-level notification operations manager.

    This class provides comprehensive notification handling for the MCP Git server,
    including event publishing, message broadcasting, error reporting, and status updates.
    It integrates with the existing notification infrastructure and provides debugging capabilities.
    """

    def __init__(self, config: GitServerConfig | None = None):
        """Initialize notification operations.

        Args:
            config: Server configuration for notification settings
        """
        self.config = config or GitServerConfig()
        self.stats = NotificationStats()
        self.interceptor = message_interceptor

        # Thread-safe storage for subscriptions and events
        self._lock = Lock()
        self._subscriptions: dict[str, SubscriptionRecord] = {}
        self._event_history: deque[NotificationEvent] = deque(maxlen=1000)
        self._error_history: deque[dict[str, Any]] = deque(maxlen=500)
        self._status_history: deque[dict[str, Any]] = deque(maxlen=300)

        # Channel configurations
        self._channel_configs: dict[NotificationChannel, dict[str, Any]] = {
            NotificationChannel.LOG: {"enabled": True, "level": "INFO"},
            NotificationChannel.CONSOLE: {"enabled": True, "level": "WARNING"},
            NotificationChannel.SYSTEM: {"enabled": True, "level": "ERROR"},
        }

        logger.info("NotificationOperations initialized")

    # EventPublisher Protocol Implementation

    def publish_event(self, event: NotificationEvent) -> None:
        """Publish an event to all interested subscribers.

        Args:
            event: NotificationEvent to publish
        """
        with self._lock:
            self.stats.total_events_published += 1
            self.stats.last_activity = datetime.now()
            self._event_history.append(event)

        logger.debug(
            f"Publishing event: {event.event_type} from {event.source_component}"
        )

        # Find and notify subscribers
        matching_subscribers = self._find_matching_subscribers(event)

        for subscription_id, subscriber in matching_subscribers:
            try:
                subscriber.handle_event(event)
                # Update subscription activity
                if subscription_id in self._subscriptions:
                    self._subscriptions[subscription_id].last_activity = datetime.now()
            except Exception as e:
                logger.error(f"Error notifying subscriber {subscription_id}: {e}")
                self._report_subscriber_error(subscription_id, e, event)

        # Log the event based on its level
        self._log_event(event)

    def subscribe(self, subscriber: EventSubscriber) -> str:
        """Register a subscriber for events.

        Args:
            subscriber: EventSubscriber to register

        Returns:
            Subscription ID for later unsubscription
        """
        subscription_id = str(uuid.uuid4())
        filters = subscriber.get_subscription_filters()

        with self._lock:
            self._subscriptions[subscription_id] = SubscriptionRecord(
                subscription_id=subscription_id, subscriber=subscriber, filters=filters
            )
            self.stats.active_subscriptions = len(self._subscriptions)

        logger.info(
            f"Registered subscriber {subscriber.get_subscriber_id()} with ID {subscription_id}"
        )
        return subscription_id

    def unsubscribe(self, subscription_id: str) -> bool:
        """Remove a subscriber.

        Args:
            subscription_id: ID returned from subscribe()

        Returns:
            True if successfully unsubscribed, False otherwise
        """
        with self._lock:
            if subscription_id in self._subscriptions:
                subscriber_id = self._subscriptions[
                    subscription_id
                ].subscriber.get_subscriber_id()
                del self._subscriptions[subscription_id]
                self.stats.active_subscriptions = len(self._subscriptions)
                logger.info(
                    f"Unsubscribed subscriber {subscriber_id} ({subscription_id})"
                )
                return True

        logger.warning(
            f"Attempted to unsubscribe unknown subscription ID: {subscription_id}"
        )
        return False

    def get_active_subscriptions(self) -> list[str]:
        """Get list of active subscription IDs."""
        with self._lock:
            return list(self._subscriptions.keys())

    # StatusReporter Protocol Implementation

    def report_status(
        self, status: str, component_id: str, metadata: dict[str, Any] | None = None
    ) -> None:
        """Report status update for a component.

        Args:
            status: Status description
            component_id: ID of component reporting status
            metadata: Optional additional status information
        """
        status_record = {
            "status": status,
            "component_id": component_id,
            "metadata": metadata or {},
            "timestamp": datetime.now(),
            "record_id": str(uuid.uuid4()),
        }

        with self._lock:
            self.stats.total_status_updates += 1
            self.stats.last_activity = datetime.now()
            self._status_history.append(status_record)

        logger.info(f"Status update from {component_id}: {status}")

        # Create and publish status event
        event = NotificationEvent(
            event_id=status_record["record_id"],
            event_type="status_update",
            level=NotificationLevel.INFO,
            message=f"{component_id}: {status}",
            timestamp=status_record["timestamp"],
            source_component=component_id,
            metadata=status_record["metadata"],
            channels=[NotificationChannel.LOG],
        )

        self.publish_event(event)

    def report_progress(
        self,
        progress: float,
        component_id: str,
        operation: str,
        details: str | None = None,
    ) -> None:
        """Report progress update for a long-running operation.

        Args:
            progress: Progress as float between 0.0 and 1.0
            component_id: ID of component reporting progress
            operation: Description of operation in progress
            details: Optional additional progress details
        """
        progress_metadata = {
            "progress": min(max(progress, 0.0), 1.0),  # Clamp to [0.0, 1.0]
            "operation": operation,
            "details": details or "",
            "percentage": f"{progress * 100:.1f}%",
        }

        self.report_status(
            f"Progress: {progress_metadata['percentage']} - {operation}",
            component_id,
            progress_metadata,
        )

    def report_completion(
        self,
        component_id: str,
        operation: str,
        success: bool,
        result_data: dict[str, Any] | None = None,
    ) -> None:
        """Report completion of an operation.

        Args:
            component_id: ID of component reporting completion
            operation: Description of completed operation
            success: Whether operation completed successfully
            result_data: Optional result data from operation
        """
        completion_metadata = {
            "operation": operation,
            "success": success,
            "result_data": result_data or {},
        }

        status_msg = f"{'Completed' if success else 'Failed'}: {operation}"
        level = NotificationLevel.INFO if success else NotificationLevel.ERROR

        # Report as status
        self.report_status(status_msg, component_id, completion_metadata)

        # Also create completion event
        event = NotificationEvent(
            event_id=str(uuid.uuid4()),
            event_type="operation_completion",
            level=level,
            message=f"{component_id}: {status_msg}",
            timestamp=datetime.now(),
            source_component=component_id,
            metadata=completion_metadata,
            channels=[NotificationChannel.LOG, NotificationChannel.CONSOLE],
        )

        self.publish_event(event)

    # ErrorReporter Protocol Implementation

    def report_error(
        self,
        error: Exception,
        component_id: str,
        operation: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Report an error that occurred in a component.

        Args:
            error: Exception that occurred
            component_id: ID of component where error occurred
            operation: Optional operation description where error occurred
            context: Optional contextual information about the error

        Returns:
            Error ID for tracking and correlation
        """
        error_id = str(uuid.uuid4())
        error_record = {
            "error_id": error_id,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "component_id": component_id,
            "operation": operation,
            "context": context or {},
            "timestamp": datetime.now(),
            "acknowledged": False,
            "acknowledged_by": None,
        }

        with self._lock:
            self.stats.total_errors_reported += 1
            self.stats.last_activity = datetime.now()
            self._error_history.append(error_record)

        logger.error(f"Error in {component_id}: {error}", exc_info=error)

        # Create and publish error event
        event = NotificationEvent(
            event_id=error_id,
            event_type="error",
            level=NotificationLevel.ERROR,
            message=f"Error in {component_id}: {error}",
            timestamp=error_record["timestamp"],
            source_component=component_id,
            metadata=error_record,
            channels=[NotificationChannel.LOG, NotificationChannel.CONSOLE],
        )

        self.publish_event(event)
        return error_id

    def report_warning(
        self, message: str, component_id: str, context: dict[str, Any] | None = None
    ) -> str:
        """Report a warning condition.

        Args:
            message: Warning message
            component_id: ID of component issuing warning
            context: Optional contextual information

        Returns:
            Warning ID for tracking
        """
        warning_id = str(uuid.uuid4())
        warning_record = {
            "warning_id": warning_id,
            "message": message,
            "component_id": component_id,
            "context": context or {},
            "timestamp": datetime.now(),
        }

        logger.warning(f"Warning from {component_id}: {message}")

        # Create and publish warning event
        event = NotificationEvent(
            event_id=warning_id,
            event_type="warning",
            level=NotificationLevel.WARNING,
            message=f"Warning from {component_id}: {message}",
            timestamp=warning_record["timestamp"],
            source_component=component_id,
            metadata=warning_record,
            channels=[NotificationChannel.LOG],
        )

        self.publish_event(event)
        return warning_id

    def get_error_history(
        self, component_id: str | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get recent error history.

        Args:
            component_id: Optional filter by component ID
            limit: Maximum number of errors to return

        Returns:
            List of error records with timestamps and details
        """
        with self._lock:
            errors = list(self._error_history)

        if component_id:
            errors = [e for e in errors if e["component_id"] == component_id]

        # Sort by timestamp (most recent first) and limit
        errors.sort(key=lambda x: x["timestamp"], reverse=True)
        return errors[:limit]

    def acknowledge_error(self, error_id: str, acknowledged_by: str) -> bool:
        """Acknowledge that an error has been seen/handled.

        Args:
            error_id: ID of error to acknowledge
            acknowledged_by: Identifier of who acknowledged the error

        Returns:
            True if successfully acknowledged
        """
        with self._lock:
            for error_record in self._error_history:
                if error_record["error_id"] == error_id:
                    error_record["acknowledged"] = True
                    error_record["acknowledged_by"] = acknowledged_by
                    error_record["acknowledged_at"] = datetime.now()
                    logger.info(f"Error {error_id} acknowledged by {acknowledged_by}")
                    return True

        logger.warning(f"Attempted to acknowledge unknown error ID: {error_id}")
        return False

    # MessageBroadcaster Protocol Implementation

    def broadcast_message(
        self,
        message: str,
        channels: list[NotificationChannel],
        level: NotificationLevel = NotificationLevel.INFO,
        metadata: dict[str, Any] | None = None,
    ) -> list[str]:
        """Broadcast a message to multiple channels.

        Args:
            message: Message to broadcast
            channels: List of channels to send message to
            level: Notification level of the message
            metadata: Optional additional message data

        Returns:
            List of delivery IDs for tracking message delivery
        """
        delivery_ids = []

        with self._lock:
            self.stats.total_messages_broadcast += 1
            self.stats.last_activity = datetime.now()

        for channel in channels:
            delivery_id = str(uuid.uuid4())
            delivery_ids.append(delivery_id)

            # Handle different channels
            if channel == NotificationChannel.LOG:
                self._log_message(message, level)
            elif channel == NotificationChannel.CONSOLE:
                self._console_message(message, level)
            # Other channels would be implemented here

            logger.debug(f"Broadcast message to {channel.value}: {message}")

        return delivery_ids

    def send_targeted_message(
        self,
        message: str,
        recipients: list[str],
        channel: NotificationChannel,
        metadata: dict[str, Any] | None = None,
    ) -> list[str]:
        """Send message to specific recipients.

        Args:
            message: Message to send
            recipients: List of recipient identifiers
            channel: Channel to use for delivery
            metadata: Optional message metadata

        Returns:
            List of delivery IDs for tracking
        """
        delivery_ids = []

        for recipient in recipients:
            delivery_id = str(uuid.uuid4())
            delivery_ids.append(delivery_id)

            logger.info(
                f"Targeted message to {recipient} via {channel.value}: {message}"
            )
            # Actual delivery implementation would go here

        return delivery_ids

    def get_delivery_status(self, delivery_ids: list[str]) -> dict[str, str]:
        """Get delivery status for messages.

        Args:
            delivery_ids: List of delivery IDs to check

        Returns:
            Dictionary mapping delivery ID to status (pending, delivered, failed)
        """
        # For now, assume all deliveries are successful
        return dict.fromkeys(delivery_ids, "delivered")

    # Notification Management Methods

    def handle_client_notification(self, notification_data: dict[str, Any]) -> bool:
        """Handle incoming client notifications.

        Args:
            notification_data: Raw notification data from client

        Returns:
            True if handled successfully, False otherwise
        """
        try:
            notification = parse_client_notification(notification_data)

            if isinstance(notification, CancelledNotification):
                with self._lock:
                    self.stats.total_cancelled_notifications += 1

                logger.info(
                    f"Handled cancelled notification for request: {notification.params.requestId}"
                )

                # Create cancellation event
                event = NotificationEvent(
                    event_id=str(uuid.uuid4()),
                    event_type="request_cancelled",
                    level=NotificationLevel.INFO,
                    message=f"Request {notification.params.requestId} was cancelled",
                    timestamp=datetime.now(),
                    source_component="client",
                    metadata={
                        "request_id": notification.params.requestId,
                        "reason": notification.params.reason,
                    },
                    channels=[NotificationChannel.LOG],
                )

                self.publish_event(event)
                return True

        except Exception as e:
            logger.error(f"Failed to handle client notification: {e}")

        return False

    # DebuggableComponent Protocol Implementation

    def get_component_state(self) -> dict[str, Any]:
        """Get current state of the notification operations component."""
        with self._lock:
            subscriptions_info = {
                sub_id: {
                    "subscriber_id": record.subscriber.get_subscriber_id(),
                    "filters": record.filters,
                    "created_at": record.created_at.isoformat(),
                    "last_activity": record.last_activity.isoformat(),
                }
                for sub_id, record in self._subscriptions.items()
            }

        interceptor_stats = self.interceptor.get_stats()

        return {
            "component_id": "notification_operations",
            "status": "operational",
            "statistics": {
                "total_events_published": self.stats.total_events_published,
                "total_messages_broadcast": self.stats.total_messages_broadcast,
                "total_errors_reported": self.stats.total_errors_reported,
                "total_status_updates": self.stats.total_status_updates,
                "total_cancelled_notifications": self.stats.total_cancelled_notifications,
                "active_subscriptions": self.stats.active_subscriptions,
                "intercepted_notifications": interceptor_stats["total_intercepted"],
                "last_activity": self.stats.last_activity.isoformat(),
            },
            "subscriptions": subscriptions_info,
            "channel_configs": {
                channel.value: config
                for channel, config in self._channel_configs.items()
            },
            "event_history_size": len(self._event_history),
            "error_history_size": len(self._error_history),
            "status_history_size": len(self._status_history),
        }

    def validate_component(self) -> dict[str, Any]:
        """Validate component configuration and state."""
        issues = []

        # Check if interceptor is working
        interceptor_stats = self.interceptor.get_stats()
        if interceptor_stats["total_intercepted"] == 0:
            issues.append(
                "No notifications have been intercepted - may indicate setup issue"
            )

        # Check subscription health
        with self._lock:
            stale_subscriptions = [
                sub_id
                for sub_id, record in self._subscriptions.items()
                if (datetime.now() - record.last_activity).seconds > 3600  # 1 hour
            ]

        if stale_subscriptions:
            issues.append(f"Found {len(stale_subscriptions)} stale subscriptions")

        return {
            "is_valid": len(issues) == 0,
            "issues": issues,
            "recommendations": [
                "Monitor subscription activity regularly",
                "Configure channel settings based on deployment environment",
                "Set up proper logging levels for different notification types",
            ],
        }

    def get_debug_info(self, detailed: bool = False) -> dict[str, Any]:
        """Get debug information about the component."""
        debug_info = {
            "component_type": "NotificationOperations",
            "state": self.get_component_state(),
            "validation": self.validate_component(),
        }

        if detailed:
            debug_info.update(
                {
                    "recent_events": [
                        {
                            "event_id": event.event_id,
                            "event_type": event.event_type,
                            "level": event.level.value,
                            "message": event.message,
                            "timestamp": event.timestamp.isoformat(),
                            "source": event.source_component,
                        }
                        for event in list(self._event_history)[-10:]  # Last 10 events
                    ],
                    "recent_errors": self.get_error_history(limit=5),
                    "interceptor_stats": self.interceptor.get_stats(),
                }
            )

        return debug_info

    # Helper Methods

    def _find_matching_subscribers(
        self, event: NotificationEvent
    ) -> list[tuple[str, EventSubscriber]]:
        """Find subscribers that match the given event."""
        matching = []

        with self._lock:
            for sub_id, record in self._subscriptions.items():
                if self._event_matches_filters(event, record.filters):
                    matching.append((sub_id, record.subscriber))

        return matching

    def _event_matches_filters(
        self, event: NotificationEvent, filters: dict[str, Any]
    ) -> bool:
        """Check if an event matches subscription filters."""
        # Simple filter matching - can be enhanced
        if "event_type" in filters:
            if event.event_type not in filters["event_type"]:
                return False

        if "level" in filters:
            if event.level.value not in filters["level"]:
                return False

        if "source_component" in filters:
            if event.source_component not in filters["source_component"]:
                return False

        return True

    def _log_event(self, event: NotificationEvent) -> None:
        """Log an event based on its level."""
        log_message = f"[{event.source_component}] {event.message}"

        if event.level == NotificationLevel.DEBUG:
            logger.debug(log_message)
        elif event.level == NotificationLevel.INFO:
            logger.info(log_message)
        elif event.level == NotificationLevel.WARNING:
            logger.warning(log_message)
        elif event.level == NotificationLevel.ERROR:
            logger.error(log_message)
        elif event.level == NotificationLevel.CRITICAL:
            logger.critical(log_message)

    def _log_message(self, message: str, level: NotificationLevel) -> None:
        """Log a message with appropriate level."""
        if level == NotificationLevel.DEBUG:
            logger.debug(message)
        elif level == NotificationLevel.INFO:
            logger.info(message)
        elif level == NotificationLevel.WARNING:
            logger.warning(message)
        elif level == NotificationLevel.ERROR:
            logger.error(message)
        elif level == NotificationLevel.CRITICAL:
            logger.critical(message)

    def _console_message(self, message: str, level: NotificationLevel) -> None:
        """Output message to console (if appropriate)."""
        if level in [
            NotificationLevel.WARNING,
            NotificationLevel.ERROR,
            NotificationLevel.CRITICAL,
        ]:
            print(f"[{level.value.upper()}] {message}")

    def _report_subscriber_error(
        self, subscription_id: str, error: Exception, event: NotificationEvent
    ) -> None:
        """Report an error that occurred while notifying a subscriber."""
        error_context = {
            "subscription_id": subscription_id,
            "event_id": event.event_id,
            "event_type": event.event_type,
            "subscriber_error": str(error),
        }

        self.report_error(
            error, "notification_operations", "notify_subscriber", error_context
        )
