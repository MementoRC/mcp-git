"""
Protected Git Operations with Repository Binding.

This module provides git operations that are protected by repository binding validation.
All operations validate the repository path matches the bound repository and check
for remote contamination before proceeding.

This prevents cross-session contamination by ensuring operations only work on
the bound repository with the expected remote URL.
"""

import logging
from pathlib import Path

# Safe git import that handles ClaudeCode redirector conflicts
from .utils.git_import import Repo

# Configuration constants
DEFAULT_CONFIRMATION_TOKEN = "CONFIRM_REMOTE_CHANGE"

__all__ = [
    "ProtectedGitOperations",
    "DEFAULT_CONFIRMATION_TOKEN",
]

from .git.operations import (
    git_add,
    git_checkout,
    git_commit,
    git_create_branch,
    git_diff,
    git_diff_staged,
    git_diff_unstaged,
    git_log,
    git_pull,
    git_push,
    git_remote_add,
    git_remote_get_url,
    git_remote_list,
    git_remote_remove,
    git_reset,
    git_show,
    git_status,
)
from .repository_binding import (
    RemoteContaminationError,
    RemoteProtectionError,
    RepositoryBindingManager,
)

logger = logging.getLogger(__name__)


class ProtectedGitOperations:
    """Git operations with repository binding protection."""

    def __init__(
        self,
        binding_manager: RepositoryBindingManager,
        confirmation_token: str = DEFAULT_CONFIRMATION_TOKEN,
    ):
        self.binding_manager = binding_manager
        self.confirmation_token = confirmation_token

    async def _validate_and_prepare_operation(self, repo_path: str | Path) -> Path:
        """
        Validate operation is allowed and prepare for execution.

        Args:
            repo_path: Repository path for operation

        Returns:
            Validated and normalized repository path

        Raises:
            RepositoryBindingError: If operation not allowed
            RemoteContaminationError: If remote contaminated
        """
        operation_path = Path(repo_path).resolve()

        # Validate operation path matches binding
        self.binding_manager.validate_operation_path(operation_path)

        # Validate remote integrity before any operation
        await self.binding_manager.validate_remote_integrity()

        return operation_path

    async def protected_git_status(self, repo_path: str) -> str:
        """Git status with repository binding protection."""
        validated_path = await self._validate_and_prepare_operation(repo_path)

        logger.debug(f"Protected git status: {validated_path}")
        repo = Repo(validated_path)
        return git_status(repo)

    async def protected_git_add(self, repo_path: str, files: list[str]) -> str:
        """Git add with repository binding protection."""
        validated_path = await self._validate_and_prepare_operation(repo_path)

        logger.debug(f"Protected git add: {validated_path} - {files}")
        repo = Repo(validated_path)
        return git_add(repo, files)

    async def protected_git_commit(
        self,
        repo_path: str,
        message: str,
        gpg_sign: bool = False,
        gpg_key_id: str | None = None,
    ) -> str:
        """Git commit with repository binding protection."""
        validated_path = await self._validate_and_prepare_operation(repo_path)

        logger.info(f"Protected git commit: {validated_path} - '{message[:50]}...'")
        repo = Repo(validated_path)
        return git_commit(repo, message, gpg_sign, gpg_key_id)

    async def protected_git_push(
        self,
        repo_path: str,
        remote: str = "origin",
        branch: str | None = None,
        force: bool = False,
    ) -> str:
        """Git push with remote protection."""
        validated_path = await self._validate_and_prepare_operation(repo_path)

        # Additional remote protection for push operations
        binding = self.binding_manager.binding
        if binding and remote == binding.remote_name:
            # Verify remote URL hasn't changed
            current_remote = await self._get_current_remote_url(validated_path)
            if current_remote != binding.expected_remote_url:
                raise RemoteContaminationError(
                    f"Cannot push: remote {remote} has been contaminated!\n"
                    f"Expected: {binding.expected_remote_url}\n"
                    f"Current: {current_remote}"
                )

        # Log protected push operation
        logger.info(
            f"Protected push: {validated_path} -> {remote}/{branch or 'current'} "
            f"(session: {self.binding_manager._session_id})"
        )

        repo = Repo(validated_path)
        return git_push(repo, remote, branch, force)

    async def protected_git_pull(
        self, repo_path: str, remote: str = "origin", branch: str | None = None
    ) -> str:
        """Git pull with repository binding protection."""
        validated_path = await self._validate_and_prepare_operation(repo_path)

        # Additional remote validation for pull operations
        binding = self.binding_manager.binding
        if binding and remote == binding.remote_name:
            current_remote = await self._get_current_remote_url(validated_path)
            if current_remote != binding.expected_remote_url:
                raise RemoteContaminationError(
                    f"Cannot pull: remote {remote} has been contaminated!\n"
                    f"Expected: {binding.expected_remote_url}\n"
                    f"Current: {current_remote}"
                )

        logger.info(
            f"Protected pull: {validated_path} <- {remote}/{branch or 'current'}"
        )

        repo = Repo(validated_path)
        return git_pull(repo, remote, branch)

    async def protected_git_remote_add(
        self, repo_path: str, name: str, url: str
    ) -> str:
        """Protected remote add with explicit confirmation."""
        validated_path = await self._validate_and_prepare_operation(repo_path)

        # Require explicit confirmation for origin remote modifications
        binding = self.binding_manager.binding
        if binding and name == "origin":
            if url != binding.expected_remote_url:
                raise RemoteProtectionError(
                    f"Attempted to change origin remote from {binding.expected_remote_url} to {url}.\n"
                    f"This could cause cross-session contamination.\n"
                    f"Use explicit_remote_change() if this is intentional."
                )

        logger.warning(
            f"Adding remote {name} -> {url} to bound repository {validated_path}"
        )

        repo = Repo(validated_path)
        return git_remote_add(repo, name, url)

    async def protected_git_remote_remove(self, repo_path: str, name: str) -> str:
        """Protected remote remove with validation."""
        validated_path = await self._validate_and_prepare_operation(repo_path)

        # Warn about origin remote removal
        if name == "origin":
            logger.warning(
                f"Removing origin remote from bound repository {validated_path}"
            )

        repo = Repo(validated_path)
        return git_remote_remove(repo, name)

    async def explicit_remote_change(
        self,
        repo_path: str,
        new_remote_url: str,
        confirmation_token: str,
        remote_name: str = "origin",
    ) -> str:
        """
        Explicitly change remote URL with confirmation.

        This is the ONLY way to change the remote of a bound repository.
        Requires explicit confirmation to prevent accidental changes.

        Args:
            repo_path: Repository path
            new_remote_url: New remote URL
            confirmation_token: Must be "CONFIRM_REMOTE_CHANGE"
            remote_name: Remote name to change

        Returns:
            Operation result
        """
        if confirmation_token != self.confirmation_token:
            raise RemoteProtectionError(
                f"Remote change requires explicit confirmation token: '{self.confirmation_token}'"
            )

        validated_path = await self._validate_and_prepare_operation(repo_path)

        # Log the intentional change
        binding = self.binding_manager.binding
        logger.critical(
            f"EXPLICIT REMOTE CHANGE: {validated_path}\n"
            f"Session: {self.binding_manager._session_id}\n"
            f"Old remote: {binding.expected_remote_url if binding else 'unknown'}\n"
            f"New remote: {new_remote_url}\n"
            f"Server will be unbound after this operation."
        )

        # Remove and re-add the remote with new URL
        repo = Repo(validated_path)
        try:
            git_remote_remove(repo, remote_name)
        except Exception as e:
            # Only ignore if remote doesn't exist, log other errors
            error_msg = str(e).lower()
            if (
                "not found" in error_msg
                or "does not exist" in error_msg
                or "no such remote" in error_msg
            ):
                logger.debug(
                    f"Remote '{remote_name}' doesn't exist, continuing with add"
                )
            else:
                logger.warning(f"Failed to remove remote '{remote_name}': {e}")
                # Continue anyway, but we've logged the real error

        result = git_remote_add(repo, remote_name, new_remote_url)

        # Unbind server since remote changed
        await self.binding_manager.unbind_repository(force=True)

        return result

    async def protected_git_diff(self, repo_path: str, target: str) -> str:
        """Git diff with repository binding protection."""
        validated_path = await self._validate_and_prepare_operation(repo_path)
        repo = Repo(validated_path)
        return git_diff(repo, target)

    async def protected_git_diff_unstaged(self, repo_path: str) -> str:
        """Git diff unstaged with repository binding protection."""
        validated_path = await self._validate_and_prepare_operation(repo_path)
        repo = Repo(validated_path)
        return git_diff_unstaged(repo)

    async def protected_git_diff_staged(self, repo_path: str) -> str:
        """Git diff staged with repository binding protection."""
        validated_path = await self._validate_and_prepare_operation(repo_path)
        repo = Repo(validated_path)
        return git_diff_staged(repo)

    async def protected_git_log(self, repo_path: str, max_count: int = 10) -> str:
        """Git log with repository binding protection."""
        validated_path = await self._validate_and_prepare_operation(repo_path)
        repo = Repo(validated_path)
        return git_log(repo, max_count)

    async def protected_git_show(self, repo_path: str, revision: str) -> str:
        """Git show with repository binding protection."""
        validated_path = await self._validate_and_prepare_operation(repo_path)
        repo = Repo(validated_path)
        return git_show(repo, revision)

    async def protected_git_checkout(self, repo_path: str, branch_name: str) -> str:
        """Git checkout with repository binding protection."""
        validated_path = await self._validate_and_prepare_operation(repo_path)
        repo = Repo(validated_path)
        return git_checkout(repo, branch_name)

    async def protected_git_create_branch(
        self, repo_path: str, branch_name: str, base_branch: str | None = None
    ) -> str:
        """Git create branch with repository binding protection."""
        validated_path = await self._validate_and_prepare_operation(repo_path)
        repo = Repo(validated_path)
        return git_create_branch(repo, branch_name, base_branch)

    async def protected_git_reset(
        self, repo_path: str, mode: str = "mixed", target: str | None = None
    ) -> str:
        """Git reset with repository binding protection."""
        validated_path = await self._validate_and_prepare_operation(repo_path)
        repo = Repo(validated_path)
        return git_reset(repo, mode, target)

    async def protected_git_remote_get_url(self, repo_path: str, name: str) -> str:
        """Git remote get-url with repository binding protection."""
        validated_path = await self._validate_and_prepare_operation(repo_path)
        repo = Repo(validated_path)
        return git_remote_get_url(repo, name)

    async def protected_git_remote_list(self, repo_path: str) -> str:
        """Git remote list with repository binding protection."""
        validated_path = await self._validate_and_prepare_operation(repo_path)
        repo = Repo(validated_path)
        return git_remote_list(repo)

    async def _get_current_remote_url(self, repo_path: Path) -> str:
        """Get current remote URL from repository."""
        repo = Repo(repo_path)
        return git_remote_get_url(repo, "origin")
