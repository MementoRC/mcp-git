"""Frameworks module for MCP Git Server.

This module contains architectural patterns and structural components that define
how the system is organized and how components interact. Frameworks provide the
foundational patterns that services and applications build upon.

Architecture:
    Frameworks represent the fourth level in the 5-level hierarchy:
    Level 4: Templates (Layouts) - Structural patterns
    - Architectural patterns and blueprints
    - Configuration schemas and validation
    - Interface definitions and contracts

Key components:
    mcp_server_framework: Core MCP server architectural patterns
    tool_registry_framework: Tool registration and execution framework
    error_handling_framework: Comprehensive error handling patterns
    security_framework: Security validation and enforcement patterns

Framework characteristics:
    - Architectural: Define system structure and component relationships
    - Reusable: Patterns can be applied across multiple components
    - Configurable: Framework behavior controlled by configuration
    - Extensible: Support for plugins and custom implementations
    - Testable: Framework patterns include testing strategies

Design patterns implemented:
    - Plugin architecture: Dynamic loading and registration of components
    - Command pattern: Tool execution and request handling
    - Observer pattern: Event notification and handling
    - Strategy pattern: Configurable algorithms and behaviors
    - Factory pattern: Component creation and initialization

Integration capabilities:
    - Dependency injection: Framework manages component dependencies
    - Configuration management: Centralized configuration handling
    - Lifecycle management: Component startup, operation, and shutdown
    - Error boundaries: Isolated error handling and recovery
    - Monitoring integration: Built-in metrics and observability

Performance characteristics:
    - Low overhead: Frameworks add minimal performance cost
    - Scalable: Patterns support horizontal and vertical scaling
    - Efficient: Optimized for high-throughput operations
    - Resilient: Built-in fault tolerance and recovery

Example usage:
    >>> from mcp_server_git.frameworks import mcp_server_framework
    >>> from mcp_server_git.configuration import ServerConfig
    >>> 
    >>> config = ServerConfig(
    ...     host="localhost",
    ...     port=8080,
    ...     max_concurrent_operations=100
    ... )
    >>> 
    >>> framework = mcp_server_framework.MCPServerFramework(config)
    >>> framework.register_service("git", git_service)
    >>> framework.register_service("github", github_service)
    >>> 
    >>> await framework.start()
    >>> # Framework now manages service lifecycle and request routing

See also:
    - services: High-level services that use framework patterns
    - applications: Complete applications built on frameworks
    - protocols: Interfaces defined and enforced by frameworks
    - configuration: Framework configuration and validation schemas
"""

__all__ = [
    # MCP server framework
    "mcp_server_framework",
    
    # Tool registry framework
    "tool_registry_framework",
    
    # Error handling framework
    "error_handling_framework",
    
    # Security framework
    "security_framework",
]