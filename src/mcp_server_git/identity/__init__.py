"""Per-repo GitHub identities: token, GPG key and author per mapped repo (#340)."""

from .config import IdentityError, RepoIdentity, identity_for_slug
from .context import current_identity, identity_scope, use_identity
from .resolve import identity_for_repo, slug_from_url

__all__ = [
    "IdentityError",
    "RepoIdentity",
    "current_identity",
    "identity_for_repo",
    "identity_for_slug",
    "identity_scope",
    "slug_from_url",
    "use_identity",
]
