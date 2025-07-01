"""Configuration module for MCP Git Server.

This module provides comprehensive configuration management using Pydantic models
for validation, type safety, and documentation. Configuration is designed to be
environment-aware, validation-rich, and easily testable.

Architecture:
    Configuration follows a hierarchical approach:
    - Base configuration: Common configuration patterns and validation
    - Service configuration: Service-specific configuration models
    - Application configuration: Top-level application configuration
    - Environment integration: Environment variable binding and defaults

Key components:
    server_config: Main server configuration with validation
    git_config: Git service configuration and validation
    github_config: GitHub service configuration and validation
    security_config: Security and authentication configuration

Configuration principles:
    - Type safety: All configuration values have explicit types
    - Validation: Comprehensive validation with clear error messages
    - Documentation: Self-documenting configuration with examples
    - Environment aware: Automatic binding to environment variables
    - Testable: Easy to create test configurations

Pydantic features used:
    - Field validation: Custom validators for complex rules
    - Environment variables: Automatic binding to environment
    - Nested models: Hierarchical configuration structures
    - Default factories: Dynamic default value generation
    - Aliases: Support for multiple naming conventions

Configuration hierarchy:
    ```python
    class ApplicationConfig(BaseModel):
        server: ServerConfig
        git: GitConfig
        github: GitHubConfig
        security: SecurityConfig
        logging: LoggingConfig
    ```

Usage examples:
    >>> from mcp_server_git.configuration import ApplicationConfig
    >>> 
    >>> # Load from environment variables
    >>> config = ApplicationConfig()
    >>> 
    >>> # Load from file
    >>> config = ApplicationConfig.parse_file("config.json")
    >>> 
    >>> # Load from dictionary
    >>> config_dict = {"server": {"host": "0.0.0.0", "port": 8080}}
    >>> config = ApplicationConfig.parse_obj(config_dict)
    >>> 
    >>> # Access typed configuration
    >>> print(f"Server running on {config.server.host}:{config.server.port}")

Environment variable binding:
    ```bash
    # Environment variables automatically bind to configuration
    export MCP_SERVER_HOST=localhost
    export MCP_SERVER_PORT=8080
    export MCP_GIT_MAX_CONCURRENT_OPERATIONS=20
    export MCP_GITHUB_TOKEN=ghp_xxxxxxxxxxxx
    ```

Validation examples:
    >>> from mcp_server_git.configuration import GitConfig
    >>> 
    >>> try:
    ...     config = GitConfig(operation_timeout_seconds=0)
    ... except ValidationError as e:
    ...     print(e.errors())
    [{'loc': ('operation_timeout_seconds',), 'msg': 'ensure this value is greater than 0'}]

Configuration testing:
    >>> from mcp_server_git.configuration import create_test_config
    >>> 
    >>> # Create configuration optimized for testing
    >>> test_config = create_test_config(
    ...     override_git_timeout=1,  # Fast timeouts for tests
    ...     override_github_token="test_token"
    ... )

Schema generation:
    >>> from mcp_server_git.configuration import ApplicationConfig
    >>> 
    >>> # Generate JSON schema for documentation
    >>> schema = ApplicationConfig.schema()
    >>> print(json.dumps(schema, indent=2))

Security considerations:
    - Secrets handling: Proper handling of sensitive configuration
    - Validation: Prevent invalid or dangerous configuration
    - Environment isolation: Separate configuration for different environments
    - Audit logging: Log configuration changes and access

See also:
    - constants: Default values used in configuration
    - types: Type definitions used in configuration models
    - validation: Additional validation utilities
"""

# Import all configuration models - will be implemented in Task 5
# from .server_config import *
# from .git_config import *
# from .github_config import *
# from .security_config import *
# from .application_config import *

# Placeholder exports - will be populated as modules are implemented
__all__ = [
    # Main application configuration - to be implemented
    # "ApplicationConfig",
    
    # Server configuration - to be implemented
    # "ServerConfig",
    # "LoggingConfig",
    # "MetricsConfig",
    
    # Service configurations - to be implemented
    # "GitConfig",
    # "GitHubConfig",
    # "SecurityConfig",
    
    # Configuration utilities - to be implemented
    # "create_test_config",
    # "load_config_from_env",
    # "validate_config_file",
    # "generate_config_schema",
]