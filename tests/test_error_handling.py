"""Tests for error handling and recovery mechanisms."""

import logging
import pytest
import time
from unittest.mock import patch

from mcp_server_git.error_handling import (
    ErrorSeverity,
    ErrorContext,
    ErrorRecoveryStrategy,
    recoverable,
    handle_error,
    classify_error,
    record_error_metric,
    get_error_stats,
    reset_error_stats,
    _attempt_recovery,
)


class TestErrorContext:
    """Test ErrorContext functionality."""

    def test_error_context_creation(self):
        """Test creating an ErrorContext with various parameters."""
        error = ValueError("test error")
        context = ErrorContext(
            error=error,
            severity=ErrorSeverity.HIGH,
            operation="test_operation",
            session_id="test-session-123",
            recoverable=False,
            metadata={"key": "value"},
        )

        assert context.error == error
        assert context.severity == ErrorSeverity.HIGH
        assert context.operation == "test_operation"
        assert context.session_id == "test-session-123"
        assert context.recoverable is False
        assert context.metadata == {"key": "value"}
        assert context.handled is False
        assert context.retry_count == 0
        assert isinstance(context.error_time, float)

    def test_error_context_defaults(self):
        """Test ErrorContext with default values."""
        error = RuntimeError("test error")
        context = ErrorContext(error)

        assert context.error == error
        assert context.severity == ErrorSeverity.MEDIUM
        assert context.operation == ""
        assert context.session_id is None
        assert context.recoverable is True
        assert context.metadata == {}
        assert context.handled is False


class TestErrorRecoveryStrategy:
    """Test ErrorRecoveryStrategy functionality."""

    def test_should_retry_recoverable_medium_error(self):
        """Test that recoverable medium errors should be retried."""
        strategy = ErrorRecoveryStrategy(max_retries=3)
        context = ErrorContext(
            ValueError("test"), severity=ErrorSeverity.MEDIUM, recoverable=True
        )

        assert strategy.should_retry(context) is True

    def test_should_not_retry_critical_error(self):
        """Test that critical errors should not be retried."""
        strategy = ErrorRecoveryStrategy(max_retries=3)
        context = ErrorContext(
            ValueError("test"), severity=ErrorSeverity.CRITICAL, recoverable=True
        )

        assert strategy.should_retry(context) is False

    def test_should_not_retry_non_recoverable(self):
        """Test that non-recoverable errors should not be retried."""
        strategy = ErrorRecoveryStrategy(max_retries=3)
        context = ErrorContext(
            ValueError("test"), severity=ErrorSeverity.LOW, recoverable=False
        )

        assert strategy.should_retry(context) is False

    def test_should_not_retry_after_max_attempts(self):
        """Test that errors should not be retried after max attempts."""
        strategy = ErrorRecoveryStrategy(max_retries=2)
        context = ErrorContext(
            ValueError("test"), severity=ErrorSeverity.MEDIUM, recoverable=True
        )
        context.retry_count = 2

        assert strategy.should_retry(context) is False

    def test_get_retry_delay_exponential_backoff(self):
        """Test exponential backoff delay calculation."""
        strategy = ErrorRecoveryStrategy(backoff_factor=1.0)
        context = ErrorContext(ValueError("test"))

        # First retry (retry_count = 0)
        context.retry_count = 0
        assert strategy.get_retry_delay(context) == 1.0

        # Second retry (retry_count = 1)
        context.retry_count = 1
        assert strategy.get_retry_delay(context) == 2.0

        # Third retry (retry_count = 2)
        context.retry_count = 2
        assert strategy.get_retry_delay(context) == 4.0


