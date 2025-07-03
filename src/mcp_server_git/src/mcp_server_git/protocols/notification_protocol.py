from abc import abstractmethod
from typing import Protocol, Any, Dict, Optional


class NotificationProtocol(Protocol):
    """
    Protocol defining the interface for handling various types of notifications.

    This protocol provides methods for sending event notifications,
    status updates, error reports, and broadcasting general messages.
    """

    @abstractmethod
    async def notify_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """
        Asynchronously sends a specific event notification.

        Args:
            event_type: A string identifying the type of event (e.g., "repo_cloned", "commit_successful").
            payload: A dictionary containing event-specific data.
        """
        ...

    @abstractmethod
    async def update_status(self, status_message: str, progress: Optional[float] = None) -> None:
        """
        Asynchronously provides a status update, potentially with a progress indicator.

        Args:
            status_message: A descriptive message about the current status.
            progress: Optional. A float between 0.0 and 1.0 indicating progress.
        """
        ...

    @abstractmethod
    async def report_error(self, error_message: str, details: Optional[Dict[str, Any]] = None) -> None:
        """
        Asynchronously reports an error that occurred.

        Args:
            error_message: A concise description of the error.
            details: Optional. A dictionary containing additional context or traceback information.
        """
        ...

    @abstractmethod
    async def broadcast_message(self, message: str, topic: Optional[str] = None) -> None:
        """
        Asynchronously broadcasts a general message to all interested listeners.

        Args:
            message: The message content to broadcast.
            topic: Optional. A topic or category for the message, allowing listeners to filter.
        """
        ...
