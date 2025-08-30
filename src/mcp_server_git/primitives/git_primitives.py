"""Git primitive operations for MCP Git Server.

This module provides atomic, indivisible Git operations that serve as the foundation
for higher-level Git functionality. These primitives handle basic Git commands,
repository validation, status parsing, and error handling.

Design Principles:
    - Single responsibility: Each function does exactly one thing
    - No side effects: Functions are pure where possible
    - Clear error handling: Consistent exception patterns
    - Type safety: Comprehensive type hints and validation
    - Performance: Fast execution with minimal overhead

Critical for TDD Compliance:
    This module implements the interface defined by test specifications.
    DO NOT modify tests to match this implementation - this implementation
    must satisfy the test requirements to prevent LLM compliance issues.
"""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# Exception classes for error handling
class GitCommandError(Exception):
    """Raised when a git command fails or is invalid."""

    def __init__(
        self,
        message: str,
        command: list[str] | None = None,
        repo_path: str | None = None,
        return_code: int | None = None,
        stderr: str | None = None,
    ):
        super().__init__(message)
        self.command = command
        self.repo_path = repo_path
        self.return_code = return_code
        self.stderr = stderr


class GitRepositoryError(Exception):
    """Raised when repository operations fail due to repository state."""

    def __init__(
        self,
        message: str,
        repo_path: str | None = None,
        suggested_action: str | None = None,
    ):
        super().__init__(message)
        self.repo_path = repo_path
        self.suggested_action = suggested_action


class GitValidationError(Exception):
    """Raised when validation of git-related data fails."""

    def __init__(
        self,
        message: str,
        field: str | None = None,
        value: Any | None = None,
        validation_rule: str | None = None,
    ):
        super().__init__(message)
        self.field = field
        self.value = value
        self.validation_rule = validation_rule


# Result classes for structured return values
@dataclass
class GitCommandResult:
    """Result of executing a git command."""

    success: bool
    output: str
    error: str | None = None
    return_code: int = 0


@dataclass
class GitStatusParsed:
    """Parsed git status output."""

    modified_files: list[str]
    added_files: list[str]
    deleted_files: list[str]
    untracked_files: list[str]
    renamed_files: list[str]
    copied_files: list[str]


@dataclass
class GitCommitParsed:
    """Parsed git commit information."""

    hash: str
    author_name: str
    author_email: str
    message: str
    date: str


@dataclass
class GitRepositoryStatus:
    """Complete repository status information."""

    is_clean: bool
    modified_files: list[str]
    untracked_files: list[str]
    staged_files: list[str]


@dataclass
class GitValidationResult:
    """Result of repository path validation."""

    is_valid: bool
    absolute_path: Path


@dataclass
class GitFormattedError:
    """Formatted git error with context."""

    message: str
    context: str
    command: list[str]
    suggestion: str | None = None


# Core primitive operations
def execute_git_command(
    repo_path: str, command: list[str], timeout: int = 30
) -> GitCommandResult:
    """Execute a git command in the specified repository.

    Args:
        repo_path: Path to the git repository
        command: Git command arguments (e.g., ['status', '--porcelain'])
        timeout: Command timeout in seconds

    Returns:
        GitCommandResult with success status and output

    Raises:
        GitRepositoryError: If repository path doesn't exist
        GitCommandError: If command is invalid or fails
    """
    # Validate command is not empty
    if not command:
        raise GitCommandError(
            "Invalid git command: command list cannot be empty",
            command=command,
            repo_path=repo_path,
        )

    # Prepare full command
    full_command = ["git"] + command

    try:
        # Execute command
        result = subprocess.run(
            full_command, cwd=repo_path, capture_output=True, text=True, timeout=timeout
        )

        if result.returncode == 0:
            return GitCommandResult(
                success=True,
                output=result.stdout.strip(),
                return_code=result.returncode,
            )
        return GitCommandResult(
            success=False,
            output=result.stdout.strip(),
            error=result.stderr.strip(),
            return_code=result.returncode,
        )

    except subprocess.TimeoutExpired:
        return GitCommandResult(
            success=False,
            output="",
            error=f"timeout: Command timed out after {timeout} seconds",
            return_code=-1,
        )
    except FileNotFoundError as e:
        # Repository path doesn't exist
        raise GitRepositoryError(
            f"Repository path does not exist: {repo_path}",
            repo_path=repo_path,
            suggested_action="Verify the repository path is correct",
        ) from e
    except Exception as e:
        return GitCommandResult(
            success=False,
            output="",
            error=f"Command execution failed: {str(e)}",
            return_code=-1,
        )


