from abc import abstractmethod
from typing import Protocol, Dict, Any, Optional


class MetricsProtocol(Protocol):
    """
    Protocol defining the interface for collecting and reporting application metrics.

    This protocol provides methods for tracking performance, operation outcomes,
    and resource usage.
    """

    @abstractmethod
    async def record_timing(self, operation_name: str, duration_seconds: float, tags: Optional[Dict[str, str]] = None) -> None:
        """
        Asynchronously records the duration of an operation.

        Args:
            operation_name: A string identifying the operation (e.g., "git.clone", "api.request").
            duration_seconds: The duration of the operation in seconds.
            tags: Optional. A dictionary of key-value pairs for additional context (e.g., {"repo": "my_repo"}).
        """
        ...

    @abstractmethod
    async def increment_counter(self, metric_name: str, value: int = 1, tags: Optional[Dict[str, str]] = None) -> None:
        """
        Asynchronously increments a counter metric.

        Args:
            metric_name: The name of the counter metric (e.g., "git.commits_total", "errors.count").
            value: The amount to increment the counter by (default is 1).
            tags: Optional. A dictionary of key-value pairs for additional context.
        """
        ...

    @abstractmethod
    async def set_gauge(self, metric_name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """
        Asynchronously sets the value of a gauge metric.

        Gauges represent a single numerical value that can go up or down.

        Args:
            metric_name: The name of the gauge metric (e.g., "memory.usage_mb", "active_connections").
            value: The current value of the gauge.
            tags: Optional. A dictionary of key-value pairs for additional context.
        """
        ...

    @abstractmethod
    async def track_success(self, operation_name: str, tags: Optional[Dict[str, str]] = None) -> None:
        """
        Asynchronously tracks the successful completion of an operation.

        This can be used to increment a success counter or record a success event.

        Args:
            operation_name: The name of the operation that succeeded.
            tags: Optional. A dictionary of key-value pairs for additional context.
        """
        ...

    @abstractmethod
    async def track_failure(self, operation_name: str, error_type: str, tags: Optional[Dict[str, str]] = None) -> None:
        """
        Asynchronously tracks the failure of an operation.

        This can be used to increment a failure counter or record a failure event.

        Args:
            operation_name: The name of the operation that failed.
            error_type: A string categorizing the type of error (e.g., "ValidationError", "NetworkError").
            tags: Optional. A dictionary of key-value pairs for additional context.
        """
        ...

    @abstractmethod
    async def record_resource_usage(self, resource_type: str, value: float, unit: str, tags: Optional[Dict[str, str]] = None) -> None:
        """
        Asynchronously records the usage of a specific resource.

        Args:
            resource_type: The type of resource being monitored (e.g., "cpu", "memory", "disk_io").
            value: The numerical value of the resource usage.
            unit: The unit of measurement for the value (e.g., "percent", "MB", "ops/sec").
            tags: Optional. A dictionary of key-value pairs for additional context.
        """
        ...
