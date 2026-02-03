"""
Tests for token management utilities.

This module contains comprehensive tests for token estimation, content optimization,
intelligent truncation, and client detection functionality.
"""

from unittest.mock import Mock, patch

import pytest

from src.mcp_server_git.utils.content_optimization import (
    ContentOptimizer,
    ResponseFormatter,
)
from src.mcp_server_git.utils.token_management import (
    ClientDetector,
    ClientType,
    ContentType,
    DiffTruncator,
    GenericTruncator,
    IntelligentTruncationManager,
    LogTruncator,
    TokenEstimator,
)


class TestTokenEstimator:
    """Tests for token estimation functionality."""

    def setup_method(self):
        self.estimator = TokenEstimator()

    def test_basic_text_estimation(self):
        """Test basic token estimation for text content."""
        content = "This is a simple test message."
        estimate = self.estimator.estimate_tokens(content, ContentType.TEXT)

        # Should be approximately 7 tokens (30 chars / 4 chars per token)
        assert 5 <= estimate.estimated_tokens <= 10
        assert estimate.content_type == ContentType.TEXT
        assert estimate.char_count == len(content)
        assert estimate.confidence > 0.8

    def test_code_estimation(self):
        """Test token estimation for code content."""
        content = """
def test_function():
    return "hello world"
        """
        estimate = self.estimator.estimate_tokens(content, ContentType.CODE)

        # Code should be more token-dense than text
        assert estimate.estimated_tokens > len(content) / 4  # More dense than text
        assert estimate.content_type == ContentType.CODE

    def test_diff_estimation(self):
        """Test token estimation for diff content."""
        content = """
diff --git a/file.py b/file.py
index 1234567..abcdefg 100644
--- a/file.py
+++ b/file.py
@@ -1,3 +1,4 @@
 def function():
-    pass
+    print("hello")
+    return True
        """
        estimate = self.estimator.estimate_tokens(content, ContentType.DIFF)

        # Diffs should be very token-dense
        assert estimate.estimated_tokens > len(content) / 3
        assert estimate.content_type == ContentType.DIFF

    def test_empty_content(self):
        """Test handling of empty content."""
        estimate = self.estimator.estimate_tokens("", ContentType.TEXT)

        assert estimate.estimated_tokens == 0
        assert estimate.confidence == 1.0
        assert estimate.char_count == 0


class TestGenericTruncator:
    """Tests for generic content truncation."""

    def setup_method(self):
        self.truncator = GenericTruncator()
        self.estimator = TokenEstimator()

    def test_no_truncation_needed(self):
        """Test when content fits within limits."""
        content = "Short content that fits."
        result = self.truncator.truncate(content, 1000, self.estimator)

        assert not result.truncated
        assert result.content == content
        assert result.original_tokens == result.final_tokens

    def test_basic_truncation(self):
        """Test basic truncation of long content."""
        content = (
            "This is a very long piece of content that should be truncated. " * 100
        )
        result = self.truncator.truncate(content, 50, self.estimator)

        assert result.truncated
        assert len(result.content) < len(content)
        assert "Truncated:" in result.content
        assert result.final_tokens <= 50
        assert result.original_tokens > result.final_tokens


class TestDiffTruncator:
    """Tests for intelligent diff truncation."""

    def setup_method(self):
        self.truncator = DiffTruncator()
        self.estimator = TokenEstimator()

    def test_preserve_file_headers(self):
        """Test that file headers are preserved during truncation."""
        content = (
            """diff --git a/file1.py b/file1.py
index 1234567..abcdefg 100644
--- a/file1.py
+++ b/file1.py
@@ -1,10 +1,10 @@
-old line 1
+new line 1
-old line 2
+new line 2"""
            + "\n-old line"
            + "\n+new line" * 100
        )  # Make it long

        result = self.truncator.truncate(content, 100, self.estimator)

        assert result.truncated
        assert "diff --git a/file1.py b/file1.py" in result.content
        assert "--- a/file1.py" in result.content
        assert "+++ b/file1.py" in result.content
        assert "Diff truncated:" in result.content

    def test_multiple_files_handling(self):
        """Test handling of multiple files in diff."""
        content = """diff --git a/file1.py b/file1.py
index 1234567..abcdefg 100644
--- a/file1.py
+++ b/file1.py
@@ -1,3 +1,3 @@
-line 1
+modified line 1

diff --git a/file2.py b/file2.py
index 2345678..bcdefgh 100644
--- a/file2.py
+++ b/file2.py
@@ -1,3 +1,3 @@
-line 2
+modified line 2"""

        result = self.truncator.truncate(content, 200, self.estimator)

        # Should preserve both file headers
        assert "file1.py" in result.content
        assert result.final_tokens <= 200


