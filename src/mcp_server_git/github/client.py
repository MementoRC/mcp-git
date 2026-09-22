"""GitHub API client and authentication"""

import logging
import os
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


class GraphQLError(Exception):
    """Raised when a GitHub GraphQL response contains a top-level ``errors``
    array.

    GraphQL returns HTTP 200 even when the operation failed — the failure
    lives in ``errors``, not the status code. Raising here (rather than
    silently returning the errors alongside ``data``) makes it hard for a
    caller to accidentally treat a failed mutation as a success.
    """

    def __init__(self, errors: list[dict[str, Any]]):
        self.errors = errors
        messages = "; ".join(e.get("message", str(e)) for e in errors)
        super().__init__(f"GraphQL request failed: {messages}")


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

    async def get(
        self,
        endpoint: str,
        *,
        accept: str = "application/vnd.github.v3+json",
        **kwargs,
    ) -> aiohttp.ClientResponse:
        """Make GET request to GitHub API"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": accept,
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

    async def graphql(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute a GraphQL request against ``/graphql``.

        GitHub's GraphQL endpoint returns HTTP 200 even when the operation
        fails; errors are reported in a top-level ``errors`` array in the
        JSON body instead. This method raises :class:`GraphQLError` when
        that array is non-empty, so a caller cannot mistake a failed
        mutation for success by checking only the HTTP status.

        Returns the ``data`` object of a successful response.
        """
        url = f"{self.base_url}/graphql"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "MCP-Git-Server/1.1.0",
        }
        payload: dict[str, Any] = {"query": query}
        if variables is not None:
            payload["variables"] = variables

        response = await self.session.post(url, headers=headers, json=payload)
        if response.status != 200:
            error_text = await response.text()
            raise GraphQLError([{"message": f"HTTP {response.status}: {error_text}"}])

        result = await response.json()
        errors = result.get("errors")
        if errors:
            raise GraphQLError(errors)

        return result.get("data", {})


def get_github_client() -> GitHubClient | None:
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


@asynccontextmanager
async def github_client_context():
    """Async context manager for GitHub client with guaranteed resource cleanup."""
    client = None
    try:
        client = get_github_client()
        if not client:
            raise ValueError(
                "GitHub token not configured. Set GITHUB_TOKEN environment variable."
            )
        yield client
    finally:
        if client and client.session:
            try:
                await client.session.close()
            except Exception as cleanup_error:
                logger.warning(f"Error during client cleanup: {cleanup_error}")
