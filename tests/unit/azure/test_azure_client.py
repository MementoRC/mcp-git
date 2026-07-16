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
    @patch("src.mcp_server_git.azure.client.aiohttp.ClientSession")
    def test_get_azure_client_no_token(self, mock_session):
        """Without a token, return an anonymous client defaulting to conda-forge."""
        client = get_azure_client()

        assert client is not None
        assert client.token is None
        # No AZURE_DEVOPS_ORG → falls back to the conda-forge default
        assert client.organization == "conda-forge"

    @patch.dict(os.environ, {"AZURE_DEVOPS_TOKEN": "a" * 52}, clear=True)
    @patch("src.mcp_server_git.azure.client.aiohttp.ClientSession")
    def test_get_azure_client_no_org(self, mock_session):
        """Without AZURE_DEVOPS_ORG, the client falls back to conda-forge."""
        client = get_azure_client()

        assert client is not None
        assert client.organization == "conda-forge"
        assert len(client.token) == 52

    @patch.dict(
        os.environ, {"AZURE_DEVOPS_TOKEN": "invalid", "AZURE_DEVOPS_ORG": "testorg"}
    )
    @patch("src.mcp_server_git.azure.client.aiohttp.ClientSession")
    def test_get_azure_client_invalid_token(self, mock_session):
        """An invalid token format still yields a client; the API call surfaces the error."""
        client = get_azure_client()

        assert client is not None
        assert client.token == "invalid"
        assert client.organization == "testorg"


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
    async def test_get_sends_text_plain_accept_header_when_accept_arg_passed(self):
        """GET with accept='text/plain' must send that value in the Accept header."""
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_session.get = AsyncMock(return_value=mock_response)

        client = AzureClient(token=None, organization="myorg", session=mock_session)

        await client.get(
            "myproject/_apis/build/builds/123/logs/5?api-version=7.1",
            accept="text/plain",
        )

        mock_session.get.assert_called_once()
        _, kwargs = mock_session.get.call_args
        assert kwargs["headers"]["Accept"] == "text/plain"

    @pytest.mark.asyncio
    async def test_get_defaults_accept_header_to_application_json(self):
        """GET without an accept arg must default the Accept header to application/json."""
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_session.get = AsyncMock(return_value=mock_response)

        client = AzureClient(token=None, organization="myorg", session=mock_session)

        await client.get("myproject/_apis/build/builds/123")

        mock_session.get.assert_called_once()
        _, kwargs = mock_session.get.call_args
        assert kwargs["headers"]["Accept"] == "application/json"

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


class TestAzureClient401Fallback:
    """Test GET 401 anonymous fallback behaviour."""

    @pytest.mark.asyncio
    async def test_get_retries_without_auth_on_401_when_token_present(self):
        """GET with auth that returns 401 is retried anonymously; second response returned."""
        session = MagicMock()

        mock_401 = MagicMock()
        mock_401.status = 401
        mock_401.release = AsyncMock()

        mock_200 = MagicMock()
        mock_200.status = 200

        session.get = AsyncMock(side_effect=[mock_401, mock_200])

        client = AzureClient(token="a" * 52, organization="myorg", session=session)

        result = await client.get("myproject/_apis/build/builds/1")

        assert session.get.call_count == 2
        mock_401.release.assert_awaited_once()

        # Second call must NOT carry an auth kwarg
        second_call_kwargs = session.get.call_args_list[1][1]
        assert "auth" not in second_call_kwargs

        assert result is mock_200

    @pytest.mark.asyncio
    async def test_get_does_not_retry_on_401_when_anonymous(self):
        """GET without a token returns the 401 directly — already anonymous, no retry."""
        session = MagicMock()

        mock_401 = MagicMock()
        mock_401.status = 401

        session.get = AsyncMock(return_value=mock_401)

        client = AzureClient(token=None, organization="myorg", session=session)

        result = await client.get("myproject/_apis/build/builds/1")

        assert session.get.call_count == 1
        assert result is mock_401

    @pytest.mark.asyncio
    async def test_get_returns_first_response_on_200(self):
        """GET with auth that returns 200 is returned directly without a retry."""
        session = MagicMock()

        mock_200 = MagicMock()
        mock_200.status = 200

        session.get = AsyncMock(return_value=mock_200)

        client = AzureClient(token="a" * 52, organization="myorg", session=session)

        result = await client.get("myproject/_apis/build/builds/1")

        assert session.get.call_count == 1
        assert result is mock_200

    @pytest.mark.asyncio
    async def test_post_does_not_retry_on_401(self):
        """POST 401 is propagated unchanged — writes require valid auth."""
        session = MagicMock()

        mock_401 = MagicMock()
        mock_401.status = 401

        session.post = AsyncMock(return_value=mock_401)

        client = AzureClient(token="a" * 52, organization="myorg", session=session)

        result = await client.post("myproject/_apis/build/builds")

        session.post.assert_called_once()
        # Confirm GET was never called
        session.get.assert_not_called()
        assert result is mock_401
