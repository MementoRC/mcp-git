"""Server middleware components for MCP Git Server.

This module provides composable middleware for cross-cutting concerns including
authentication, logging, error handling, and request tracking.
"""

import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from mcp.types import (
    ErrorData,
    JSONRPCError,
)

# Note: DebuggableComponent protocol integration planned for future versions


# Type aliases for middleware
MiddlewareHandler = Callable[[Any], Awaitable[Any]]
MiddlewareChain = list["BaseMiddleware"]

logger = logging.getLogger(__name__)


@dataclass
class MiddlewareContext:
    """Context object passed through middleware chain."""

    request: Any
    response: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)

    def elapsed_time(self) -> float:
        """Get elapsed time since context creation."""
        return time.time() - self.start_time


class BaseMiddleware(ABC):
    """Abstract base class for all middleware components."""

    def __init__(self, name: str):
        self.name = name
        self.enabled = True
        self.logger = logging.getLogger(f"{__name__}.{name}")

    @abstractmethod
    async def process_request(
        self, context: MiddlewareContext, next_handler: MiddlewareHandler
    ) -> Any:
        """Process a request through this middleware.

        Args:
            context: The middleware context
            next_handler: The next handler in the chain

        Returns:
            The processed response
        """
        pass

    def is_enabled(self) -> bool:
        """Check if this middleware is enabled."""
        return self.enabled

    def enable(self) -> None:
        """Enable this middleware."""
        self.enabled = True

    def disable(self) -> None:
        """Disable this middleware."""
        self.enabled = False


class AuthenticationMiddleware(BaseMiddleware):
    """Middleware for handling GitHub token authentication."""

    def __init__(self, required_scopes: list[str] | None = None):
        super().__init__("authentication")
        self.required_scopes = required_scopes or []
        self.token_cache: dict[str, dict[str, Any]] = {}
        self.last_validation: dict[str, float] = {}
        self.validation_interval = 300  # 5 minutes

    async def process_request(
        self, context: MiddlewareContext, next_handler: MiddlewareHandler
    ) -> Any:
        """Process request with authentication validation."""
        if not self.is_enabled():
            return await next_handler(context)

        # Check if this request requires authentication
        if not self._requires_auth(context.request):
            return await next_handler(context)

        try:
            # Validate GitHub token
            token_valid = await self._validate_github_token(context)
            if not token_valid:
                return self._create_auth_error("Invalid or missing GitHub token")

            # Add authentication metadata
            context.metadata["authenticated"] = True
            context.metadata["auth_method"] = "github_token"

            self.logger.debug("Authentication successful")
            return await next_handler(context)

        except Exception as e:
            self.logger.error(f"Authentication error: {e}")
            return self._create_auth_error(f"Authentication failed: {str(e)}")

    def _requires_auth(self, request: Any) -> bool:
        """Check if request requires authentication."""
        if hasattr(request, "method") and request.method.startswith("github_"):
            return True
        return False

    async def _validate_github_token(self, context: MiddlewareContext) -> bool:
        """Validate GitHub token (simplified implementation)."""
        import os

        token = os.getenv("GITHUB_TOKEN")
        if not token:
            return False

        # Check cache first
        now = time.time()
        if (
            token in self.last_validation
            and now - self.last_validation[token] < self.validation_interval
        ):
            return token in self.token_cache

        # Validate token format
        valid_prefixes = ["ghp_", "gho_", "ghu_", "ghs_", "github_pat_", "ghr_"]
        if not any(token.startswith(prefix) for prefix in valid_prefixes):
            return False

        # Cache validation result
        self.token_cache[token] = {"valid": True, "timestamp": now}
        self.last_validation[token] = now

        return True

    def _create_auth_error(self, message: str) -> JSONRPCError:
        """Create authentication error response."""
        return JSONRPCError(
            jsonrpc="2.0",
            id="auth-error",
            error=ErrorData(
                code=-32001,
                message="Authentication Error",
                data={"details": message},
            ),
        )