def is_git_repository(repo_path: str) -> bool:
    """Check if the given path is a git repository.

    Args:
        repo_path: Path to check

    Returns:
        True if path is a git repository, False otherwise
    """
    repo_path_obj = Path(repo_path)

    # Check if path exists and is a directory
    if not repo_path_obj.exists() or not repo_path_obj.is_dir():
        return False

    # Check for .git directory
    git_dirs = list(repo_path_obj.glob(".git"))
    return len(git_dirs) > 0


def validate_repository_path(repo_path: str) -> GitValidationResult:
    """Validate a repository path and return validation result.

    Args:
        repo_path: Path to validate

    Returns:
        GitValidationResult with validation status and normalized path

    Raises:
        GitValidationError: If path is invalid
    """
    repo_path_obj = Path(repo_path)

    # Check if path exists
    if not repo_path_obj.exists():
        raise GitValidationError(
            f"Invalid repository path: path does not exist - {repo_path}",
            field="repo_path",
            value=repo_path,
            validation_rule="path_must_exist",
        )

    # Check if it's a git repository
    if not is_git_repository(repo_path):
        raise GitValidationError(
            f"Invalid repository path: not a git repository - {repo_path}",
            field="repo_path",
            value=repo_path,
            validation_rule="must_be_git_repository",
        )

    return GitValidationResult(is_valid=True, absolute_path=repo_path_obj.resolve())


def get_repository_status(repo_path: str) -> GitRepositoryStatus:
    """Get the complete status of a git repository.

    Args:
        repo_path: Path to the git repository

    Returns:
        GitRepositoryStatus with file status information
    """
    result = execute_git_command(repo_path, ["status", "--porcelain"])

    if not result.success:
        raise GitRepositoryError(
            f"Failed to get repository status: {result.error}", repo_path=repo_path
        )

    # Parse status output
    parsed = parse_git_status_output(result.output)

    # Determine if repository is clean
    is_clean = (
        len(parsed.modified_files) == 0
        and len(parsed.added_files) == 0
        and len(parsed.deleted_files) == 0
        and len(parsed.untracked_files) == 0
    )

    return GitRepositoryStatus(
        is_clean=is_clean,
        modified_files=parsed.modified_files,
        untracked_files=parsed.untracked_files,
        staged_files=parsed.added_files,
    )


def get_staged_files(repo_path: str) -> list[str]:
    """Get list of staged files in the repository.

    Args:
        repo_path: Path to the git repository

    Returns:
        List of staged file paths
    """
    result = execute_git_command(repo_path, ["status", "--porcelain"])

    if not result.success:
        raise GitRepositoryError(
            f"Failed to get staged files: {result.error}", repo_path=repo_path
        )

    parsed = parse_git_status_output(result.output)
    return parsed.added_files


def get_unstaged_files(repo_path: str) -> list[str]:
    """Get list of unstaged modified files in the repository.

    Args:
        repo_path: Path to the git repository

    Returns:
        List of unstaged modified file paths
    """
    result = execute_git_command(repo_path, ["status", "--porcelain"])

    if not result.success:
        raise GitRepositoryError(
            f"Failed to get unstaged files: {result.error}", repo_path=repo_path
        )

    parsed = parse_git_status_output(result.output)
    return parsed.modified_files + parsed.deleted_files


def get_untracked_files(repo_path: str) -> list[str]:
    """Get list of untracked files in the repository.

    Args:
        repo_path: Path to the git repository

    Returns:
        List of untracked file paths
    """
    result = execute_git_command(repo_path, ["status", "--porcelain"])

    if not result.success:
        raise GitRepositoryError(
            f"Failed to get untracked files: {result.error}", repo_path=repo_path
        )

    parsed = parse_git_status_output(result.output)
    return parsed.untracked_files


def get_current_branch(repo_path: str) -> str | None:
    """Get the current branch name.

    Args:
        repo_path: Path to the git repository

    Returns:
        Current branch name, or None if in detached HEAD state
    """
    result = execute_git_command(repo_path, ["branch", "--show-current"])

    if not result.success:
        raise GitRepositoryError(
            f"Failed to get current branch: {result.error}", repo_path=repo_path
        )

    branch_name = result.output.strip()

    # Check for detached HEAD
    if not branch_name or "detached" in branch_name.lower():
        return None

    return branch_name