class TestRecoverableDecorator:
    """Test the @recoverable decorator."""

    @pytest.mark.asyncio
    async def test_async_function_success(self):
        """Test that successful async functions work normally."""

        @recoverable(max_retries=2)
        async def test_func():
            return "success"

        result = await test_func()
        assert result == "success"

    def test_sync_function_success(self):
        """Test that successful sync functions work normally."""

        @recoverable(max_retries=2)
        def test_func():
            return "success"

        result = test_func()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_async_function_retry_and_succeed(self, caplog):
        """Test async function that fails then succeeds."""
        call_count = 0

        @recoverable(max_retries=2, backoff_factor=0.1)
        async def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError(f"attempt {call_count}")
            return "success"

        result = await test_func()
        assert result == "success"
        assert call_count == 2
        assert "retry 1/2" in caplog.text

    def test_sync_function_retry_and_succeed(self, caplog):
        """Test sync function that fails then succeeds."""
        call_count = 0

        @recoverable(max_retries=2, backoff_factor=0.1)
        def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError(f"attempt {call_count}")
            return "success"

        result = test_func()
        assert result == "success"
        assert call_count == 2
        assert "retry 1/2" in caplog.text

    @pytest.mark.asyncio
    async def test_async_function_max_retries_exceeded(self, caplog):
        """Test async function that fails all retries."""

        @recoverable(max_retries=2, backoff_factor=0.1)
        async def test_func():
            raise ValueError("persistent error")

        with pytest.raises(ValueError, match="persistent error"):
            await test_func()

        assert "Failed after 2 retries" in caplog.text

    def test_sync_function_max_retries_exceeded(self, caplog):
        """Test sync function that fails all retries."""

        @recoverable(max_retries=2, backoff_factor=0.1)
        def test_func():
            raise ValueError("persistent error")

        with pytest.raises(ValueError, match="persistent error"):
            test_func()

        assert "Failed after 2 retries" in caplog.text


class TestHandleError:
    """Test the handle_error function."""

    @pytest.mark.asyncio
    async def test_handle_critical_error(self, caplog):
        """Test handling of critical errors."""
        context = ErrorContext(
            RuntimeError("critical"),
            severity=ErrorSeverity.CRITICAL,
            operation="test_op",
        )

        result = await handle_error(context)
        assert result is False
        assert context.handled is False
        assert "CRITICAL error in test_op" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_non_recoverable_error(self, caplog):
        """Test handling of non-recoverable errors."""
        context = ErrorContext(
            PermissionError("access denied"),
            severity=ErrorSeverity.HIGH,
            operation="test_op",
            recoverable=False,
        )

        result = await handle_error(context)
        assert result is True
        assert context.handled is True
        assert "Non-recoverable error" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_recoverable_error(self, caplog):
        """Test handling of recoverable errors."""
        # Set log level to capture INFO messages
        caplog.set_level(logging.INFO)

        context = ErrorContext(
            ConnectionError("network issue"),
            severity=ErrorSeverity.MEDIUM,
            operation="test_op",
            recoverable=True,
        )

        # Mock the recovery function to return success
        async def mock_recovery(ctx):
            return True

        with patch(
            "mcp_server_git.error_handling._attempt_recovery", side_effect=mock_recovery
        ):
            result = await handle_error(context)

        assert result is True
        assert context.handled is True
        assert "Successfully recovered" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_error_with_metadata(self, caplog):
        """Test handling errors with additional metadata."""
        context = ErrorContext(
            ValueError("test error"),
            operation="test_op",
            session_id="session-123",
            metadata={"user": "test", "action": "commit"},
        )

        await handle_error(context)
        assert "Session ID: session-123" in caplog.text


class TestAttemptRecovery:
    """Test the _attempt_recovery function."""

    @pytest.mark.asyncio
    async def test_network_error_recovery(self):
        """Test recovery strategy for network errors."""
        context = ErrorContext(ConnectionError("network error"))

        start_time = time.time()
        result = await _attempt_recovery(context)
        elapsed = time.time() - start_time

        assert result is True
        assert elapsed >= 1.0  # Should have slept for network recovery

    @pytest.mark.asyncio
    async def test_git_error_recovery(self):
        """Test recovery strategy for git errors."""
        context = ErrorContext(Exception("GitCommandError"))

        result = await _attempt_recovery(context)
        assert result is True

    @pytest.mark.asyncio
    async def test_validation_error_recovery(self):
        """Test recovery strategy for validation errors."""
        context = ErrorContext(ValueError("ValidationError"))

        result = await _attempt_recovery(context)
        assert result is True

    @pytest.mark.asyncio
    async def test_unknown_error_recovery_medium_severity(self):
        """Test default recovery for unknown medium severity errors."""
        context = ErrorContext(
            RuntimeError("unknown error"), severity=ErrorSeverity.MEDIUM
        )

        result = await _attempt_recovery(context)
        assert result is True

    @pytest.mark.asyncio
    async def test_unknown_error_recovery_high_severity(self):
        """Test default recovery for unknown high severity errors."""
        context = ErrorContext(
            RuntimeError("unknown error"), severity=ErrorSeverity.HIGH
        )

        result = await _attempt_recovery(context)
        assert result is False


