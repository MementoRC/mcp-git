"""
Notification protocol definitions for event handling and status updates.

This module defines protocols for event notification, status updates, 
error reporting, and message broadcasting throughout the system.
"""

from typing import Protocol, Dict, Any, List, Optional, Union, Callable, AsyncIterator
from abc import abstractmethod
from enum import Enum
from datetime import datetime
from dataclasses import dataclass


class NotificationLevel(Enum):
    """Enumeration of notification severity levels."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class NotificationChannel(Enum):
    """Enumeration of notification delivery channels."""
    LOG = "log"
    CONSOLE = "console"
    WEBHOOK = "webhook"
    EMAIL = "email"
    SLACK = "slack"
    SYSTEM = "system"


@dataclass
class NotificationEvent:
    """Data structure for notification events."""
    event_id: str
    event_type: str
    level: NotificationLevel
    message: str
    timestamp: datetime
    source_component: str
    metadata: Dict[str, Any]
    channels: List[NotificationChannel]


class EventSubscriber(Protocol):
    """Protocol for components that can receive event notifications."""
    
    @abstractmethod
    def handle_event(self, event: NotificationEvent) -> None:
        """
        Handle an incoming notification event.
        
        Args:
            event: NotificationEvent to process
            
        Example:
            >>> subscriber = MyEventSubscriber()
            >>> event = NotificationEvent(...)
            >>> subscriber.handle_event(event)
        """
        ...
    
    @abstractmethod
    def get_subscription_filters(self) -> Dict[str, Any]:
        """
        Get filters for events this subscriber is interested in.
        
        Returns:
            Dictionary with filter criteria (event_type, level, source, etc.)
            
        Example:
            >>> subscriber = MyEventSubscriber()
            >>> filters = subscriber.get_subscription_filters()
            >>> # {"event_type": ["git_operation"], "level": ["ERROR", "CRITICAL"]}
        """
        ...
    
    @abstractmethod
    def get_subscriber_id(self) -> str:
        """Get unique identifier for this subscriber."""
        ...


class EventPublisher(Protocol):
    """Protocol for components that can publish events."""
    
    @abstractmethod
    def publish_event(self, event: NotificationEvent) -> None:
        """
        Publish an event to all interested subscribers.
        
        Args:
            event: NotificationEvent to publish
            
        Example:
            >>> publisher = MyEventPublisher()
            >>> event = NotificationEvent(
            ...     event_id="git_001",
            ...     event_type="git_commit",
            ...     level=NotificationLevel.INFO,
            ...     message="Commit successful",
            ...     timestamp=datetime.now(),
            ...     source_component="git_service",
            ...     metadata={"commit_hash": "abc123"},
            ...     channels=[NotificationChannel.LOG]
            ... )
            >>> publisher.publish_event(event)
        """
        ...
    
    @abstractmethod
    def subscribe(self, subscriber: EventSubscriber) -> str:
        """
        Register a subscriber for events.
        
        Args:
            subscriber: EventSubscriber to register
            
        Returns:
            Subscription ID for later unsubscription
            
        Example:
            >>> publisher = MyEventPublisher()
            >>> subscriber = MyEventSubscriber()
            >>> sub_id = publisher.subscribe(subscriber)
        """
        ...
    
    @abstractmethod
    def unsubscribe(self, subscription_id: str) -> bool:
        """
        Remove a subscriber.
        
        Args:
            subscription_id: ID returned from subscribe()
            
        Returns:
            True if successfully unsubscribed, False otherwise
        """
        ...
    
    @abstractmethod
    def get_active_subscriptions(self) -> List[str]:
        """Get list of active subscription IDs."""
        ...


class StatusReporter(Protocol):
    """Protocol for reporting component status updates."""
    
    @abstractmethod
    def report_status(self, status: str, component_id: str, 
                     metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Report status update for a component.
        
        Args:
            status: Status description
            component_id: ID of component reporting status
            metadata: Optional additional status information
            
        Example:
            >>> reporter = MyStatusReporter()
            >>> reporter.report_status(
            ...     "Processing request", 
            ...     "git_handler",
            ...     {"progress": 0.5, "eta": "30s"}
            ... )
        """
        ...
    
    @abstractmethod
    def report_progress(self, progress: float, component_id: str,
                       operation: str, details: Optional[str] = None) -> None:
        """
        Report progress update for a long-running operation.
        
        Args:
            progress: Progress as float between 0.0 and 1.0
            component_id: ID of component reporting progress
            operation: Description of operation in progress
            details: Optional additional progress details
            
        Example:
            >>> reporter = MyStatusReporter()
            >>> reporter.report_progress(0.75, "clone_handler", "Cloning repository", "Receiving objects")
        """
        ...
    
    @abstractmethod
    def report_completion(self, component_id: str, operation: str,
                         success: bool, result_data: Optional[Dict[str, Any]] = None) -> None:
        """
        Report completion of an operation.
        
        Args:
            component_id: ID of component reporting completion
            operation: Description of completed operation
            success: Whether operation completed successfully
            result_data: Optional result data from operation
            
        Example:
            >>> reporter = MyStatusReporter()
            >>> reporter.report_completion(
            ...     "git_clone", "Repository clone", True, 
            ...     {"commit_count": 150, "size_mb": 45.2}
            ... )
        """
        ...


