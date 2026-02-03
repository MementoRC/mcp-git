"""Performance profiling utilities for comprehensive performance monitoring and analysis.

This module provides tools for measuring, tracking, and analyzing performance
metrics across components and operations with LLM-friendly reporting.
"""

import functools
import statistics
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import psutil


@dataclass
class PerformanceMetric:
    """A single performance measurement."""

    metric_name: str
    value: float
    unit: str
    timestamp: datetime
    operation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "metric_name": self.metric_name,
            "value": self.value,
            "unit": self.unit,
            "timestamp": self.timestamp.isoformat(),
            "operation_id": self.operation_id,
            "metadata": self.metadata,
        }


@dataclass
class OperationProfile:
    """Performance profile for a specific operation."""

    operation_name: str
    total_calls: int
    total_duration: float
    min_duration: float
    max_duration: float
    avg_duration: float
    last_call_time: datetime
    durations: list[float] = field(default_factory=list)
    errors: int = 0

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_calls == 0:
            return 100.0
        return ((self.total_calls - self.errors) / self.total_calls) * 100.0

    @property
    def calls_per_second(self) -> float:
        """Calculate average calls per second."""
        if self.total_duration == 0:
            return 0.0
        return self.total_calls / self.total_duration

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "operation_name": self.operation_name,
            "total_calls": self.total_calls,
            "total_duration": self.total_duration,
            "min_duration": self.min_duration,
            "max_duration": self.max_duration,
            "avg_duration": self.avg_duration,
            "last_call_time": self.last_call_time.isoformat(),
            "errors": self.errors,
            "success_rate": self.success_rate,
            "calls_per_second": self.calls_per_second,
            "duration_stats": {
                "median": statistics.median(self.durations) if self.durations else 0.0,
                "std_dev": statistics.stdev(self.durations)
                if len(self.durations) > 1
                else 0.0,
                "percentile_95": statistics.quantiles(self.durations, n=20)[18]
                if len(self.durations) >= 20
                else (self.max_duration if self.durations else 0.0),
            },
        }


@dataclass
class ResourceSnapshot:
    """Snapshot of system resource usage."""

    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_available_mb: float
    disk_io_read_mb: float
    disk_io_write_mb: float
    network_sent_mb: float
    network_recv_mb: float
    open_files: int
    threads: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "memory_available_mb": self.memory_available_mb,
            "disk_io_read_mb": self.disk_io_read_mb,
            "disk_io_write_mb": self.disk_io_write_mb,
            "network_sent_mb": self.network_sent_mb,
            "network_recv_mb": self.network_recv_mb,
            "open_files": self.open_files,
            "threads": self.threads,
        }


