"""
Protocol definitions for MCP Git server component interfaces.

This package provides comprehensive protocol definitions that define clear contracts
between components in the MCP Git server system. These protocols enable type-safe
interfaces for debugging, repository operations, notifications, and metrics collection.

The protocols in this package are designed to:
- Provide clear contracts between components
- Enable dependency injection and testing
- Support both synchronous and asynchronous operations
- Facilitate debugging and introspection
- Enable comprehensive monitoring and metrics collection

Usage:
    >>> from mcp_server_git.protocols import DebuggableComponent, RepositoryOperations
    >>> 
    >>> class MyComponent(DebuggableComponent):
    ...     def get_component_state(self) -> ComponentState:
    ...         # Implementation here
    ...         pass
"""

# Debugging Protocol Exports
from .debugging_protocol import (
    ComponentState,
    ValidationResult,
    DebugInfo,
    DebuggableComponent,
    StateInspector,
    DebuggingContext,
)

# Repository Protocol Exports
from .repository_protocol import (
    RepositoryValidator,
    BranchManager,
    CommitManager,
    DiffProvider,
    RemoteManager,
    RepositoryOperations,
    AsyncRepositoryOperations,
)

# Notification Protocol Exports
from .notification_protocol import (
    NotificationLevel,
    NotificationChannel,
    NotificationEvent,
    EventSubscriber,
    EventPublisher,
    StatusReporter,
    ErrorReporter,
    MessageBroadcaster,
    NotificationSystem,
    AsyncNotificationSystem,
    NotificationFilter,
)

# Metrics Protocol Exports
from .metrics_protocol import (
    MetricType,
    MetricUnit,
    MetricValue,
    TimingResult,
    MetricCollector,
    PerformanceTimer,
    SuccessFailureTracker,
    ResourceMonitor,
    MetricsAggregator,
    MetricsSystem,
    AsyncMetricsSystem,
)

# Convenience type aliases for common protocol combinations
from typing import Union

# Common protocol combinations for dependency injection
DebuggableRepositoryComponent = Union[DebuggableComponent, RepositoryOperations]
MonitoredComponent = Union[DebuggableComponent, MetricsSystem, NotificationSystem]
FullServiceComponent = Union[
    DebuggableComponent, 
    RepositoryOperations, 
    NotificationSystem, 
    MetricsSystem
]

# Export all protocol classes
__all__ = [
    # Debugging Protocols
    "ComponentState",
    "ValidationResult", 
    "DebugInfo",
    "DebuggableComponent",
    "StateInspector",
    "DebuggingContext",
    
    # Repository Protocols
    "RepositoryValidator",
    "BranchManager",
    "CommitManager",
    "DiffProvider",
    "RemoteManager",
    "RepositoryOperations",
    "AsyncRepositoryOperations",
    
    # Notification Protocols
    "NotificationLevel",
    "NotificationChannel",
    "NotificationEvent",
    "EventSubscriber",
    "EventPublisher",
    "StatusReporter",
    "ErrorReporter",
    "MessageBroadcaster",
    "NotificationSystem",
    "AsyncNotificationSystem",
    "NotificationFilter",
    
    # Metrics Protocols
    "MetricType",
    "MetricUnit",
    "MetricValue",
    "TimingResult",
    "MetricCollector",
    "PerformanceTimer",
    "SuccessFailureTracker",
    "ResourceMonitor",
    "MetricsAggregator",
    "MetricsSystem",
    "AsyncMetricsSystem",
    
    # Convenience Types
    "DebuggableRepositoryComponent",
    "MonitoredComponent",
    "FullServiceComponent",
]

# Protocol version for compatibility checking
PROTOCOL_VERSION = "1.0.0"

# Protocol metadata
PROTOCOL_INFO = {
    "version": PROTOCOL_VERSION,
    "description": "MCP Git Server Protocol Definitions",
    "protocols": {
        "debugging": {
            "primary": "DebuggableComponent",
            "supporting": ["ComponentState", "ValidationResult", "DebugInfo"],
            "description": "Component debugging and state inspection"
        },
        "repository": {
            "primary": "RepositoryOperations", 
            "supporting": ["RepositoryValidator", "BranchManager", "CommitManager"],
            "description": "Git repository operations and management"
        },
        "notification": {
            "primary": "NotificationSystem",
            "supporting": ["EventPublisher", "StatusReporter", "ErrorReporter"],
            "description": "Event notification and status reporting"
        },
        "metrics": {
            "primary": "MetricsSystem",
            "supporting": ["MetricCollector", "PerformanceTimer", "ResourceMonitor"],
            "description": "Performance monitoring and metrics collection"
        }
    }
}


