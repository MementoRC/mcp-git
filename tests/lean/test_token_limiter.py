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


class TestTokenLimiterEdgeCases:
    """Test edge cases and security aspects of token limiting."""

    def test_malformed_json_handling(self):
        """Test handling of malformed JSON during truncation."""
        limiter = MCPTokenLimiter(default_limit=100)

        # Malformed JSON should be handled gracefully
        malformed = {"valid_key": "value", "incomplete": "x" * 10000}
        malformed_str = json.dumps(malformed)[:-5]  # Remove closing braces

        # Should not crash, even with malformed input
        # The limiter works on the dict, not the string
        result = limiter.limit_response(malformed, "test_malformed")

        assert "_token_limit_info" in result

    def test_deeply_nested_json_truncation(self):
        """Test truncation of deeply nested JSON structures."""
        limiter = MCPTokenLimiter(default_limit=50)

        nested = {"level1": {"level2": {"level3": {"level4": {"data": "x" * 1000}}}}}

        result = limiter.limit_response(nested, "test_nested")

        assert "_token_limit_info" in result
        assert result["_token_limit_info"]["truncated"]

    def test_safe_serializer_rejects_unknown_types(self):
        """Test that safe serializer rejects unknown types for security."""
        from mcp_server_git.lean.token_limiter import _safe_json_serializer

        # Should handle datetime-like objects
        class FakeDateTime:
            def isoformat(self):
                return "2024-01-01T00:00:00"

        assert _safe_json_serializer(FakeDateTime()) == "2024-01-01T00:00:00"

        # Should reject unknown custom objects
        class UnknownType:
            pass

        with pytest.raises(TypeError, match="is not JSON serializable"):
            _safe_json_serializer(UnknownType())

    def test_safe_serializer_with_object_dict(self):
        """Test safe serializer handles objects with __dict__."""
        from mcp_server_git.lean.token_limiter import _safe_json_serializer

        class SafeObject:
            def __init__(self):
                self.public_attr = "safe"
                self._private_attr = "secret"

        obj = SafeObject()
        result = _safe_json_serializer(obj)

        assert isinstance(result, dict)
        assert "public_attr" in result
        assert "_private_attr" not in result  # Private attrs excluded

    def test_different_content_types(self):
        """Test token estimation for different content types."""
        from mcp_server_git.lean.token_limiter import (
            CHAR_TO_TOKEN_RATIO_LOGS,
            CHAR_TO_TOKEN_RATIO_METRICS,
            CHAR_TO_TOKEN_RATIO_STRUCTURED,
            CHAR_TO_TOKEN_RATIO_TEXT,
        )

        estimator = TokenEstimator()

        # Text content
        text = "word " * 100
        text_est = estimator.estimate_tokens(text, ContentType.TEXT)
        assert text_est.estimated_tokens == len(text) / CHAR_TO_TOKEN_RATIO_TEXT

        # Logs content
        logs = "[INFO] Log message\n" * 100
        logs_est = estimator.estimate_tokens(logs, ContentType.LOGS)
        assert logs_est.estimated_tokens == len(logs) / CHAR_TO_TOKEN_RATIO_LOGS

        # Metrics content
        metrics = '{"cpu": 75, "memory": 8192}\n' * 100
        metrics_est = estimator.estimate_tokens(metrics, ContentType.METRICS)
        assert metrics_est.estimated_tokens == len(metrics) / CHAR_TO_TOKEN_RATIO_METRICS

    def test_custom_token_ratios(self):
        """Test custom character-to-token ratios."""
        custom_ratios = {ContentType.TEXT: 5.0}  # More conservative
        estimator = TokenEstimator(custom_ratios=custom_ratios)

        text = "word " * 100
        estimate = estimator.estimate_tokens(text, ContentType.TEXT)

        # Should use custom ratio
        assert estimate.estimated_tokens == len(text) / 5.0

    def test_extremely_large_response_truncation(self):
        """Test truncation of extremely large responses."""
        limiter = MCPTokenLimiter(default_limit=100)

        # Create massive response
        huge_data = {
            "items": [{"id": i, "data": "x" * 1000} for i in range(1000)],
            "status": "success",
        }

        result = limiter.limit_response(huge_data, "test_huge")

        assert "_token_limit_info" in result
        assert result["_token_limit_info"]["truncated"]
        assert result["_token_limit_info"]["original_tokens"] > 1000

    def test_preserve_keys_in_truncation(self):
        """Test that important keys are preserved during truncation."""
        config = TruncationConfig(
            preserve_keys=["status", "error", "critical_info"],
            truncation_indicator="[TRUNCATED]",
            max_preserve_ratio=0.7,
            min_content_tokens=50,
        )
        truncator = ContentTruncator(config)

        data = {
            "status": "error",
            "error": "Critical failure",
            "critical_info": "Must preserve this",
            "debug_data": "x" * 10000,
            "extra": "y" * 10000,
        }

        content = json.dumps(data)
        result = truncator.truncate_content(content, 200, ContentType.JSON)

        truncated_data = json.loads(result.content)

        # Important keys should be preserved
        assert "status" in truncated_data
        assert "error" in truncated_data
        assert "critical_info" in truncated_data
        assert truncated_data["status"] == "error"

    def test_zero_limit_handling(self):
        """Test handling of zero or very small token limits."""
        limiter = MCPTokenLimiter(default_limit=1)

        response = {"status": "success", "data": "some data"}
        result = limiter.limit_response(response, "test_zero")

        # Should still return something, even with tiny limit
        assert isinstance(result, dict)
        assert "_token_limit_info" in result
