"""Azure DevOps API client and authentication"""

import logging
import os
import re
from dataclasses import dataclass

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class AzureClient:
    """Azure DevOps API client with authentication."""

    token: str
    organization: str
    session: aiohttp.ClientSession
    base_url: str = "https://dev.azure.com"

    def __post_init__(self):
        """Validate Azure token format"""
        if not self._is_valid_azure_token(self.token):
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

    async def get(self, endpoint: str, **kwargs) -> aiohttp.ClientResponse:
        """Make GET request to Azure DevOps API"""
        # Azure DevOps API expects the organization in the URL
        # Format: https://dev.azure.com/{organization}/{project}/_apis/...
        url = f"{self.base_url}/{self.organization}/{endpoint.lstrip('/')}"

        # Azure DevOps uses Basic authentication with PAT
        auth = aiohttp.BasicAuth("", self.token)

        headers = {
            "Accept": "application/json",
            "User-Agent": "MCP-Git-Server/1.1.0",
        }

        return await self.session.get(url, auth=auth, headers=headers, **kwargs)

    async def post(self, endpoint: str, **kwargs) -> aiohttp.ClientResponse:
        """Make POST request to Azure DevOps API"""
        url = f"{self.base_url}/{self.organization}/{endpoint.lstrip('/')}"
        auth = aiohttp.BasicAuth("", self.token)

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "MCP-Git-Server/1.1.0",
        }

        return await self.session.post(url, auth=auth, headers=headers, **kwargs)

    async def patch(self, endpoint: str, **kwargs) -> aiohttp.ClientResponse:
        """Make PATCH request to Azure DevOps API"""
        url = f"{self.base_url}/{self.organization}/{endpoint.lstrip('/')}"
        auth = aiohttp.BasicAuth("", self.token)

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "MCP-Git-Server/1.1.0",
        }

        return await self.session.patch(url, auth=auth, headers=headers, **kwargs)


def get_azure_client() -> AzureClient | None:
    """Get Azure DevOps client with token and organization from environment.

    Assumes environment variables have already been loaded by the server.
    Requires:
    - AZURE_DEVOPS_TOKEN: Personal Access Token
    - AZURE_DEVOPS_ORG: Organization name
    """
    token = os.getenv("AZURE_DEVOPS_TOKEN")
    organization = os.getenv("AZURE_DEVOPS_ORG")

    logger.debug(f"🔑 AZURE_DEVOPS_TOKEN check: {'Found' if token else 'Not found'}")
    org_status = "Found" if organization else "Not found"
    logger.debug(f"🏢 AZURE_DEVOPS_ORG check: {org_status}")

    if not token:
        logger.error(
            "🔍 No Azure DevOps token found in environment (AZURE_DEVOPS_TOKEN). "
            "Ensure environment variables are loaded before calling this function."
        )
        return None

    if not organization:
        logger.error(
            "🔍 No Azure DevOps organization found in environment (AZURE_DEVOPS_ORG). "
            "Ensure environment variables are loaded before calling this function."
        )
        return None

    if not AzureClient._is_valid_azure_token(token):
        logger.warning("⚠️ AZURE_DEVOPS_TOKEN appears to be invalid format")
        return None

    logger.debug("✅ Azure DevOps token and organization found and validated")

    # Create aiohttp session (caller is responsible for closing)
    session = aiohttp.ClientSession()
    return AzureClient(token=token, organization=organization, session=session)
