"""Server metrics and monitoring service for MCP Git server.

This module provides comprehensive metrics collection and monitoring capabilities
for the MCP Git server, including performance tracking, usage statistics, and
health monitoring.
"""

import asyncio
import json
import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import Lock
from typing import Any

from mcp_server_git.protocols.debugging_protocol import (
    DebuggableComponent,
)


@dataclass
class ComponentState:
    """Component state information for debugging."""

    name: str
    status: str
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Component validation result."""

    is_valid: bool
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    component_name: str = ""


@dataclass
class MetricPoint:
    """A single metric data point."""

    name: str
    value: float
    timestamp: datetime
    labels: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "value": self.value,
            "timestamp": self.timestamp.isoformat(),
            "labels": self.labels,
        }


@dataclass
class PerformanceMetrics:
    """Performance tracking metrics."""

    operation_count: int = 0
    total_duration: float = 0.0
    min_duration: float = float("inf")
    max_duration: float = 0.0
    error_count: int = 0
    last_operation_time: datetime | None = None

    @property
    def average_duration(self) -> float:
        """Calculate average operation duration."""
        return (
            self.total_duration / self.operation_count
            if self.operation_count > 0
            else 0.0
        )

    @property
    def success_rate(self) -> float:
        """Calculate operation success rate."""
        return (
            (self.operation_count - self.error_count) / self.operation_count
            if self.operation_count > 0
            else 1.0
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "operation_count": self.operation_count,
            "total_duration": self.total_duration,
            "min_duration": self.min_duration
            if self.min_duration != float("inf")
            else 0.0,
            "max_duration": self.max_duration,
            "average_duration": self.average_duration,
            "error_count": self.error_count,
            "success_rate": self.success_rate,
            "last_operation_time": (
                self.last_operation_time.isoformat()
                if self.last_operation_time
                else None
            ),
        }


@dataclass
class SystemHealthMetrics:
    """System health monitoring metrics."""

    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    disk_usage: float = 0.0
    active_connections: int = 0
    request_queue_size: int = 0
    last_health_check: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "cpu_usage": self.cpu_usage,
            "memory_usage": self.memory_usage,
            "disk_usage": self.disk_usage,
            "active_connections": self.active_connections,
            "request_queue_size": self.request_queue_size,
            "last_health_check": (
                self.last_health_check.isoformat() if self.last_health_check else None
            ),
        }


class MetricsService(DebuggableComponent):
    """Comprehensive metrics collection and monitoring service.

    Provides performance tracking, usage statistics, and health monitoring
    for the MCP Git server with thread-safe operations and configurable
    retention policies.
    """

    def __init__(
        self,
        max_metric_history: int = 10000,
        health_check_interval: float = 60.0,
        enable_system_metrics: bool = True,
    ):
        """Initialize the metrics service.

        Args:
            max_metric_history: Maximum number of metric points to retain
            health_check_interval: Interval for system health checks in seconds
            enable_system_metrics: Whether to collect system-level metrics
        """
        self._max_metric_history = max_metric_history
        self._health_check_interval = health_check_interval
        self._enable_system_metrics = enable_system_metrics

        # Thread-safe metric storage
        self._metrics_lock = Lock()
        self._metric_points: deque[MetricPoint] = deque(maxlen=max_metric_history)
        self._performance_metrics: dict[str, PerformanceMetrics] = defaultdict(
            PerformanceMetrics
        )
        self._system_health = SystemHealthMetrics()

        # Service state
        self._is_running = False
        self._health_check_task: asyncio.Task | None = None
        self._start_time = datetime.now()

        # Logger
        self._logger = logging.getLogger(__name__)

    async def start(self) -> None:
        """Start the metrics service."""
        if self._is_running:
            self._logger.warning("Metrics service already running")
            return

        self._is_running = True
        self._start_time = datetime.now()

        # Start health monitoring if system metrics enabled
        if self._enable_system_metrics:
            self._health_check_task = asyncio.create_task(self._health_check_loop())

        self._logger.info("Metrics service started")

    async def stop(self) -> None:
        """Stop the metrics service."""
        if not self._is_running:
            return

        self._is_running = False

        # Cancel health check task
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        self._logger.info("Metrics service stopped")

    def record_metric(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Record a custom metric point.

        Args:
            name: Metric name
            value: Metric value
            labels: Optional metric labels
        """
        metric_point = MetricPoint(
            name=name,
            value=value,
            timestamp=datetime.now(),
            labels=labels or {},
        )

        with self._metrics_lock:
            self._metric_points.append(metric_point)

    def record_operation(
        self,
        operation_name: str,
        duration: float,
        success: bool = True,
    ) -> None:
        """Record an operation performance metric.

        Args:
            operation_name: Name of the operation
            duration: Operation duration in seconds
            success: Whether the operation succeeded
        """
        with self._metrics_lock:
            metrics = self._performance_metrics[operation_name]
            metrics.operation_count += 1
            metrics.total_duration += duration
            metrics.min_duration = min(metrics.min_duration, duration)
            metrics.max_duration = max(metrics.max_duration, duration)
            metrics.last_operation_time = datetime.now()

            if not success:
                metrics.error_count += 1

        # Record as metric point
        self.record_metric(
            f"operation.{operation_name}.duration",
            duration,
            {"success": str(success)},
        )

    def get_metrics_summary(self) -> dict[str, Any]:
        """Get a summary of all metrics."""
        with self._metrics_lock:
            # Performance metrics summary
            perf_summary = {}
            for operation, metrics in self._performance_metrics.items():
                perf_summary[operation] = metrics.to_dict()

            # Recent metric points (last 100)
            recent_metrics = []
            for metric in list(self._metric_points)[-100:]:
                recent_metrics.append(metric.to_dict())

            return {
                "service_uptime": (datetime.now() - self._start_time).total_seconds(),
                "total_metric_points": len(self._metric_points),
                "performance_metrics": perf_summary,
                "system_health": self._system_health.to_dict(),
                "recent_metrics": recent_metrics,
                "is_running": self._is_running,
            }

    def get_operation_metrics(self, operation_name: str) -> dict[str, Any] | None:
        """Get metrics for a specific operation."""
        with self._metrics_lock:
            if operation_name in self._performance_metrics:
                return self._performance_metrics[operation_name].to_dict()
            return None

    def clear_metrics(self) -> None:
        """Clear all stored metrics."""
        with self._metrics_lock:
            self._metric_points.clear()
            self._performance_metrics.clear()
            self._system_health = SystemHealthMetrics()

        self._logger.info("All metrics cleared")

    async def _health_check_loop(self) -> None:
        """Background health monitoring loop."""
        while self._is_running:
            try:
                await self._collect_system_health()
                await asyncio.sleep(self._health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Health check failed: {e}")
                await asyncio.sleep(self._health_check_interval)

    async def _collect_system_health(self) -> None:
        """Collect system health metrics."""
        try:
            import psutil

            # CPU and memory usage
            self._system_health.cpu_usage = psutil.cpu_percent(interval=1)
            self._system_health.memory_usage = psutil.virtual_memory().percent
            self._system_health.disk_usage = psutil.disk_usage("/").percent
            self._system_health.last_health_check = datetime.now()

            # Record as metric points
            self.record_metric("system.cpu_usage", self._system_health.cpu_usage)
            self.record_metric("system.memory_usage", self._system_health.memory_usage)
            self.record_metric("system.disk_usage", self._system_health.disk_usage)

        except ImportError:
            # psutil not available, use basic metrics
            self._system_health.last_health_check = datetime.now()
        except Exception as e:
            self._logger.error(f"Failed to collect system health: {e}")

    # DebuggableComponent implementation

    def get_component_state(self) -> ComponentState:
        """Get the current component state."""
        with self._metrics_lock:
            status = "HEALTHY" if self._is_running else "STOPPED"

            return ComponentState(
                name="MetricsService",
                status=status,
                timestamp=datetime.now(),
                metadata={
                    "is_running": self._is_running,
                    "uptime_seconds": (
                        datetime.now() - self._start_time
                    ).total_seconds(),
                    "total_metrics": len(self._metric_points),
                    "tracked_operations": len(self._performance_metrics),
                    "system_metrics_enabled": self._enable_system_metrics,
                },
                details={
                    "performance_metrics": {
                        op: metrics.to_dict()
                        for op, metrics in self._performance_metrics.items()
                    },
                    "system_health": self._system_health.to_dict(),
                },
            )

    def validate_component(self) -> ValidationResult:
        """Validate component state and configuration."""
        issues = []

        # Check if service is running
        if not self._is_running:
            issues.append("Metrics service is not running")

        # Check metric collection health
        with self._metrics_lock:
            if len(self._metric_points) >= self._max_metric_history * 0.9:
                issues.append("Metric storage approaching capacity")

        # Check system health if enabled
        if self._enable_system_metrics:
            if self._system_health.last_health_check:
                time_since_check = (
                    datetime.now() - self._system_health.last_health_check
                )
                if time_since_check > timedelta(
                    seconds=self._health_check_interval * 2
                ):
                    issues.append("System health checks are stale")

        return ValidationResult(
            is_valid=len(issues) == 0,
            issues=issues,
            warnings=[],
            component_name="MetricsService",
        )

    def get_debug_info(self, debug_level: str = "INFO") -> dict[str, Any]:
        """Get debug information about the metrics service."""
        debug_info = {
            "component_type": "MetricsService",
            "is_running": self._is_running,
            "configuration": {
                "max_metric_history": self._max_metric_history,
                "health_check_interval": self._health_check_interval,
                "enable_system_metrics": self._enable_system_metrics,
            },
        }

        if debug_level in ["DEBUG", "detailed"]:
            debug_info.update(self.get_metrics_summary())

        return debug_info

    def inspect_state(self, path: str | None = None) -> dict[str, Any]:
        """Inspect specific parts of the component state."""
        full_state = {
            "service_config": {
                "max_metric_history": self._max_metric_history,
                "health_check_interval": self._health_check_interval,
                "enable_system_metrics": self._enable_system_metrics,
            },
            "runtime_state": {
                "is_running": self._is_running,
                "start_time": self._start_time.isoformat(),
                "uptime_seconds": (datetime.now() - self._start_time).total_seconds(),
            },
            "metrics_data": self.get_metrics_summary(),
        }

        if path is None:
            return full_state

        # Simple path navigation (e.g., "service_config.max_metric_history")
        parts = path.split(".")
        current = full_state
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return {}

        return {path: current} if not isinstance(current, dict) else current

    def get_component_dependencies(self) -> list[str]:
        """Get list of component dependencies."""
        # MetricsService has minimal dependencies
        dependencies = []
        if self._enable_system_metrics:
            dependencies.append("psutil")  # Optional system dependency
        return dependencies

    def export_state_json(self) -> str:
        """Export component state as JSON for external analysis."""
        state = {
            "component_type": "MetricsService",
            "timestamp": datetime.now().isoformat(),
            "state": self.inspect_state(),
            "health": self.health_check(),
        }

        return json.dumps(state, indent=2, default=str)

    def health_check(self) -> dict[str, bool | str | int | float | None]:
        """Perform a health check on the component."""
        current_time = datetime.now()
        uptime = (current_time - self._start_time).total_seconds()

        # Check for any health issues
        healthy = True
        status = "healthy"
        error_count = 0
        last_error = None

        if not self._is_running:
            healthy = False
            status = "stopped"

        # Check metric storage capacity
        with self._metrics_lock:
            storage_usage = len(self._metric_points) / self._max_metric_history
            if storage_usage > 0.9:
                healthy = False
                status = "storage_full"
                error_count += 1
                last_error = f"Metric storage {storage_usage:.1%} full"

        # Check health check staleness
        if self._enable_system_metrics and self._system_health.last_health_check:
            time_since_check = current_time - self._system_health.last_health_check
            if time_since_check > timedelta(seconds=self._health_check_interval * 2):
                healthy = False
                status = "stale_health_checks"
                error_count += 1
                last_error = (
                    f"Health checks stale by {time_since_check.total_seconds():.1f}s"
                )

        return {
            "healthy": healthy,
            "status": status,
            "uptime": uptime,
            "last_error": last_error,
            "error_count": error_count,
            "storage_usage": storage_usage if "storage_usage" in locals() else 0.0,
            "system_metrics_enabled": self._enable_system_metrics,
        }
