"""Task-local active identity, read by ``get_github_client`` (issue #340)."""

import contextvars
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from .config import RepoIdentity, identity_for_owner, identity_for_slug

logger = logging.getLogger(__name__)

__all__ = ["current_identity", "identity_scope", "use_identity"]

current_identity: contextvars.ContextVar[RepoIdentity | None] = contextvars.ContextVar(
    "mcp_git_current_identity", default=None
)


@contextmanager
def use_identity(identity: RepoIdentity | None) -> Iterator[None]:
    """Make *identity* current for the enclosed block, then restore."""
    token = current_identity.set(identity)
    try:
        yield
    finally:
        current_identity.reset(token)


@contextmanager
def identity_scope(parameters: dict[str, Any]) -> Iterator[None]:
    """Activate the identity mapped to ``repo_owner``/``repo_name``, if any.

    Owner-level tools (``owner`` + ``owner_type``, no repo params) use
    :func:`identity_for_owner` instead.
    """
    owner = parameters.get("repo_owner")
    name = parameters.get("repo_name")
    identity = None
    label = f"{owner}/{name}"
    if isinstance(owner, str) and isinstance(name, str):
        identity = identity_for_slug(label)
    elif (
        owner is None
        and name is None
        and isinstance(parameters.get("owner"), str)
        and "owner_type" in parameters
    ):
        label = parameters["owner"]
        identity = identity_for_owner(label)
    if identity is None:
        yield
        return
    logger.info("API call for %s using identity %s", label, identity.name)
    with use_identity(identity):
        yield
