"""Per-repo GitHub identity map (issue #340).

``MCP_GIT_IDENTITIES`` (default ``~/.config/mcp-git/identities.toml``) maps
``Owner/repo`` slugs to an env file holding that identity's token, GPG key and
author/committer. Env files are read with ``dotenv_values`` only: never loaded
into ``os.environ``, and token values are never logged.

Fail closed: a broken map or env file raises :class:`IdentityError` rather than
falling back to the owner's credentials.
"""

import logging
import os
import threading
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

logger = logging.getLogger(__name__)

CONFIG_ENV_VAR = "MCP_GIT_IDENTITIES"
DEFAULT_CONFIG = "~/.config/mcp-git/identities.toml"

__all__ = [
    "IdentityError",
    "RepoIdentity",
    "config_path",
    "identity_for_owner",
    "identity_for_slug",
]


class IdentityError(Exception):
    """A mapped (or possibly mapped) repo has no usable identity configuration."""


@dataclass(frozen=True)
class RepoIdentity:
    """Credentials and commit attribution for one mapped identity."""

    name: str
    token: str | None = field(default=None, repr=False)
    gpg_key: str | None = None
    author_name: str | None = None
    author_email: str | None = None
    committer_name: str | None = None
    committer_email: str | None = None

    def commit_env(self) -> dict[str, str]:
        """GIT_AUTHOR_*/GIT_COMMITTER_* for one commit subprocess only."""
        pairs = {
            "GIT_AUTHOR_NAME": self.author_name,
            "GIT_AUTHOR_EMAIL": self.author_email,
            "GIT_COMMITTER_NAME": self.committer_name or self.author_name,
            "GIT_COMMITTER_EMAIL": self.committer_email or self.author_email,
        }
        return {k: v for k, v in pairs.items() if v}


_Entries = dict[str, tuple[str, Path]]
# (path, mtime_ns) -> parsed map, or the invalid-map reason (a str).
_cache: dict[tuple[str, int], _Entries | str] = {}
_cache_lock = threading.Lock()


def config_path() -> Path:
    return Path(os.environ.get(CONFIG_ENV_VAR) or DEFAULT_CONFIG).expanduser()


def _parse_entry(name: str, entry: object) -> tuple[Path, list[str]]:
    if not isinstance(entry, dict):
        raise ValueError(f"identity '{name}' must be a table")
    env_file = entry.get("env_file")
    if not isinstance(env_file, str):
        raise ValueError(f"identity '{name}': env_file must be a string")
    repos = entry.get("repos", [])
    if not isinstance(repos, list) or not all(isinstance(r, str) for r in repos):
        raise ValueError(f"identity '{name}': repos must be a list of strings")
    return Path(env_file).expanduser(), repos


def _parse(path: Path) -> _Entries | str:
    """Parsed map, or the reason it is invalid."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        identities = data.get("identities", {})
        if not isinstance(identities, dict):
            raise ValueError("identities must be a table")
        mapping: _Entries = {}
        for name, entry in identities.items():
            env_file, repos = _parse_entry(name, entry)
            for slug in repos:
                mapping[slug.lower()] = (name, env_file)
        return mapping
    except (OSError, ValueError) as exc:  # TOMLDecodeError is a ValueError
        logger.warning("Invalid identity map %s: %s", path, exc)
        return str(exc)


def _load_map() -> _Entries:
    path = config_path()
    try:
        key = (str(path), path.stat().st_mtime_ns)
    except OSError:
        return {}
    with _cache_lock:
        if key not in _cache:
            _cache.clear()
            _cache[key] = _parse(path)
        loaded = _cache[key]
    if isinstance(loaded, str):
        raise IdentityError(f"identity map {path} is invalid: {loaded}")
    return loaded


def _build(name: str, env_file: Path) -> RepoIdentity:
    try:
        values = dotenv_values(env_file) if env_file.is_file() else None
    except (OSError, UnicodeDecodeError):
        values = None
    if values is None:
        raise IdentityError(
            f"identity '{name}': env file {env_file} missing or unreadable"
        )
    token = values.get("GITHUB_TOKEN")
    if not token:
        raise IdentityError(f"identity '{name}': env file has no GITHUB_TOKEN")
    return RepoIdentity(
        name=name,
        token=token,
        gpg_key=values.get("GPG_SIGNING_KEY") or None,
        author_name=values.get("GIT_AUTHOR_NAME") or None,
        author_email=values.get("GIT_AUTHOR_EMAIL") or None,
        committer_name=values.get("GIT_COMMITTER_NAME") or None,
        committer_email=values.get("GIT_COMMITTER_EMAIL") or None,
    )


def identity_for_slug(slug: str) -> RepoIdentity | None:
    """Identity mapped to ``owner/repo`` (case-insensitive), else None.

    Raises:
        IdentityError: the map or the mapped env file is invalid.
    """
    hit = _load_map().get(slug.strip().lower())
    return _build(*hit) if hit else None


def identity_for_owner(owner: str) -> RepoIdentity | None:
    """Identity for an owner-level resource (e.g. a GitHub Project), else None.

    Collects the identities of every ``owner/...`` slug in the map. Exactly one
    distinct identity is returned. With no mapped slug the result is None, so
    the caller falls back to the default ``GITHUB_TOKEN``, exactly as an
    unmapped repo does.

    Raises:
        IdentityError: the owner's repos map to different identities (fail
            closed: the owner-level token is ambiguous), or the map or the
            mapped env file is invalid.
    """
    prefix = owner.strip().lower() + "/"
    hits = {
        name: env_file
        for slug, (name, env_file) in _load_map().items()
        if slug.startswith(prefix)
    }
    if len(hits) > 1:
        raise IdentityError(
            f"owner '{owner}' maps to conflicting identities {sorted(hits)}; "
            "cannot choose a token for an owner-level resource"
        )
    return _build(*next(iter(hits.items()))) if hits else None
