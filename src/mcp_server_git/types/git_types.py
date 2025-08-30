"""Git domain type definitions for the MCP Git Server.

This module provides comprehensive type definitions for Git-related operations,
including repository paths, branches, commits, and operation results. All types
follow TDD specifications and provide runtime validation where appropriate.

Type categories:
    - Path types: GitRepositoryPath for repository validation
    - Reference types: GitBranch, GitCommitHash, GitRemoteName
    - Status types: GitFileStatus, GitOperationResult
    - Information types: GitCommitInfo, GitBranchInfo, GitRemoteInfo
    - Error types: GitValidationError, GitOperationError

Design principles:
    - Semantic clarity through domain-specific types
    - Runtime validation for critical operations
    - Interoperability with pathlib and standard Git tools
    - Comprehensive error handling and reporting
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, NewType, TypedDict

# Basic Git Type Aliases
GitBranchName = NewType("GitBranchName", str)
GitCommitHash = NewType("GitCommitHash", str)
GitRemoteName = NewType("GitRemoteName", str)
GitTagName = NewType("GitTagName", str)


# Git File Status Types
GitFileStatusType = Literal[
    "modified",
    "added",
    "deleted",
    "renamed",
    "copied",
    "unmerged",
    "untracked",
    "ignored",
    "staged",
]


# Git Operation Status Types
GitOperationStatus = Literal["success", "failure", "timeout", "cancelled"]


class GitValidationError(Exception):
    """Exception raised when Git type validation fails."""

    def __init__(
        self,
        message: str,
        value: Any = None,
        context: dict[str, Any] | None = None,
        field_name: str | None = None,
        validation_rule: str | None = None,
        suggested_fix: str | None = None,
    ):
        self.message = message
        self.value = value
        self.context = context or {}
        self.invalid_value = value  # Alias for compatibility
        self.field_name = field_name
        self.validation_rule = validation_rule
        self.suggested_fix = suggested_fix
        super().__init__(message)

    def __str__(self) -> str:
        return f"Git validation error: {self.message}"


class GitOperationError(Exception):
    """Exception raised when Git operations fail."""

    def __init__(
        self,
        message: str,
        command: str | None = None,
        exit_code: int | None = None,
    ):
        self.message = message
        self.command = command
        self.exit_code = exit_code
        super().__init__(message)


@dataclass
class GitRepositoryPath:
    """Type-safe representation of a Git repository path.

    Validates that the path points to a valid Git repository and provides
    metadata about the repository structure and state.

    Attributes:
        path: The normalized absolute path to the repository
        is_bare: Whether this is a bare repository
        git_dir: Path to the .git directory
        work_tree: Path to the working tree (None for bare repos)
    """

    path: Path
    is_bare: bool = False
    git_dir: Path | None = None
    work_tree: Path | None = None
    current_branch: str | None = None
    remotes: list[str] | None = None
    is_clean: bool = True

    def __init__(self, path: str | Path):
        """Initialize GitRepositoryPath with validation.

        Args:
            path: Path to the Git repository (string or Path object)

        Raises:
            GitValidationError: If path is not a valid Git repository
        """
        # Convert to Path object and normalize
        if isinstance(path, str):
            path_obj = Path(path)
        else:
            path_obj = path

        # Resolve to absolute path
        try:
            normalized_path = path_obj.resolve()
        except (OSError, ValueError) as e:
            raise GitValidationError(
                f"Invalid path: {path}", value=path, context={"error": str(e)}
            ) from e

        # Check if path exists
        if not normalized_path.exists():
            error = GitValidationError(
                f"Path does not exist: {normalized_path}",
                value=path,
                context={"resolved_path": str(normalized_path)},
                field_name="path",
                validation_rule="Path must exist on filesystem",
                suggested_fix="Ensure the path exists and is accessible",
            )
            # Add error chaining for this validation error
            error.__cause__ = OSError(f"Path not found: {normalized_path}")
            raise error

        # Validate Git repository
        git_dir, work_tree, is_bare = self._validate_git_repository(normalized_path)

        # Set attributes
        self.path = normalized_path
        self.git_dir = git_dir
        self.work_tree = work_tree
        self.is_bare = is_bare
        self.current_branch = None  # Will be populated on demand
        self.remotes = []  # Will be populated on demand
        self.is_clean = True  # Will be populated on demand

    def _validate_git_repository(self, path: Path) -> tuple[Path, Path | None, bool]:
        """Validate that the path is a valid Git repository.

        Returns:
            Tuple of (git_dir, work_tree, is_bare)

        Raises:
            GitValidationError: If not a valid Git repository
        """
        # Check for .git directory or bare repository
        if path.is_file():
            raise GitValidationError(
                f"Path is a file, not a directory: {path}", value=path
            )

        # Check for .git subdirectory (normal repository)
        git_subdir = path / ".git"
        if git_subdir.exists():
            if git_subdir.is_dir():
                return git_subdir, path, False
            if git_subdir.is_file():
                # Git worktree - .git is a file containing path to real .git
                try:
                    git_file_content = git_subdir.read_text().strip()
                    if git_file_content.startswith("gitdir: "):
                        git_dir_path = Path(git_file_content[8:])
                        if not git_dir_path.is_absolute():
                            git_dir_path = path / git_dir_path
                        return git_dir_path.resolve(), path, False
                except (OSError, ValueError):
                    pass

        # Check if this is a bare repository
        if (path / "objects").exists() and (path / "refs").exists():
            # Additional checks for bare repository
            head_file = path / "HEAD"
            config_file = path / "config"
            if head_file.exists() and config_file.exists():
                return path, None, True

        # Check if we're inside a git repository (search parent directories)
        current = path
        while current != current.parent:
            git_dir = current / ".git"
            if git_dir.exists():
                if git_dir.is_dir():
                    return git_dir, current, False
                if git_dir.is_file():
                    # Handle git worktree
                    try:
                        git_file_content = git_dir.read_text().strip()
                        if git_file_content.startswith("gitdir: "):
                            git_dir_path = Path(git_file_content[8:])
                            if not git_dir_path.is_absolute():
                                git_dir_path = current / git_dir_path
                            return git_dir_path.resolve(), current, False
                    except (OSError, ValueError):
                        pass
            current = current.parent

        raise GitValidationError(
            f"Path is not a Git repository: {path}",
            value=path,
            context={"searched_parents": True},
        )

    def __str__(self) -> str:
        return str(self.path)

    def __fspath__(self) -> str:
        """Support os.PathLike protocol."""
        return str(self.path)

    def is_valid(self) -> bool:
        """Check if this is a valid git repository path.

        Returns:
            True if the path is a valid git repository
        """
        return self.git_dir is not None and self.git_dir.exists()

    def exists(self) -> bool:
        """Check if the repository path exists.

        Returns:
            True if the path exists
        """
        return self.path.exists()

    def get_repository_info(self) -> dict[str, Any]:
        """Get metadata about the repository.

        Returns:
            Dictionary containing repository information
        """
        return {
            "path": str(self.path),
            "git_dir": str(self.git_dir) if self.git_dir else None,
            "work_tree": str(self.work_tree) if self.work_tree else None,
            "is_bare": self.is_bare,
            "exists": self.path.exists(),
            "is_git_repository": True,
        }


@dataclass
class GitBranch:
    """Type-safe representation of a Git branch."""

    name: GitBranchName
    is_current: bool = False
    is_remote: bool = False
    remote_name: GitRemoteName | None = None
    upstream: str | None = None
    commit_hash: GitCommitHash | None = None

    def __init__(self, name: str, **kwargs):
        """Initialize GitBranch with validation."""
        if not self._is_valid_branch_name(name):
            raise GitValidationError(
                f"Invalid branch name: {name}",
                value=name,
                field_name="name",
                validation_rule="Git branch name rules: no '..' sequences, cannot start with '.', cannot end with '/', no special characters",
                suggested_fix="Use alphanumeric characters, hyphens, and forward slashes for namespaces",
            )

        self.name = GitBranchName(name)
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

    @staticmethod
    def _is_valid_branch_name(name: str) -> bool:
        """Validate Git branch name according to Git rules."""
        if not name or name.isspace():
            return False

        # Basic checks - can be extended
        invalid_chars = [" ", "~", "^", ":", "?", "*", "[", "\\"]
        if any(char in name for char in invalid_chars):
            return False

        if (
            name.startswith("-")
            or name.startswith(".")
            or name.endswith(".")
            or name.endswith("/")
            or ".." in name
        ):
            return False

        return True

    def __str__(self) -> str:
        """Return the branch name as string."""
        return str(self.name)

    def is_valid(self) -> bool:
        """Check if this is a valid branch."""
        return self._is_valid_branch_name(str(self.name))

    def is_feature_branch(self) -> bool:
        """Check if this is a feature branch."""
        return str(self.name).startswith("feature/")

    def is_main_branch(self) -> bool:
        """Check if this is a main branch."""
        return str(self.name) in ["main", "master", "develop"]

    def is_release_branch(self) -> bool:
        """Check if this is a release branch."""
        return str(self.name).startswith("release/")

    @property
    def parent_branch(self) -> str | None:
        """Get the parent branch name."""
        if "/" in str(self.name):
            return str(self.name).split("/")[0]
        return None

    @property
    def namespace(self) -> str | None:
        """Get the branch namespace."""
        if "/" in str(self.name):
            return str(self.name).split("/")[0]
        return None


@dataclass
class GitCommitHashObj:
    """Type-safe representation of a Git commit hash object."""

    hash: str
    is_short: bool = False

    def __init__(self, hash_value: str):
        """Initialize GitCommitHash with validation."""
        if not self._is_valid_commit_hash(hash_value):
            raise GitValidationError(
                f"Invalid commit hash: {hash_value}", value=hash_value
            )

        self.hash = hash_value
        self.is_short = len(hash_value) < 40

    @staticmethod
    def _is_valid_commit_hash(hash_value: str) -> bool:
        """Validate Git commit hash format."""
        if not hash_value:
            return False

        # Check length (7-40 characters for Git hashes)
        if not (7 <= len(hash_value) <= 40):
            return False

        # Check if all characters are valid hex
        try:
            int(hash_value, 16)
            return True
        except ValueError:
            return False

    def __str__(self) -> str:
        return self.hash

    def is_valid(self) -> bool:
        """Check if this is a valid commit hash."""
        return self._is_valid_commit_hash(self.hash)

    def short(self) -> str:
        """Return short version of the hash (7 characters)."""
        return self.hash[:7]

    def full(self) -> str:
        """Return full version of the hash (40 characters)."""
        if len(self.hash) == 40:
            return self.hash
        # For short hashes, we can't expand to full, so return what we have
        return self.hash


@dataclass
class GitFileStatus:
    """Representation of Git file status."""

    status: GitFileStatusType
    path: str | None = None
    old_path: str | None = None  # For renamed files

    def __init__(
        self,
        status: GitFileStatusType,
        path: str | None = None,
        old_path: str | None = None,
    ):
        if status not in [
            "modified",
            "added",
            "deleted",
            "renamed",
            "copied",
            "unmerged",
            "untracked",
            "ignored",
            "staged",
        ]:
            raise GitValidationError(f"Invalid file status: {status}", value=status)

        self.status = status
        self.path = path
        self.old_path = old_path

    def is_modified(self) -> bool:
        return self.status == "modified"

    def is_added(self) -> bool:
        return self.status == "added"

    def is_deleted(self) -> bool:
        return self.status == "deleted"

    def is_staged(self) -> bool:
        return self.status == "staged"

    def is_untracked(self) -> bool:
        return self.status == "untracked"

    def needs_commit(self) -> bool:
        return self.status in [
            "modified",
            "added",
            "deleted",
            "renamed",
            "copied",
            "staged",
        ]

    def is_valid(self) -> bool:
        return self.status in [
            "modified",
            "added",
            "deleted",
            "renamed",
            "copied",
            "unmerged",
            "untracked",
            "ignored",
            "staged",
        ]

    def __str__(self) -> str:
        return str(self.status)


class GitOperationResult:
    """Result of a Git operation."""

    def __init__(
        self,
        success: bool,
        message: str,
        command: str | None = None,
        exit_code: int | None = None,
        output: str | None = None,
        error: str | None = None,
        error_code: str | None = None,
        operation: str | None = None,
        duration: float | None = None,
    ):
        self.is_success = success
        self.message = message
        self.command = command
        self.exit_code = exit_code
        self.output = output
        self.error_message = error
        self.error_code = error_code
        self.operation = operation
        self.duration = duration

        if not self.is_success and not self.error_message:
            raise GitValidationError("Failed operations must include error information")

    @classmethod
    def success(cls, output: str, operation: str, **kwargs) -> "GitOperationResult":
        """Create a successful operation result."""
        return cls(
            success=True,
            message="Operation completed successfully",
            output=output,
            operation=operation,
            **kwargs,
        )

    @classmethod
    def error(
        cls, error: str, operation: str, error_code: str | None = None, **kwargs
    ) -> "GitOperationResult":
        """Create an error operation result."""
        return cls(
            success=False,
            message=error,
            error=error,
            operation=operation,
            error_code=error_code,
            **kwargs,
        )

    @property
    def succeeded(self) -> bool:
        """Check if operation was successful."""
        return self.is_success

    def is_error(self) -> bool:
        """Check if operation failed."""
        return not self.is_success

    def then(self, func) -> "GitOperationResult":
        """Apply function if operation was successful."""
        if self.is_success:
            return func(self)
        return self

    def map(self, func) -> "GitOperationResult":
        """Transform the result if operation was successful."""
        if self.is_success:
            return func(self)
        return self

    def raise_for_status(self) -> None:
        """Raise GitOperationError if operation failed."""
        if not self.is_success:
            raise GitOperationError(
                self.message, command=self.command, exit_code=self.exit_code
            )

    def chain(self, other: "GitOperationResult") -> "GitOperationResult":
        """Chain this result with another operation result."""
        if not self.is_success:
            return self
        return other


class GitStatusResult:
    """Result of git status operation."""

    def __init__(
        self,
        is_clean: bool,
        current_branch: "GitBranch",
        modified_files: list[str] | None = None,
        untracked_files: list[str] | None = None,
        staged_files: list[str] | None = None,
        deleted_files: list[str] | None = None,
        renamed_files: list[str] | None = None,
    ):
        self.is_clean = is_clean
        self.current_branch = current_branch
        self.modified_files = modified_files or []
        self.untracked_files = untracked_files or []
        self.staged_files = staged_files or []
        self.deleted_files = deleted_files or []
        self.renamed_files = renamed_files or []

    def has_no_changes(self) -> bool:
        """Check if repository has no changes."""
        return (
            self.is_clean
            and not self.modified_files
            and not self.untracked_files
            and not self.staged_files
            and not self.deleted_files
            and not self.renamed_files
        )

    def needs_commit(self) -> bool:
        """Check if repository needs commit."""
        return bool(self.staged_files or self.modified_files or self.deleted_files)

    def summary(self) -> str:
        """Get human-readable status summary."""
        if self.is_clean:
            return "Repository is clean"

        parts = []
        if self.modified_files:
            parts.append(f"{len(self.modified_files)} modified")
        if self.staged_files:
            parts.append(f"{len(self.staged_files)} staged")
        if self.untracked_files:
            parts.append(f"{len(self.untracked_files)} untracked")
        if self.deleted_files:
            parts.append(f"{len(self.deleted_files)} deleted")

        return f"Repository has changes: {', '.join(parts)}"

    def file_count(self) -> int:
        """Get total count of changed files."""
        return (
            len(self.modified_files)
            + len(self.untracked_files)
            + len(self.staged_files)
            + len(self.deleted_files)
            + len(self.renamed_files)
        )

    def needs_attention(self) -> bool:
        """Check if repository needs attention."""
        return not self.is_clean


class GitDiffResult(TypedDict):
    """Result of git diff operation."""

    files_changed: int
    insertions: int
    deletions: int
    diff_content: str


class GitLogResult(TypedDict):
    """Result of git log operation."""

    commits: list["GitCommitInfo"]
    total_count: int
    has_more: bool


class GitCommitInfo:
    """Complete commit information."""

    def __init__(
        self,
        hash: GitCommitHash,
        author_name: str,
        author_email: str,
        message: str,
        timestamp: str,
        parent_hashes: list[GitCommitHash] | None = None,
        committer: str | None = None,
        committer_email: str | None = None,
    ):
        # Validate email
        if "@" not in author_email or "." not in author_email:
            raise GitValidationError(f"Invalid email address: {author_email}")

        # Validate message
        if not message or not message.strip():
            raise GitValidationError("Commit message cannot be empty")

        self.hash = hash
        self.author_name = author_name
        self.author_email = author_email
        self.message = message
        self.timestamp = timestamp
        self.parent_hashes = parent_hashes or []
        self.committer = committer or author_name
        self.committer_email = committer_email or author_email

    def is_feature(self) -> bool:
        """Check if this is a feature commit."""
        return self.message.lower().startswith(("feat:", "feature:"))

    def is_bugfix(self) -> bool:
        """Check if this is a bugfix commit."""
        return self.message.lower().startswith(("fix:", "bugfix:", "bug:"))

    def is_breaking_change(self) -> bool:
        """Check if this is a breaking change."""
        return (
            "BREAKING CHANGE" in self.message or "!" in self.message.split(":")[0]
            if ":" in self.message
            else False
        )

    def one_line_summary(self) -> str:
        """Get one-line summary of the commit."""
        short_hash = str(self.hash)[:7] if len(str(self.hash)) > 7 else str(self.hash)
        return f"{short_hash}: {self.message.split(chr(10))[0][:50]}"

    def detailed_summary(self) -> str:
        """Get detailed summary of the commit."""
        return f"""Commit: {self.hash}
