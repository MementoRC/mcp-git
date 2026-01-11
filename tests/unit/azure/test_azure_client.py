"""Unit tests for Azure DevOps client module."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import BasicAuth

from src.mcp_server_git.azure.client import AzureClient, get_azure_client


class TestAzureClient:
    """Test Azure DevOps client initialization and validation."""

    def test_valid_azure_token(self):
        """Test Azure client with valid token format."""
        # Azure PAT tokens are variable length (base64 encoded)
        valid_token = "a" * 52
        session = MagicMock()

        client = AzureClient(token=valid_token, organization="myorg", session=session)

        assert client.token == valid_token
        assert client.organization == "myorg"
        assert client.base_url == "https://dev.azure.com"

    def test_invalid_azure_token(self):
        """Test Azure client with invalid token format."""
        invalid_token = "invalid_token"
        session = MagicMock()

        # Should still create client but log warning
        client = AzureClient(token=invalid_token, organization="myorg", session=session)

        assert client.token == invalid_token

    def test_is_valid_azure_token(self):
        """Test Azure token validation logic."""
        # Valid 52-character token
        assert AzureClient._is_valid_azure_token("a" * 52) is True

        # Valid - minimum 20 characters
        assert AzureClient._is_valid_azure_token("a" * 20) is True

        # Valid - variable length tokens
        assert AzureClient._is_valid_azure_token("a" * 53) is True
        assert AzureClient._is_valid_azure_token("a" * 100) is True

        # Invalid - too short (less than 20)
        assert AzureClient._is_valid_azure_token("short") is False
        assert AzureClient._is_valid_azure_token("a" * 19) is False

        # Invalid - empty
        assert AzureClient._is_valid_azure_token("") is False

        # Valid - with base64 characters
        assert (
            AzureClient._is_valid_azure_token(
                "a1B2c3D4e5F6g7H8i9J0K1L2m3N4o5P6q7R8s9T0u1V2w3X4y5Z6"
            )
            is True
        )

    @patch.dict(
        os.environ, {"AZURE_DEVOPS_TOKEN": "a" * 52, "AZURE_DEVOPS_ORG": "testorg"}
    )
    @patch("src.mcp_server_git.azure.client.aiohttp.ClientSession")
    def test_get_azure_client_success(self, mock_session):
        """Test getting Azure client with valid environment variables."""
        client = get_azure_client()

        assert client is not None
        assert client.organization == "testorg"
        assert len(client.token) == 52

    @patch.dict(os.environ, {}, clear=True)
    def test_get_azure_client_no_token(self):
        """Test getting Azure client without token."""
        client = get_azure_client()
        assert client is None

    @patch.dict(os.environ, {"AZURE_DEVOPS_TOKEN": "a" * 52}, clear=True)
    def test_get_azure_client_no_org(self):
        """Test getting Azure client without organization."""
        client = get_azure_client()
        assert client is None

    @patch.dict(
        os.environ, {"AZURE_DEVOPS_TOKEN": "invalid", "AZURE_DEVOPS_ORG": "testorg"}
    )
    def test_get_azure_client_invalid_token(self):
        """Test getting Azure client with invalid token format."""
        client = get_azure_client()
        assert client is None


class TestAzureClientMethods:
    """Test Azure DevOps client HTTP methods."""

    @pytest.mark.asyncio
    async def test_get_request(self):
        """Test Azure client GET request."""
        session = MagicMock()
        mock_response = MagicMock()
        session.get = AsyncMock(return_value=mock_response)

        client = AzureClient(token="a" * 52, organization="myorg", session=session)

        result = await client.get("myproject/_apis/build/builds/123")

        # Verify the URL construction
        session.get.assert_called_once()
        call_args = session.get.call_args
        assert (
            call_args[0][0]
            == "https://dev.azure.com/myorg/myproject/_apis/build/builds/123"
        )

        # Verify BasicAuth is used
        assert "auth" in call_args[1]
        auth = call_args[1]["auth"]
        assert isinstance(auth, BasicAuth)

    @pytest.mark.asyncio
    async def test_post_request(self):
        """Test Azure client POST request."""
        session = MagicMock()
        mock_response = MagicMock()
        session.post = AsyncMock(return_value=mock_response)

        client = AzureClient(token="a" * 52, organization="myorg", session=session)

        result = await client.post("myproject/_apis/build/builds")

        session.post.assert_called_once()
        call_args = session.post.call_args
        assert (
            call_args[0][0]
            == "https://dev.azure.com/myorg/myproject/_apis/build/builds"
        )
