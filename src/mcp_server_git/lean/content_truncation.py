"""
Content truncation strategies for MCP Git Server.

Provides intelligent truncation for JSON, structured, log, metrics, and plain text
content while preserving structure integrity and important information.
"""

import json
import re

from mcp_server_git.lean.token_estimation import TokenEstimator
from mcp_server_git.lean.token_types import (
    ContentType,
    TruncationConfig,
    TruncationResult,
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
                for _, item in enumerate(data):
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
        char_limit = max_tokens * self.token_estimator.ratios[ContentType.TEXT]

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