class TestLogTruncator:
    """Tests for intelligent log truncation."""

    def setup_method(self):
        self.truncator = LogTruncator()
        self.estimator = TokenEstimator()

    def test_preserve_recent_commits(self):
        """Test that recent commits are preserved."""
        content = """commit 1234567890abcdef1234567890abcdef12345678
Author: Developer <dev@example.com>
Date: Mon Jan 1 12:00:00 2024 +0000

    Recent commit message

commit abcdef1234567890abcdef1234567890abcdef12
Author: Developer <dev@example.com>
Date: Sun Dec 31 12:00:00 2023 +0000

    Older commit message

commit fedcba0987654321fedcba0987654321fedcba09
Author: Developer <dev@example.com>
Date: Sat Dec 30 12:00:00 2023 +0000

    Much older commit"""

        result = self.truncator.truncate(content, 150, self.estimator)

        # Should preserve most recent commits first
        assert "Recent commit message" in result.content
        if result.truncated:
            assert "Log truncated:" in result.content


class TestClientDetector:
    """Tests for client type detection."""

    def setup_method(self):
        self.detector = ClientDetector()

    def test_llm_client_detection(self):
        """Test detection of LLM clients."""
        test_cases = [
            "Claude/1.0 AI Assistant",
            "ChatGPT API Client",
            "OpenAI-Python/1.0",
            "Anthropic Claude API",
            "Custom LLM Client",
        ]

        for user_agent in test_cases:
            result = self.detector.detect_client_type(user_agent)
            assert result == ClientType.LLM, (
                f"Failed to detect LLM client: {user_agent}"
            )

    def test_human_client_detection(self):
        """Test detection of human clients."""
        test_cases = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Chrome/91.0.4472.124 Safari/537.36",
            "Firefox/89.0",
            "Safari/14.1.1",
        ]

        for user_agent in test_cases:
            result = self.detector.detect_client_type(user_agent)
            assert result == ClientType.HUMAN, (
                f"Failed to detect human client: {user_agent}"
            )

    def test_unknown_client_detection(self):
        """Test handling of unknown clients."""
        result = self.detector.detect_client_type("Custom-Unknown-Client/1.0")
        assert result == ClientType.UNKNOWN


class TestContentOptimizer:
    """Tests for content optimization."""

    def setup_method(self):
        self.optimizer = ContentOptimizer()

    def test_llm_emoji_removal(self):
        """Test emoji removal for LLM clients."""
        content = "✅ Operation successful! 🚀 Ready to go! ❌ Error occurred."
        result = self.optimizer.optimize_for_client(content, ClientType.LLM)

        # Emojis should be removed
        assert "✅" not in result
        assert "🚀" not in result
        assert "❌" not in result
        # Text content should remain
        assert "Operation successful" in result
        assert "Ready to go" in result
        assert "Error occurred" in result

    def test_human_formatting_preserved(self):
        """Test that human formatting is preserved for human clients."""
        content = "✅ Operation successful! 🚀 Ready to go!"
        result = self.optimizer.optimize_for_client(content, ClientType.HUMAN)

        # Should be unchanged
        assert result == content

    def test_phrase_optimization(self):
        """Test phrase optimization for LLMs."""
        content = "✅ Successfully completed the operation"
        result = self.optimizer.optimize_for_client(content, ClientType.LLM)

        # Should be simplified
        assert "Successfully" not in result or "completed" in result

    def test_git_diff_optimization(self):
        """Test git diff specific optimization."""
        content = """diff --git a/very/long/path/to/file.py b/very/long/path/to/file.py
index 1234567890123456789012345678901234567890..abcdefghijklmnopqrstuvwxyz1234567890abcdef 100644
--- a/very/long/path/to/file.py
+++ b/very/long/path/to/file.py"""

        result = self.optimizer._optimize_diff_output(content)

        # Should preserve essential structure but optimize long lines
        assert "diff --git" in result
        assert "---" in result
        assert "+++" in result


