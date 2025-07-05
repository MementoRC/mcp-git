"""
Unit tests for the domain-specific type system.

This package contains comprehensive test specifications that define the behavioral
requirements for all type definitions in the MCP Git server.

Test Structure:
- test_git_types.py: Git domain type specifications
- test_github_types.py: GitHub API type specifications  
- test_mcp_types.py: MCP protocol type specifications
- test_validation_types.py: Validation and error handling specifications

All tests in this package follow TDD principles:
- Tests define requirements and are IMMUTABLE once complete
- Implementation must satisfy these test specifications
- Tests should fail initially (RED phase) until implementation is complete
"""