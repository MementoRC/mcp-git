"""GitHub API client and authentication"""

import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class GitHubClient:
    """GitHub API client with authentication and rate limiting."""

    token: str
    session: aiohttp.ClientSession
    base_url: str = "https://api.github.com"

    def __post_init__(self):
        """Validate GitHub token format"""
        if not self._is_valid_github_token(self.token):
            logger.warning("⚠️ GitHub token format appears invalid")

    @staticmethod
    def _is_valid_github_token(token: str) -> bool:
        """Validate GitHub token format"""
        if not token or len(token.strip()) == 0:
            return False

        # GitHub token patterns
        patterns = [
            r"^ghp_[a-zA-Z0-9]{36}$",  # Personal access tokens (classic)
            r"^github_pat_[a-zA-Z0-9_]{82}$",  # Fine-grained personal access tokens
            r"^ghs_[a-zA-Z0-9]{36}$",  # GitHub App installation tokens
            r"^ghu_[a-zA-Z0-9]{36}$",  # GitHub App user tokens
        ]

        return any(re.match(pattern, token.strip()) for pattern in patterns)

    async def get(self, endpoint: str, **kwargs) -> aiohttp.ClientResponse:
        """Make GET request to GitHub API"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "MCP-Git-Server/1.1.0",
        }

        return await self.session.get(url, headers=headers, **kwargs)

    async def post(self, endpoint: str, **kwargs) -> aiohttp.ClientResponse:
        """Make POST request to GitHub API"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "MCP-Git-Server/1.1.0",
        }

        return await self.session.post(url, headers=headers, **kwargs)

    async def patch(self, endpoint: str, **kwargs) -> aiohttp.ClientResponse:
        """Make PATCH request to GitHub API"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "MCP-Git-Server/1.1.0",
        }

        return await self.session.patch(url, headers=headers, **kwargs)

    async def put(self, endpoint: str, **kwargs) -> aiohttp.ClientResponse:
        """Make PUT request to GitHub API"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "MCP-Git-Server/1.1.0",
        }

        return await self.session.put(url, headers=headers, **kwargs)

    async def delete(self, endpoint: str, **kwargs) -> aiohttp.ClientResponse:
        """Make DELETE request to GitHub API"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "MCP-Git-Server/1.1.0",
        }

        return await self.session.delete(url, headers=headers, **kwargs)


def get_github_client() -> Optional[GitHubClient]:
    """Get GitHub client with token from environment.

    Assumes environment variables have already been loaded by the server.
    """
    token = os.getenv("GITHUB_TOKEN")
    logger.debug(f"🔑 GITHUB_TOKEN check: {'Found' if token else 'Not found'}")

    if not token:
        logger.error(
            "🔍 No GitHub token found in environment (GITHUB_TOKEN). "
            "Ensure environment variables are loaded before calling this function."
        )
        logger.debug(
            f"📋 Available env vars starting with 'GITHUB': {[k for k in os.environ.keys() if k.startswith('GITHUB')]}"
        )
        return None

    if not GitHubClient._is_valid_github_token(token):
        logger.warning("⚠️ GITHUB_TOKEN appears to be invalid format")
        return None

    logger.debug("✅ GitHub token found and validated")

    # Create aiohttp session (caller is responsible for closing)
    session = aiohttp.ClientSession()
    return GitHubClient(token=token, session=session)