class PerformanceProfiler:
    """Comprehensive performance profiler with operation tracking and resource monitoring.

    This class provides tools for measuring operation performance, tracking resource
    usage, and generating detailed performance reports optimized for LLM analysis.
    """

    def __init__(
        self,
        max_history_per_operation: int = 1000,
        enable_resource_monitoring: bool = True,
    ):
        """Initialize the performance profiler.

        Args:
            max_history_per_operation: Maximum number of performance measurements to keep per operation
            enable_resource_monitoring: Whether to enable system resource monitoring
        """
        self._lock = threading.RLock()
        self._operation_profiles: dict[str, OperationProfile] = {}
        self._metrics_history: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=max_history_per_operation)
        )
        self._resource_snapshots: deque = deque(maxlen=max_history_per_operation)
        self._active_operations: dict[str, dict[str, Any]] = {}
        self._enable_resource_monitoring = enable_resource_monitoring
        self._start_time = datetime.now()

        # Initialize process handle for resource monitoring
        if self._enable_resource_monitoring:
            try:
                self._process = psutil.Process()
                self._initial_io = self._process.io_counters()
                self._initial_net = psutil.net_io_counters()
            except (psutil.AccessDenied, psutil.NoSuchProcess, AttributeError):
                self._enable_resource_monitoring = False
                self._process = None
                self._initial_io = None
                self._initial_net = None

    def capture_resource_snapshot(self) -> ResourceSnapshot | None:
        """Capture current system resource usage."""
        if not self._enable_resource_monitoring or not self._process:
            return None

        try:
            # CPU and memory
            cpu_percent = self._process.cpu_percent()
            self._process.memory_info()
            memory_percent = self._process.memory_percent()

            # System memory
            sys_memory = psutil.virtual_memory()
            memory_available_mb = sys_memory.available / (1024 * 1024)

            # Disk I/O
            current_io = self._process.io_counters()
            if self._initial_io is not None:
                disk_read_mb = (current_io.read_bytes - self._initial_io.read_bytes) / (
                    1024 * 1024
                )
                disk_write_mb = (
                    current_io.write_bytes - self._initial_io.write_bytes
                ) / (1024 * 1024)
            else:
                disk_read_mb = 0.0
                disk_write_mb = 0.0

            # Network I/O
            current_net = psutil.net_io_counters()
            if self._initial_net and current_net:
                net_sent_mb = (
                    current_net.bytes_sent - self._initial_net.bytes_sent
                ) / (1024 * 1024)
                net_recv_mb = (
                    current_net.bytes_recv - self._initial_net.bytes_recv
                ) / (1024 * 1024)
            else:
                net_sent_mb = net_recv_mb = 0.0

            # Process stats
            open_files = len(self._process.open_files())
            threads = self._process.num_threads()

            snapshot = ResourceSnapshot(
                timestamp=datetime.now(),
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                memory_available_mb=memory_available_mb,
                disk_io_read_mb=disk_read_mb,
                disk_io_write_mb=disk_write_mb,
                network_sent_mb=net_sent_mb,
                network_recv_mb=net_recv_mb,
                open_files=open_files,
                threads=threads,
            )

            with self._lock:
                self._resource_snapshots.append(snapshot)

            return snapshot

        except (psutil.AccessDenied, psutil.NoSuchProcess, AttributeError):
            return None

    @contextmanager
    def profile_operation(
        self, operation_name: str, operation_id: str | None = None
    ) -> Iterator[dict[str, Any]]:
        """Context manager for profiling an operation.

        Args:
            operation_name: Name of the operation to profile
            operation_id: Optional unique identifier for this operation instance

        Yields:
            Dictionary containing operation metadata that can be updated during execution
        """
        start_time = time.perf_counter()
        start_datetime = datetime.now()
        op_id = operation_id or f"{operation_name}_{int(time.time() * 1000)}"

        # Capture initial resource snapshot
        initial_resources = self.capture_resource_snapshot()

        # Track active operation
        operation_metadata = {
            "operation_id": op_id,
            "operation_name": operation_name,
            "start_time": start_datetime,
            "initial_resources": initial_resources,
        }

        with self._lock:
            self._active_operations[op_id] = operation_metadata

        error_occurred = False
        try:
            yield operation_metadata
        except Exception as e:
            error_occurred = True
            operation_metadata["error"] = str(e)
            operation_metadata["error_type"] = type(e).__name__
            raise
        finally:
            end_time = time.perf_counter()
            end_datetime = datetime.now()
            duration = end_time - start_time

            # Capture final resource snapshot
            final_resources = self.capture_resource_snapshot()

            # Update operation metadata
            operation_metadata.update(
                {
                    "end_time": end_datetime,
                    "duration": duration,
                    "final_resources": final_resources,
                    "error_occurred": error_occurred,
                }
            )

            # Record the operation
            self._record_operation(
                operation_name, duration, error_occurred, operation_metadata
            )

            # Remove from active operations
            with self._lock:
                self._active_operations.pop(op_id, None)

    def _record_operation(
        self,
        operation_name: str,
        duration: float,
        error_occurred: bool,
        metadata: dict[str, Any],
    ) -> None:
        """Record an operation's performance metrics."""
        with self._lock:
            # Update or create operation profile
            if operation_name in self._operation_profiles:
                profile = self._operation_profiles[operation_name]
                profile.total_calls += 1
                profile.total_duration += duration
                profile.min_duration = min(profile.min_duration, duration)
                profile.max_duration = max(profile.max_duration, duration)
                profile.durations.append(duration)
                profile.last_call_time = datetime.now()

                if error_occurred:
                    profile.errors += 1

                # Recalculate average
                profile.avg_duration = profile.total_duration / profile.total_calls

                # Limit duration history
                if len(profile.durations) > 1000:
                    profile.durations.pop(0)
            else:
                profile = OperationProfile(
                    operation_name=operation_name,
                    total_calls=1,
                    total_duration=duration,
                    min_duration=duration,
                    max_duration=duration,
                    avg_duration=duration,
                    last_call_time=datetime.now(),
                    durations=[duration],
                    errors=1 if error_occurred else 0,
                )
                self._operation_profiles[operation_name] = profile

            # Record individual metric
            metric = PerformanceMetric(
                metric_name=f"{operation_name}_duration",
                value=duration,
                unit="seconds",
                timestamp=datetime.now(),
                operation_id=metadata.get("operation_id"),
                metadata=metadata,
            )

            self._metrics_history[operation_name].append(metric)

    def record_custom_metric(
        self,
        metric_name: str,
        value: float,
        unit: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a custom performance metric.

        Args:
            metric_name: Name of the metric
            value: Metric value
            unit: Unit of measurement
            metadata: Optional additional metadata
        """
        metric = PerformanceMetric(
            metric_name=metric_name,
            value=value,
            unit=unit,
            timestamp=datetime.now(),
            metadata=metadata or {},
        )

        with self._lock:
            self._metrics_history[metric_name].append(metric)

    def get_operation_profile(self, operation_name: str) -> OperationProfile | None:
        """Get performance profile for a specific operation."""
        with self._lock:
            return self._operation_profiles.get(operation_name)

    def get_all_operation_profiles(self) -> dict[str, OperationProfile]:
        """Get all operation profiles."""
        with self._lock:
            return dict(self._operation_profiles)

    def get_active_operations(self) -> dict[str, dict[str, Any]]:
        """Get currently active operations."""
        with self._lock:
            return dict(self._active_operations)

    def get_resource_history(self, limit: int | None = None) -> list[ResourceSnapshot]:
        """Get resource usage history."""
        with self._lock:
            snapshots = list(self._resource_snapshots)
            if limit:
                snapshots = snapshots[-limit:]
            return snapshots

    def get_performance_summary(self) -> dict[str, Any]:
        """Get comprehensive performance summary."""
        with self._lock:
            current_time = datetime.now()
            uptime_seconds = (current_time - self._start_time).total_seconds()

            # Operation statistics
            total_operations = sum(
                profile.total_calls for profile in self._operation_profiles.values()
            )
            total_errors = sum(
                profile.errors for profile in self._operation_profiles.values()
            )

            # Resource statistics
            resource_snapshots = list(self._resource_snapshots)
            current_resources = self.capture_resource_snapshot()

            avg_cpu = 0.0
            avg_memory = 0.0
            if resource_snapshots:
                avg_cpu = statistics.mean(
                    snap.cpu_percent for snap in resource_snapshots
                )
                avg_memory = statistics.mean(
                    snap.memory_percent for snap in resource_snapshots
                )

            # Top operations by call count and duration
            operations_by_calls = sorted(
                self._operation_profiles.values(),
                key=lambda x: x.total_calls,
                reverse=True,
            )[:5]

            operations_by_duration = sorted(
                self._operation_profiles.values(),
                key=lambda x: x.total_duration,
                reverse=True,
            )[:5]

            return {
                "summary_timestamp": current_time.isoformat(),
                "uptime_seconds": uptime_seconds,
                "total_operations": total_operations,
                "total_errors": total_errors,
                "error_rate": (total_errors / total_operations * 100)
                if total_operations > 0
                else 0.0,
                "operations_per_second": total_operations / uptime_seconds
                if uptime_seconds > 0
                else 0.0,
                "unique_operation_types": len(self._operation_profiles),
                "active_operations_count": len(self._active_operations),
                "resource_monitoring_enabled": self._enable_resource_monitoring,
                "current_resources": current_resources.to_dict()
                if current_resources
                else None,
                "average_cpu_percent": avg_cpu,
                "average_memory_percent": avg_memory,
                "top_operations_by_calls": [op.to_dict() for op in operations_by_calls],
                "top_operations_by_duration": [
                    op.to_dict() for op in operations_by_duration
                ],
            }

    def generate_performance_report(
        self, include_detailed_history: bool = False
    ) -> str:
        """Generate a comprehensive performance report optimized for LLM analysis.

        Args:
            include_detailed_history: Whether to include detailed metric history

        Returns:
            Formatted performance report
        """
        summary = self.get_performance_summary()

        report_lines = []
        report_lines.append("# Performance Analysis Report")
        report_lines.append(f"Generated: {summary['summary_timestamp']}")
        report_lines.append("")

        # Overall statistics
        report_lines.append("## Overall Performance Statistics")
        report_lines.append(
            f"**Uptime**: {summary['uptime_seconds']:.1f} seconds ({summary['uptime_seconds'] / 3600:.1f} hours)"
        )
        report_lines.append(f"**Total Operations**: {summary['total_operations']:,}")
        report_lines.append(f"**Total Errors**: {summary['total_errors']:,}")
        report_lines.append(f"**Error Rate**: {summary['error_rate']:.2f}%")
        report_lines.append(
            f"**Operations/Second**: {summary['operations_per_second']:.2f}"
        )
        report_lines.append(
            f"**Unique Operation Types**: {summary['unique_operation_types']}"
        )
        report_lines.append(
            f"**Active Operations**: {summary['active_operations_count']}"
        )
        report_lines.append("")

        # Resource usage
        if summary["resource_monitoring_enabled"]:
            report_lines.append("## Resource Usage")
            report_lines.append(
                f"**Average CPU**: {summary['average_cpu_percent']:.1f}%"
            )
            report_lines.append(
                f"**Average Memory**: {summary['average_memory_percent']:.1f}%"
            )

            if summary["current_resources"]:
                current = summary["current_resources"]
                report_lines.append("### Current Resource Usage")
                report_lines.append(f"- CPU: {current['cpu_percent']:.1f}%")
                report_lines.append(f"- Memory: {current['memory_percent']:.1f}%")
                report_lines.append(
                    f"- Available Memory: {current['memory_available_mb']:.1f} MB"
                )
                report_lines.append(f"- Open Files: {current['open_files']}")
                report_lines.append(f"- Threads: {current['threads']}")
                report_lines.append(
                    f"- Disk I/O: {current['disk_io_read_mb']:.1f} MB read, {current['disk_io_write_mb']:.1f} MB write"
                )
                report_lines.append(
                    f"- Network I/O: {current['network_sent_mb']:.1f} MB sent, {current['network_recv_mb']:.1f} MB received"
                )
        else:
            report_lines.append("## Resource Usage")
            report_lines.append("Resource monitoring disabled")

        report_lines.append("")

        # Top operations by call frequency
        if summary["top_operations_by_calls"]:
            report_lines.append("## Most Frequent Operations")
            for i, op in enumerate(summary["top_operations_by_calls"], 1):
                report_lines.append(f"### {i}. {op['operation_name']}")
                report_lines.append(f"- **Calls**: {op['total_calls']:,}")
                report_lines.append(f"- **Success Rate**: {op['success_rate']:.1f}%")
                report_lines.append(
                    f"- **Avg Duration**: {op['avg_duration'] * 1000:.2f}ms"
                )
                report_lines.append(f"- **Calls/Second**: {op['calls_per_second']:.2f}")
                report_lines.append("")

        # Top operations by total duration
        if summary["top_operations_by_duration"]:
            report_lines.append("## Operations by Total Duration")
            for i, op in enumerate(summary["top_operations_by_duration"], 1):
                report_lines.append(f"### {i}. {op['operation_name']}")
                report_lines.append(
                    f"- **Total Duration**: {op['total_duration']:.2f}s"
                )
                report_lines.append(f"- **Calls**: {op['total_calls']:,}")
                report_lines.append(
                    f"- **Avg Duration**: {op['avg_duration'] * 1000:.2f}ms"
                )
                report_lines.append(
                    f"- **Min/Max**: {op['min_duration'] * 1000:.2f}ms / {op['max_duration'] * 1000:.2f}ms"
                )
                if "duration_stats" in op:
                    stats = op["duration_stats"]
                    report_lines.append(f"- **Median**: {stats['median'] * 1000:.2f}ms")
                    report_lines.append(
                        f"- **95th Percentile**: {stats['percentile_95'] * 1000:.2f}ms"
                    )
                    report_lines.append(
                        f"- **Std Dev**: {stats['std_dev'] * 1000:.2f}ms"
                    )
                report_lines.append("")

        # Active operations
        active_ops = self.get_active_operations()
        if active_ops:
            report_lines.append("## Currently Active Operations")
            for op_id, op_data in active_ops.items():
                duration = (datetime.now() - op_data["start_time"]).total_seconds()
                report_lines.append(f"- **{op_data['operation_name']}** ({op_id})")
                report_lines.append(f"  - Running for: {duration:.2f}s")
                report_lines.append(f"  - Started: {op_data['start_time'].isoformat()}")
            report_lines.append("")

        # Detailed history if requested
        if include_detailed_history:
            report_lines.append("## Detailed Performance History")

            with self._lock:
                for operation_name, metrics in self._metrics_history.items():
                    if metrics:
                        report_lines.append(f"### {operation_name}")
                        recent_metrics = list(metrics)[-10:]  # Last 10 measurements
                        for metric in recent_metrics:
                            report_lines.append(
                                f"- {metric.timestamp.isoformat()}: {metric.value:.3f} {metric.unit}"
                            )
                        report_lines.append("")

        # Performance recommendations
        report_lines.append("## Performance Recommendations")

        error_rate = summary["error_rate"]
        if error_rate > 5.0:
            report_lines.append(
                "🔴 **High Error Rate**: Error rate exceeds 5%. Investigate failing operations."
            )
        elif error_rate > 1.0:
            report_lines.append(
                "🟡 **Elevated Error Rate**: Error rate above 1%. Monitor for trends."
            )
        else:
            report_lines.append("✅ **Good Error Rate**: Error rate is acceptable.")

        if summary["resource_monitoring_enabled"]:
            avg_cpu = summary["average_cpu_percent"]
            avg_memory = summary["average_memory_percent"]

            if avg_cpu > 80:
                report_lines.append(
                    "🔴 **High CPU Usage**: Average CPU usage above 80%. Consider optimization."
                )
            elif avg_cpu > 60:
                report_lines.append(
                    "🟡 **Moderate CPU Usage**: Average CPU usage above 60%. Monitor trends."
                )

            if avg_memory > 80:
                report_lines.append(
                    "🔴 **High Memory Usage**: Average memory usage above 80%. Check for memory leaks."
                )
            elif avg_memory > 60:
                report_lines.append(
                    "🟡 **Moderate Memory Usage**: Average memory usage above 60%. Monitor trends."
                )

        # Check for slow operations
        with self._lock:
            slow_operations = []
            for profile in self._operation_profiles.values():
                if (
                    profile.avg_duration > 1.0
                ):  # Operations taking more than 1 second on average
                    slow_operations.append(profile)

        if slow_operations:
            report_lines.append("🔍 **Slow Operations Detected**:")
            for op in sorted(
                slow_operations, key=lambda x: x.avg_duration, reverse=True
            )[:3]:
                report_lines.append(
                    f"  - {op.operation_name}: {op.avg_duration:.2f}s average"
                )

        report_lines.append("")
        report_lines.append("---")
        report_lines.append(
            "*This report is optimized for LLM analysis and performance optimization*"
        )

        return "\n".join(report_lines)

    def profile_function(self, operation_name: str | None = None):
        """Decorator for profiling function calls.

        Args:
            operation_name: Optional custom operation name (defaults to function name)

        Returns:
            Decorator function
        """

        def decorator(func: Callable) -> Callable:
            op_name = operation_name or f"{func.__module__}.{func.__name__}"

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                with self.profile_operation(op_name):
                    return func(*args, **kwargs)

            return wrapper

        return decorator

    def clear_history(self) -> None:
        """Clear all performance history and metrics."""
        with self._lock:
            self._operation_profiles.clear()
            self._metrics_history.clear()
            self._resource_snapshots.clear()
            self._active_operations.clear()
            self._start_time = datetime.now()


# Global performance profiler instance
_global_profiler: PerformanceProfiler | None = None
_profiler_lock = threading.Lock()


def get_global_profiler() -> PerformanceProfiler:
    """Get or create the global performance profiler instance."""
    global _global_profiler

    if _global_profiler is None:
        with _profiler_lock:
            if _global_profiler is None:
                _global_profiler = PerformanceProfiler()

    return _global_profiler


def profile_operation(operation_name: str):
    """Convenience decorator using the global profiler.

    Args:
        operation_name: Name of the operation to profile
    """
    return get_global_profiler().profile_function(operation_name)


@contextmanager
def profile(operation_name: str) -> Iterator[dict[str, Any]]:
    """Convenience context manager using the global profiler.

    Args:
        operation_name: Name of the operation to profile

    Yields:
        Operation metadata dictionary
    """
    with get_global_profiler().profile_operation(operation_name) as metadata:
        yield metadata
