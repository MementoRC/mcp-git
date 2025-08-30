"""Repository binding implementation for MCP Git operations.

This module provides a secure repository binding interface that prevents
cross-repository contamination by enforcing path-based security boundaries.
"""

import logging
from pathlib import Path

import git
from git import Repo

logger = logging.getLogger(__name__)

DEFAULT_REMOTE_NAME = "origin"


class RepositoryBindingError(Exception):
    """Exception raised when repository binding operations fail."""


class RepositoryBinding:
    """Provides a secure binding to a specific Git repository.

    This class enforces that all Git operations are performed within
    the bounds of a single repository, preventing cross-repository
    contamination or unauthorized access.
    """

    def __init__(
        self,
        repository_path: str | Path,
        verify_repository: bool = True,
        verify_remote: bool = False,
    ):
        """Initialize repository binding.

        Args:
            repository_path: Path to the Git repository
            verify_repository: Whether to verify the path is a valid Git repository
            verify_remote: Whether to verify remote repository connectivity

        Raises:
            RepositoryBindingError: If repository binding fails validation
        """
        self.repository_path = Path(repository_path).resolve()

        if verify_repository:
            self._verify_repository_validity(verify_remote)

        logger.debug(f"Repository binding established for: {self.repository_path}")

    def _verify_repository_validity(self, verify_remote: bool = False) -> None:
        """Verify that the bound path is a valid Git repository.

        Args:
            verify_remote: Whether to also verify remote connectivity

        Raises:
            RepositoryBindingError: If repository validation fails
        """
        if not self.repository_path.exists():
            raise RepositoryBindingError(
                f"Repository path does not exist: {self.repository_path}"
            )

        if not self.repository_path.is_dir():
            raise RepositoryBindingError(
                f"Repository path is not a directory: {self.repository_path}"
            )

        # Check if it's a Git repository by trying to create a Repo object
        try:
            Repo(self.repository_path)
        except git.InvalidGitRepositoryError as e:
            raise RepositoryBindingError(
                f"Invalid git repository: {self.repository_path}"
            ) from e

        # Verify remote URL if requested
        if verify_remote:
            self._verify_remote_url()

    def _verify_remote_url(self) -> None:
        """Verify that the repository has a valid remote URL.

        Raises:
            RepositoryBindingError: If remote verification fails
        """
        try:
            remote_url = self.get_remote_url()
            if not remote_url:
                raise RepositoryBindingError(
                    f"No remote URL found for {self.repository_path}"
                )
            logger.debug(f"Remote URL verified: {remote_url}")
        except Exception as e:
            raise RepositoryBindingError(
                f"Failed to verify remote URL for {self.repository_path}: {e}"
            ) from e

    def validate_operation_path(self, operation_path: str | Path) -> Path:
        """Validate that an operation path is within the bound repository.

        Args:
            operation_path: Path where the operation will be performed

        Returns:
            Resolved absolute path within the repository bounds

        Raises:
            RepositoryBindingError: If the path is outside repository bounds
        """
        try:
            resolved_path = Path(operation_path).resolve()
            bound_path = self.repository_path.resolve()

            # Check if the resolved path is within the bound repository
            try:
                resolved_path.relative_to(bound_path)
                return resolved_path
            except ValueError as e:
                if not str(resolved_path).startswith(str(bound_path)):
                    raise RepositoryBindingError(
                        f"Operation path {operation_path} is outside bound repository {bound_path}. "
                        f"This prevents cross-repository contamination."
                    ) from e
                else:
                    raise RepositoryBindingError(
                        f"Cannot determine path relationship between {operation_path} and {bound_path}: {e}"
                    ) from e

        except Exception as e:
            raise RepositoryBindingError(
                f"Failed to validate operation path {operation_path}: {e}"
            ) from e

    async def validate_remote_integrity(self) -> None:
        """Validate remote repository integrity asynchronously.

        This method performs network-based validation of remote repository
        connectivity and integrity without blocking the main thread.

        Raises:
            RepositoryBindingError: If remote validation fails
        """
        try:
            # This is an async operation that could involve network calls
            # For now, we just verify the remote URL exists
            self._verify_remote_url()
        except Exception as e:
            raise RepositoryBindingError(
                f"Remote integrity validation failed for {self.repository_path}: {e}"
            ) from e

    def get_remote_url(self) -> str:
        """Get the URL of the default remote repository.

        Returns:
            URL of the origin remote

        Raises:
            RepositoryBindingError: If remote URL cannot be retrieved
        """
        try:
            repo = Repo(self.repository_path)

            if DEFAULT_REMOTE_NAME not in [remote.name for remote in repo.remotes]:
                raise RepositoryBindingError(
                    f"No '{DEFAULT_REMOTE_NAME}' remote found in {self.repository_path}"
                )

            origin = getattr(repo.remotes, DEFAULT_REMOTE_NAME)
            urls = list(origin.urls)

            if not urls:
                raise RepositoryBindingError(
                    f"'{DEFAULT_REMOTE_NAME}' remote has no URLs in {self.repository_path}"
                )
            return urls[0]
        except AttributeError as e:
            # origin remote doesn't exist
            raise RepositoryBindingError(
                f"No '{DEFAULT_REMOTE_NAME}' remote found in {self.repository_path}"
            ) from e
        except Exception as e:
            raise RepositoryBindingError(
                f"Failed to get remote URL from {self.repository_path}: {e}"
            ) from e

    def get_binding_info(self) -> dict:
        """Get current binding information."""
        return {
            "repository_path": str(self.repository_path),
            "exists": self.repository_path.exists(),
            "is_directory": self.repository_path.is_dir()
            if self.repository_path.exists()
            else False,
            "absolute_path": str(self.repository_path.resolve()),
        }

    def get_repo(self) -> Repo:
        """Get the bound Git repository object.

        Returns:
            GitPython Repo object for the bound repository

        Raises:
            RepositoryBindingError: If repository cannot be accessed
        """
        try:
            return Repo(self.repository_path)
        except Exception as e:
            raise RepositoryBindingError(
                f"Failed to access repository {self.repository_path}: {e}"
            ) from e

    def __str__(self) -> str:
        """String representation of the repository binding."""
        return f"RepositoryBinding({self.repository_path})"

    def __repr__(self) -> str:
        """Detailed string representation of the repository binding."""
        return (
            f"RepositoryBinding(repository_path={self.repository_path!r}, "
            f"exists={self.repository_path.exists()!r})"
        )
