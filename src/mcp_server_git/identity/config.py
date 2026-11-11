"""Per-repo GitHub identity map (issue #340).

``MCP_GIT_IDENTITIES`` (default ``~/.config/mcp-git/identities.toml``) maps
``Owner/repo`` slugs to an env file holding that identity's token, GPG key and
author/committer. An identity may also list ``owners = ["login", ...]``: only
those owners (case-insensitive, exact) get that identity for owner-level
resources such as GitHub Projects; repo slugs are never promoted to owner
level, and an owner listed under two identities makes the map invalid. Env files are read with ``dotenv_values`` only: never loaded
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
from typing import NamedTuple

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


class _IdentityMap(NamedTuple):
    repos: _Entries  # lowercased ``owner/repo`` slug -> (identity, env file)
    owners: _Entries  # lowercased owner login -> (identity, env file)


# (path, mtime_ns) -> parsed map, or the invalid-map reason (a str).
_cache: dict[tuple[str, int], _IdentityMap | str] = {}
_cache_lock = threading.Lock()


def config_path() -> Path:
    return Path(os.environ.get(CONFIG_ENV_VAR) or DEFAULT_CONFIG).expanduser()


def _str_list(name: str, entry: dict, key: str) -> list[str]:
    value = entry.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"identity '{name}': {key} must be a list of strings")
    return value


def _parse_entry(name: str, entry: object) -> tuple[Path, list[str], list[str]]:
    if not isinstance(entry, dict):
        raise ValueError(f"identity '{name}' must be a table")
    env_file = entry.get("env_file")
    if not isinstance(env_file, str):
        raise ValueError(f"identity '{name}': env_file must be a string")
    return (
        Path(env_file).expanduser(),
        _str_list(name, entry, "repos"),
        _str_list(name, entry, "owners"),
    )


def _parse(path: Path) -> _IdentityMap | str:
    """Parsed map, or the reason it is invalid."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        identities = data.get("identities", {})
        if not isinstance(identities, dict):
            raise ValueError("identities must be a table")
        repo_map: _Entries = {}
        owner_map: _Entries = {}
        for name, entry in identities.items():
            env_file, repos, owners = _parse_entry(name, entry)
            for slug in repos:
                repo_map[slug.lower()] = (name, env_file)
            for owner in owners:
                prior = owner_map.get(owner.strip().lower())
                if prior and prior[0] != name:
                    raise ValueError(
                        f"owner '{owner}' is listed under both identities "
                        f"'{prior[0]}' and '{name}'"
                    )
                owner_map[owner.strip().lower()] = (name, env_file)
        return _IdentityMap(repo_map, owner_map)
    except (OSError, ValueError) as exc:  # TOMLDecodeError is a ValueError
        logger.warning("Invalid identity map %s: %s", path, exc)
        return str(exc)


def _load_map() -> _IdentityMap:
    path = config_path()
    try:
        key = (str(path), path.stat().st_mtime_ns)
    except OSError:
        return _IdentityMap({}, {})
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
    hit = _load_map().repos.get(slug.strip().lower())
    return _build(*hit) if hit else None


def identity_for_owner(owner: str) -> RepoIdentity | None:
    """Identity for an owner-level resource (e.g. a GitHub Project), else None.

    Only an identity that explicitly lists the owner in its ``owners`` key
    (case-insensitive, exact) is returned. Repo slugs are never consulted: a
    repo mapping is not promoted to owner level. Otherwise the result is None,
    so the caller falls back to the default ``GITHUB_TOKEN``.

    Raises:
        IdentityError: the map is invalid (including an owner listed under two
            identities) or the mapped env file is invalid.
    """
    hit = _load_map().owners.get(owner.strip().lower())
    return _build(*hit) if hit else None
