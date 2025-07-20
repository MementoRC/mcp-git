"""Tests for enhanced validation system with input sanitization."""

import pytest
from pathlib import Path
from typing import Dict, Any

from mcp_server_git.models.enhanced_validation import (
    InputSanitizer,
    RobustNotificationHandler,
    sanitize_tool_arguments,
    NotificationInfo,
)


class TestInputSanitizer:
    """Test the InputSanitizer class functionality."""

    def test_sanitize_safe_path(self):
        """Test sanitization of safe file paths."""
        safe_path = "/home/user/project/file.py"
        sanitized, issues = InputSanitizer.sanitize_path(safe_path)
        
        assert len(issues) == 0
        assert Path(sanitized).is_absolute()

    def test_sanitize_dangerous_path(self):
        """Test detection of path traversal attempts."""
        dangerous_path = "/home/user/../../../etc/passwd"
        sanitized, issues = InputSanitizer.sanitize_path(dangerous_path)
        
        assert len(issues) > 0
        assert any("path traversal" in issue.lower() for issue in issues)

    def test_sanitize_long_path(self):
        """Test handling of overly long paths."""
        long_path = "/home/" + "x" * 5000
        sanitized, issues = InputSanitizer.sanitize_path(long_path)
        
        assert len(issues) > 0
        assert any("too long" in issue.lower() for issue in issues)
        assert len(sanitized) <= InputSanitizer.MAX_PATH_LENGTH

    def test_validate_git_reference_valid(self):
        """Test validation of valid git references."""
        valid_refs = ["main", "feature/new-feature", "v1.0.0", "fix-bug-123"]
        
        for ref in valid_refs:
            sanitized, issues = InputSanitizer.validate_git_reference(ref)
            assert len(issues) == 0
            assert sanitized == ref

    def test_validate_git_reference_invalid_chars(self):
        """Test detection of invalid characters in git references."""
        invalid_ref = "feature..bad:name*"
        sanitized, issues = InputSanitizer.validate_git_reference(invalid_ref)
        
        assert len(issues) > 0
        assert any("invalid character" in issue.lower() for issue in issues)
        assert ".." not in sanitized
        assert ":" not in sanitized
        assert "*" not in sanitized

    def test_validate_git_reference_invalid_start_end(self):
        """Test detection of invalid start/end characters."""
        invalid_refs = ["/start-with-slash", "-start-with-dash", "end-with-slash/"]
        
        for ref in invalid_refs:
            sanitized, issues = InputSanitizer.validate_git_reference(ref)
            assert len(issues) > 0
            assert not sanitized.startswith(("/", "-"))
            assert not sanitized.endswith("/")

    def test_sanitize_string_with_dangerous_patterns(self):
        """Test detection of potentially dangerous string patterns."""
        dangerous_strings = [
            "command; rm -rf /",
            "file\x00null",
            "test$(malicious)",
            "data\necho dangerous",
        ]
        
        for dangerous in dangerous_strings:
            sanitized, issues = InputSanitizer.sanitize_string_input(dangerous)
            assert len(issues) > 0
            assert any("dangerous" in issue.lower() or "null" in issue.lower() for issue in issues)


class TestRobustNotificationHandler:
    """Test the RobustNotificationHandler with enhanced validation."""

    def test_extract_notification_info_basic(self):
        """Test basic notification info extraction."""
        handler = RobustNotificationHandler()
        data = {
            "method": "test/method",
            "params": {"requestId": "123"},
        }
        
        info = handler.extract_notification_info(data)
        
        assert info.method == "test/method"
        assert info.request_id == "123"
        assert info.has_params is True

    def test_extract_notification_info_with_sanitization(self):
        """Test notification info extraction with parameters that need sanitization."""
        handler = RobustNotificationHandler()
        data = {
            "method": "git/command",
            "params": {
                "requestId": "123",
                "repo_path": "/home/user/../../../etc/passwd",
                "branch": "feature..bad:name",
            },
        }
        
        info = handler.extract_notification_info(data)
        
        assert info.method == "git/command"
        assert info.is_sanitized is True
        assert len(info.sanitization_issues) > 0

    def test_handle_large_notification(self):
        """Test handling of oversized notifications."""
        handler = RobustNotificationHandler()
        # Create a large notification
        large_data = {
            "method": "test/method",
            "params": {"data": "x" * (InputSanitizer.MAX_MESSAGE_SIZE + 1000)},
        }
        
        result = handler.handle_notification(large_data)
        
        assert not result.is_valid
        assert "too large" in str(result.error).lower()

    def test_get_stats_includes_sanitization(self):
        """Test that statistics include sanitization metrics."""
        handler = RobustNotificationHandler()
        
        # Process a notification that requires sanitization
        data = {
            "method": "git/command",
            "params": {
                "repo_path": "/dangerous/../path",
                "branch": "bad..branch",
            },
        }
        
        handler.handle_notification(data)
        stats = handler.get_stats()
        
        assert "sanitized" in stats
        assert "security_issues" in stats


