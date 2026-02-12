"""Security middleware for HTTP transport.

This module provides security layers for the HTTP transport:
- LocalhostOnlyMiddleware: Restricts access to localhost connections only
- APIKeyMiddleware: Optional API key validation via X-API-Key header
"""

import logging
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class LocalhostOnlyMiddleware(BaseHTTPMiddleware):
    """Middleware that restricts access to localhost connections only.

    This middleware checks the client IP address and only allows requests
    from localhost (127.0.0.1, ::1, or localhost hostname).

    Any requests from other IP addresses will receive a 403 Forbidden response.
    """

    ALLOWED_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}

    async def dispatch(self, request: Request, call_next):
        """Process the request and validate client IP.

        Args:
            request: The incoming HTTP request
            call_next: The next middleware or endpoint handler

        Returns:
            Response from the next handler if allowed, otherwise 403 Forbidden
        """
        client_host = request.client.host if request.client else None

        if client_host not in self.ALLOWED_HOSTS:
            logger.warning(
                "Blocked non-localhost request from %s to %s",
                client_host,
                request.url.path
            )
            return JSONResponse(
                status_code=403,
                content={
                    "error": "Forbidden",
                    "message": "Access restricted to localhost only"
                }
            )

        return await call_next(request)


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Middleware that validates API key via X-API-Key header.

    This middleware provides optional API key authentication. If an API key
    is configured, all requests must include a matching X-API-Key header.
    If no API key is configured, all requests are allowed through.

    Args:
        api_key: The expected API key, or None to skip validation
    """

    def __init__(self, app, api_key: Optional[str] = None):
        """Initialize the API key middleware.

        Args:
            app: The ASGI application
            api_key: The expected API key, or None to skip validation
        """
        super().__init__(app)
        self.api_key = api_key
        self.enabled = api_key is not None

        if self.enabled:
            logger.info("API key authentication enabled")
        else:
            logger.info("API key authentication disabled")

    async def dispatch(self, request: Request, call_next):
        """Process the request and validate API key if enabled.

        Args:
            request: The incoming HTTP request
            call_next: The next middleware or endpoint handler

        Returns:
            Response from the next handler if authorized, otherwise 401 Unauthorized
        """
        # Skip validation if API key is not configured
        if not self.enabled:
            return await call_next(request)

        # Check for X-API-Key header
        provided_key = request.headers.get("X-API-Key")

        if not provided_key:
            logger.warning(
                "Request to %s missing X-API-Key header",
                request.url.path
            )
            return JSONResponse(
                status_code=401,
                content={
                    "error": "Unauthorized",
                    "message": "X-API-Key header required"
                }
            )

        if provided_key != self.api_key:
            logger.warning(
                "Request to %s with invalid API key",
                request.url.path
            )
            return JSONResponse(
                status_code=401,
                content={
                    "error": "Unauthorized",
                    "message": "Invalid API key"
                }
            )

        # API key is valid, proceed with request
        return await call_next(request)
