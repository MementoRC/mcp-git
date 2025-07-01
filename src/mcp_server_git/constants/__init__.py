"""Constants module for MCP Git Server.

This module contains organized constant definitions grouped in logical classes
to provide centralized configuration values, limits, defaults, and other
immutable values used throughout the application.

Architecture:
    Constants are organized into logical groups to provide:
    - Clear categorization of related values
    - Type safety for constant values
    - Documentation of purpose and usage
    - Easy maintenance and updates

Constant categories:
    git_constants: Git operation defaults, timeouts, and limits
    github_constants: GitHub API configuration and limits
    server_constants: Server configuration defaults and limits
    validation_constants: Validation rules and constraints

Design principles:
    - Immutability: All constants are Final and cannot be modified
    - Documentation: Each constant group and value is documented
    - Type safety: Constants use appropriate types
    - Logical grouping: Related constants are grouped together
    - No magic numbers: All numeric values are named constants

Organization pattern:
    ```python
    class CategoryDefaults:
        \"\"\"Default values for category operations.\"\"\"
        SOME_VALUE: Final[int] = 100
        ANOTHER_VALUE: Final[str] = "default"

    class CategoryLimits:
        \"\"\"Limits and constraints for category operations.\"\"\"
        MAX_ITEMS: Final[int] = 1000
        MIN_TIMEOUT: Final[int] = 1
    ```

Usage examples:
    >>> from mcp_server_git.constants import GitOperationDefaults
    >>> from mcp_server_git.constants import GitHubAPIDefaults
    >>>
    >>> max_log_entries = GitOperationDefaults.MAX_LOG_ENTRIES
    >>> api_timeout = GitHubAPIDefaults.DEFAULT_TIMEOUT_SECONDS
    >>>
    >>> print(f"Fetching {max_log_entries} log entries")
    >>> print(f"API timeout: {api_timeout}s")

Constant validation:
    - Constants are validated at module import time
    - Type annotations ensure correct types
    - Value constraints are documented and enforced
    - Dependencies between constants are clearly marked

Performance considerations:
    - Constants are resolved at import time
    - No runtime overhead for constant access
    - Constants can be optimized by Python interpreter
    - Memory efficient through singleton pattern

See also:
    - configuration: Runtime configuration that may override constants
    - types: Type definitions used in constant declarations
    - validation: Validation rules that use these constants
"""

# Import all constant groups - will be implemented in Task 3
# from .git_constants import *
# from .github_constants import *
# from .server_constants import *
# from .validation_constants import *

# Placeholder exports - will be populated as modules are implemented
__all__ = [
    # Git constants - to be implemented
    # "GitOperationDefaults",
    # "GitTimeouts",
    # "GitSecurityLimits",
    # "GitCommitMessagePatterns",
    # GitHub constants - to be implemented
    # "GitHubAPIDefaults",
    # "GitHubRateLimits",
    # "GitHubWebhookEvents",
    # Server constants - to be implemented
    # "ServerDefaults",
    # "ServerLimits",
    # "LoggingDefaults",
    # Validation constants - to be implemented
    # "ValidationLimits",
    # "ValidationPatterns",
    # "SecurityConstraints",
]
