"""Tests for token limiting system."""

import json

import pytest

from mcp_server_git.lean.token_limiter import (
    ContentType,
    ContentTruncator,
    MCPTokenLimiter,
    TokenEstimator,
    TruncationConfig,
)


class TestTokenEstimator:
    """Test token estimation functionality."""

    def test_default_ratios(self):
        """Test default character-to-token ratios."""
        estimator = TokenEstimator()
        assert estimator.ratios[ContentType.TEXT] == 4.0
        assert estimator.ratios[ContentType.JSON] == 3.5

    def test_custom_ratios(self):
        """Test custom character-to-token ratios."""
        custom = {ContentType.TEXT: 5.0}
        estimator = TokenEstimator(custom_ratios=custom)
        assert estimator.ratios[ContentType.TEXT] == 5.0
        assert estimator.ratios[ContentType.JSON] == 3.5  # Default preserved

    def test_empty_content(self):
        """Test estimation of empty content."""
        estimator = TokenEstimator()
        estimate = estimator.estimate_tokens("", ContentType.TEXT)
        assert estimate.estimated_tokens == 0
        assert estimate.method == "empty"

    def test_text_estimation(self):
        """Test token estimation for text content."""
        estimator = TokenEstimator()
        content = "Hello world! " * 100  # ~1300 chars
        estimate = estimator.estimate_tokens(content, ContentType.TEXT)
        # At 4 chars/token, should be ~325 tokens
        assert 300 < estimate.estimated_tokens < 350


class TestContentTruncator:
    """Test content truncation functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = TruncationConfig(
            preserve_keys=["status", "error", "result"],
            truncation_indicator="... [Truncated]",
            max_preserve_ratio=0.7,
            min_content_tokens=50,
        )
        self.truncator = ContentTruncator(self.config)

    def test_no_truncation_needed(self):
        """Test when content is already under limit."""
        content = "Short content"
        result = self.truncator.truncate_content(content, 1000, ContentType.TEXT)
        assert not result.truncated
        assert result.content == content

    def test_json_truncation_preserves_keys(self):
        """Test JSON truncation preserves important keys."""
        data = {
            "status": "success",
            "result": "important",
            "debug_info": "x" * 1000,
            "extra": "y" * 1000,
        }
        content = json.dumps(data)
        result = self.truncator.truncate_content(content, 100, ContentType.JSON)
        assert result.truncated
        truncated_data = json.loads(result.content)
        assert "status" in truncated_data
        assert "result" in truncated_data

    def test_list_truncation(self):
        """Test list truncation."""
        data = [{"item": i} for i in range(100)]
        content = json.dumps(data)
        result = self.truncator.truncate_content(content, 50, ContentType.JSON)
        assert result.truncated
        truncated_data = json.loads(result.content)
        assert len(truncated_data) < len(data)

    def test_text_truncation(self):
        """Test plain text truncation."""
        content = "word " * 1000
        result = self.truncator.truncate_content(content, 100, ContentType.TEXT)
        assert result.truncated
        assert len(result.content) < len(content)
        assert "... [Truncated]" in result.content


class TestMCPTokenLimiter:
    """Test main token limiter class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.limiter = MCPTokenLimiter(default_limit=100)

    def test_response_under_limit(self):
        """Test response that's already under limit."""
        response = {"status": "success", "data": "small"}
        result = self.limiter.limit_response(response, "test_operation")
        assert "_token_limit_info" not in result

    def test_response_over_limit(self):
        """Test response that exceeds limit."""
        response = {"status": "success", "large_data": "x" * 10000}
        result = self.limiter.limit_response(response, "test_operation")
        assert "_token_limit_info" in result
        assert result["_token_limit_info"]["truncated"]

    def test_operation_specific_limits(self):
        """Test operation-specific token limits."""
        limiter = MCPTokenLimiter(
            default_limit=100, operation_limits={"special_op": 200}
        )
        assert limiter.operation_limits["special_op"] == 200

    def test_update_limits(self):
        """Test updating operation limits."""
        self.limiter.update_limits(new_op=150)
        assert self.limiter.operation_limits["new_op"] == 150


# TODO: Add tests for:
# - Edge cases (malformed JSON, etc.)
# - Different content types (LOGS, METRICS, STRUCTURED)
# - Truncation of nested structures
# - Error handling in truncation
# - Token estimation accuracy validation
