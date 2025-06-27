"""Error handling and recovery mechanisms for MCP Git Server."""

import asyncio
import functools
import logging
import time
from enum import Enum
from typing import Any, Callable, Dict, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ErrorSeverity(Enum):
    """Classification of error severity levels."""

    CRITICAL = "critical"  # Session must terminate
    HIGH = "high"  # Operation must abort, session can continue
    MEDIUM = "medium"  # Operation might recover
    LOW = "low"  # Can safely ignore


class ErrorContext:
    """Context information about an error for recovery decisions."""

    def __init__(
        self,
        error: Exception,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        operation: str = "",
        session_id: Optional[str] = None,
        recoverable: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.error = error
        self.severity = severity
        self.operation = operation
        self.session_id = session_id
        self.recoverable = recoverable
        self.metadata = metadata or {}
        self.handled = False
        self.retry_count = 0
        self.error_time = time.time()


class ErrorRecoveryStrategy:
    """Strategy for recovering from specific error types."""

    def __init__(self, max_retries: int = 3, backoff_factor: float = 1.0):
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    def should_retry(self, context: ErrorContext) -> bool:
        """Determine if an error should be retried."""
        if not context.recoverable:
            return False

        if context.severity in (ErrorSeverity.CRITICAL, ErrorSeverity.HIGH):
            return False

        return context.retry_count < self.max_retries

    def get_retry_delay(self, context: ErrorContext) -> float:
        """Calculate delay before retry."""
        return self.backoff_factor * (2**context.retry_count)


# Global error recovery strategy
_default_strategy = ErrorRecoveryStrategy()


def recoverable(max_retries: int = 3, backoff_factor: float = 1.0):
    """Decorator for functions that should recover from errors with retry logic."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> T:
            context = None

            while True:
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if context is None:
                        context = ErrorContext(
                            error=e,
                            operation=func.__name__,
                            severity=ErrorSeverity.MEDIUM,
                            recoverable=True,
                        )
                    else:
                        context.error = e
                        context.retry_count += 1

                    strategy = ErrorRecoveryStrategy(max_retries, backoff_factor)

                    if not strategy.should_retry(context):
                        logger.error(
                            f"Failed after {context.retry_count} retries in {func.__name__}: {e}"
                        )
                        raise e

                    delay = strategy.get_retry_delay(context)
                    logger.warning(
                        f"Error in {func.__name__}, retry {context.retry_count + 1}/"
                        f"{max_retries} after {delay}s: {e}"
                    )
                    await asyncio.sleep(delay)

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> T:
            context = None

            while True:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if context is None:
                        context = ErrorContext(
                            error=e,
                            operation=func.__name__,
                            severity=ErrorSeverity.MEDIUM,
                            recoverable=True,
                        )
                    else:
                        context.error = e
                        context.retry_count += 1

                    strategy = ErrorRecoveryStrategy(max_retries, backoff_factor)

                    if not strategy.should_retry(context):
                        logger.error(
                            f"Failed after {context.retry_count} retries in {func.__name__}: {e}"
                        )
                        raise e

                    delay = strategy.get_retry_delay(context)
                    logger.warning(
                        f"Error in {func.__name__}, retry {context.retry_count + 1}/"
                        f"{max_retries} after {delay}s: {e}"
                    )
                    time.sleep(delay)

        # Return appropriate wrapper based on whether function is async
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


async def handle_error(context: ErrorContext) -> bool:
    """
    Central error handler that determines recovery strategy.

    Returns:
        bool: True if error was handled and operation can continue,
              False if error is critical and session should terminate.
    """
    logger.error(
        f"{context.severity.value.upper()} error in {context.operation}: {context.error}"
    )

    # Log additional context
    if context.session_id:
        logger.error(f"Session ID: {context.session_id}")

    if context.metadata:
        logger.debug(f"Error metadata: {context.metadata}")

    # Handle critical errors
    if context.severity == ErrorSeverity.CRITICAL:
        logger.critical("Critical error detected, session must terminate")
        context.handled = False
        return False

    # Handle non-recoverable errors
    if not context.recoverable:
        logger.error("Non-recoverable error, but session can continue")
        context.handled = True
        return True

    # Implement recovery strategies based on error type
    recovery_successful = await _attempt_recovery(context)

    if recovery_successful:
        logger.info(f"Successfully recovered from error in {context.operation}")
        context.handled = True
        return True
    else:
        logger.warning(f"Failed to recover from error in {context.operation}")
        context.handled = False
        return context.severity != ErrorSeverity.HIGH


async def _attempt_recovery(context: ErrorContext) -> bool:
    """Attempt to recover from an error based on its type and context."""
    error_type = type(context.error).__name__

    # Recovery strategies for specific error types
    if "Network" in error_type or "Connection" in error_type:
        logger.info("Attempting network error recovery")
        await asyncio.sleep(1.0)  # Brief pause for network issues
        return True

    if "Git" in error_type:
        logger.info("Attempting git operation recovery")
        # Could implement git-specific recovery strategies here
        return True

    if "Validation" in error_type:
        logger.info("Attempting validation error recovery")
        # Validation errors are often recoverable by falling back to defaults
        return True

    # Default recovery for unknown error types
    logger.info(f"Attempting default recovery for {error_type}")
    return context.severity in (ErrorSeverity.LOW, ErrorSeverity.MEDIUM)


def classify_error(error: Exception, operation: str = "") -> ErrorContext:
    """
    Classify an error and create an appropriate ErrorContext.

    Args:
        error: The exception that occurred
        operation: The operation during which the error occurred

    Returns:
        ErrorContext with appropriate severity and recoverability settings
    """
    error_type = type(error).__name__

    # Critical errors that require session termination
    if error_type in ("SystemExit", "KeyboardInterrupt", "MemoryError"):
        return ErrorContext(
            error=error,
            severity=ErrorSeverity.CRITICAL,
            operation=operation,
            recoverable=False,
        )

    # High severity errors that abort operations but allow session to continue
    if error_type in ("PermissionError", "FileNotFoundError"):
        return ErrorContext(
            error=error,
            severity=ErrorSeverity.HIGH,
            operation=operation,
            recoverable=False,
        )

    # Medium severity errors that might be recoverable
    if any(x in error_type for x in ["Network", "Connection", "Timeout", "Git"]):
        return ErrorContext(
            error=error,
            severity=ErrorSeverity.MEDIUM,
            operation=operation,
            recoverable=True,
        )

    # Low severity errors that are usually recoverable
    error_message = str(error)
    if (
        any(x in error_type for x in ["Validation", "Parse", "Format"])
        or any(x in error_message for x in ["Validation", "Parse", "Format"])
        or error_type == "ValueError"
    ):
        return ErrorContext(
            error=error,
            severity=ErrorSeverity.LOW,
            operation=operation,
            recoverable=True,
        )

    # Default classification for unknown errors
    return ErrorContext(
        error=error,
        severity=ErrorSeverity.MEDIUM,
        operation=operation,
        recoverable=True,
    )


# Error metrics tracking
_error_stats: Dict[str, Any] = {
    "total_errors": 0,
    "errors_by_type": {},
    "errors_by_severity": {severity.value: 0 for severity in ErrorSeverity},
    "recovered_errors": 0,
    "critical_errors": 0,
}


def record_error_metric(context: ErrorContext) -> None:
    """Record error metrics for monitoring and analysis."""
    _error_stats["total_errors"] += 1

    error_type = type(context.error).__name__
    _error_stats["errors_by_type"][error_type] = (
        _error_stats["errors_by_type"].get(error_type, 0) + 1
    )

    _error_stats["errors_by_severity"][context.severity.value] += 1

    if context.handled:
        _error_stats["recovered_errors"] += 1

    if context.severity == ErrorSeverity.CRITICAL:
        _error_stats["critical_errors"] += 1


def get_error_stats() -> Dict[str, Any]:
    """Get current error statistics."""
    return _error_stats.copy()


def reset_error_stats() -> None:
    """Reset error statistics (useful for testing)."""
    global _error_stats
    _error_stats = {
        "total_errors": 0,
        "errors_by_type": {},
        "errors_by_severity": {severity.value: 0 for severity in ErrorSeverity},
        "recovered_errors": 0,
        "critical_errors": 0,
    }