class ErrorReporter(Protocol):
    """Protocol for reporting and handling errors."""
    
    @abstractmethod
    def report_error(self, error: Exception, component_id: str,
                    operation: Optional[str] = None, 
                    context: Optional[Dict[str, Any]] = None) -> str:
        """
        Report an error that occurred in a component.
        
        Args:
            error: Exception that occurred
            component_id: ID of component where error occurred
            operation: Optional operation description where error occurred
            context: Optional contextual information about the error
            
        Returns:
            Error ID for tracking and correlation
            
        Example:
            >>> reporter = MyErrorReporter()
            >>> error_id = reporter.report_error(
            ...     ValueError("Invalid repository path"),
            ...     "git_validator",
            ...     "validate_path",
            ...     {"path": "/invalid/path", "user": "test"}
            ... )
        """
        ...
    
    @abstractmethod
    def report_warning(self, message: str, component_id: str,
                      context: Optional[Dict[str, Any]] = None) -> str:
        """
        Report a warning condition.
        
        Args:
            message: Warning message
            component_id: ID of component issuing warning
            context: Optional contextual information
            
        Returns:
            Warning ID for tracking
        """
        ...
    
    @abstractmethod
    def get_error_history(self, component_id: Optional[str] = None,
                         limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent error history.
        
        Args:
            component_id: Optional filter by component ID
            limit: Maximum number of errors to return
            
        Returns:
            List of error records with timestamps and details
        """
        ...
    
    @abstractmethod
    def acknowledge_error(self, error_id: str, acknowledged_by: str) -> bool:
        """
        Acknowledge that an error has been seen/handled.
        
        Args:
            error_id: ID of error to acknowledge
            acknowledged_by: Identifier of who acknowledged the error
            
        Returns:
            True if successfully acknowledged
        """
        ...


class MessageBroadcaster(Protocol):
    """Protocol for broadcasting messages to multiple recipients."""
    
    @abstractmethod
    def broadcast_message(self, message: str, channels: List[NotificationChannel],
                         level: NotificationLevel = NotificationLevel.INFO,
                         metadata: Optional[Dict[str, Any]] = None) -> List[str]:
        """
        Broadcast a message to multiple channels.
        
        Args:
            message: Message to broadcast
            channels: List of channels to send message to
            level: Notification level of the message
            metadata: Optional additional message data
            
        Returns:
            List of delivery IDs for tracking message delivery
            
        Example:
            >>> broadcaster = MyMessageBroadcaster()
            >>> delivery_ids = broadcaster.broadcast_message(
            ...     "System maintenance starting",
            ...     [NotificationChannel.CONSOLE, NotificationChannel.LOG],
            ...     NotificationLevel.WARNING
            ... )
        """
        ...
    
    @abstractmethod
    def send_targeted_message(self, message: str, recipients: List[str],
                             channel: NotificationChannel,
                             metadata: Optional[Dict[str, Any]] = None) -> List[str]:
        """
        Send message to specific recipients.
        
        Args:
            message: Message to send
            recipients: List of recipient identifiers
            channel: Channel to use for delivery
            metadata: Optional message metadata
            
        Returns:
            List of delivery IDs for tracking
        """
        ...
    
    @abstractmethod
    def get_delivery_status(self, delivery_ids: List[str]) -> Dict[str, str]:
        """
        Get delivery status for messages.
        
        Args:
            delivery_ids: List of delivery IDs to check
            
        Returns:
            Dictionary mapping delivery ID to status (pending, delivered, failed)
        """
        ...


class NotificationSystem(Protocol):
    """
    Comprehensive notification system protocol.
    
    This protocol combines all notification capabilities into a unified interface
    for components that need full notification functionality.
    """
    
    # Composition of all notification sub-protocols
    event_publisher: EventPublisher
    status_reporter: StatusReporter
    error_reporter: ErrorReporter
    message_broadcaster: MessageBroadcaster
    
    @abstractmethod
    def initialize_notifications(self, config: Dict[str, Any]) -> None:
        """
        Initialize the notification system with configuration.
        
        Args:
            config: Configuration dictionary with channel settings, etc.
            
        Example:
            >>> notification_system = MyNotificationSystem()
            >>> config = {
            ...     "channels": {
            ...         "webhook": {"url": "https://api.example.com/webhook"},
            ...         "email": {"smtp_server": "smtp.example.com"}
            ...     },
            ...     "default_level": "INFO"
            ... }
            >>> notification_system.initialize_notifications(config)
        """
        ...
    
    @abstractmethod
    def shutdown_notifications(self) -> None:
        """Gracefully shutdown the notification system."""
        ...
    
    @abstractmethod
    def get_notification_stats(self) -> Dict[str, Union[int, float]]:
        """
        Get statistics about notification system usage.
        
        Returns:
            Dictionary with stats like message count, error rate, etc.
            
        Example:
            >>> notification_system = MyNotificationSystem()
            >>> stats = notification_system.get_notification_stats()
            >>> print(f"Messages sent: {stats['total_messages']}")
            >>> print(f"Error rate: {stats['error_rate']:.2%}")
        """
        ...
    
    @abstractmethod
    def health_check_notifications(self) -> Dict[str, Union[bool, str]]:
        """
        Perform health check on notification system.
        
        Returns:
            Dictionary with health status of notification channels
        """
        ...


class AsyncNotificationSystem(Protocol):
    """Protocol for asynchronous notification operations."""
    
    @abstractmethod
    async def publish_event_async(self, event: NotificationEvent) -> None:
        """Async version of publish_event."""
        ...
    
    @abstractmethod
    async def broadcast_message_async(self, message: str, 
                                    channels: List[NotificationChannel]) -> List[str]:
        """Async version of broadcast_message."""
        ...
    
    @abstractmethod
    async def notification_stream(self, filters: Optional[Dict[str, Any]] = None) -> AsyncIterator[NotificationEvent]:
        """
        Stream notifications matching filters.
        
        Args:
            filters: Optional filters for event types, levels, etc.
            
        Yields:
            NotificationEvent objects as they occur
            
        Example:
            >>> async for event in notification_system.notification_stream({"level": ["ERROR"]}):
            ...     print(f"Error: {event.message}")
        """
        ...


class NotificationFilter(Protocol):
    """Protocol for filtering notification events."""
    
    @abstractmethod
    def should_process_event(self, event: NotificationEvent) -> bool:
        """
        Determine if an event should be processed based on filters.
        
        Args:
            event: NotificationEvent to evaluate
            
        Returns:
            True if event should be processed, False otherwise
        """
        ...
    
    @abstractmethod
    def apply_rate_limiting(self, event: NotificationEvent) -> bool:
        """
        Apply rate limiting to prevent notification spam.
        
        Args:
            event: NotificationEvent to check for rate limiting
            
        Returns:
            True if event is within rate limits, False if should be throttled
        """
        ...
    
    @abstractmethod
    def transform_event(self, event: NotificationEvent) -> NotificationEvent:
        """
        Transform an event before delivery (e.g., redact sensitive data).
        
        Args:
            event: Original NotificationEvent
            
        Returns:
            Transformed NotificationEvent
        """
        ...