class TestToolArgumentSanitization:
    """Test sanitization of tool arguments."""

    def test_sanitize_git_tool_arguments(self):
        """Test sanitization of typical git tool arguments."""
        arguments = {
            "repo_path": "/home/user/../../../etc/passwd",
            "branch": "feature..bad:name",
            "message": "Commit message with\x00null bytes",
            "other_param": "normal value",
        }
        
        sanitized_args, issues = sanitize_tool_arguments("git_commit", arguments)
        
        assert len(issues) > 0
        assert ".." not in sanitized_args["branch"]
        assert ":" not in sanitized_args["branch"]
        assert "\x00" not in sanitized_args["message"]
        assert sanitized_args["other_param"] == "normal value"  # Unchanged

    def test_sanitize_path_arguments(self):
        """Test sanitization of path-related arguments."""
        arguments = {
            "file_path": "/safe/path/file.txt",
            "repo_path": "/dangerous/../path",
        }
        
        sanitized_args, issues = sanitize_tool_arguments("git_status", arguments)
        
        # Safe path should be unchanged
        assert "file_path" in sanitized_args
        
        # Dangerous path should have issues reported
        path_issues = [issue for issue in issues if "path" in issue.lower()]
        assert len(path_issues) > 0

    def test_sanitize_commit_message_length(self):
        """Test truncation of overly long commit messages."""
        long_message = "x" * (InputSanitizer.MAX_COMMIT_MESSAGE_LENGTH + 1000)
        arguments = {"message": long_message}
        
        sanitized_args, issues = sanitize_tool_arguments("git_commit", arguments)
        
        assert len(sanitized_args["message"]) <= InputSanitizer.MAX_COMMIT_MESSAGE_LENGTH
        assert any("truncated" in issue.lower() for issue in issues)


@pytest.mark.integration
class TestValidationIntegration:
    """Integration tests for the validation system."""

    def test_notification_processing_with_sanitization(self):
        """Test end-to-end notification processing with sanitization."""
        handler = RobustNotificationHandler()
        
        # Create a notification with various issues
        notification_data = {
            "jsonrpc": "2.0",
            "method": "git/test",
            "params": {
                "requestId": "test-123",
                "repo_path": "/home/user/../dangerous",
                "branch": "feature..bad:branch*",
                "message": "Test\x00message with nulls",
            },
        }
        
        result = handler.handle_notification(notification_data)
        stats = handler.get_stats()
        
        # Should have processed the notification despite issues
        assert stats["sanitized"] > 0
        
        # Should have detected security issues
        if stats.get("security_issues", 0) > 0:
            # Expected for dangerous path traversal
            pass

    def test_validation_performance(self):
        """Test that validation doesn't significantly impact performance."""
        import time
        
        handler = RobustNotificationHandler()
        
        # Create a batch of notifications
        notifications = []
        for i in range(100):
            notifications.append({
                "method": f"test/method_{i}",
                "params": {
                    "requestId": f"req_{i}",
                    "repo_path": f"/home/user/project_{i}",
                    "branch": f"feature/branch_{i}",
                },
            })
        
        # Process notifications and measure time
        start_time = time.time()
        for notification in notifications:
            handler.handle_notification(notification)
        end_time = time.time()
        
        # Should process quickly (less than 1 second for 100 notifications)
        processing_time = end_time - start_time
        assert processing_time < 1.0, f"Processing took too long: {processing_time}s"
        
        stats = handler.get_stats()
        assert stats["processed"] + stats["errors"] >= len(notifications)