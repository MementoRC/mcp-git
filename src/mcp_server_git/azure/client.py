"""Azure DevOps API client and authentication"""

import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# Default organization for conda-forge feedstock CI lookups.
# Override with AZURE_DEVOPS_ORG environment variable.
_DEFAULT_ORG = "conda-forge"


@dataclass
class AzureClient:
    """Azure DevOps API client with optional authentication.

    When token is None or empty the client operates in anonymous mode,
    which works for public projects (e.g. conda-forge) on read-only endpoints.
    Write endpoints (POST/PATCH) always require a token.
    """

    token: Optional[str]
    organization: str
    session: aiohttp.ClientSession
    base_url: str = "https://dev.azure.com"

    def __post_init__(self):
        """Warn when a token is present but appears malformed."""
        if self.token and not self._is_valid_azure_token(self.token):
            logger.warning("⚠️ Azure DevOps token format appears invalid")

    @staticmethod
    def _is_valid_azure_token(token: str) -> bool:
        """Validate Azure DevOps token format (Personal Access Token)"""
        if not token or len(token.strip()) == 0:
            return False

        # Azure DevOps PAT tokens are variable length (base64 encoded)
        # They can contain alphanumeric characters, +, /, and =
        # Accept tokens with 20 or more characters
        pattern = r"^[a-zA-Z0-9+/=]{20,}$"
        return bool(re.match(pattern, token.strip()))

    def _auth(self) -> Optional[aiohttp.BasicAuth]:
        """Return BasicAuth only when a token is present.

        Omitting auth entirely avoids sending an Authorization header,
        which is required for anonymous access to public Azure DevOps projects.
        """
        if self.token:
            return aiohttp.BasicAuth("", self.token)
        return None

    async def get(
        self, endpoint: str, accept: str = "application/json", **kwargs
    ) -> aiohttp.ClientResponse:
        """Make GET request to Azure DevOps API.

        Args:
            endpoint: API endpoint (organization is prepended automatically).
            accept: Value for the Accept header. Defaults to
                "application/json". Pass "text/plain" for endpoints that return
                a bare ``List<String>`` — notably build log *content*
                (``.../logs/{logId}``), which Azure DevOps refuses to serialize
                as JSON with a 500 "doesn't implement ISecuredObject" error.
        """
        # Azure DevOps API expects the organization in the URL
        # Format: https://dev.azure.com/{organization}/{project}/_apis/...
        url = f"{self.base_url}/{self.organization}/{endpoint.lstrip('/')}"

        headers = {
            "Accept": accept,
            "User-Agent": "MCP-Git-Server/1.1.0",
        }

        auth = self._auth()
        # Only pass auth kwarg when we have credentials; passing auth=None
        # still causes aiohttp to omit the header, but being explicit is safer.
        if auth is not None:
            response = await self.session.get(url, auth=auth, headers=headers, **kwargs)
            if response.status == 401:
                # Stale or expired PAT — retry without auth so public projects
                # can still be reached anonymously.
                await response.release()
                logger.warning(
                    "Azure 401 with auth — retrying anonymously for public project access"
                )
                response = await self.session.get(url, headers=headers, **kwargs)
            return response
        return await self.session.get(url, headers=headers, **kwargs)

    async def post(self, endpoint: str, **kwargs) -> aiohttp.ClientResponse:
        """Make POST request to Azure DevOps API.

        Raises ValueError if no token is configured — write operations on
        Azure DevOps always require authentication.
        """
        if not self.token:
            raise ValueError("AZURE_DEVOPS_TOKEN required for write operations")

        url = f"{self.base_url}/{self.organization}/{endpoint.lstrip('/')}"
        auth = aiohttp.BasicAuth("", self.token)

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "MCP-Git-Server/1.1.0",
        }

        return await self.session.post(url, auth=auth, headers=headers, **kwargs)

    async def patch(self, endpoint: str, **kwargs) -> aiohttp.ClientResponse:
        """Make PATCH request to Azure DevOps API.

        Raises ValueError if no token is configured — write operations on
        Azure DevOps always require authentication.
        """
        if not self.token:
            raise ValueError("AZURE_DEVOPS_TOKEN required for write operations")

        url = f"{self.base_url}/{self.organization}/{endpoint.lstrip('/')}"
        auth = aiohttp.BasicAuth("", self.token)

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "MCP-Git-Server/1.1.0",
        }

        return await self.session.patch(url, auth=auth, headers=headers, **kwargs)


def get_azure_client() -> AzureClient | None:
    """Get Azure DevOps client from environment variables.

    AZURE_DEVOPS_TOKEN is optional — omitting it enables anonymous (read-only)
    access to public projects such as conda-forge.

    AZURE_DEVOPS_ORG defaults to "conda-forge" when unset, covering the primary
    use case of inspecting conda-forge feedstock pipelines.

    Returns None only when the organization cannot be determined.
    """
    token = os.getenv("AZURE_DEVOPS_TOKEN") or None  # coerce "" → None
    organization = os.getenv("AZURE_DEVOPS_ORG") or _DEFAULT_ORG

    token_status = "Found" if token else "Not set (anonymous mode)"
    logger.debug(f"🔑 AZURE_DEVOPS_TOKEN check: {token_status}")
    logger.debug(f"🏢 AZURE_DEVOPS_ORG: {organization}")

    if token and not AzureClient._is_valid_azure_token(token):
        logger.warning("⚠️ AZURE_DEVOPS_TOKEN appears to be invalid format")
        # Still build the client; the API call will fail with a useful error.

    logger.debug(
        "✅ Azure DevOps client ready"
        + (" (authenticated)" if token else " (anonymous)")
    )

    # Create aiohttp session (caller is responsible for closing)
    session = aiohttp.ClientSession()
    return AzureClient(token=token, organization=organization, session=session)
