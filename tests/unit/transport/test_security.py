"""Unit tests for security middleware.

Tests the LocalhostOnlyMiddleware and APIKeyMiddleware components
used to secure the HTTP transport layer.
"""

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from mcp_server_git.transport.security import (
    APIKeyMiddleware,
    LocalhostOnlyMiddleware,
)


# Test fixtures for LocalhostOnlyMiddleware
@pytest.fixture
def localhost_app():
    """Create a simple FastAPI app with LocalhostOnlyMiddleware."""
    app = FastAPI()
    app.add_middleware(LocalhostOnlyMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"message": "success"}

    return app


@pytest.fixture
def localhost_client(localhost_app):
    """Create a test client for the localhost-only app."""
    return TestClient(localhost_app)


# Test fixtures for APIKeyMiddleware
@pytest.fixture
def no_key_app():
    """Create a FastAPI app with APIKeyMiddleware but no key required."""
    app = FastAPI()
    app.add_middleware(APIKeyMiddleware, api_key=None)

    @app.get("/test")
    async def test_endpoint():
        return {"message": "success"}

    return app


@pytest.fixture
def with_key_app():
    """Create a FastAPI app with APIKeyMiddleware requiring a key."""
    app = FastAPI()
    app.add_middleware(APIKeyMiddleware, api_key="test-secret-key")

    @app.get("/test")
    async def test_endpoint():
        return {"message": "success"}

    return app


@pytest.fixture
def no_key_client(no_key_app):
    """Create a test client for the app with no key required."""
    return TestClient(no_key_app)


@pytest.fixture
def with_key_client(with_key_app):
    """Create a test client for the app requiring an API key."""
    return TestClient(with_key_app)


# LocalhostOnlyMiddleware Tests
class TestLocalhostOnlyMiddleware:
    """Tests for LocalhostOnlyMiddleware."""

    def test_localhost_ipv4_allowed(self, localhost_client):
        """Test that localhost IPv4 (127.0.0.1) requests are allowed."""
        # TestClient by default uses testclient as the host,
        # but we can override via base_url
        response = localhost_client.get("/test")
        assert response.status_code == 200
        assert response.json() == {"message": "success"}

    @pytest.mark.asyncio
    async def test_localhost_ipv6_allowed(self, localhost_app):
        """Test that localhost IPv6 (::1) requests are allowed."""
        # Use mocking approach to simulate IPv6 client
        from unittest.mock import AsyncMock, MagicMock

        from starlette.requests import Request

        middleware = LocalhostOnlyMiddleware(localhost_app)

        # Create a mock request with IPv6 localhost
        mock_request = MagicMock(spec=Request)
        mock_request.client = MagicMock()
        mock_request.client.host = "::1"
        mock_request.url.path = "/test"

        # Mock call_next to return a success response
        async def mock_call_next(request):
            from starlette.responses import JSONResponse

            return JSONResponse({"message": "success"})

        response = await middleware.dispatch(mock_request, mock_call_next)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_external_ip_blocked(self, localhost_app):
        """Test that external IP addresses are blocked with 403."""
        # We need to create a test scenario where request.client.host
        # is set to an external IP. We'll use a custom test setup.
        from unittest.mock import AsyncMock, MagicMock

        from starlette.requests import Request
        from starlette.responses import Response

        middleware = LocalhostOnlyMiddleware(localhost_app)

        # Create a mock request with external IP
        mock_request = MagicMock(spec=Request)
        mock_request.client = MagicMock()
        mock_request.client.host = "192.168.1.100"
        mock_request.url.path = "/test"

        # Mock call_next (should not be called for blocked requests)
        call_next = AsyncMock()

        response = await middleware.dispatch(mock_request, call_next)

        # Verify the response
        assert response.status_code == 403
        assert (
            response.body
            == b'{"error":"Forbidden","message":"Access restricted to localhost only"}'
        )

        # Verify call_next was not called
        call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_blocked_response_is_json(self, localhost_app):
        """Test that blocked requests receive a valid JSON response."""
        import json
        from unittest.mock import AsyncMock, MagicMock

        from starlette.requests import Request

        middleware = LocalhostOnlyMiddleware(localhost_app)

        # Create a mock request with external IP
        mock_request = MagicMock(spec=Request)
        mock_request.client = MagicMock()
        mock_request.client.host = "10.0.0.1"
        mock_request.url.path = "/test"

        call_next = AsyncMock()

        response = await middleware.dispatch(mock_request, call_next)

        # Verify response is JSON
        assert response.status_code == 403
        assert "application/json" in response.headers.get("content-type", "")

        # Verify JSON structure
        body = json.loads(response.body.decode("utf-8"))
        assert "error" in body
        assert "message" in body
        assert body["error"] == "Forbidden"
        assert "localhost only" in body["message"]


