"""
Token Limiting System for MCP Git Server.

Provides intelligent response truncation while preserving critical information
and maintaining JSON structure integrity.

Features:
- Content-type aware truncation (JSON, structured, logs, metrics, text)
- Configurable limits per operation
- Intelligent preservation of important keys
- Structure integrity maintenance
- Comprehensive token estimation

Re-exports all public types from submodules for backward compatibility.
"""

import json
import logging
from typing import Any

from mcp_server_git.lean.content_truncation import ContentTruncator
from mcp_server_git.lean.token_estimation import (
    CHAR_TO_TOKEN_RATIO_JSON,
    CHAR_TO_TOKEN_RATIO_LOGS,
    CHAR_TO_TOKEN_RATIO_METRICS,
    CHAR_TO_TOKEN_RATIO_STRUCTURED,
    CHAR_TO_TOKEN_RATIO_TEXT,
    TokenEstimator,
)
from mcp_server_git.lean.token_types import (
    ContentType,
    TokenEstimate,
    TruncationConfig,
    TruncationResult,
    _safe_json_serializer,
)

logger = logging.getLogger(__name__)

# Re-export everything so existing callers remain unaffected
__all__ = [
    "MCPTokenLimiter",
    "apply_token_limits",
    "ContentTruncator",
    "TokenEstimator",
    "ContentType",
    "TokenEstimate",
    "TruncationConfig",
    "TruncationResult",
    "_safe_json_serializer",
    "CHAR_TO_TOKEN_RATIO_TEXT",
    "CHAR_TO_TOKEN_RATIO_JSON",
    "CHAR_TO_TOKEN_RATIO_STRUCTURED",
    "CHAR_TO_TOKEN_RATIO_LOGS",
    "CHAR_TO_TOKEN_RATIO_METRICS",
]


class MCPTokenLimiter:
    """
    Main token limiting system for MCP servers.

    Coordinates token estimation, content truncation, and response management
    to ensure responses fit within specified token limits while preserving
    maximum utility.
    """

    def __init__(
        self,
        default_limit: int = 2000,
        operation_limits: dict[str, int] | None = None,
        preserve_keys: list[str] | None = None,
    ):
        """
        Initialize token limiter.

        Args:
            default_limit: Default token limit for operations
            operation_limits: Operation-specific token limits
            preserve_keys: Keys to always preserve in JSON truncation
        """
        self.default_limit = default_limit
        self.operation_limits = operation_limits or {}

        # Default important keys to preserve
        default_preserve_keys = [
            "status",
            "result",
            "error",
            "message",
            "data",
            "tools",
            "available_tools",
            "tool_results",
            "summary",
        ]
        preserve_keys = preserve_keys or []
        all_preserve_keys = list(set(default_preserve_keys + preserve_keys))

        # Setup truncation configuration
        self.config = TruncationConfig(
            preserve_keys=all_preserve_keys,
            truncation_indicator="... [Content truncated for token limit compliance]",
            max_preserve_ratio=0.7,  # Preserve up to 70% for important keys
            min_content_tokens=50,  # Always preserve at least 50 tokens
        )

        self.truncator = ContentTruncator(self.config)
        self.token_estimator = TokenEstimator()

        logger.info(f"Token limiter initialized with default limit: {default_limit}")

    def limit_response(
        self, response: dict[str, Any], operation: str = "unknown"
    ) -> dict[str, Any]:
        """
        Apply token limits to a response.

        Args:
            response: Response dictionary to limit
            operation: Operation name for context and limits

        Returns:
            Limited response dictionary
        """
        # Get operation-specific limit or use default
        token_limit = self.operation_limits.get(operation, self.default_limit)

        # Convert response to JSON for processing using safe serializer
        response_json = json.dumps(response, indent=2, default=_safe_json_serializer)

        # Estimate tokens
        estimate = self.token_estimator.estimate_tokens(response_json, ContentType.JSON)

        # Return early if under limit
        if estimate.estimated_tokens <= token_limit:
            logger.debug(
                f"Response for {operation}: {estimate.estimated_tokens} tokens (under limit)"
            )
            return response

        logger.info(
            f"Response for {operation}: {estimate.estimated_tokens} tokens exceeds limit "
            f"of {token_limit}, truncating..."
        )

        # Truncate the response
        truncation_result = self.truncator.truncate_content(
            response_json, token_limit, ContentType.JSON
        )

        try:
            # Parse back to dict
            truncated_response = json.loads(truncation_result.content)

            # Add metadata about truncation
            if isinstance(truncated_response, dict):
                truncated_response["_token_limit_info"] = {
                    "original_tokens": truncation_result.original_tokens,
                    "final_tokens": truncation_result.final_tokens,
                    "truncated": truncation_result.truncated,
                    "operation": operation,
                    "limit": token_limit,
                    "summary": truncation_result.truncation_summary,
                }

            logger.info(
                f"Successfully truncated {operation}: {truncation_result.original_tokens} -> "
                f"{truncation_result.final_tokens} tokens"
            )
            return truncated_response

        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"Failed to parse truncated response: {e}")
            # Return minimal error response
            return {
                "error": "Response too large and truncation failed",
                "original_size_tokens": estimate.estimated_tokens,
                "limit": token_limit,
                "operation": operation,
            }

    def would_truncate(
        self, response: dict[str, Any], operation: str = "unknown"
    ) -> bool:
        """Check if a response would be truncated without modifying it.

        Args:
            response: Response dictionary to check
            operation: Operation name for limit lookup

        Returns:
            True if the response exceeds the applicable token limit
        """
        token_limit = self.operation_limits.get(operation, self.default_limit)
        response_json = json.dumps(response, indent=2, default=_safe_json_serializer)
        estimate = self.token_estimator.estimate_tokens(response_json, ContentType.JSON)
        return estimate.estimated_tokens > token_limit

    def update_limits(self, **operation_limits):
        """Update operation-specific limits."""
        self.operation_limits.update(operation_limits)
        logger.info(f"Updated operation limits: {operation_limits}")


def apply_token_limits(
    response: dict[str, Any], operation: str = "unknown", max_tokens: int = 2000
) -> dict[str, Any]:
    """Convenience function to apply token limits to responses."""
    limiter = MCPTokenLimiter(default_limit=max_tokens)
    return limiter.limit_response(response, operation)
