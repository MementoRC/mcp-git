"""GitHub token discovery (repo .env, GITHUB_TOKEN, GitHub CLI) for push auth."""

import logging
import os
import subprocess
from pathlib import Path

from ..utils.git_import import Repo

logger = logging.getLogger(__name__)

CLI_AUTH_TIMEOUT = 10  # seconds for GitHub CLI authentication
MIN_TOKEN_LENGTH = 10  # minimum length for a valid GitHub token

__all__ = ["_get_github_token_from_cli", "resolve_github_token"]


def _get_github_token_from_cli() -> str | None:
    """Extract token from GitHub CLI if available"""
    try:
        logger.debug("🔍 DEBUG: Running 'gh auth token' command...")
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=CLI_AUTH_TIMEOUT,
        )
        # Never log stdout: it is the token itself (#303).
        logger.debug(f"🔍 DEBUG: gh auth token return code: {result.returncode}")
        logger.debug(f"🔍 DEBUG: gh auth token stderr: {result.stderr}")

        if result.returncode == 0:
            token = result.stdout.strip()
            token_valid = token and len(token) >= MIN_TOKEN_LENGTH
            logger.debug(
                f"🔍 DEBUG: Token valid: {token_valid}, length: {len(token) if token else 0}"
            )
            return token if token_valid else None
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.debug(f"🔍 DEBUG: gh command failed: {e}")
        pass
    return None


def resolve_github_token(repo: Repo) -> tuple[str, str] | None:
    """Find a GitHub token and its source: repo .env, GITHUB_TOKEN, then gh CLI.

    Returns ``(token, source)`` with source ``".env"``, ``"env"`` or ``"gh"``,
    or None when no token resolves. The repo .env is still loaded into the
    process environment, as before.
    """
    from dotenv import dotenv_values, load_dotenv

    repo_env = Path(repo.working_dir) / ".env"
    if repo_env.exists():
        logger.info(f"🔍 DEBUG: Loading .env from repository: {repo_env}")
        load_dotenv(repo_env, override=True)
        token = dotenv_values(repo_env).get("GITHUB_TOKEN")
        if token:
            return token, ".env"

    token = os.getenv("GITHUB_TOKEN")
    if token:
        return token, "env"

    logger.debug("🔍 DEBUG: Attempting GitHub CLI token extraction...")
    token = _get_github_token_from_cli()
    return (token, "gh") if token else None