def get_commit_hash(repo_path: str, short: bool = False) -> str:
    """Get the current commit hash.

    Args:
        repo_path: Path to the git repository
        short: If True, return short hash format

    Returns:
        Current commit hash
    """
    command = ["rev-parse"]
    if short:
        command.append("--short")
    command.append("HEAD")

    result = execute_git_command(repo_path, command)

    if not result.success:
        raise GitRepositoryError(
            f"Failed to get commit hash: {result.error}", repo_path=repo_path
        )

    return result.output.strip()


def parse_git_status_output(status_output: str) -> GitStatusParsed:
    """Parse git status --porcelain output into categorized file lists.

    Args:
        status_output: Raw git status --porcelain output

    Returns:
        GitStatusParsed with categorized file lists
    """
    modified_files = []
    added_files = []
    deleted_files = []
    untracked_files = []
    renamed_files = []
    copied_files = []

    for line in status_output.split("\n"):
        if not line.strip():
            continue

        # Parse status codes (first two characters)
        status_codes = line[:2]
        filename = line[3:].strip()

        # Handle different status combinations
        if status_codes == "??":
            untracked_files.append(filename)
        elif status_codes[0] == "A":
            added_files.append(filename)
        elif status_codes[0] == "M" or status_codes[1] == "M":
            if status_codes[0] == " ":
                # Unstaged modification
                modified_files.append(filename)
            else:
                # Staged modification
                added_files.append(filename)
        elif status_codes[0] == "D" or status_codes[1] == "D":
            deleted_files.append(filename)
        elif status_codes[0] == "R":
            renamed_files.append(filename)
        elif status_codes[0] == "C":
            copied_files.append(filename)

    return GitStatusParsed(
        modified_files=modified_files,
        added_files=added_files,
        deleted_files=deleted_files,
        untracked_files=untracked_files,
        renamed_files=renamed_files,
        copied_files=copied_files,
    )


def parse_git_log_output(log_output: str) -> list[GitCommitParsed]:
    """Parse git log output into commit information.

    Args:
        log_output: Raw git log output

    Returns:
        List of GitCommitParsed objects
    """
    commits = []
    current_commit = None
    current_message_lines = []

    for line in log_output.split("\n"):
        if line.startswith("commit "):
            # Save previous commit if exists
            if current_commit:
                current_commit.message = "\n".join(current_message_lines).strip()
                commits.append(current_commit)
                current_message_lines = []

            # Start new commit
            commit_hash = line.split(" ")[1]
            current_commit = GitCommitParsed(
                hash=commit_hash, author_name="", author_email="", message="", date=""
            )
        elif line.startswith("Author: ") and current_commit:
            # Parse author line: "Author: Name <email>"
            author_info = line[8:]  # Remove "Author: "
            match = re.match(r"(.+) <(.+)>", author_info)
            if match:
                current_commit.author_name = match.group(1)
                current_commit.author_email = match.group(2)
        elif line.startswith("Date: ") and current_commit:
            current_commit.date = line[6:].strip()  # Remove "Date: "
        elif line.startswith("    ") and current_commit:
            # Commit message line (indented)
            current_message_lines.append(line[4:])  # Remove indentation
        elif line.strip() == "" and current_commit and current_message_lines:
            # Empty line in message
            current_message_lines.append("")

    # Add the last commit
    if current_commit:
        current_commit.message = "\n".join(current_message_lines).strip()
        commits.append(current_commit)

    return commits


def format_git_error(
    raw_error: str, command: list[str], repo_path: str
) -> GitFormattedError:
    """Format a raw git error into a human-readable error with context.

    Args:
        raw_error: Raw error message from git
        command: The git command that failed
        repo_path: Repository path where command was executed

    Returns:
        GitFormattedError with formatted message and suggestions
    """
    # Create human-readable message
    if "not a git repository" in raw_error.lower():
        message = f"The directory '{repo_path}' is not a git repository."
        suggestion = "Initialize a git repository with 'git init' or navigate to an existing repository."
    elif "not found" in raw_error.lower():
        message = f"Git repository or file not found in '{repo_path}'."
        suggestion = "Check that the path exists and contains a valid git repository."
    elif "permission denied" in raw_error.lower():
        message = f"Permission denied accessing git repository at '{repo_path}'."
        suggestion = (
            "Check file permissions and ensure you have access to the repository."
        )
    else:
        message = f"Git operation failed: {raw_error}"
        suggestion = "Check the git command syntax and repository state."

    return GitFormattedError(
        message=message,
        context=f"Command: git {' '.join(command)} (in {repo_path})",
        command=command,
        suggestion=suggestion,
    )
