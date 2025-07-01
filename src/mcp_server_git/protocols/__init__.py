"""Protocols module for MCP Git Server.

This module contains protocol definitions that define interfaces and contracts
between components. Protocols enable type-safe duck typing and clear
architectural boundaries throughout the system.

Architecture:
    Protocols define the interfaces that components must implement:
    - Clear contracts between system layers
    - Type-safe duck typing with structural subtyping
    - Interface segregation for focused responsibilities
    - Dependency inversion through abstract interfaces

Key protocol categories:
    repository_protocol: Interfaces for repository operations
    notification_protocol: Interfaces for notification handling
    metrics_protocol: Interfaces for metrics collection
    debugging_protocol: Interfaces for state inspection and debugging

Protocol design principles:
    - Single responsibility: Each protocol has one clear purpose
    - Minimal interface: Protocols define only essential methods
    - Type safety: Full type annotations for all methods
    - Documentation: Comprehensive documentation for each method
    - Testability: Protocols enable easy mocking and testing

Usage patterns:
    ```python
    from typing import Protocol
    
    class RepositoryProtocol(Protocol):
        def get_status(self) -> RepositoryStatus:
            \"\"\"Get current repository status.\"\"\"
            ...
            
        def commit_changes(self, message: str) -> CommitResult:
            \"\"\"Commit staged changes.\"\"\"
            ...
    ```

Implementation examples:
    >>> from mcp_server_git.protocols import DebuggableComponent
    >>> 
    >>> class MyService:
    ...     def get_debug_state(self) -> Dict[str, Any]:
    ...         return {"status": "active", "connections": 5}
    ...     
    ...     def explain_state_change(self, prev, curr) -> str:
    ...         return "State changed from active to idle"
    >>> 
    >>> # MyService now implements DebuggableComponent protocol
    >>> service: DebuggableComponent = MyService()

Protocol benefits:
    - Type checking: Static analysis can verify implementations
    - Documentation: Protocols serve as interface documentation
    - Testing: Easy to create mock implementations
    - Flexibility: Multiple implementations of same interface
    - Evolution: Protocols can evolve without breaking changes

Integration with frameworks:
    - Dependency injection: Protocols define injection interfaces
    - Plugin systems: Protocols define plugin interfaces
    - Service discovery: Protocols enable service registration
    - Configuration: Protocols define configurable behaviors

See also:
    - abc: Abstract base classes for inheritance-based interfaces
    - typing: Type system features used in protocol definitions
    - frameworks: Framework patterns that use these protocols
"""

# Import all protocol definitions
from .repository_protocol import *
from .notification_protocol import *
from .metrics_protocol import *
from .debugging_protocol import *

__all__ = [
    # Repository protocols
    "RepositoryProtocol",
    "GitRepositoryProtocol", 
    "GitHubRepositoryProtocol",
    
    # Notification protocols
    "NotificationProtocol",
    "NotificationHandlerProtocol",
    "NotificationRouterProtocol",
    
    # Metrics protocols
    "MetricsCollectorProtocol",
    "MetricsReporterProtocol",
    "PerformanceMonitorProtocol",
    
    # Debugging protocols
    "DebuggableComponent",
    "StateInspectorProtocol",
    "DiagnosticProviderProtocol",
]