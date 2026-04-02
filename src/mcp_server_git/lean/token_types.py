"""
Token limiting types: enums, dataclasses, and JSON serialization helper.

Used by token_estimation.py, content_truncation.py, and token_limiter.py.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


def _safe_json_serializer(obj: Any) -> str | dict[str, Any]:
    """
    Safe JSON serializer that doesn't expose internal object details.

    Only serializes known safe types. Raises TypeError for unknown types
    rather than exposing object representations.

    Args:
        obj: Object to serialize

    Returns:
        String or dict representation for known safe types

    Raises:
        TypeError: For unknown/unsafe types
    """
    # Handle common safe types
    if hasattr(obj, "isoformat"):  # datetime, date, time
        return obj.isoformat()
    if hasattr(obj, "__dict__") and isinstance(obj.__dict__, dict):
        # For objects with __dict__, only include public attributes
        return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
    # Reject unknown types for security
    raise TypeError(
        f"Object of type {type(obj).__name__} is not JSON serializable. "
        "Add explicit handling for this type if needed."
    )


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
