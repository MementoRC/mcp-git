"""
Repository Binding Architecture for MCP Git Server.

This module implements repository binding with explicit remote protection to prevent
cross-session contamination of git repositories. Key features:

- Repository binding with remote URL validation
- Cross-session contamination detection
- Explicit remote change operations with confirmation
- Protected git operations with path validation
- Session isolation and boundary enforcement

This addresses the critical incident of cross-session git remote contamination
documented in CRITICAL_INCIDENT_REPORT.md.
"""

import asyncio
import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from git.repo import Repo

# Safe git import that handles ClaudeCode redirector conflicts
from .utils.git_import import git

# Constants
DEFAULT_REMOTE_NAME = "origin"

__all__ = [
    "RepositoryBinding",
    "RepositoryBindingManager",
    "RepositoryBindingState",
    "RepositoryBindingError",
    "RemoteProtectionError",
    "DEFAULT_REMOTE_NAME",
]

logger = logging.getLogger(__name__)


class RepositoryBindingState(Enum):
    """States for repository binding lifecycle."""

    UNBOUND = "unbound"
    BINDING = "binding"
    BOUND = "bound"
    PROTECTED = "protected"
    CORRUPTED = "corrupted"


class RepositoryBindingError(Exception):
    """Raised when repository binding operations fail."""

    pass


class RemoteContaminationError(RepositoryBindingError):
    """Raised when remote URL contamination is detected."""

    pass


class UnboundServerError(RepositoryBindingError):
    """Raised when operations attempted on unbound server."""

    pass


class RemoteProtectionError(RepositoryBindingError):
    """Raised when protected remote operations are attempted without confirmation."""

    pass


@dataclass(frozen=True)
class RepositoryBinding:
    """Immutable repository binding configuration."""

    repository_path: Path
    expected_remote_url: str
    remote_name: str = DEFAULT_REMOTE_NAME
    binding_timestamp: float = field(default_factory=time.time)
    binding_hash: str = field(init=False)

    def __post_init__(self):
        """Create unique binding hash for verification."""
        binding_data = f"{self.repository_path}:{self.expected_remote_url}:{self.binding_timestamp}"
        object.__setattr__(
            self, "binding_hash", hashlib.sha256(binding_data.encode()).hexdigest()
        )

    def verify_integrity(self) -> bool:
        """Verify binding hasn't been tampered with."""
        expected_hash = hashlib.sha256(
            f"{self.repository_path}:{self.expected_remote_url}:{self.binding_timestamp}".encode()
        ).hexdigest()
        return self.binding_hash == expected_hash


