"""
Metrics protocol definitions for performance monitoring and data collection.

This module defines protocols for performance metrics collection, operation timing,
success/failure tracking, and resource usage monitoring.
"""

from typing import Protocol, Dict, Any, List, Optional, Union, Iterator, Callable
from abc import abstractmethod
from enum import Enum
from datetime import datetime, timedelta
from dataclasses import dataclass


class MetricType(Enum):
    """Enumeration of metric types."""
    COUNTER = "counter"           # Monotonically increasing values
    GAUGE = "gauge"              # Current value at a point in time
    HISTOGRAM = "histogram"      # Distribution of values
    TIMER = "timer"              # Duration measurements
    RATE = "rate"                # Events per unit time


class MetricUnit(Enum):
    """Enumeration of metric units."""
    SECONDS = "seconds"
    MILLISECONDS = "milliseconds"
    MICROSECONDS = "microseconds"
    BYTES = "bytes"
    KILOBYTES = "kilobytes"
    MEGABYTES = "megabytes"
    COUNT = "count"
    PERCENT = "percent"
    OPERATIONS_PER_SECOND = "ops/sec"


@dataclass
class MetricValue:
    """Data structure for metric values."""
    name: str
    value: Union[int, float]
    metric_type: MetricType
    unit: MetricUnit
    timestamp: datetime
    tags: Dict[str, str]
    metadata: Dict[str, Any]


@dataclass
class TimingResult:
    """Data structure for timing measurements."""
    operation_name: str
    duration: float
    unit: MetricUnit
    start_time: datetime
    end_time: datetime
    success: bool
    metadata: Dict[str, Any]


class MetricCollector(Protocol):
    """Protocol for collecting and recording metrics."""
    
    @abstractmethod
    def record_counter(self, name: str, value: Union[int, float] = 1,
                      tags: Optional[Dict[str, str]] = None) -> None:
        """
        Record a counter metric (monotonically increasing).
        
        Args:
            name: Metric name
            value: Value to add to counter (default 1)
            tags: Optional tags for metric categorization
            
        Example:
            >>> collector = MyMetricCollector()
            >>> collector.record_counter("git.commits.created", 1, {"branch": "main"})
            >>> collector.record_counter("api.requests.total")
        """
        ...
    
    @abstractmethod
    def record_gauge(self, name: str, value: Union[int, float],
                    tags: Optional[Dict[str, str]] = None) -> None:
        """
        Record a gauge metric (current value).
        
        Args:
            name: Metric name
            value: Current value
            tags: Optional tags for metric categorization
            
        Example:
            >>> collector = MyMetricCollector()
            >>> collector.record_gauge("system.memory.usage", 75.5, {"unit": "percent"})
            >>> collector.record_gauge("active.connections", 42)
        """
        ...
    
    @abstractmethod
    def record_histogram(self, name: str, value: Union[int, float],
                        tags: Optional[Dict[str, str]] = None) -> None:
        """
        Record a histogram metric (value distribution).
        
        Args:
            name: Metric name
            value: Value to record in distribution
            tags: Optional tags for metric categorization
            
        Example:
            >>> collector = MyMetricCollector()
            >>> collector.record_histogram("request.size.bytes", 1024)
            >>> collector.record_histogram("operation.duration", 250.5, {"unit": "ms"})
        """
        ...
    
    @abstractmethod
    def record_timer(self, name: str, duration: float,
                    unit: MetricUnit = MetricUnit.MILLISECONDS,
                    tags: Optional[Dict[str, str]] = None) -> None:
        """
        Record a timing metric.
        
        Args:
            name: Metric name
            duration: Duration value
            unit: Time unit for duration
            tags: Optional tags for metric categorization
            
        Example:
            >>> collector = MyMetricCollector()
            >>> collector.record_timer("git.clone.duration", 15.2, MetricUnit.SECONDS)
            >>> collector.record_timer("api.response.time", 150.0)
        """
        ...
    
    @abstractmethod
    def increment(self, name: str, tags: Optional[Dict[str, str]] = None) -> None:
        """
        Increment a counter by 1.
        
        Args:
            name: Metric name
            tags: Optional tags for metric categorization
            
        Example:
            >>> collector = MyMetricCollector()
            >>> collector.increment("errors.validation")
            >>> collector.increment("requests.processed", {"endpoint": "/status"})
        """
        ...
    
    @abstractmethod
    def decrement(self, name: str, tags: Optional[Dict[str, str]] = None) -> None:
        """
        Decrement a gauge by 1.
        
        Args:
            name: Metric name
            tags: Optional tags for metric categorization
        """
        ...


