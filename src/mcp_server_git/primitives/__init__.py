"""Primitive operations module for MCP Git Server.

This module contains atomic, indivisible operations that serve as the foundation
for higher-level functionality in the MCP Git Server. These primitives handle
basic Git commands, GitHub API calls, validation, and type operations.

Architecture:
    Primitives represent the lowest level in the 5-level hierarchy:
    Level 1: Atoms (Primitives) - Basic, indivisible units
    - Pure functions with single operations
    - Basic data structures
    - Fundamental utilities

Key components:
    git_primitives: Atomic Git operations (status, add, commit basics)
    github_primitives: Basic GitHub API calls (GET, POST, authentication)
    validation_primitives: Core validation functions (type checking, format validation)
    type_primitives: Fundamental type operations and conversions

Design principles:
    - Single responsibility: Each function does exactly one thing
    - No side effects: Functions are pure where possible
    - Clear error handling: Consistent exception patterns
    - Type safety: Comprehensive type hints and validation
    - Documentation: Every function fully documented with examples

Performance characteristics:
    - Fast execution: Operations complete in < 100ms typically
    - Low memory usage: Minimal object creation
    - Stateless: No persistent state between calls

Example usage:
    >>> from mcp_server_git.primitives import git_primitives
    >>> from mcp_server_git.types import RepoPath
    >>> 
    >>> repo_path = RepoPath("/path/to/repository")
    >>> status = git_primitives.get_repository_status(repo_path)
    >>> print(status.is_clean)
    False

See also:
    - operations: Higher-level operations that combine primitives
    - types: Type definitions used by primitives
    - constants: Constants and configuration values
"""

__all__ = [
    # Git primitive operations
    "git_primitives",
    
    # GitHub primitive operations  
    "github_primitives",
    
    # Validation primitive operations
    "validation_primitives",
    
    # Type primitive operations
    "type_primitives",
]