class RepositoryBindingManager:
    """Manages repository binding with remote protection."""

    def __init__(self, server_name: str):
        self.server_name = server_name
        self._binding: RepositoryBinding | None = None
        self._state: RepositoryBindingState = RepositoryBindingState.UNBOUND
        self._lock = asyncio.Lock()
        self._session_id: str = str(uuid.uuid4())

    async def bind_repository(
        self,
        repository_path: Path,
        expected_remote_url: str,
        verify_remote: bool = True,
        force: bool = False,
    ) -> RepositoryBinding:
        """
        Bind server to specific repository with remote protection.

        Args:
            repository_path: Path to git repository
            expected_remote_url: Expected remote URL for validation
            verify_remote: Verify remote URL matches expectation
            force: Force binding even if already bound

        Returns:
            RepositoryBinding object

        Raises:
            RepositoryBindingError: If binding fails
            RemoteContaminationError: If remote doesn't match expected
        """
        async with self._lock:
            if self._state == RepositoryBindingState.BOUND and not force:
                assert self._binding is not None, (
                    "Binding must exist when state is BOUND"
                )
                raise RepositoryBindingError(
                    f"Server already bound to {self._binding.repository_path}. "
                    f"Use force=True or unbind first."
                )

            # Validate repository exists and is valid git repo
            if not repository_path.exists():
                raise RepositoryBindingError(
                    f"Repository path does not exist: {repository_path}"
                )

            try:
                Repo(repository_path)
            except git.InvalidGitRepositoryError as err:
                raise RepositoryBindingError(
                    f"Invalid git repository: {repository_path}"
                ) from err

            # Verify remote URL if requested
            if verify_remote:
                current_remote = await self._get_current_remote_url(repository_path)
                if current_remote != expected_remote_url:
                    raise RemoteContaminationError(
                        f"Remote URL mismatch in {repository_path}:\n"
                        f"Expected: {expected_remote_url}\n"
                        f"Current: {current_remote}\n"
                        f"This indicates cross-session contamination!"
                    )

            # Create binding
            self._binding = RepositoryBinding(
                repository_path=repository_path.resolve(),
                expected_remote_url=expected_remote_url,
            )
            self._state = RepositoryBindingState.BOUND

            logger.info(
                f"Repository bound: {self.server_name} -> {repository_path} "
                f"(remote: {expected_remote_url}) [session: {self._session_id}]"
            )

            return self._binding

    async def unbind_repository(self, force: bool = False) -> None:
        """
        Unbind server from repository.

        Args:
            force: Force unbind even if operations are in progress
        """
        async with self._lock:
            if self._state == RepositoryBindingState.UNBOUND:
                logger.warning("Server already unbound")
                return

            if not force and self._state == RepositoryBindingState.PROTECTED:
                raise RepositoryBindingError(
                    "Cannot unbind protected repository. Use force=True if necessary."
                )

            assert self._binding is not None, (
                "Binding must exist when not in UNBOUND state"
            )
            old_binding = self._binding
            self._binding = None
            self._state = RepositoryBindingState.UNBOUND

            logger.info(
                f"Repository unbound: {self.server_name} from {old_binding.repository_path} "
                f"[session: {self._session_id}]"
            )

    def validate_operation_path(self, operation_path: Path) -> None:
        """
        Validate that operation path matches bound repository.

        Args:
            operation_path: Path for git operation

        Raises:
            RepositoryBindingError: If path doesn't match binding
            UnboundServerError: If server not bound to repository
        """
        if self._state == RepositoryBindingState.UNBOUND:
            raise UnboundServerError(
                f"Server {self.server_name} not bound to any repository. "
                f"Bind to repository before performing git operations."
            )

        if not self._binding:
            raise RepositoryBindingError("No binding available despite bound state")

        # Verify binding integrity
        if not self._binding.verify_integrity():
            self._state = RepositoryBindingState.CORRUPTED
            raise RepositoryBindingError(
                "Repository binding corrupted - potential tampering detected"
            )

        # Normalize paths for comparison
        bound_path = self._binding.repository_path.resolve()
        operation_path = operation_path.resolve()

        # Check if operation path is within bound repository
        try:
            operation_path.relative_to(bound_path)
        except ValueError as e:
            # relative_to() can fail for different reasons - provide specific error message
            if "is not in the subpath of" in str(e) or not str(
                operation_path
            ).startswith(str(bound_path)):
                raise RepositoryBindingError(
                    f"Operation path {operation_path} is outside bound repository {bound_path}. "
                    f"This prevents cross-repository contamination."
                ) from e
            else:
                raise RepositoryBindingError(
                    f"Cannot determine path relationship between {operation_path} and {bound_path}: {e}"
                ) from e

    async def validate_remote_integrity(self) -> None:
        """
        Validate that repository remote hasn't been contaminated.

        Raises:
            RemoteContaminationError: If remote has been modified
        """
        if self._state == RepositoryBindingState.UNBOUND or not self._binding:
            return

        current_remote = await self._get_current_remote_url(
            self._binding.repository_path
        )

        if current_remote != self._binding.expected_remote_url:
            self._state = RepositoryBindingState.CORRUPTED
            raise RemoteContaminationError(
                f"Remote contamination detected in {self._binding.repository_path}:\n"
                f"Expected: {self._binding.expected_remote_url}\n"
                f"Current: {current_remote}\n"
                f"Cross-session contamination detected!"
            )

    async def _get_current_remote_url(self, repo_path: Path) -> str:
        """Get current remote URL from repository."""
        try:
            repo = Repo(repo_path)
            # Safe remote access to prevent race condition
            try:
                origin_remote = getattr(repo.remotes, DEFAULT_REMOTE_NAME)
                urls = list(origin_remote.urls)
                if not urls:
                    raise RepositoryBindingError(
                        f"'{DEFAULT_REMOTE_NAME}' remote has no URLs in {repo_path}"
                    )
                return urls[0]
            except AttributeError as err:
                # origin remote doesn't exist
                raise RepositoryBindingError(
                    f"No '{DEFAULT_REMOTE_NAME}' remote found in {repo_path}"
                ) from err
        except Exception as e:
            raise RepositoryBindingError(
                f"Failed to get remote URL from {repo_path}: {e}"
            ) from e

    def get_binding_info(self) -> dict:
        """Get current binding information."""
        return {
            "state": self._state.value,
            "session_id": self._session_id,
            "server_name": self.server_name,
            "binding": {
                "repository_path": str(self._binding.repository_path),
                "expected_remote_url": self._binding.expected_remote_url,
                "remote_name": self._binding.remote_name,
                "binding_timestamp": self._binding.binding_timestamp,
                "binding_hash": self._binding.binding_hash,
            }
            if self._binding
            else None,
        }

    @property
    def is_bound(self) -> bool:
        """Check if server is bound to a repository."""
        return self._state == RepositoryBindingState.BOUND and self._binding is not None

    @property
    def binding(self) -> RepositoryBinding | None:
        """Get current repository binding."""
        return self._binding

    @property
    def state(self) -> RepositoryBindingState:
        """Get current binding state."""
        return self._state