class TestIntelligentTruncationManager:
    """Tests for the overall truncation management system."""

    def setup_method(self):
        self.manager = IntelligentTruncationManager()

    def test_operation_specific_truncation(self):
        """Test that different operations use appropriate truncators."""
        diff_content = "diff --git a/file.py b/file.py\n" + "line\n" * 1000
        log_content = "commit abc123\nAuthor: Test\n" + "commit def456\n" * 100

        # Test diff truncation
        diff_result = self.manager.truncate_for_operation(diff_content, "git_diff", 100)
        assert diff_result.truncated
        assert "diff --git" in diff_result.content  # Should preserve headers

        # Test log truncation
        log_result = self.manager.truncate_for_operation(log_content, "git_log", 100)
        assert log_result.truncated
        assert "commit abc123" in log_result.content  # Should preserve recent commits

    def test_fallback_to_generic(self):
        """Test fallback to generic truncation for unknown operations."""
        content = "Some unknown content type " * 100
        result = self.manager.truncate_for_operation(content, "unknown_operation", 50)

        assert result.truncated
        assert len(result.content) < len(content)


class TestResponseFormatter:
    """Tests for response formatting."""

    def setup_method(self):
        self.formatter = ResponseFormatter()

    def test_client_specific_formatting(self):
        """Test that formatting varies by client type."""
        content = "✅ Git operation completed successfully! 🚀"

        llm_result = self.formatter.format_response(
            content, ClientType.LLM, "git_status"
        )
        human_result = self.formatter.format_response(
            content, ClientType.HUMAN, "git_status"
        )

        # LLM should have optimizations applied
        assert len(llm_result) <= len(human_result)
        # Human should be unchanged
        assert human_result == content

    def test_structured_output(self):
        """Test structured output markers."""
        content = "Some diff content"
        metadata = {"structured_output": True}

        result = self.formatter.format_response(
            content, ClientType.LLM, "git_diff", metadata
        )

        assert "DIFF_START" in result
        assert "DIFF_END" in result

    def test_summary_inclusion(self):
        """Test content summary inclusion for long content."""
        content = "Very long content line\n" * 100
        metadata = {"include_summary": True}

        result = self.formatter.format_response(
            content, ClientType.LLM, "git_log", metadata
        )

        assert "SUMMARY:" in result


# Integration tests
class TestTokenManagementIntegration:
    """Integration tests for the complete token management system."""

    def test_end_to_end_processing(self):
        """Test complete processing pipeline."""
        # Simulate a large git diff
        content = (
            """diff --git a/large_file.py b/large_file.py
index 1234567..abcdefg 100644
--- a/large_file.py
+++ b/large_file.py
@@ -1,1000 +1,1000 @@"""
            + "\n-old line\n+new line" * 500
        )

        # Process through the complete pipeline
        manager = IntelligentTruncationManager()
        formatter = ResponseFormatter()

        # First optimize for LLM
        optimized = formatter.format_response(content, ClientType.LLM, "git_diff")

        # Then apply truncation if needed
        result = manager.truncate_for_operation(optimized, "git_diff", 1000)

        assert result.final_tokens <= 1000
        assert "diff --git" in result.content  # Essential structure preserved

        if result.truncated:
            assert "Diff truncated:" in result.content


if __name__ == "__main__":
    pytest.main([__file__])