# APIKeyMiddleware Tests
class TestAPIKeyMiddleware:
    """Tests for APIKeyMiddleware."""

    def test_no_key_required_allows_all(self, no_key_client):
        """Test that when api_key=None, all requests are allowed."""
        # Request without any API key header
        response = no_key_client.get("/test")
        assert response.status_code == 200
        assert response.json() == {"message": "success"}

        # Request with an arbitrary header (should still work)
        response = no_key_client.get("/test", headers={"X-API-Key": "anything"})
        assert response.status_code == 200
        assert response.json() == {"message": "success"}

    def test_valid_key_allowed(self, with_key_client):
        """Test that requests with correct X-API-Key header are allowed."""
        response = with_key_client.get(
            "/test", headers={"X-API-Key": "test-secret-key"}
        )
        assert response.status_code == 200
        assert response.json() == {"message": "success"}

    def test_invalid_key_rejected(self, with_key_client):
        """Test that requests with wrong API key are rejected with 401."""
        response = with_key_client.get("/test", headers={"X-API-Key": "wrong-key"})
        assert response.status_code == 401

        body = response.json()
        assert body["error"] == "Unauthorized"
        assert "Invalid API key" in body["message"]

    def test_missing_key_rejected(self, with_key_client):
        """Test that requests missing X-API-Key header are rejected when key required."""
        response = with_key_client.get("/test")
        assert response.status_code == 401

        body = response.json()
        assert body["error"] == "Unauthorized"
        assert "X-API-Key header required" in body["message"]

    def test_unauthorized_response_is_json(self, with_key_client):
        """Test that unauthorized responses are valid JSON."""
        # Test missing key response
        response = with_key_client.get("/test")
        assert response.status_code == 401
        assert "application/json" in response.headers.get("content-type", "")

        body = response.json()
        assert "error" in body
        assert "message" in body

        # Test invalid key response
        response = with_key_client.get("/test", headers={"X-API-Key": "invalid"})
        assert response.status_code == 401
        assert "application/json" in response.headers.get("content-type", "")

        body = response.json()
        assert "error" in body
        assert "message" in body


# Additional integration-style tests
class TestMiddlewareCombination:
    """Tests for middleware combinations."""

    def test_both_middlewares_together(self):
        """Test that both middlewares can work together."""
        app = FastAPI()
        # Apply both middlewares (order matters: outermost first)
        app.add_middleware(APIKeyMiddleware, api_key="secret")
        app.add_middleware(LocalhostOnlyMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"message": "success"}

        client = TestClient(app)

        # Request with valid API key should succeed
        response = client.get("/test", headers={"X-API-Key": "secret"})
        assert response.status_code == 200

        # Request without API key should fail
        response = client.get("/test")
        assert response.status_code == 401

    def test_middleware_init_logging(self, caplog):
        """Test that middleware initialization logs appropriately."""
        import logging

        # Test APIKeyMiddleware with key
        app = FastAPI()
        with caplog.at_level(logging.INFO):
            middleware = APIKeyMiddleware(app, api_key="test-key")
            assert "API key authentication enabled" in caplog.text

        caplog.clear()

        # Test APIKeyMiddleware without key
        app2 = FastAPI()
        with caplog.at_level(logging.INFO):
            middleware2 = APIKeyMiddleware(app2, api_key=None)
            assert "API key authentication disabled" in caplog.text

    @pytest.mark.asyncio
    async def test_middleware_warning_logging(self, caplog):
        """Test that middleware logs warnings for blocked requests."""
        import logging
        from unittest.mock import AsyncMock, MagicMock

        from starlette.requests import Request

        app = FastAPI()

        # Test LocalhostOnlyMiddleware warning
        middleware = LocalhostOnlyMiddleware(app)
        mock_request = MagicMock(spec=Request)
        mock_request.client = MagicMock()
        mock_request.client.host = "192.168.1.1"
        mock_request.url.path = "/test"

        with caplog.at_level(logging.WARNING):
            await middleware.dispatch(mock_request, AsyncMock())
            assert "Blocked non-localhost request" in caplog.text
            assert "192.168.1.1" in caplog.text

        caplog.clear()

        # Test APIKeyMiddleware warning for missing key
        api_middleware = APIKeyMiddleware(app, api_key="secret")
        mock_request2 = MagicMock(spec=Request)
        mock_request2.headers.get.return_value = None
        mock_request2.url.path = "/api/test"

        with caplog.at_level(logging.WARNING):
            await api_middleware.dispatch(mock_request2, AsyncMock())
            assert "missing X-API-Key header" in caplog.text

        caplog.clear()

        # Test APIKeyMiddleware warning for invalid key
        mock_request3 = MagicMock(spec=Request)
        mock_request3.headers.get.return_value = "wrong-key"
        mock_request3.url.path = "/api/test"

        with caplog.at_level(logging.WARNING):
            await api_middleware.dispatch(mock_request3, AsyncMock())
            assert "invalid API key" in caplog.text
