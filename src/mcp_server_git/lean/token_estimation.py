"""
Token estimation for MCP Git Server.

Provides character-based token count approximation per content type.
"""

from mcp_server_git.lean.token_types import ContentType, TokenEstimate

# Token estimation constants - configurable for tuning
# These ratios are approximate chars-per-token based on empirical testing
CHAR_TO_TOKEN_RATIO_TEXT = 4.0  # English text averages ~4 chars/token
CHAR_TO_TOKEN_RATIO_JSON = 3.5  # JSON slightly more dense due to structure
CHAR_TO_TOKEN_RATIO_STRUCTURED = 3.8  # Structured data middle ground
CHAR_TO_TOKEN_RATIO_LOGS = 4.2  # Logs tend to be more verbose
CHAR_TO_TOKEN_RATIO_METRICS = 3.0  # Metrics are dense numerical data


class TokenEstimator:
    """
    Estimates token counts for different content types.

    Uses character-based approximation as a fallback when advanced tokenizers
    aren't available. This provides reasonable estimates for most use cases.
    """

    # Default approximate character-to-token ratios for different content types
    DEFAULT_CHAR_TO_TOKEN_RATIOS = {
        ContentType.TEXT: CHAR_TO_TOKEN_RATIO_TEXT,
        ContentType.JSON: CHAR_TO_TOKEN_RATIO_JSON,
        ContentType.STRUCTURED: CHAR_TO_TOKEN_RATIO_STRUCTURED,
        ContentType.LOGS: CHAR_TO_TOKEN_RATIO_LOGS,
        ContentType.METRICS: CHAR_TO_TOKEN_RATIO_METRICS,
    }

    def __init__(self, custom_ratios: dict[ContentType, float] | None = None):
        """
        Initialize token estimator with optional custom ratios.

        Args:
            custom_ratios: Optional custom character-to-token ratios per content type
        """
        self.ratios = {**self.DEFAULT_CHAR_TO_TOKEN_RATIOS}
        if custom_ratios:
            self.ratios.update(custom_ratios)

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
        ratio = self.ratios.get(content_type, 4.0)
        estimated_tokens = max(1, int(char_count / ratio))

        return TokenEstimate(
            estimated_tokens=estimated_tokens,
            content_length=char_count,
            content_type=content_type,
            method="character_based",
        )
