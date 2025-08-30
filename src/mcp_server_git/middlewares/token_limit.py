"""Token limit middleware for MCP Git Server.

This middleware intercepts responses before they're sent to clients and applies
intelligent token limit protection, content optimization, and truncation strategies
to prevent overwhelming LLM clients while preserving semantic meaning.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from ..frameworks.server_middleware import (
    BaseMiddleware,
    MiddlewareContext,
    MiddlewareHandler,
)
from ..utils.content_optimization import ClientType, ResponseFormatter
from ..utils.token_management import (
    ClientDetector,
    IntelligentTruncationManager,
    TokenEstimator,
)

logger = logging.getLogger(__name__)


@dataclass
class TokenLimitConfig:
    """Configuration for token limit middleware."""

    # Token limits per client type
    llm_token_limit: int = 20000  # Conservative limit for LLMs
    human_token_limit: int = 0  # Unlimited for humans (0 = no limit)
    unknown_token_limit: int = 25000  # Conservative limit for unknown clients

    # Optimization settings
    enable_content_optimization: bool = True
    enable_intelligent_truncation: bool = True
    add_truncation_warnings: bool = True

    # Client detection settings
    enable_client_detection: bool = True
    default_client_type: ClientType = ClientType.UNKNOWN

    # Performance settings
    max_processing_time_ms: int = 100  # Max time to spend on optimization

    # Operation-specific overrides
    operation_overrides: dict[str, int] = field(default_factory=dict)

    def get_token_limit(self, client_type: ClientType, operation: str = "") -> int:
        """Get token limit for client type and operation."""
        # Check for operation-specific override first
        if operation in self.operation_overrides:
            return self.operation_overrides[operation]

        # Return limit based on client type
        if client_type == ClientType.LLM:
            return self.llm_token_limit
        if client_type == ClientType.HUMAN:
            return self.human_token_limit
        return self.unknown_token_limit


class TokenLimitMiddleware(BaseMiddleware):
    """Middleware for intelligent token limit management and content optimization.

    This middleware:
    1. Detects client types (LLM vs human vs unknown)
    2. Estimates token usage in responses
    3. Applies intelligent truncation when limits are exceeded
    4. Optimizes content formatting for LLM clients
    5. Provides detailed logging and metrics
    """

    def __init__(self, config: TokenLimitConfig = None):
        super().__init__("token_limit")
        self.config = config or TokenLimitConfig()

        # Initialize components
        self.client_detector = ClientDetector()
        self.truncation_manager = IntelligentTruncationManager()
        self.response_formatter = ResponseFormatter()
        self.token_estimator = TokenEstimator()

        # Metrics tracking
        self.processed_requests = 0
        self.truncated_responses = 0
        self.total_tokens_saved = 0
        self.processing_times = []

        self.logger.info(f"Initialized TokenLimitMiddleware with config: {self.config}")

    async def process_request(
        self, context: MiddlewareContext, next_handler: MiddlewareHandler
    ) -> Any:
        """Process request with token limit management."""
        if not self.is_enabled():
            return await next_handler(context)

        import time

        start_time = time.time()

        try:
            # Get response from next handler
            response = await next_handler(context)

            # Process response if it's a tool call result
            if self._should_process_response(response, context):
                processed_response = await self._process_response(response, context)

                # Track processing time
                processing_time = (time.time() - start_time) * 1000
                self.processing_times.append(processing_time)

                # Keep only last 100 processing times for metrics
                if len(self.processing_times) > 100:
                    del self.processing_times[:-100]  # More memory efficient

                self.processed_requests += 1
                return processed_response

            return response

        except (ImportError, AttributeError) as e:
            # Specific exceptions for dependency issues
            self.logger.error(f"Token limit component error: {e}")
            return await next_handler(context)
        except Exception as e:
            self.logger.error(f"Unexpected error in TokenLimitMiddleware: {e}")
            # Consider re-raising in development mode
            if os.getenv("MCP_DEBUG") or os.getenv("DEVELOPMENT_MODE"):
                self.logger.exception("Full traceback for debugging:")
                raise
            # Return original response on error in production
            return await next_handler(context)

    def _should_process_response(
        self, response: Any, context: MiddlewareContext
    ) -> bool:
        """Determine if response should be processed for token limits."""
        # Only process successful tool call responses that contain content
        if not hasattr(response, "content") or not response.content:
            return False

        # Check if response contains text content
        for content_item in response.content:
            if hasattr(content_item, "text") and content_item.text:
                return True

        return False

    async def _process_response(self, response: Any, context: MiddlewareContext) -> Any:
        """Process response with token limit management."""
        # Extract operation name from request
        operation = self._extract_operation_name(context.request)

        # Detect client type
        client_type = self._detect_client_type(context)

        # Get token limit for this client and operation
        token_limit = self.config.get_token_limit(client_type, operation)

        # Process each content item
        processed_content = []
        total_original_tokens = 0
        total_final_tokens = 0

        for content_item in response.content:
            if hasattr(content_item, "text") and content_item.text:
                result = await self._process_text_content(
                    content_item.text, client_type, operation, token_limit
                )

                # Update the content item
                content_item.text = result["content"]
                processed_content.append(content_item)

                total_original_tokens += result["original_tokens"]
                total_final_tokens += result["final_tokens"]

                # Track truncation metrics
                if result["truncated"]:
                    self.truncated_responses += 1
                    self.total_tokens_saved += (
                        result["original_tokens"] - result["final_tokens"]
                    )
            else:
                processed_content.append(content_item)

        # Update response content
        response.content = processed_content

        # Add token usage metadata to response
        self._add_token_metadata(
            response,
            {
                "original_tokens": total_original_tokens,
                "final_tokens": total_final_tokens,
                "client_type": client_type.value,
                "operation": operation,
                "token_limit": token_limit,
            },
        )

        self.logger.debug(
            f"Processed {operation} for {client_type.value}: "
            f"{total_original_tokens} -> {total_final_tokens} tokens"
        )

        return response

    async def _process_text_content(
        self, content: str, client_type: ClientType, operation: str, token_limit: int
    ) -> dict[str, Any]:
        """Process individual text content."""
        # Estimate original token count
        original_estimate = self.token_estimator.estimate_tokens(content)

        # Apply content optimization first (if enabled)
        optimized_content = content
        if self.config.enable_content_optimization:
            optimized_content = self.response_formatter.format_response(
                content, client_type, operation
            )

        # Check if truncation is needed
        final_content = optimized_content
        truncation_result = None

        if token_limit > 0 and self.config.enable_intelligent_truncation:
            optimized_estimate = self.token_estimator.estimate_tokens(optimized_content)

            if optimized_estimate.estimated_tokens > token_limit:
                truncation_result = self.truncation_manager.truncate_for_operation(
                    optimized_content, operation, token_limit
                )
                final_content = truncation_result.content

        return {
            "content": final_content,
            "original_tokens": original_estimate.estimated_tokens,
            "final_tokens": self.token_estimator.estimate_tokens(
                final_content
            ).estimated_tokens,
            "truncated": truncation_result is not None and truncation_result.truncated,
            "truncation_summary": truncation_result.truncation_summary
            if truncation_result
            else "",
        }

    def _extract_operation_name(self, request: Any) -> str:
        """Extract operation name from request."""
        if hasattr(request, "method"):
            return request.method
        if hasattr(request, "name"):
            return request.name
        return "unknown"

    def _detect_client_type(self, context: MiddlewareContext) -> ClientType:
        """Detect client type from context."""
        if not self.config.enable_client_detection:
            return self.config.default_client_type

        # Try to extract user agent from metadata
        user_agent = ""
        request_metadata = {}

        if hasattr(context, "metadata"):
            user_agent = context.metadata.get("user_agent", "")
            request_metadata = context.metadata

        detected_type = self.client_detector.detect_client_type(
            user_agent, request_metadata
        )

        if detected_type == ClientType.UNKNOWN:
            return self.config.default_client_type

        return detected_type

    def _add_token_metadata(self, response: Any, metadata: dict[str, Any]) -> None:
        """Add token usage metadata to response."""
        try:
            if not hasattr(response, "meta"):
                response.meta = {}

            response.meta["token_usage"] = metadata
        except Exception as e:
            self.logger.debug(f"Could not add token metadata: {e}")

    def get_metrics(self) -> dict[str, Any]:
        """Get middleware performance metrics."""
        avg_processing_time = (
            sum(self.processing_times) / len(self.processing_times)
            if self.processing_times
            else 0
        )

        return {
            "processed_requests": self.processed_requests,
            "truncated_responses": self.truncated_responses,
            "truncation_rate": (
                self.truncated_responses / self.processed_requests
                if self.processed_requests > 0
                else 0
            ),
            "total_tokens_saved": self.total_tokens_saved,
            "avg_processing_time_ms": avg_processing_time,
            "config": {
                "llm_token_limit": self.config.llm_token_limit,
                "human_token_limit": self.config.human_token_limit,
                "unknown_token_limit": self.config.unknown_token_limit,
                "optimization_enabled": self.config.enable_content_optimization,
                "truncation_enabled": self.config.enable_intelligent_truncation,
            },
        }

    def update_config(self, **kwargs) -> None:
        """Update middleware configuration."""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
                self.logger.info(f"Updated config {key} = {value}")
            else:
                self.logger.warning(f"Unknown config key: {key}")

    def reset_metrics(self) -> None:
        """Reset performance metrics."""
        self.processed_requests = 0
        self.truncated_responses = 0
        self.total_tokens_saved = 0
        self.processing_times = []
        self.logger.info("Token limit middleware metrics reset")


def create_token_limit_middleware(
    llm_token_limit: int = 20000,
    enable_optimization: bool = True,
    enable_truncation: bool = True,
) -> TokenLimitMiddleware:
    """Create a pre-configured token limit middleware.

    Args:
        llm_token_limit: Token limit for LLM clients
        enable_optimization: Enable content optimization
        enable_truncation: Enable intelligent truncation

    Returns:
        Configured TokenLimitMiddleware instance
    """
    config = TokenLimitConfig(
        llm_token_limit=llm_token_limit,
        enable_content_optimization=enable_optimization,
        enable_intelligent_truncation=enable_truncation,
    )

    return TokenLimitMiddleware(config)
