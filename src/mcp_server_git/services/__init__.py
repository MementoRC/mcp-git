"""Services module for MCP Git Server.

This module contains complete, self-contained service implementations that provide
high-level interfaces for major functional areas. Services orchestrate operations
and primitives to deliver complete business capabilities.

Architecture:
    Services represent the third level in the 5-level hierarchy:
    Level 3: Organisms (Features) - Complex, self-contained units
    - Complete feature implementations
    - Classes with full functionality
    - Service modules with comprehensive APIs

Key components:
    git_service: Complete Git repository management service
    github_service: Complete GitHub API integration service
    session_service: Complete session lifecycle management service
    metrics_service: Complete metrics collection and reporting service

Design principles:
    - Complete functionality: Services provide end-to-end capabilities
    - State management: Services may maintain persistent state
    - Configuration driven: Extensive use of configuration for behavior
    - Error recovery: Robust error handling and recovery mechanisms
    - Extensibility: Plugin-like architecture for extension

Service characteristics:
    - Stateful: Services maintain operational state
    - Configurable: Behavior controlled by configuration
    - Observable: Comprehensive metrics and logging
    - Recoverable: Graceful degradation and error recovery
    - Testable: Comprehensive test coverage and mocking support

Integration patterns:
    - Dependency injection: Services receive dependencies
    - Event-driven: Services communicate via events/notifications
    - Async/await: Services support asynchronous operations
    - Context management: Services provide context for operations

Performance expectations:
    - High throughput: Services handle multiple concurrent requests
    - Resource efficient: Proper resource pooling and management
    - Scalable: Services designed for horizontal scaling
    - Monitored: Comprehensive performance monitoring

Example usage:
    >>> from mcp_server_git.services import git_service
    >>> from mcp_server_git.configuration import GitServiceConfig
    >>>
    >>> config = GitServiceConfig(
    ...     max_concurrent_operations=10,
    ...     operation_timeout_seconds=300,
    ...     enable_security_validation=True
    ... )
    >>>
    >>> service = git_service.GitService(config)
    >>> await service.start()
    >>>
    >>> result = await service.commit_changes(
    ...     repository_path="/path/to/repo",
    ...     message="feat: implement new feature",
    ...     files=["src/feature.py"]
    ... )
    >>>
    >>> print(result.commit_hash)
    'a1b2c3d4e5f6...'

See also:
    - operations: Lower-level operations orchestrated by services
    - frameworks: Architectural patterns that services implement
    - configuration: Service configuration and validation
    - protocols: Interfaces implemented by services
"""

# Placeholder exports - will be populated as modules are implemented
__all__ = [
    # Git service - to be implemented in Task 23
    # "git_service",
    # GitHub service - to be implemented in Task 24
    # "github_service",
    # Session service - to be implemented
    # "session_service",
    # Metrics service - to be implemented
    # "metrics_service",
]
