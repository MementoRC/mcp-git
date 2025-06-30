"""Performance optimizations for MCP Git Server."""

import json
import logging
from functools import lru_cache, wraps
from typing import Any, Callable, Dict, Optional, Protocol, runtime_checkable
from functools import _CacheInfo  # Import the internal CacheInfo type for type hinting

from .models.validation import ValidationResult

logger = logging.getLogger(__name__)


# Define a protocol for the LRU cached function to include cache_info and cache_clear
@runtime_checkable
class LRUCachedFunction(Protocol):
    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...
    def cache_info(self) -> _CacheInfo: ...  # Use the actual CacheInfo type
    def cache_clear(self) -> None: ...


# This will hold the reference to the actual cached function
_cached_parse_function: Optional[LRUCachedFunction] = None
_cache_maxsize: int = 1024
_cache_enabled: bool = True


def _get_cache_info():
    """Helper to get cache info if the function is cached."""
    if _cached_parse_function is not None:
        return _cached_parse_function.cache_info()
    return None


def _clear_cache():
    """Helper to clear the cache if the function is cached."""
    if _cached_parse_function is not None:
        _cached_parse_function.cache_clear()
        logger.info("Validation cache cleared.")


def enable_validation_cache():
    """Enables the validation cache."""
    global _cache_enabled
    _cache_enabled = True
    logger.info("Validation cache enabled.")


def disable_validation_cache():
    """Disables the validation cache."""
    global _cache_enabled
    _cache_enabled = False
    logger.info("Validation cache disabled.")


def clear_validation_cache():
    """Clears all items from the validation cache."""
    _clear_cache()


def get_validation_cache_stats() -> Dict[str, Any]:
    """Returns validation cache statistics."""
    info = _get_cache_info()
    if info:
        return {
            "hits": info.hits,
            "misses": info.misses,
            "current_size": info.currsize,
            "max_size": info.maxsize,
            "enabled": _cache_enabled,
        }
    else:
        return {
            "hits": 0,
            "misses": 0,
            "current_size": 0,
            "max_size": _cache_maxsize,
            "enabled": _cache_enabled,
        }


def _create_cache_key(data: Dict[str, Any]) -> str:
    """Create a stable cache key from message data."""
    try:
        # Create a reproducible key from the essential fields
        key_data = {
            "method": data.get("method", "unknown"),
            "jsonrpc": data.get("jsonrpc", "2.0"),
        }

        # Add params if present, but normalize them
        if "params" in data:
            params = data["params"]
            if isinstance(params, dict):
                # Sort keys to ensure consistent ordering
                key_data["params"] = json.dumps(params, sort_keys=True)
            else:
                key_data["params"] = str(params)

        # Create final key
        return json.dumps(key_data, sort_keys=True)
    except Exception:
        # Fallback to string representation
        return str(data)


def apply_validation_cache(
    func: Callable[[Dict[str, Any]], ValidationResult],
) -> Callable[[Dict[str, Any]], ValidationResult]:
    """
    Decorator to apply caching to validation functions.

    This creates an LRU cache that can be enabled/disabled and provides
    cache statistics for performance monitoring.
    """
    global _cached_parse_function

    # Create the cached version of the function
    @lru_cache(maxsize=_cache_maxsize)
    def _cached_validation(cache_key: str, original_data_str: str) -> ValidationResult:
        """Internal cached function that works on cache keys."""
        # Reconstruct the original data and call the function
        try:
            data = json.loads(original_data_str)
            return func(data)
        except Exception as e:
            logger.error(f"Cache key reconstruction failed: {e}")
            # Return error result
            return ValidationResult(error=e, raw_data={})

    @wraps(func)
    def wrapper(data: Dict[str, Any]) -> ValidationResult:
        """Wrapper that handles caching logic."""
        if not _cache_enabled:
            # Cache disabled, call function directly
            return func(data)

        try:
            # Create cache key and serialized data
            cache_key = _create_cache_key(data)
            # Ensure data is always serializable for the cache key
            serialized_data = json.dumps(data, sort_keys=True)

            # Call cached function
            return _cached_validation(cache_key, serialized_data)
        except Exception as e:
            logger.warning(f"Caching failed, falling back to direct call: {e}")
            # Fallback to direct function call
            return func(data)

    # Store reference to cached function for stats
    # The lru_cache decorator returns an object that implements the LRUCachedFunction protocol.
    _cached_parse_function = _cached_validation  # type: ignore[assignment]

    return wrapper


# Performance monitoring utilities
class PerformanceTimer:
    """Simple performance timer for benchmarking."""

    def __init__(self, name: str):
        self.name = name
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

    def __enter__(self):
        import time

        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        import time

        self.end_time = time.perf_counter()
        # Ensure start_time and end_time are not None before subtraction
        if self.start_time is not None and self.end_time is not None:
            duration = self.end_time - self.start_time
            logger.info(f"Performance [{self.name}]: {duration:.6f} seconds")
        else:
            logger.warning(
                f"PerformanceTimer '{self.name}' exited without proper start/end times."
            )

    @property
    def duration(self) -> float:
        """Get the duration in seconds."""
        if self.start_time is None or self.end_time is None:
            return 0.0
        # Type checker should now correctly infer float types here
        return self.end_time - self.start_time


def measure_performance(name: str):
    """Decorator to measure function performance."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with PerformanceTimer(name):
                return func(*args, **kwargs)

        return wrapper

    return decorator


# Memory optimization utilities
def optimize_message_validation(data: Dict[str, Any]) -> ValidationResult:
    """
    Optimized message validation function.

    This function applies various optimizations:
    - Fast path for common message types
    - Minimal object creation
    - Efficient error handling
    """
    # Fast path for common cancelled notifications
    if data.get("method") == "notifications/cancelled":
        # Basic structure validation
        if "params" in data and isinstance(data["params"], dict):
            params = data["params"]
            if "requestId" in params:
                # This is likely a valid cancelled notification
                try:
                    from .models.notifications import CancelledNotification

                    model = CancelledNotification.model_validate(data)
                    return ValidationResult(model=model, raw_data=data)
                except Exception as e:
                    logger.debug(f"Fast path validation failed: {e}")

    # Fall back to full validation
    from .models.validation import safe_parse_notification

    return safe_parse_notification(data)