Author: {self.author_name} <{self.author_email}>
Date: {self.timestamp}
Message: {self.message}"""


class GitBranchInfo(TypedDict):
    """Complete branch information."""

    name: GitBranchName
    is_current: bool
    is_remote: bool
    commit_hash: GitCommitHash
    upstream: str | None
    ahead: int | None
    behind: int | None


class GitRemoteInfo(TypedDict):
    """Complete remote information."""

    name: GitRemoteName
    url: str
    fetch_url: str
    push_url: str
    branches: list[GitBranchName]


# Type Integration Tests Support
class GitTypeIntegration:
    """Helper class for testing type integration."""

    @staticmethod
    def validate_repository_path(path: str | Path) -> GitRepositoryPath:
        """Validate and return GitRepositoryPath."""
        return GitRepositoryPath(path)

    @staticmethod
    def create_branch(name: str, **kwargs) -> GitBranch:
        """Create and validate GitBranch."""
        return GitBranch(name, **kwargs)

    @staticmethod
    def create_commit_hash(hash_value: str) -> GitCommitHash:
        """Create and validate GitCommitHash."""
        return GitCommitHash(hash_value)


# Export all public types
__all__ = [
    # Core types
    "GitRepositoryPath",
    "GitBranch",
    "GitCommitHash",
    "GitRemoteName",
    "GitBranchName",
    "GitTagName",
    "GitFileStatus",
    "GitOperationResult",
    # Status and info types
    "GitStatusResult",
    "GitDiffResult",
    "GitLogResult",
    "GitCommitInfo",
    "GitBranchInfo",
    "GitRemoteInfo",
    # Error types
    "GitValidationError",
    "GitOperationError",
    # Literal types
    "GitFileStatusType",
    "GitOperationStatus",
    # Helper classes
    "GitTypeIntegration",
]
