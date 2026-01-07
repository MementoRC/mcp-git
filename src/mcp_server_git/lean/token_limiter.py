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
"""

import json
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ContentType(Enum):
    """Types of content for different truncation strategies."""

    TEXT = "text"
    JSON = "json"
    STRUCTURED = "structured"
    LOGS = "logs"
    METRICS = "metrics"


@dataclass
class TokenEstimate:
    """Represents a token count estimate for content."""

    estimated_tokens: int
    content_length: int
    content_type: ContentType
    method: str = "character_based"


@dataclass
class TruncationConfig:
    """Configuration for content truncation behavior."""

    preserve_keys: list[str]
    truncation_indicator: str
    max_preserve_ratio: float  # Maximum ratio of content to preserve for important keys
    min_content_tokens: int  # Minimum tokens to preserve


@dataclass
class TruncationResult:
    """Results from content truncation operation."""

    content: str
    original_tokens: int
    final_tokens: int
    truncated: bool
    truncation_summary: str


class TokenEstimator:
    """
    Estimates token counts for different content types.

    Uses character-based approximation as a fallback when advanced tokenizers
    aren't available. This provides reasonable estimates for most use cases.
    """

    # Approximate character-to-token ratios for different content types
    CHAR_TO_TOKEN_RATIOS = {
        ContentType.TEXT: 4.0,  # ~4 chars per token for English text
        ContentType.JSON: 3.5,  # JSON is slightly more dense
        ContentType.STRUCTURED: 3.8,  # Structured data middle ground
        ContentType.LOGS: 4.2,  # Logs tend to be more verbose
        ContentType.METRICS: 3.0,  # Metrics are dense numerical data
    }

    def estimate_tokens(self, content: str, content_type: ContentType) -> TokenEstimate:
        """
        Estimate token count for content.

        Args:
            content: Content to estimate
            content_type: Type of content for appropriate ratio

        Returns:
            Token estimate with metadata
        """
        if not content:
            return TokenEstimate(
                estimated_tokens=0,
                content_length=0,
                content_type=content_type,
                method="empty",
            )

        char_count = len(content)
        ratio = self.CHAR_TO_TOKEN_RATIOS.get(content_type, 4.0)
        estimated_tokens = max(1, int(char_count / ratio))

        return TokenEstimate(
            estimated_tokens=estimated_tokens,
            content_length=char_count,
            content_type=content_type,
            method="character_based",
        )


class ContentTruncator:
    """
    Intelligently truncates content while preserving structure and important information.

    Different strategies are applied based on content type to maintain usability
    while reducing token count.
    """

    def __init__(self, config: TruncationConfig):
        """Initialize with truncation configuration."""
        self.config = config
        self.token_estimator = TokenEstimator()

    def truncate_content(
        self, content: str, max_tokens: int, content_type: ContentType
    ) -> TruncationResult:
        """
        Truncate content to fit within token limit.

        Args:
            content: Content to truncate
            max_tokens: Maximum allowed tokens
            content_type: Type of content for appropriate strategy

        Returns:
            Truncation result with metadata
        """
        if not content:
            return TruncationResult(
                content="",
                original_tokens=0,
                final_tokens=0,
                truncated=False,
                truncation_summary="Empty content",
            )

        # Estimate original tokens
        original_estimate = self.token_estimator.estimate_tokens(content, content_type)

        # Return early if already under limit
        if original_estimate.estimated_tokens <= max_tokens:
            return TruncationResult(
                content=content,
                original_tokens=original_estimate.estimated_tokens,
                final_tokens=original_estimate.estimated_tokens,
                truncated=False,
                truncation_summary="No truncation needed",
            )

        # Apply content-type specific truncation
        if content_type == ContentType.JSON:
            truncated_content = self._truncate_json(content, max_tokens)
        elif content_type == ContentType.STRUCTURED:
            truncated_content = self._truncate_structured(content, max_tokens)
        elif content_type == ContentType.LOGS:
            truncated_content = self._truncate_logs(content, max_tokens)
        elif content_type == ContentType.METRICS:
            truncated_content = self._truncate_metrics(content, max_tokens)
        else:  # TEXT or fallback
            truncated_content = self._truncate_text(content, max_tokens)

        # Estimate final tokens
        final_estimate = self.token_estimator.estimate_tokens(
            truncated_content, content_type
        )

        # Calculate savings
        tokens_saved = (
            original_estimate.estimated_tokens - final_estimate.estimated_tokens
        )
        truncation_summary = (
            f"Content truncated: {tokens_saved} tokens saved "
            f"({original_estimate.estimated_tokens} -> {final_estimate.estimated_tokens})"
        )

        return TruncationResult(
            content=truncated_content,
            original_tokens=original_estimate.estimated_tokens,
            final_tokens=final_estimate.estimated_tokens,
            truncated=True,
            truncation_summary=truncation_summary,
        )

    def _truncate_json(self, content: str, max_tokens: int) -> str:
        """Truncate JSON content intelligently."""
        try:
            data = json.loads(content)

            # For dictionaries, prioritize certain keys
            if isinstance(data, dict):
                # Keep priority keys first (from config)
                truncated_data = {}
                for key in self.config.preserve_keys:
                    if key in data:
                        truncated_data[key] = data[key]

                # Add other keys until we hit the limit
                remaining_keys = [k for k in data if k not in self.config.preserve_keys]
                for key in remaining_keys:
                    test_data = {**truncated_data, key: data[key]}
                    test_content = json.dumps(test_data, indent=2)
                    if (
                        self.token_estimator.estimate_tokens(
                            test_content, ContentType.JSON
                        ).estimated_tokens
                        > max_tokens
                    ):
                        break
                    truncated_data[key] = data[key]

                # Add truncation indicator
                if len(truncated_data) < len(data):
                    truncated_data["_meta"] = {
                        "truncated": True,
                        "original_keys": len(data),
                        "preserved_keys": len(truncated_data),
                        "truncation_indicator": self.config.truncation_indicator,
                    }

                return json.dumps(truncated_data, indent=2)

            elif isinstance(data, list):
                # For lists, keep first N items
                truncated_list = []
                for _i, item in enumerate(data):
                    test_list = truncated_list + [item]
                    test_content = json.dumps(test_list, indent=2)
                    if (
                        self.token_estimator.estimate_tokens(
                            test_content, ContentType.JSON
                        ).estimated_tokens
                        > max_tokens
                    ):
                        break
                    truncated_list.append(item)

                # Add truncation indicator
                if len(truncated_list) < len(data):
                    truncated_list.append(
                        {
                            "_truncated": True,
                            "original_length": len(data),
                            "preserved_length": len(truncated_list),
                            "indicator": self.config.truncation_indicator,
                        }
                    )

                return json.dumps(truncated_list, indent=2)

            else:
                # For other JSON types, fall back to text truncation
                return self._truncate_text(content, max_tokens)

        except (json.JSONDecodeError, TypeError):
            # Fall back to text truncation if JSON parsing fails
            return self._truncate_text(content, max_tokens)

    def _truncate_structured(self, content: str, max_tokens: int) -> str:
        """Truncate structured content (YAML, TOML, etc.)."""
        # For structured content, use line-based truncation to preserve structure
        lines = content.split("\n")
        truncated_lines = []
        current_content = ""

        for line in lines:
            test_content = current_content + line + "\n"
            if (
                self.token_estimator.estimate_tokens(
                    test_content, ContentType.STRUCTURED
                ).estimated_tokens
                > max_tokens
            ):
                break
            truncated_lines.append(line)
            current_content = test_content

        # Add truncation indicator
        if len(truncated_lines) < len(lines):
            truncated_lines.append(f"# {self.config.truncation_indicator}")
            truncated_lines.append(
                f"# Truncated: {len(lines) - len(truncated_lines)} lines removed"
            )

        return "\n".join(truncated_lines)

    def _truncate_logs(self, content: str, max_tokens: int) -> str:
        """Truncate log content, preserving important entries."""
        lines = content.split("\n")

        # Identify important log lines (errors, warnings)
        important_lines = []
        regular_lines = []

        for i, line in enumerate(lines):
            if re.search(r"\b(ERROR|CRITICAL|FATAL|WARNING)\b", line, re.IGNORECASE):
                important_lines.append((i, line))
            else:
                regular_lines.append((i, line))

        # Always preserve important lines first
        truncated_lines = [line for _, line in important_lines]
        current_content = "\n".join(truncated_lines)

        # Add regular lines until we hit the limit
        for _, line in regular_lines:
            test_content = current_content + "\n" + line
            if (
                self.token_estimator.estimate_tokens(
                    test_content, ContentType.LOGS
                ).estimated_tokens
                > max_tokens
            ):
                break
            truncated_lines.append(line)
            current_content = test_content

        # Add truncation indicator
        if len(truncated_lines) < len(lines):
            truncated_lines.append(f"... {self.config.truncation_indicator}")
            truncated_lines.append(
                f"... Truncated: {len(lines) - len(truncated_lines)} lines removed"
            )

        return "\n".join(truncated_lines)

    def _truncate_metrics(self, content: str, max_tokens: int) -> str:
        """Truncate metrics content, preserving important metrics."""
        try:
            # Try to parse as JSON first
            data = json.loads(content)
            if isinstance(data, dict):
                # Preserve metrics with high priority
                important_keys = [
                    "error",
                    "errors",
                    "status",
                    "health",
                    "critical",
                    "alerts",
                ]
                truncated_data = {}

                # Add important keys first
                for key in important_keys:
                    if key in data:
                        truncated_data[key] = data[key]

                # Add other keys
                for key, value in data.items():
                    if key not in important_keys:
                        test_data = {**truncated_data, key: value}
                        test_content = json.dumps(test_data, indent=2)
                        if (
                            self.token_estimator.estimate_tokens(
                                test_content, ContentType.METRICS
                            ).estimated_tokens
                            > max_tokens
                        ):
                            break
                        truncated_data[key] = value

                return json.dumps(truncated_data, indent=2)
        except (json.JSONDecodeError, TypeError):
            pass

        # Fall back to text truncation
        return self._truncate_text(content, max_tokens)

    def _truncate_text(self, content: str, max_tokens: int) -> str:
        """Truncate plain text content."""
        # Calculate approximate character limit
        char_limit = max_tokens * TokenEstimator.CHAR_TO_TOKEN_RATIOS[ContentType.TEXT]

        if len(content) <= char_limit:
            return content

        # Truncate to character limit and add indicator
        truncated = content[
            : int(char_limit - len(self.config.truncation_indicator) - 10)
        ]

        # Try to break at word boundary
        if " " in truncated:
            last_space = truncated.rfind(" ")
            if last_space > char_limit * 0.8:  # Only if we don't lose too much
                truncated = truncated[:last_space]

        return truncated + f"\n\n{self.config.truncation_indicator}"


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

        # Convert response to JSON for processing
        response_json = json.dumps(response, indent=2, default=str)

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