class LoggingMiddleware(BaseMiddleware):
    """Middleware for centralized request/response logging."""

    def __init__(self, log_requests: bool = True, log_responses: bool = True):
        super().__init__("logging")
        self.log_requests = log_requests
        self.log_responses = log_responses
        self.request_counter = 0

    async def process_request(
        self, context: MiddlewareContext, next_handler: MiddlewareHandler
    ) -> Any:
        """Process request with comprehensive logging."""
        if not self.is_enabled():
            return await next_handler(context)

        self.request_counter += 1
        request_id = f"req_{self.request_counter}_{int(time.time())}"
        context.metadata["request_id"] = request_id

        # Log incoming request
        if self.log_requests:
            self._log_request(context, request_id)

        try:
            # Process request
            response = await next_handler(context)
            context.response = response

            # Log successful response
            if self.log_responses:
                self._log_response(context, request_id, success=True)

            return response

        except Exception as e:
            # Log error response
            if self.log_responses:
                self._log_response(context, request_id, success=False, error=e)
            raise

    def _log_request(self, context: MiddlewareContext, request_id: str) -> None:
        """Log incoming request details."""
        request = context.request
        method = getattr(request, "method", "unknown")

        self.logger.info(f"🔄 [{request_id}] Incoming request: {method}")
        self.logger.debug(
            f"📝 [{request_id}] Request details: {type(request).__name__}"
        )

    def _log_response(
        self,
        context: MiddlewareContext,
        request_id: str,
        success: bool,
        error: Exception | None = None,
    ) -> None:
        """Log response details."""
        elapsed = context.elapsed_time()

        if success:
            response_type = (
                type(context.response).__name__ if context.response else "None"
            )
            self.logger.info(
                f"✅ [{request_id}] Request completed in {elapsed:.3f}s -> {response_type}"
            )
        else:
            error_msg = str(error) if error else "Unknown error"
            self.logger.error(
                f"❌ [{request_id}] Request failed in {elapsed:.3f}s: {error_msg}"
            )


class ErrorHandlingMiddleware(BaseMiddleware):
    """Middleware for consistent error processing and recovery."""

    def __init__(self, mask_sensitive_data: bool = True):
        super().__init__("error_handling")
        self.mask_sensitive_data = mask_sensitive_data
        self.error_counts: dict[str, int] = {}

    async def process_request(
        self, context: MiddlewareContext, next_handler: MiddlewareHandler
    ) -> Any:
        """Process request with comprehensive error handling."""
        if not self.is_enabled():
            return await next_handler(context)

        try:
            return await next_handler(context)

        except Exception as e:
            # Check if it's a JSONRPCError (which is a Pydantic model, not an exception)
            if hasattr(e, "jsonrpc") and hasattr(e, "error"):
                # Re-raise JSON-RPC errors as-is
                raise
            # Handle unexpected errors
            self._track_error(e)
            return self._create_error_response(e, context)

    def _track_error(self, error: Exception) -> None:
        """Track error occurrences for monitoring."""
        error_type = type(error).__name__
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1

        self.logger.error(f"🚨 Unhandled error ({error_type}): {str(error)}")

    def _create_error_response(
        self, error: Exception, context: MiddlewareContext
    ) -> JSONRPCError:
        """Create standardized error response."""
        error_message = str(error)

        # Mask sensitive information if enabled
        if self.mask_sensitive_data:
            error_message = self._mask_sensitive_info(error_message)

        # Determine error code based on error type
        error_code = self._get_error_code(error)

        return JSONRPCError(
            jsonrpc="2.0",
            id="error",
            error=ErrorData(
                code=error_code,
                message="Internal Server Error",
                data={"details": error_message, "error_type": type(error).__name__},
            ),
        )

    def _mask_sensitive_info(self, message: str) -> str:
        """Mask sensitive information in error messages."""
        import re

        # Mask tokens and API keys
        message = re.sub(
            r"(token|key|secret)[:=]\s*\S+",
            r"\1: [REDACTED]",
            message,
            flags=re.IGNORECASE,
        )

        # Mask file paths (keep just filename)
        message = re.sub(r"/[^/\s]+/", "/...//", message)

        return message

    def _get_error_code(self, error: Exception) -> int:
        """Determine appropriate JSON-RPC error code."""
        error_type = type(error).__name__

        code_mapping = {
            "ValueError": -32602,  # Invalid params
            "FileNotFoundError": -32603,  # Internal error
            "PermissionError": -32001,  # Authentication error
            "TimeoutError": -32603,  # Internal error
        }

        return code_mapping.get(error_type, -32603)  # Default to internal error