class PerformanceTimer(Protocol):
    """Protocol for timing operations and measuring performance."""
    
    @abstractmethod
    def start_timer(self, operation_name: str, 
                   metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Start timing an operation.
        
        Args:
            operation_name: Name of operation being timed
            metadata: Optional metadata about the operation
            
        Returns:
            Timer ID for stopping the timer
            
        Example:
            >>> timer = MyPerformanceTimer()
            >>> timer_id = timer.start_timer("git.push", {"branch": "main"})
            >>> # ... perform operation ...
            >>> result = timer.stop_timer(timer_id)
        """
        ...
    
    @abstractmethod
    def stop_timer(self, timer_id: str, success: bool = True) -> TimingResult:
        """
        Stop a timer and get the result.
        
        Args:
            timer_id: ID returned from start_timer()
            success: Whether the operation succeeded
            
        Returns:
            TimingResult with duration and metadata
            
        Example:
            >>> timer = MyPerformanceTimer()
            >>> timer_id = timer.start_timer("database.query")
            >>> # ... perform database operation ...
            >>> result = timer.stop_timer(timer_id, success=True)
            >>> print(f"Query took {result.duration} {result.unit.value}")
        """
        ...
    
    @abstractmethod
    def time_operation(self, operation_name: str, operation: Callable[[], Any],
                      metadata: Optional[Dict[str, Any]] = None) -> TimingResult:
        """
        Time a callable operation.
        
        Args:
            operation_name: Name of operation
            operation: Callable to time
            metadata: Optional metadata about the operation
            
        Returns:
            TimingResult with duration and operation result
            
        Example:
            >>> timer = MyPerformanceTimer()
            >>> def expensive_operation():
            ...     # ... do work ...
            ...     return "result"
            >>> result = timer.time_operation("data.processing", expensive_operation)
            >>> print(f"Operation took {result.duration}ms")
        """
        ...
    
    @abstractmethod
    def get_timing_stats(self, operation_name: str) -> Dict[str, float]:
        """
        Get timing statistics for an operation.
        
        Args:
            operation_name: Name of operation to get stats for
            
        Returns:
            Dictionary with timing statistics (avg, min, max, p95, etc.)
            
        Example:
            >>> timer = MyPerformanceTimer()
            >>> stats = timer.get_timing_stats("git.clone")
            >>> print(f"Average: {stats['avg']}ms, P95: {stats['p95']}ms")
        """
        ...


class SuccessFailureTracker(Protocol):
    """Protocol for tracking operation success and failure rates."""
    
    @abstractmethod
    def record_success(self, operation: str, 
                      metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Record a successful operation.
        
        Args:
            operation: Name of operation that succeeded
            metadata: Optional metadata about the operation
            
        Example:
            >>> tracker = MySuccessFailureTracker()
            >>> tracker.record_success("git.commit", {"files": 3})
        """
        ...
    
    @abstractmethod
    def record_failure(self, operation: str, error_type: str,
                      metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Record a failed operation.
        
        Args:
            operation: Name of operation that failed
            error_type: Type or category of error
            metadata: Optional metadata about the failure
            
        Example:
            >>> tracker = MySuccessFailureTracker()
            >>> tracker.record_failure("git.push", "authentication_error", {"repo": "origin"})
        """
        ...
    
    @abstractmethod
    def get_success_rate(self, operation: str, 
                        time_window: Optional[timedelta] = None) -> float:
        """
        Get success rate for an operation.
        
        Args:
            operation: Name of operation
            time_window: Optional time window to calculate rate for
            
        Returns:
            Success rate as float between 0.0 and 1.0
            
        Example:
            >>> tracker = MySuccessFailureTracker()
            >>> rate = tracker.get_success_rate("api.requests", timedelta(hours=1))
            >>> print(f"Success rate: {rate:.2%}")
        """
        ...
    
    @abstractmethod
    def get_failure_breakdown(self, operation: str,
                             time_window: Optional[timedelta] = None) -> Dict[str, int]:
        """
        Get breakdown of failure types for an operation.
        
        Args:
            operation: Name of operation
            time_window: Optional time window to analyze
            
        Returns:
            Dictionary mapping error types to occurrence counts
            
        Example:
            >>> tracker = MySuccessFailureTracker()
            >>> failures = tracker.get_failure_breakdown("git.clone")
            >>> # {"network_error": 5, "auth_error": 2, "timeout": 1}
        """
        ...


class ResourceMonitor(Protocol):
    """Protocol for monitoring system resource usage."""
    
    @abstractmethod
    def get_memory_usage(self) -> Dict[str, float]:
        """
        Get current memory usage statistics.
        
        Returns:
            Dictionary with memory statistics (used, available, percent, etc.)
            
        Example:
            >>> monitor = MyResourceMonitor()
            >>> memory = monitor.get_memory_usage()
            >>> print(f"Memory usage: {memory['percent']:.1f}%")
        """
        ...
    
    @abstractmethod
    def get_cpu_usage(self) -> Dict[str, float]:
        """
        Get current CPU usage statistics.
        
        Returns:
            Dictionary with CPU statistics (percent, load average, etc.)
        """
        ...
    
    @abstractmethod
    def get_disk_usage(self, path: str = "/") -> Dict[str, float]:
        """
        Get disk usage statistics for a path.
        
        Args:
            path: Path to check disk usage for
            
        Returns:
            Dictionary with disk statistics (used, free, percent, etc.)
        """
        ...
    
    @abstractmethod
    def get_network_stats(self) -> Dict[str, int]:
        """
        Get network usage statistics.
        
        Returns:
            Dictionary with network statistics (bytes sent/received, packets, etc.)
        """
        ...
    
    @abstractmethod
    def start_resource_monitoring(self, interval: float = 60.0) -> None:
        """
        Start continuous resource monitoring.
        
        Args:
            interval: Monitoring interval in seconds
        """
        ...
    
    @abstractmethod
    def stop_resource_monitoring(self) -> None:
        """Stop continuous resource monitoring."""
        ...


class MetricsAggregator(Protocol):
    """Protocol for aggregating and analyzing metrics."""
    
    @abstractmethod
    def get_metric_summary(self, metric_name: str,
                          time_window: Optional[timedelta] = None) -> Dict[str, float]:
        """
        Get summary statistics for a metric.
        
        Args:
            metric_name: Name of metric to summarize
            time_window: Optional time window for analysis
            
        Returns:
            Dictionary with summary statistics (count, avg, min, max, etc.)
        """
        ...
    
    @abstractmethod
    def get_metrics_by_tag(self, tag_filter: Dict[str, str]) -> List[MetricValue]:
        """
        Get metrics matching tag filters.
        
        Args:
            tag_filter: Dictionary of tag key-value pairs to match
            
        Returns:
            List of MetricValue objects matching the filter
        """
        ...
    
    @abstractmethod
    def export_metrics(self, format: str = "json") -> str:
        """
        Export metrics in specified format.
        
        Args:
            format: Export format (json, csv, prometheus, etc.)
            
        Returns:
            Formatted metrics data
        """
        ...
    
    @abstractmethod
    def get_top_metrics(self, metric_type: MetricType, limit: int = 10) -> List[MetricValue]:
        """
        Get top metrics by value for a given type.
        
        Args:
            metric_type: Type of metrics to analyze
            limit: Maximum number of metrics to return
            
        Returns:
            List of top metrics sorted by value
        """
        ...


class MetricsSystem(Protocol):
    """
    Comprehensive metrics system protocol.
    
    This protocol combines all metrics collection capabilities into a unified
    interface for components that need full metrics functionality.
    """
    
    # Composition of all metrics sub-protocols
    collector: MetricCollector
    timer: PerformanceTimer
    tracker: SuccessFailureTracker
    resource_monitor: ResourceMonitor
    aggregator: MetricsAggregator
    
    @abstractmethod
    def initialize_metrics(self, config: Dict[str, Any]) -> None:
        """
        Initialize the metrics system with configuration.
        
        Args:
            config: Configuration dictionary with collection settings, etc.
            
        Example:
            >>> metrics_system = MyMetricsSystem()
            >>> config = {
            ...     "collection_interval": 60,
            ...     "retention_days": 30,
            ...     "export_endpoints": ["prometheus", "grafana"]
            ... }
            >>> metrics_system.initialize_metrics(config)
        """
        ...
    
    @abstractmethod
    def shutdown_metrics(self) -> None:
        """Gracefully shutdown the metrics system."""
        ...
    
    @abstractmethod
    def get_system_health(self) -> Dict[str, Union[bool, float, int]]:
        """
        Get overall system health metrics.
        
        Returns:
            Dictionary with health indicators and key metrics
            
        Example:
            >>> metrics_system = MyMetricsSystem()
            >>> health = metrics_system.get_system_health()
            >>> print(f"System healthy: {health['healthy']}")
            >>> print(f"Error rate: {health['error_rate']:.2%}")
        """
        ...
    
    @abstractmethod
    def create_dashboard_data(self, dashboard_type: str = "overview") -> Dict[str, Any]:
        """
        Create data for metrics dashboards.
        
        Args:
            dashboard_type: Type of dashboard (overview, performance, errors, etc.)
            
        Returns:
            Dictionary with dashboard data and visualization configs
        """
        ...


class AsyncMetricsSystem(Protocol):
    """Protocol for asynchronous metrics operations."""
    
    @abstractmethod
    async def collect_metrics_async(self) -> None:
        """Async collection of all metrics."""
        ...
    
    @abstractmethod
    async def export_metrics_async(self, endpoints: List[str]) -> Dict[str, bool]:
        """
        Async export to multiple endpoints.
        
        Args:
            endpoints: List of export endpoints
            
        Returns:
            Dictionary mapping endpoint to success status
        """
        ...
    
    @abstractmethod
    async def metrics_stream(self, filters: Optional[Dict[str, Any]] = None) -> Iterator[MetricValue]:
        """
        Stream metrics as they are collected.
        
        Args:
            filters: Optional filters for metric types, names, etc.
            
        Yields:
            MetricValue objects as they are collected
        """
        ...