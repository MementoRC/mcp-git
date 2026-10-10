"""GitHub token discovery (repo .env, GITHUB_TOKEN, GitHub CLI) for push auth."""

import logging
import os
import subprocess
from pathlib import Path

from ..utils.git_import import Repo

logger = logging.getLogger(__name__)

CLI_AUTH_TIMEOUT = 10  # seconds for GitHub CLI authentication
MIN_TOKEN_LENGTH = 10  # minimum length for a valid GitHub token

__all__ = ["_get_github_token_from_cli", "_resolve_github_token"]


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
        logger.debug(f"🔍 DEBUG: gh auth token return code: {result.returncode}")
        logger.debug(
            f"🔍 DEBUG: gh auth token stdout: {result.stdout[:50]}..."
            if result.stdout
            else "🔍 DEBUG: gh auth token stdout: EMPTY"
        )
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


def _resolve_github_token(repo: Repo) -> str | None:
    """Find a GitHub token: repo .env, GITHUB_TOKEN, then GitHub CLI."""
    from dotenv import load_dotenv

    repo_env = Path(repo.working_dir) / ".env"
    if repo_env.exists():
        logger.info(f"🔍 DEBUG: Loading .env from repository: {repo_env}")
        load_dotenv(repo_env, override=True)

    github_token = os.getenv("GITHUB_TOKEN")
    logger.info(
        f"🔍 DEBUG: GITHUB_TOKEN from env: {'SET' if github_token else 'NOT SET'}"
    )
    logger.info(f"🔍 DEBUG: Repository working dir: {repo.working_dir}")
    logger.info(f"🔍 DEBUG: .env file exists: {repo_env.exists()}")

    if not github_token:
        logger.debug("🔍 DEBUG: Attempting GitHub CLI token extraction...")
        github_token = _get_github_token_from_cli()
        logger.debug(
            f"🔍 DEBUG: GitHub CLI token: {'SET' if github_token else 'NOT SET'}"
        )
    return github_token