class RequestTrackingMiddleware(BaseMiddleware):
    """Middleware for tracking request metrics and performance."""

    def __init__(self, max_history: int = 1000):
        super().__init__("request_tracking")
        self.max_history = max_history
        self.request_history: list[dict[str, Any]] = []
        self.active_requests: dict[str, dict[str, Any]] = {}

    async def process_request(
        self, context: MiddlewareContext, next_handler: MiddlewareHandler
    ) -> Any:
        """Process request with performance tracking."""
        if not self.is_enabled():
            return await next_handler(context)

        request_id = context.metadata.get("request_id", "unknown")

        # Track request start
        request_info = {
            "id": request_id,
            "method": getattr(context.request, "method", "unknown"),
            "start_time": context.start_time,
            "timestamp": datetime.now().isoformat(),
        }

        self.active_requests[request_id] = request_info

        try:
            # Process request
            response = await next_handler(context)

            # Track successful completion
            self._record_completion(request_id, context, success=True)

            return response

        except Exception as e:
            # Track failed completion
            self._record_completion(request_id, context, success=False, error=e)
            raise
        finally:
            # Remove from active requests
            self.active_requests.pop(request_id, None)

    def _record_completion(
        self,
        request_id: str,
        context: MiddlewareContext,
        success: bool,
        error: Exception | None = None,
    ) -> None:
        """Record request completion in history."""
        request_info = self.active_requests.get(request_id, {})

        completion_record = {
            **request_info,
            "success": success,
            "duration": context.elapsed_time(),
            "end_time": time.time(),
            "error_type": type(error).__name__ if error else None,
        }

        self.request_history.append(completion_record)

        # Maintain history size limit
        if len(self.request_history) > self.max_history:
            self.request_history = self.request_history[-self.max_history :]

    def get_metrics(self) -> dict[str, Any]:
        """Get request tracking metrics."""
        if not self.request_history:
            return {}

        total_requests = len(self.request_history)
        successful_requests = sum(1 for r in self.request_history if r["success"])

        durations = [r["duration"] for r in self.request_history if "duration" in r]
        avg_duration = sum(durations) / len(durations) if durations else 0

        return {
            "total_requests": total_requests,
            "successful_requests": successful_requests,
            "error_rate": (total_requests - successful_requests) / total_requests,
            "average_duration": avg_duration,
            "active_requests": len(self.active_requests),
            "last_request": self.request_history[-1]["timestamp"]
            if self.request_history
            else None,
        }