class TestClassifyError:
    """Test the classify_error function."""

    def test_classify_critical_errors(self):
        """Test classification of critical errors."""
        critical_errors = [
            SystemExit("exit"),
            KeyboardInterrupt(),
            MemoryError("out of memory"),
        ]

        for error in critical_errors:
            context = classify_error(error, "test_op")
            assert context.severity == ErrorSeverity.CRITICAL
            assert context.recoverable is False

    def test_classify_high_severity_errors(self):
        """Test classification of high severity errors."""
        high_errors = [
            PermissionError("access denied"),
            FileNotFoundError("file not found"),
        ]

        for error in high_errors:
            context = classify_error(error, "test_op")
            assert context.severity == ErrorSeverity.HIGH
            assert context.recoverable is False

    def test_classify_medium_severity_errors(self):
        """Test classification of medium severity errors."""
        medium_errors = [
            ConnectionError("network error"),
            TimeoutError("timeout"),
            Exception("GitError"),
        ]

        for error in medium_errors:
            context = classify_error(error, "test_op")
            assert context.severity == ErrorSeverity.MEDIUM
            assert context.recoverable is True

    def test_classify_low_severity_errors(self):
        """Test classification of low severity errors."""
        low_errors = [
            ValueError("ValidationError"),
            Exception("ParseError"),
            Exception("FormatError"),
        ]

        for error in low_errors:
            context = classify_error(error, "test_op")
            assert context.severity == ErrorSeverity.LOW
            assert context.recoverable is True

    def test_classify_unknown_error(self):
        """Test classification of unknown errors."""
        error = Exception("unknown error")
        context = classify_error(error, "test_op")

        assert context.severity == ErrorSeverity.MEDIUM
        assert context.recoverable is True
        assert context.operation == "test_op"


class TestErrorMetrics:
    """Test error metrics functionality."""

    def setup_method(self):
        """Reset error stats before each test."""
        reset_error_stats()

    def test_record_error_metric(self):
        """Test recording error metrics."""
        context = ErrorContext(
            ValueError("test error"), severity=ErrorSeverity.HIGH, recoverable=True
        )
        context.handled = True

        record_error_metric(context)

        stats = get_error_stats()
        assert stats["total_errors"] == 1
        assert stats["errors_by_type"]["ValueError"] == 1
        assert stats["errors_by_severity"]["high"] == 1
        assert stats["recovered_errors"] == 1
        assert stats["critical_errors"] == 0

    def test_record_critical_error_metric(self):
        """Test recording critical error metrics."""
        context = ErrorContext(
            RuntimeError("exit"), severity=ErrorSeverity.CRITICAL, recoverable=False
        )
        context.handled = False

        record_error_metric(context)

        stats = get_error_stats()
        assert stats["total_errors"] == 1
        assert stats["errors_by_type"]["SystemExit"] == 1
        assert stats["errors_by_severity"]["critical"] == 1
        assert stats["recovered_errors"] == 0
        assert stats["critical_errors"] == 1

    def test_multiple_error_metrics(self):
        """Test recording multiple error metrics."""
        errors = [
            ErrorContext(ValueError("error1"), severity=ErrorSeverity.LOW),
            ErrorContext(ValueError("error2"), severity=ErrorSeverity.LOW),
            ErrorContext(RuntimeError("error3"), severity=ErrorSeverity.MEDIUM),
        ]

        for context in errors:
            context.handled = True
            record_error_metric(context)

        stats = get_error_stats()
        assert stats["total_errors"] == 3
        assert stats["errors_by_type"]["ValueError"] == 2
        assert stats["errors_by_type"]["RuntimeError"] == 1
        assert stats["errors_by_severity"]["low"] == 2
        assert stats["errors_by_severity"]["medium"] == 1
        assert stats["recovered_errors"] == 3

    def test_reset_error_stats(self):
        """Test resetting error statistics."""
        context = ErrorContext(ValueError("test"))
        record_error_metric(context)

        # Verify stats were recorded
        stats = get_error_stats()
        assert stats["total_errors"] == 1

        # Reset and verify
        reset_error_stats()
        stats = get_error_stats()
        assert stats["total_errors"] == 0
        assert stats["errors_by_type"] == {}
        assert stats["recovered_errors"] == 0
