"""Resolve a repository's mapped identity from its ``origin`` remote."""

import re
from typing import Any

from .config import RepoIdentity, identity_for_slug

__all__ = ["identity_for_repo", "slug_from_url"]

_GITHUB_URL = re.compile(
    r"^(?:https?://(?:[^@/]+@)?|ssh://(?:[^@/]+@)?|git@)"
    r"github\.com[:/]+([^/\s]+)/([^/\s]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)


def slug_from_url(url: str) -> str | None:
    """``owner/repo`` for a GitHub remote URL, else None."""
    match = _GITHUB_URL.match(url.strip())
    return f"{match.group(1)}/{match.group(2)}" if match else None


def identity_for_repo(repo: Any) -> RepoIdentity | None:
    """Identity mapped to the repo's ``origin`` GitHub slug, else None."""
    try:
        url = repo.remote("origin").url
    except (ValueError, AttributeError):
        return None
    slug = slug_from_url(url) if isinstance(url, str) else None
    return identity_for_slug(slug) if slug else None