class MiddlewareChainManager:
    """Manager for composing and executing middleware chains."""

    def __init__(self):
        self.middlewares: list[BaseMiddleware] = []
        self.logger = logging.getLogger(f"{__name__}.MiddlewareChainManager")

    def add_middleware(self, middleware: BaseMiddleware) -> None:
        """Add middleware to the chain."""
        self.middlewares.append(middleware)
        self.logger.debug(f"Added middleware: {middleware.name}")

    def remove_middleware(self, name: str) -> bool:
        """Remove middleware by name."""
        for i, middleware in enumerate(self.middlewares):
            if middleware.name == name:
                removed = self.middlewares.pop(i)
                self.logger.debug(f"Removed middleware: {removed.name}")
                return True
        return False

    def get_middleware(self, name: str) -> BaseMiddleware | None:
        """Get middleware by name."""
        for middleware in self.middlewares:
            if middleware.name == name:
                return middleware
        return None

    async def process_request(self, request: Any) -> Any:
        """Process request through the entire middleware chain."""
        context = MiddlewareContext(request=request)

        # Create the middleware chain
        async def create_handler(index: int) -> MiddlewareHandler:
            """Create handler for middleware at given index."""
            if index >= len(self.middlewares):
                # End of chain - return the request as-is
                async def end_handler(ctx: MiddlewareContext) -> Any:
                    return ctx.request

                return end_handler

            middleware = self.middlewares[index]

            if not middleware.is_enabled():
                # Skip disabled middleware
                return await create_handler(index + 1)

            async def handler(ctx: MiddlewareContext) -> Any:
                next_handler = await create_handler(index + 1)
                return await middleware.process_request(ctx, next_handler)

            return handler

        # Execute the chain
        handler = await create_handler(0)
        return await handler(context)

    def get_chain_state(self) -> dict[str, Any]:
        """Get current state of the middleware chain."""
        return {
            "middleware_count": len(self.middlewares),
            "middlewares": [
                {"name": m.name, "enabled": m.is_enabled(), "type": type(m).__name__}
                for m in self.middlewares
            ],
        }

    def validate_chain_configuration(self) -> dict[str, Any]:
        """Validate middleware chain configuration."""
        issues = []

        # Check for duplicate middleware names
        names = [m.name for m in self.middlewares]
        duplicates = [name for name in names if names.count(name) > 1]
        if duplicates:
            issues.append(f"Duplicate middleware names: {duplicates}")

        # Check middleware ordering
        middleware_types = [type(m).__name__ for m in self.middlewares]

        # Authentication should come early
        if "AuthenticationMiddleware" in middleware_types:
            auth_index = middleware_types.index("AuthenticationMiddleware")
            if auth_index > 2:
                issues.append(
                    "AuthenticationMiddleware should be positioned earlier in chain"
                )

        # Error handling should be early to catch all errors
        if "ErrorHandlingMiddleware" in middleware_types:
            error_index = middleware_types.index("ErrorHandlingMiddleware")
            if error_index > 1:
                issues.append(
                    "ErrorHandlingMiddleware should be positioned early in chain"
                )

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "middleware_order": middleware_types,
        }

    def get_debug_info(self) -> dict[str, Any]:
        """Get debug information about the middleware chain."""
        debug_info = {
            "chain_length": len(self.middlewares),
            "enabled_count": sum(1 for m in self.middlewares if m.is_enabled()),
            "middleware_details": [],
        }

        for middleware in self.middlewares:
            middleware_debug = {
                "name": middleware.name,
                "type": type(middleware).__name__,
                "enabled": middleware.is_enabled(),
            }

            # Add specific debug info for different middleware types
            if isinstance(middleware, RequestTrackingMiddleware):
                middleware_debug["metrics"] = middleware.get_metrics()
            elif isinstance(middleware, ErrorHandlingMiddleware):
                middleware_debug["error_counts"] = middleware.error_counts
            elif isinstance(middleware, AuthenticationMiddleware):
                middleware_debug["cache_size"] = len(middleware.token_cache)

            debug_info["middleware_details"].append(middleware_debug)

        return debug_info


def create_default_middleware_chain() -> MiddlewareChainManager:
    """Create a default middleware chain with standard components."""
    chain = MiddlewareChainManager()

    # Add middleware in order (most critical first)
    chain.add_middleware(ErrorHandlingMiddleware(mask_sensitive_data=True))
    chain.add_middleware(LoggingMiddleware(log_requests=True, log_responses=True))
    chain.add_middleware(AuthenticationMiddleware())
    chain.add_middleware(RequestTrackingMiddleware(max_history=1000))

    return chain


def create_enhanced_middleware_chain(
    enable_token_limits: bool = True,
) -> MiddlewareChainManager:
    """Create an enhanced middleware chain with token limit protection."""
    chain = MiddlewareChainManager()

    # Add middleware in order (most critical first)
    chain.add_middleware(ErrorHandlingMiddleware(mask_sensitive_data=True))
    chain.add_middleware(LoggingMiddleware(log_requests=True, log_responses=True))
    chain.add_middleware(AuthenticationMiddleware())
    chain.add_middleware(RequestTrackingMiddleware(max_history=1000))

    # Add token limit middleware if enabled
    if enable_token_limits:
        try:
            from ..middlewares.token_limit import create_token_limit_middleware

            token_middleware = create_token_limit_middleware(
                llm_token_limit=20000,  # Conservative limit for LLMs
                enable_optimization=True,
                enable_truncation=True,
            )
            chain.add_middleware(token_middleware)
        except ImportError as e:
            # Log warning but continue without token limits
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Token limit middleware not available: {e}")

    return chain
