"""Operations module for MCP Git Server.

This module contains simple compositions of primitive operations that provide
more complex functionality while maintaining clear boundaries and responsibilities.
Operations build on primitives to create meaningful business logic.

Architecture:
    Operations represent the second level in the 5-level hierarchy:
    Level 2: Molecules (Combinations) - Simple compositions
    - Functions combining 2-3 atoms (primitives)
    - Small classes with limited methods
    - Basic patterns and workflows

Key components:
    git_operations: Git workflow operations (commit with validation, push with checks)
    github_operations: GitHub workflow operations (PR creation, status checks)
    session_operations: Session management operations (create, validate, cleanup)
    notification_operations: Notification handling operations (send, validate, route)

Design principles:
    - Composition over inheritance: Build functionality by combining primitives
    - Clear interfaces: Well-defined inputs and outputs
    - Error propagation: Proper handling of primitive errors
    - Transaction safety: Atomic operations where needed
    - Logging: Comprehensive operation logging for debugging

Integration points:
    - Depends on: primitives, types, constants
    - Used by: services, frameworks, applications
    - Configuration: Uses configuration for operation parameters
    - State management: May maintain operation context

Performance considerations:
    - Moderate complexity: Operations may take 1-10 seconds
    - Resource management: Proper cleanup of resources
    - Concurrency: Thread-safe operation design
    - Caching: Strategic caching of expensive operations

Example usage:
    >>> from mcp_server_git.operations import git_operations
    >>> from mcp_server_git.types import RepoPath, GitCommitRequest
    >>>
    >>> repo_path = RepoPath("/path/to/repository")
    >>> commit_request = GitCommitRequest(
    ...     message="feat: add new feature",
    ...     files=["src/new_feature.py"],
    ...     author="Developer <dev@example.com>"
    ... )
    >>>
    >>> result = git_operations.commit_changes_with_validation(
    ...     repo_path, commit_request
    ... )
    >>> print(result.success)
    True

See also:
    - primitives: Atomic operations used to build these operations
    - services: Higher-level services that orchestrate operations
    - types: Type definitions for operation parameters and results
"""

# Placeholder exports - will be populated as modules are implemented
__all__ = [
    # Git operations - to be implemented in Task 21
    # "git_operations",
    # GitHub operations - to be implemented in Task 22
    # "github_operations",
    # Session operations - to be implemented
    # "session_operations",
    # Notification operations - to be implemented
    # "notification_operations",
]
