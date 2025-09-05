"""Repository binding implementation for MCP Git operations.

This module provides a secure repository binding interface that prevents
cross-repository contamination by enforcing path-based security boundaries.
"""

import logging
import uuid
from pathlib import Path
from typing import Optional

import git
from git import Repo

logger = logging.getLogger(__name__)

DEFAULT_REMOTE_NAME = "origin"


class RepositoryBindingError(Exception):
    """Exception raised when repository binding operations fail."""


class RemoteContaminationError(Exception):
    """Exception raised when remote repository contamination is detected."""


class RemoteProtectionError(Exception):
    """Exception raised when remote repository protection is violated.

    This exception is raised when operations attempt to modify remote URLs
    without proper confirmation, which could lead to cross-session contamination.
    """


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

    def validate_remote_integrity(self) -> None:
        """Validate remote repository integrity.

        This method performs validation of remote repository
        connectivity and integrity.

        Raises:
            RepositoryBindingError: If remote validation fails
        """
        try:
            # Verify the remote URL exists
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


class RepositoryBindingManager:
    """Manages repository bindings for MCP Git operations.

    This class provides a centralized interface for managing repository bindings,
    session tracking, and remote protection across MCP server operations.
    """

    def __init__(self, server_name: str = "mcp-git-server"):
        """Initialize the repository binding manager.

        Args:
            server_name: Name identifier for this server instance
        """
        self.server_name = server_name
        self._session_id = str(uuid.uuid4())
        self._binding: RepositoryBinding | None = None
        self._expected_remote_url: str | None = None
        self._remote_name: str = DEFAULT_REMOTE_NAME

        logger.debug(
            f"Repository binding manager initialized for {server_name} (session: {self._session_id})"
        )

    @property
    def binding(self) -> Optional["RepositoryBindingInfo"]:
        """Get the current repository binding information.

        Returns:
            Current binding info with expected remote URL and remote name, or None if unbound
        """
        if self._binding is None:
            return None

        return RepositoryBindingInfo(
            repository_path=self._binding.repository_path,
            expected_remote_url=self._expected_remote_url,
            remote_name=self._remote_name,
        )

    def bind_repository(
        self,
        repository_path: str | Path,
        expected_remote_url: str,
        remote_name: str = DEFAULT_REMOTE_NAME,
        verify_remote: bool = True,
    ) -> None:
        """Bind to a repository with remote protection.

        Args:
            repository_path: Path to the Git repository
            expected_remote_url: Expected remote URL for contamination detection
            remote_name: Name of the remote to monitor (default: "origin")
            verify_remote: Whether to verify remote connectivity

        Raises:
            RepositoryBindingError: If binding fails
        """
        try:
            self._binding = RepositoryBinding(
                repository_path=repository_path,
                verify_repository=True,
                verify_remote=verify_remote,
            )
            self._expected_remote_url = expected_remote_url
            self._remote_name = remote_name

            logger.info(
                f"Repository bound: {repository_path} -> {expected_remote_url} "
                f"(session: {self._session_id})"
            )

        except Exception as e:
            raise RepositoryBindingError(f"Failed to bind repository: {e}") from e

    def unbind_repository(self) -> None:
        """Unbind from the current repository."""
        if self._binding:
            logger.info(
                f"Repository unbound: {self._binding.repository_path} (session: {self._session_id})"
            )

        self._binding = None
        self._expected_remote_url = None
        self._remote_name = DEFAULT_REMOTE_NAME

    def validate_operation_path(self, operation_path: str | Path) -> Path:
        """Validate an operation path against the current binding.

        Args:
            operation_path: Path to validate

        Returns:
            Validated absolute path

        Raises:
            RepositoryBindingError: If no binding exists or path is invalid
        """
        if self._binding is None:
            raise RepositoryBindingError(
                "No repository binding active. Use bind_repository() first."
            )

        return self._binding.validate_operation_path(operation_path)

    def validate_remote_integrity(self) -> None:
        """Validate remote integrity against expected URL.

        Raises:
            RepositoryBindingError: If no binding exists
            RemoteContaminationError: If remote URL has changed
        """
        if self._binding is None:
            raise RepositoryBindingError(
                "No repository binding active. Use bind_repository() first."
            )

        try:
            current_remote = self._binding.get_remote_url()
            if (
                self._expected_remote_url
                and current_remote != self._expected_remote_url
            ):
                raise RemoteContaminationError(
                    f"Remote contamination detected!\n"
                    f"Expected: {self._expected_remote_url}\n"
                    f"Current: {current_remote}"
                )
        except git.GitError as e:
            # Git errors during remote validation
            raise RepositoryBindingError(
                f"Failed to validate remote integrity: {e}"
            ) from e

        self._binding.validate_remote_integrity()

    def get_status(self) -> dict:
        """Get current binding manager status.

        Returns:
            Dictionary with binding status information
        """
        return {
            "server_name": self.server_name,
            "session_id": self._session_id,
            "bound": self._binding is not None,
            "repository_path": str(self._binding.repository_path)
            if self._binding
            else None,
            "expected_remote_url": self._expected_remote_url,
            "remote_name": self._remote_name,
        }

    def get_binding_info(self) -> dict:
        """Get current binding information.

        Returns:
            Dictionary with binding information (alias for get_status)
        """
        return self.get_status()


class RepositoryBindingInfo:
    """Information about a repository binding.

    This class provides a read-only view of binding information used by
    protected git operations for validation and contamination detection.
    """

    def __init__(
        self,
        repository_path: Path,
        expected_remote_url: str | None,
        remote_name: str = DEFAULT_REMOTE_NAME,
    ):
        """Initialize binding information.

        Args:
            repository_path: Path to the bound repository
            expected_remote_url: Expected remote URL for contamination detection
            remote_name: Name of the monitored remote
        """
        self.repository_path = repository_path
        self.expected_remote_url = expected_remote_url
        self.remote_name = remote_name
