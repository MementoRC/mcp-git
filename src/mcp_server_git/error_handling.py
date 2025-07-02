"""Error handling and recovery mechanisms for MCP Git Server."""

import asyncio
import functools
import logging
import time
from enum import Enum
from typing import Any, Callable, Dict, Optional, TypeVar, cast

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
                    if asyncio.iscoroutinefunction(func):
                        result = await func(*args, **kwargs)
                    else:
                        result = func(*args, **kwargs)
                    return cast(T, result)
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
                    result = func(*args, **kwargs)
                    return cast(T, result)
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
            return async_wrapper  # type: ignore
        else:
            return sync_wrapper  # type: ignore

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


# Circuit Breaker Pattern Implementation


class CircuitState(Enum):
    """States of a circuit breaker."""

    CLOSED = "closed"  # Normal operation, allowing requests
    OPEN = "open"  # Failing fast, not allowing requests
    HALF_OPEN = "half_open"  # Testing if system has recovered


class CircuitOpenError(Exception):
    """Error raised when a circuit is open and rejects a request."""

    pass


class CircuitBreaker:
    """
    Implements the circuit breaker pattern to prevent cascading failures.

    The circuit breaker has three states:
    - CLOSED: Normal operation, requests are allowed
    - OPEN: Circuit is tripped, requests fail fast
    - HALF_OPEN: Testing recovery, limited requests allowed
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.half_open_calls = 0

        # Metrics
        self._total_requests = 0
        self._successful_requests = 0
        self._failed_requests = 0
        self._rejected_requests = 0

    def reset(self) -> None:
        """Reset the circuit breaker to closed state."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.half_open_calls = 0
        logger.info(f"Circuit {self.name} reset to CLOSED state")

    def record_failure(self) -> None:
        """Record a failure and potentially trip the circuit."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        self._failed_requests += 1

        if (
            self.state == CircuitState.CLOSED
            and self.failure_count >= self.failure_threshold
        ):
            logger.warning(
                f"Circuit {self.name} tripped after {self.failure_count} failures"
            )
            self.state = CircuitState.OPEN
        elif self.state == CircuitState.HALF_OPEN:
            logger.warning(f"Circuit {self.name} reopened after test failure")
            self.state = CircuitState.OPEN
            self.half_open_calls = 0

    def record_success(self) -> None:
        """Record a success and potentially reset the circuit."""
        self._successful_requests += 1

        if self.state == CircuitState.HALF_OPEN:
            self.reset()
            logger.info(f"Circuit {self.name} closed after successful test")
        elif self.state == CircuitState.CLOSED:
            # Reset failure count on successful operation in CLOSED state
            self.failure_count = 0

    def allow_request(self) -> bool:
        """Check if a request should be allowed based on circuit state."""
        self._total_requests += 1

        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if recovery timeout has elapsed
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"Circuit {self.name} entering half-open state for testing")
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
            else:
                self._rejected_requests += 1
                return False  # Still open, fail fast

        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_calls < self.half_open_max_calls:
                self.half_open_calls += 1
                return True
            else:
                self._rejected_requests += 1
                return False

        return True

    @property
    def failure_rate(self) -> float:
        """Calculate the current failure rate."""
        if self._total_requests == 0:
            return 0.0
        return self._failed_requests / self._total_requests

    @property
    def success_rate(self) -> float:
        """Calculate the current success rate."""
        if self._total_requests == 0:
            return 0.0
        return self._successful_requests / self._total_requests

    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "total_requests": self._total_requests,
            "successful_requests": self._successful_requests,
            "failed_requests": self._failed_requests,
            "rejected_requests": self._rejected_requests,
            "failure_rate": self.failure_rate,
            "success_rate": self.success_rate,
            "time_since_last_failure": time.time() - self.last_failure_time
            if self.last_failure_time > 0
            else 0,
        }


def with_circuit_breaker(circuit: CircuitBreaker):
    """Decorator to apply circuit breaker to a function."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> T:
            if not circuit.allow_request():
                raise CircuitOpenError(f"Circuit {circuit.name} is open")

            try:
                result = await func(*args, **kwargs)
                circuit.record_success()
                return result
            except Exception:
                circuit.record_failure()
                raise

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> T:
            if not circuit.allow_request():
                raise CircuitOpenError(f"Circuit {circuit.name} is open")

            try:
                result = func(*args, **kwargs)
                circuit.record_success()
                return result
            except Exception:
                circuit.record_failure()
                raise

        # Return appropriate wrapper based on whether function is async
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# Global circuit breaker registry
_circuit_breakers: Dict[str, CircuitBreaker] = {}


def get_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
    half_open_max_calls: int = 1,
) -> CircuitBreaker:
    """Get or create a circuit breaker by name."""
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            half_open_max_calls=half_open_max_calls,
        )
    return _circuit_breakers[name]


def get_all_circuit_breakers() -> Dict[str, CircuitBreaker]:
    """Get all registered circuit breakers."""
    return _circuit_breakers.copy()


def reset_circuit_breaker(name: str) -> bool:
    """Reset a specific circuit breaker by name."""
    if name in _circuit_breakers:
        _circuit_breakers[name].reset()
        return True
    return False


def reset_all_circuit_breakers() -> None:
    """Reset all circuit breakers (useful for testing)."""
    for circuit in _circuit_breakers.values():
        circuit.reset()


def remove_circuit_breaker(name: str) -> bool:
    """Remove a circuit breaker from the registry."""
    if name in _circuit_breakers:
        del _circuit_breakers[name]
        return True
    return False


def clear_circuit_breakers() -> None:
    """Clear all circuit breakers (useful for testing)."""
    global _circuit_breakers
    _circuit_breakers = {}