def get_protocol_info() -> dict:
    """
    Get information about available protocols.
    
    Returns:
        Dictionary with protocol metadata and version information
        
    Example:
        >>> from mcp_server_git.protocols import get_protocol_info
        >>> info = get_protocol_info()
        >>> print(f"Protocol version: {info['version']}")
        >>> for name, details in info['protocols'].items():
        ...     print(f"{name}: {details['description']}")
    """
    return PROTOCOL_INFO.copy()


def validate_protocol_implementation(obj: object, protocol_name: str) -> bool:
    """
    Validate that an object properly implements a protocol.
    
    Args:
        obj: Object to validate
        protocol_name: Name of protocol to validate against
        
    Returns:
        True if object implements the protocol correctly
        
    Example:
        >>> from mcp_server_git.protocols import validate_protocol_implementation
        >>> component = MyDebuggableComponent()
        >>> is_valid = validate_protocol_implementation(component, "DebuggableComponent")
    """
    protocol_map = {
        "DebuggableComponent": DebuggableComponent,
        "RepositoryOperations": RepositoryOperations,
        "NotificationSystem": NotificationSystem,
        "MetricsSystem": MetricsSystem,
        "ComponentState": ComponentState,
        "ValidationResult": ValidationResult,
        "DebugInfo": DebugInfo,
        "RepositoryValidator": RepositoryValidator,
        "BranchManager": BranchManager,
        "CommitManager": CommitManager,
        "DiffProvider": DiffProvider,
        "RemoteManager": RemoteManager,
        "EventSubscriber": EventSubscriber,
        "EventPublisher": EventPublisher,
        "StatusReporter": StatusReporter,
        "ErrorReporter": ErrorReporter,
        "MessageBroadcaster": MessageBroadcaster,
        "MetricCollector": MetricCollector,
        "PerformanceTimer": PerformanceTimer,
        "SuccessFailureTracker": SuccessFailureTracker,
        "ResourceMonitor": ResourceMonitor,
        "MetricsAggregator": MetricsAggregator,
    }
    
    protocol_class = protocol_map.get(protocol_name)
    if protocol_class is None:
        return False
    
    # In Python 3.8+, we can use isinstance with Protocol
    # For now, we'll do a simple attribute check
    try:
        # Get all methods from the protocol class
        required_methods = [name for name in dir(protocol_class) 
                          if not name.startswith('_') and 
                          hasattr(protocol_class, name) and
                          callable(getattr(protocol_class, name, None))]
        
        for method_name in required_methods:
            if not hasattr(obj, method_name):
                return False
            method = getattr(obj, method_name)
            if not callable(method):
                return False
        
        return True
    except Exception:
        return False


# Development utilities
def list_protocol_methods(protocol_name: str) -> list:
    """
    List all methods required by a protocol.
    
    Args:
        protocol_name: Name of the protocol
        
    Returns:
        List of method names required by the protocol
    """
    protocol_map = {
        "DebuggableComponent": DebuggableComponent,
        "RepositoryOperations": RepositoryOperations,
        "NotificationSystem": NotificationSystem,
        "MetricsSystem": MetricsSystem,
    }
    
    protocol_class = protocol_map.get(protocol_name)
    if protocol_class is None:
        return []
    
    methods = []
    for attr_name in dir(protocol_class):
        if not attr_name.startswith('_'):
            attr = getattr(protocol_class, attr_name)
            if callable(attr):
                methods.append(attr_name)
    
    return sorted(methods)


def get_protocol_dependencies() -> dict:
    """
    Get protocol dependency relationships.
    
    Returns:
        Dictionary mapping protocols to their dependencies
    """
    return {
        "RepositoryOperations": [
            "RepositoryValidator", 
            "BranchManager", 
            "CommitManager", 
            "DiffProvider", 
            "RemoteManager"
        ],
        "NotificationSystem": [
            "EventPublisher", 
            "StatusReporter", 
            "ErrorReporter", 
            "MessageBroadcaster"
        ],
        "MetricsSystem": [
            "MetricCollector", 
            "PerformanceTimer", 
            "SuccessFailureTracker", 
            "ResourceMonitor", 
            "MetricsAggregator"
        ],
        "DebuggableComponent": [
            "ComponentState", 
            "ValidationResult", 
            "DebugInfo"
        ]
    }