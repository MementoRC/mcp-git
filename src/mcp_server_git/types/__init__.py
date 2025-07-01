"""Type definitions module for MCP Git Server.

This module contains comprehensive type definitions including domain-specific type
aliases, TypedDict definitions, Literal types, and Protocol definitions that provide
type safety and clarity throughout the codebase.

Architecture:
    Types provide the foundational type system for the entire application:
    - Domain-specific type aliases for clarity
    - Complex structured types using TypedDict
    - Literal types for constrained values
    - Protocol definitions for interfaces

Key type categories:
    git_types: Git-specific types (RepoPath, GitCommitHash, GitBranchName)
    github_types: GitHub-specific types (PRNumber, GitHubToken, WorkflowRunId)
    session_types: Session management types (SessionId, UserId, SessionStatus)
    mcp_types: MCP protocol types (RequestId, ToolName, MessageType)

Type design principles:
    - Semantic clarity: Types convey domain meaning, not just structure
    - Type safety: Prevent common errors through type checking
    - Documentation: Types serve as documentation for data structures
    - Validation: Types support runtime validation where needed
    - Interoperability: Types work well with external libraries

Advanced type features:
    - NewType for domain-specific aliases
    - TypedDict for structured data
    - Literal types for constrained values
    - Union types for flexible parameters
    - Generic types for reusable patterns

Example type definitions:
    ```python
    # Domain-specific type aliases
    RepoPath = NewType('RepoPath', Path)
    GitCommitHash = NewType('GitCommitHash', str)
    PRNumber = NewType('PRNumber', int)
    
    # Structured data types
    class GitCommitInfo(TypedDict):
        hash: GitCommitHash
        author: str
        message: str
        timestamp: datetime
        
    # Constrained value types
    GitOperationStatus = Literal["success", "failure", "timeout"]
    ```

Usage patterns:
    >>> from mcp_server_git.types import RepoPath, GitCommitHash
    >>> from mcp_server_git.types.git_types import GitCommitInfo
    >>> 
    >>> repo_path = RepoPath("/path/to/repository")
    >>> commit_hash = GitCommitHash("a1b2c3d4e5f6...")
    >>> 
    >>> commit_info: GitCommitInfo = {
    ...     "hash": commit_hash,
    ...     "author": "Developer <dev@example.com>",
    ...     "message": "feat: add new feature",
    ...     "timestamp": datetime.now()
    ... }

Type checking:
    - Use mypy for static type checking
    - Runtime validation with pydantic where needed
    - Type guards for complex type narrowing
    - Assertion helpers for type validation

See also:
    - validation: Runtime type validation utilities
    - protocols: Interface definitions and contracts
    - constants: Type-related constants and defaults
"""

# Core type imports
from .git_types import *
from .github_types import *
from .session_types import *
from .mcp_types import *

__all__ = [
    # Git types
    "RepoPath",
    "GitCommitHash", 
    "GitBranchName",
    "GitRemoteName",
    "GitTagName",
    "GitOperationStatus",
    "GitFileStatus",
    "GitCommitInfo",
    "GitRepositoryState",
    
    # GitHub types
    "GitHubToken",
    "GitHubRepoOwner",
    "GitHubRepoName", 
    "PRNumber",
    "WorkflowRunId",
    "GitHubCheckStatus",
    "GitHubPRInfo",
    "GitHubWorkflowInfo",
    
    # Session types
    "SessionId",
    "UserId",
    "SessionStatus",
    "SessionInfo",
    "SessionMetrics",
    
    # MCP types
    "RequestId",
    "ToolName",
    "MessageType",
    "MCPRequest",
    "MCPResponse",
    "MCPError",
]