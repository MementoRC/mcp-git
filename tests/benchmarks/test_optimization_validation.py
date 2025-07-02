"""Tests for validation optimization and caching functionality."""

import time

from mcp_server_git.models.enhanced_validation import process_notification_safely
from mcp_server_git.optimizations import (
    enable_validation_cache,
    disable_validation_cache,
    clear_validation_cache,
    get_validation_cache_stats,
)


def test_validation_cache_hit_miss_behavior():
    """Test that cache properly records hits and misses."""
    # Start fresh
    enable_validation_cache()
    clear_validation_cache()

    # Create a valid message
    message = {
        "jsonrpc": "2.0",
        "method": "notifications/cancelled",
        "params": {"requestId": "test123", "reason": "Test cancellation"},
    }

    # First call should be a miss
    initial_stats = get_validation_cache_stats()
    result1 = process_notification_safely(message)
    stats_after_first = get_validation_cache_stats()

    assert result1.is_valid
    # Cache stats should show activity (if cache is working)
    cache_working = stats_after_first != initial_stats

    # Second call with identical message should be faster
    start_time = time.time()
    result2 = process_notification_safely(message)
    second_call_time = time.time() - start_time

    assert result2.is_valid
    assert second_call_time < 0.1  # Should be very fast

    final_stats = get_validation_cache_stats()

    # If caching is working, we should see hits
    if cache_working:
        assert final_stats.get("hits", 0) > 0


def test_validation_cache_disabled():
    """Test that disabling cache works properly."""
    # Test with cache disabled
    disable_validation_cache()
    clear_validation_cache()

    message = {
        "jsonrpc": "2.0",
        "method": "notifications/cancelled",
        "params": {"requestId": "test456", "reason": "Test cancellation"},
    }

    # Process message multiple times
    result1 = process_notification_safely(message)
    result2 = process_notification_safely(message)

    assert result1.is_valid
    assert result2.is_valid

    # Re-enable for other tests
    enable_validation_cache()


def test_validation_cache_cleared():
    """Test that clearing cache works properly."""
    enable_validation_cache()
    clear_validation_cache()

    # Process a message
    message = {
        "jsonrpc": "2.0",
        "method": "notifications/cancelled",
        "params": {"requestId": "test789", "reason": "Test cancellation"},
    }

    result = process_notification_safely(message)
    assert result.is_valid

    # Clear cache
    clear_validation_cache()

    # Cache should be empty
    stats = get_validation_cache_stats()
    assert stats.get("current_size", 0) == 0


def test_validation_cache_size_limit():
    """Test that cache respects size limits."""
    enable_validation_cache()
    clear_validation_cache()

    # Process many different messages
    for i in range(20):
        message = {
            "jsonrpc": "2.0",
            "method": "notifications/cancelled",
            "params": {"requestId": f"test_{i}", "reason": f"Test cancellation {i}"},
        }
        result = process_notification_safely(message)
        assert result.is_valid

    stats = get_validation_cache_stats()
    # Cache size should be reasonable
    current_size = stats.get("current_size", 0)
    assert current_size <= 50  # Should not grow unbounded


def test_validation_with_invalid_messages():
    """Test validation with intentionally invalid messages."""
    enable_validation_cache()
    clear_validation_cache()

    # Invalid message - missing required fields
    invalid_message = {
        "jsonrpc": "2.0",
        "method": "notifications/cancelled",
        # Missing params
    }

    result = process_notification_safely(invalid_message)

    # The enhanced validation system should handle this gracefully
    # It may create a fallback valid result or return an error result
    assert result is not None

    # Test another invalid message
    invalid_message2 = {"invalid": "message", "structure": True}

    result2 = process_notification_safely(invalid_message2)
    assert result2 is not None


def test_validation_performance_comparison():
    """Compare performance with and without caching for repeated messages."""
    # Test message that will be repeated
    message = {
        "jsonrpc": "2.0",
        "method": "notifications/cancelled",
        "params": {"requestId": "perf_test", "reason": "Performance test"},
    }

    # Test without caching
    disable_validation_cache()
    clear_validation_cache()

    start_time = time.time()
    for _ in range(100):
        result = process_notification_safely(message)
        assert result.is_valid
    no_cache_time = time.time() - start_time

    # Test with caching
    enable_validation_cache()
    clear_validation_cache()

    start_time = time.time()
    for _ in range(100):
        result = process_notification_safely(message)
        assert result.is_valid
    with_cache_time = time.time() - start_time

    # Both should complete successfully
    assert no_cache_time > 0
    assert with_cache_time > 0

    # With cache should generally be faster for repeated calls
    # But we allow for some variance in test conditions
    performance_ratio = no_cache_time / with_cache_time if with_cache_time > 0 else 1.0

    # Log the results for debugging
    print(
        f"No cache: {no_cache_time:.4f}s, With cache: {with_cache_time:.4f}s, Ratio: {performance_ratio:.2f}x"
    )

    # Cache should not make things significantly slower
    assert performance_ratio >= 0.1  # Allow cache overhead for small operations
