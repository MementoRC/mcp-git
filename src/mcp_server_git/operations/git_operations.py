"""Git operations module for MCP Git Server.

This module provides higher-level Git operations that build on primitive operations
to provide more complex functionality. Operations combine 2-3 primitives to create
meaningful business logic while maintaining clear boundaries and responsibilities.

Design principles:
    - Composition over inheritance: Build functionality by combining primitives
    - Clear interfaces: Well-defined inputs and outputs
    - Error propagation: Proper handling of primitive errors
    - Transaction safety: Atomic operations where needed
    - Logging: Comprehensive operation logging for debugging

Critical for TDD Compliance:
    This module implements the interface defined by test specifications.
    DO NOT modify tests to match this implementation - this implementation
    must satisfy the test requirements to prevent LLM compliance issues.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..primitives.git_primitives import (
    GitCommandError,
    GitRepositoryError,
    GitValidationError,
    execute_git_command,
    get_commit_hash,
    get_current_branch,
    get_repository_status,
    validate_repository_path,
)

logger = logging.getLogger(__name__)


@dataclass
class CommitRequest:
    """Request parameters for commit operations."""

    message: str
    files: list[str] | None = None
    author: str | None = None
    email: str | None = None
    allow_empty: bool = False
    sign_off: bool = False
    gpg_sign: bool = False
    gpg_key_id: str | None = None


@dataclass
class CommitResult:
    """Result of a commit operation."""

    success: bool
    commit_hash: str | None = None
    message: str = ""
    files_committed: list[str] | None = None
    error: str | None = None


@dataclass
class BranchRequest:
    """Request parameters for branch operations."""

    name: str
    base_branch: str | None = None
    checkout: bool = True
    force: bool = False


@dataclass
class BranchResult:
    """Result of a branch operation."""

    success: bool
    branch_name: str | None = None
    message: str = ""
    previous_branch: str | None = None
    error: str | None = None


@dataclass
class MergeRequest:
    """Request parameters for merge operations."""

    source_branch: str
    target_branch: str | None = None
    message: str | None = None
    no_fast_forward: bool = False
    squash: bool = False


@dataclass
class MergeResult:
    """Result of a merge operation."""

    success: bool
    merge_commit_hash: str | None = None
    message: str = ""
    conflicts: list[str] | None = None
    error: str | None = None


def commit_changes_with_validation(
    repo_path: str | Path, commit_request: CommitRequest
) -> CommitResult:
    """Commit changes to a Git repository with comprehensive validation.

    This operation combines repository validation, status checking, staging,
    and committing into a single atomic operation with proper error handling.

    Args:
        repo_path: Path to the Git repository
        commit_request: Commit parameters including message, files, and options

    Returns:
        CommitResult with success status, commit hash, and details

    Raises:
        GitRepositoryError: If repository is invalid or in bad state
        GitCommandError: If Git commands fail
        GitValidationError: If commit parameters are invalid

    Example:
        >>> repo_path = Path("/path/to/repository")
        >>> commit_request = CommitRequest(
        ...     message="feat: add new feature",
        ...     files=["src/new_feature.py"],
        ...     author="Developer",
        ...     email="dev@example.com"
        ... )
        >>> result = commit_changes_with_validation(repo_path, commit_request)
        >>> print(result.success)
        True
    """
    try:
        logger.info(f"Starting commit operation for repository: {repo_path}")

        # Step 1: Validate repository
        repo_path_str = str(repo_path)
        validate_repository_path(repo_path_str)

        # Step 2: Check repository status
        get_repository_status(repo_path_str)

        # Step 3: Validate commit request
        if not commit_request.message.strip():
            raise GitValidationError("Commit message cannot be empty")

        # Step 4: Stage files if specified
        if commit_request.files:
            for file_path in commit_request.files:
                try:
                    execute_git_command(repo_path_str, ["add", file_path])
                    logger.debug(f"Staged file: {file_path}")
                except GitCommandError as e:
                    logger.error(f"Failed to stage file {file_path}: {e}")
                    return CommitResult(
                        success=False, error=f"Failed to stage file {file_path}: {e}"
                    )

        # Step 5: Build commit command
        commit_cmd = ["commit", "-m", commit_request.message]

        if commit_request.allow_empty:
            commit_cmd.append("--allow-empty")

        if commit_request.sign_off:
            commit_cmd.append("--signoff")

        if commit_request.gpg_sign:
            commit_cmd.append("--gpg-sign")
            if commit_request.gpg_key_id:
                commit_cmd.extend(["-S", commit_request.gpg_key_id])

        if commit_request.author:
            author_string = commit_request.author
            if commit_request.email:
                author_string = f"{commit_request.author} <{commit_request.email}>"
            commit_cmd.extend(["--author", author_string])

        # Step 6: Execute commit
        try:
            execute_git_command(repo_path_str, commit_cmd)
            logger.info("Commit command executed successfully")
        except GitCommandError as e:
            logger.error(f"Commit command failed: {e}")
            return CommitResult(success=False, error=f"Commit failed: {e}")

        # Step 7: Get commit hash
        try:
            commit_hash = get_commit_hash(repo_path_str)
            logger.info(f"Created commit: {commit_hash}")
        except GitCommandError as e:
            logger.warning(f"Could not retrieve commit hash: {e}")
            commit_hash = None

        return CommitResult(
            success=True,
            commit_hash=commit_hash,
            message=f"Successfully committed: {commit_request.message}",
            files_committed=commit_request.files,
        )

    except (GitRepositoryError, GitValidationError, GitCommandError) as e:
        logger.error(f"Commit operation failed: {e}")
        return CommitResult(success=False, error=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during commit: {e}")
        return CommitResult(success=False, error=f"Unexpected error: {e}")


def create_branch_with_checkout(
    repo_path: str | Path, branch_request: BranchRequest
) -> BranchResult:
    """Create a new Git branch with optional checkout.

    This operation combines branch creation, base branch validation, and
    checkout into a single atomic operation with proper error handling.

    Args:
        repo_path: Path to the Git repository
        branch_request: Branch parameters including name, base, and options

    Returns:
        BranchResult with success status, branch name, and details

    Raises:
        GitRepositoryError: If repository is invalid or in bad state
        GitCommandError: If Git commands fail
        GitValidationError: If branch parameters are invalid

    Example:
        >>> repo_path = Path("/path/to/repository")
        >>> branch_request = BranchRequest(
        ...     name="feature/new-feature",
        ...     base_branch="main",
        ...     checkout=True
        ... )
        >>> result = create_branch_with_checkout(repo_path, branch_request)
        >>> print(result.success)
        True
    """
    try:
        logger.info(
            f"Creating branch '{branch_request.name}' in repository: {repo_path}"
        )

        # Step 1: Validate repository
        repo_path_str = str(repo_path)
        validate_repository_path(repo_path_str)

        # Step 2: Get current branch for rollback
        try:
            current_branch = get_current_branch(repo_path_str)
            logger.debug(f"Current branch: {current_branch}")
        except GitCommandError as e:
            logger.warning(f"Could not determine current branch: {e}")
            current_branch = None

        # Step 3: Validate branch name
        if not branch_request.name.strip():
            raise GitValidationError("Branch name cannot be empty")

        # Step 4: Check if branch already exists
        try:
            execute_git_command(
                repo_path_str,
                ["show-ref", "--verify", f"refs/heads/{branch_request.name}"],
            )
            if not branch_request.force:
                return BranchResult(
                    success=False,
                    error=f"Branch '{branch_request.name}' already exists. Use force=True to overwrite.",
                )
        except GitCommandError:
            # Branch doesn't exist, which is what we want
            pass

        # Step 5: Build branch creation command
        if branch_request.base_branch:
            branch_cmd = [
                "checkout",
                "-b",
                branch_request.name,
                branch_request.base_branch,
            ]
        else:
            branch_cmd = ["checkout", "-b", branch_request.name]

        if branch_request.force:
            branch_cmd.insert(1, "-B")  # Force branch creation

        # Step 6: Create and optionally checkout branch
        if branch_request.checkout:
            try:
                execute_git_command(repo_path_str, branch_cmd)
                logger.info(f"Created and checked out branch: {branch_request.name}")
            except GitCommandError as e:
                logger.error(f"Failed to create/checkout branch: {e}")
                return BranchResult(
                    success=False,
                    error=f"Failed to create branch: {e}",
                    previous_branch=current_branch,
                )
        else:
            # Create branch without checkout
            create_cmd = ["branch", branch_request.name]
            if branch_request.base_branch:
                create_cmd.append(branch_request.base_branch)
            if branch_request.force:
                create_cmd.insert(1, "-f")

            try:
                execute_git_command(repo_path_str, create_cmd)
                logger.info(f"Created branch: {branch_request.name}")
            except GitCommandError as e:
                logger.error(f"Failed to create branch: {e}")
                return BranchResult(
                    success=False,
                    error=f"Failed to create branch: {e}",
                    previous_branch=current_branch,
                )

        return BranchResult(
            success=True,
            branch_name=branch_request.name,
            message=f"Successfully created branch: {branch_request.name}",
            previous_branch=current_branch,
        )

    except (GitRepositoryError, GitValidationError, GitCommandError) as e:
        logger.error(f"Branch creation failed: {e}")
        return BranchResult(success=False, error=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during branch creation: {e}")
        return BranchResult(success=False, error=f"Unexpected error: {e}")


def merge_branches_with_conflict_detection(
    repo_path: str | Path, merge_request: MergeRequest
) -> MergeResult:
    """Merge Git branches with comprehensive conflict detection and handling.

    This operation combines branch validation, conflict detection, merging,
    and result reporting into a single atomic operation.

    Args:
        repo_path: Path to the Git repository
        merge_request: Merge parameters including source, target, and options

    Returns:
        MergeResult with success status, merge commit, and conflict details

    Raises:
        GitRepositoryError: If repository is invalid or in bad state
        GitCommandError: If Git commands fail
        GitValidationError: If merge parameters are invalid

    Example:
        >>> repo_path = Path("/path/to/repository")
        >>> merge_request = MergeRequest(
        ...     source_branch="feature/new-feature",
        ...     target_branch="main",
        ...     message="Merge feature/new-feature into main"
        ... )
        >>> result = merge_branches_with_conflict_detection(repo_path, merge_request)
        >>> print(result.success)
        True
    """
    try:
        logger.info(
            f"Merging '{merge_request.source_branch}' in repository: {repo_path}"
        )

        # Step 1: Validate repository
        repo_path_str = str(repo_path)
        validate_repository_path(repo_path_str)

        # Step 2: Get current branch
        try:
            current_branch = get_current_branch(repo_path_str)
            logger.debug(f"Current branch: {current_branch}")
        except GitCommandError as e:
            logger.error(f"Could not determine current branch: {e}")
            return MergeResult(
                success=False, error=f"Could not determine current branch: {e}"
            )

        # Step 3: Validate merge request
        if not merge_request.source_branch.strip():
            raise GitValidationError("Source branch cannot be empty")

        # Step 4: Checkout target branch if specified
        if (
            merge_request.target_branch
            and merge_request.target_branch != current_branch
        ):
            try:
                execute_git_command(
                    repo_path_str, ["checkout", merge_request.target_branch]
                )
                logger.info(f"Checked out target branch: {merge_request.target_branch}")
            except GitCommandError as e:
                logger.error(f"Failed to checkout target branch: {e}")
                return MergeResult(
                    success=False,
                    error=f"Failed to checkout target branch '{merge_request.target_branch}': {e}",
                )

        # Step 5: Check if source branch exists
        try:
            execute_git_command(
                repo_path_str,
                ["show-ref", "--verify", f"refs/heads/{merge_request.source_branch}"],
            )
        except GitCommandError:
            return MergeResult(
                success=False,
                error=f"Source branch '{merge_request.source_branch}' does not exist",
            )

        # Step 6: Build merge command
        merge_cmd = ["merge"]

        if merge_request.no_fast_forward:
            merge_cmd.append("--no-ff")

        if merge_request.squash:
            merge_cmd.append("--squash")

        if merge_request.message:
            merge_cmd.extend(["-m", merge_request.message])

        merge_cmd.append(merge_request.source_branch)

        # Step 7: Execute merge
        try:
            execute_git_command(repo_path_str, merge_cmd)
            logger.info("Merge command executed successfully")
        except GitCommandError as e:
            # Check if this is a merge conflict
            if "conflict" in str(e).lower() or "merge conflict" in str(e).lower():
                # Get list of conflicted files
                try:
                    status_result = get_repository_status(repo_path_str)
                    conflict_files = []
                    if hasattr(status_result, "conflicted_files"):
                        conflict_files = status_result.conflicted_files

                    logger.warning(
                        f"Merge conflicts detected in files: {conflict_files}"
                    )
                    return MergeResult(
                        success=False,
                        conflicts=conflict_files,
                        error=f"Merge conflicts detected: {e}",
                    )
                except Exception:
                    return MergeResult(
                        success=False,
                        conflicts=["Unknown files"],
                        error=f"Merge conflicts detected: {e}",
                    )
            else:
                logger.error(f"Merge command failed: {e}")
                return MergeResult(success=False, error=f"Merge failed: {e}")

        # Step 8: Get merge commit hash
        merge_commit_hash = None
        if (
            not merge_request.squash
        ):  # Squash merges don't create merge commits immediately
            try:
                merge_commit_hash = get_commit_hash(repo_path_str)
                logger.info(f"Merge commit created: {merge_commit_hash}")
            except GitCommandError as e:
                logger.warning(f"Could not retrieve merge commit hash: {e}")

        return MergeResult(
            success=True,
            merge_commit_hash=merge_commit_hash,
            message=f"Successfully merged '{merge_request.source_branch}'",
        )

    except (GitRepositoryError, GitValidationError, GitCommandError) as e:
        logger.error(f"Merge operation failed: {e}")
        return MergeResult(success=False, error=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during merge: {e}")
        return MergeResult(success=False, error=f"Unexpected error: {e}")


def push_with_validation(
    repo_path: str | Path,
    remote: str = "origin",
    branch: str | None = None,
    force: bool = False,
    set_upstream: bool = False,
) -> dict[str, Any]:
    """Push changes to remote repository with comprehensive validation.

    This operation combines repository validation, remote checking, branch
    validation, and pushing into a single atomic operation.

    Args:
        repo_path: Path to the Git repository
        remote: Remote name (default: "origin")
        branch: Branch name (default: current branch)
        force: Force push (default: False)
        set_upstream: Set upstream tracking (default: False)

    Returns:
        Dictionary with success status and operation details

    Raises:
        GitRepositoryError: If repository is invalid or in bad state
        GitCommandError: If Git commands fail
        GitValidationError: If push parameters are invalid

    Example:
        >>> repo_path = Path("/path/to/repository")
        >>> result = push_with_validation(
        ...     repo_path,
        ...     remote="origin",
        ...     branch="main",
        ...     set_upstream=True
        ... )
        >>> print(result["success"])
        True
    """
    try:
        logger.info(f"Pushing to remote '{remote}' from repository: {repo_path}")

        # Step 1: Validate repository
        repo_path_str = str(repo_path)
        validate_repository_path(repo_path_str)

        # Step 2: Get current branch if not specified
        if branch is None:
            try:
                branch = get_current_branch(repo_path_str)
                logger.debug(f"Using current branch: {branch}")
            except GitCommandError as e:
                logger.error(f"Could not determine current branch: {e}")
                return {
                    "success": False,
                    "error": f"Could not determine current branch: {e}",
                }

        # Step 3: Validate remote exists
        try:
            execute_git_command(repo_path_str, ["remote", "get-url", remote])
            logger.debug(f"Remote '{remote}' validated")
        except GitCommandError as e:
            logger.error(f"Remote '{remote}' not found: {e}")
            return {
                "success": False,
                "error": f"Remote '{remote}' not found: {e}",
                "remote": remote,
            }

        # Step 4: Check repository status
        try:
            get_repository_status(repo_path_str)
            logger.debug("Repository status checked")
        except GitCommandError as e:
            logger.warning(f"Could not check repository status: {e}")

        # Step 5: Build push command
        push_cmd = ["push"]

        if force:
            push_cmd.append("--force")

        if set_upstream:
            push_cmd.extend(["--set-upstream", remote, branch])  # type: ignore[list-item]
        else:
            push_cmd.extend([remote, branch])  # type: ignore[list-item]

        # Step 6: Execute push
        try:
            execute_git_command(repo_path_str, push_cmd)
            logger.info(f"Successfully pushed '{branch}' to '{remote}'")

            return {
                "success": True,
                "message": f"Successfully pushed '{branch}' to '{remote}'",
                "remote": remote,
                "branch": branch,
                "force": force,
                "set_upstream": set_upstream,
            }

        except GitCommandError as e:
            logger.error(f"Push command failed: {e}")
            return {
                "success": False,
                "error": f"Push failed: {e}",
                "remote": remote,
                "branch": branch,
            }

    except (GitRepositoryError, GitValidationError, GitCommandError) as e:
        logger.error(f"Push operation failed: {e}")
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"Unexpected error during push: {e}")
        return {"success": False, "error": f"Unexpected error: {e}"}
