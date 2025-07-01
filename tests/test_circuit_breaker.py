"""Tests for circuit breaker pattern implementation."""

import asyncio
import logging
import pytest
import time

from mcp_server_git.error_handling import (
    CircuitState,
    CircuitBreaker,
    CircuitOpenError,
    with_circuit_breaker,
    get_circuit_breaker,
    get_all_circuit_breakers,
    reset_circuit_breaker,
    reset_all_circuit_breakers,
    remove_circuit_breaker,
    clear_circuit_breakers,
)


class TestCircuitBreaker:
    """Test CircuitBreaker class functionality."""

    def setup_method(self):
        """Reset circuit breakers before each test."""
        clear_circuit_breakers()

    def test_circuit_breaker_creation(self):
        """Test creating a circuit breaker with various parameters."""
        circuit = CircuitBreaker(
            name="test-circuit",
            failure_threshold=3,
            recovery_timeout=60.0,
            half_open_max_calls=2,
        )

        assert circuit.name == "test-circuit"
        assert circuit.failure_threshold == 3
        assert circuit.recovery_timeout == 60.0
        assert circuit.half_open_max_calls == 2
        assert circuit.state == CircuitState.CLOSED
        assert circuit.failure_count == 0
        assert circuit._total_requests == 0

    def test_circuit_breaker_defaults(self):
        """Test circuit breaker with default values."""
        circuit = CircuitBreaker("default-circuit")

        assert circuit.name == "default-circuit"
        assert circuit.failure_threshold == 5
        assert circuit.recovery_timeout == 30.0
        assert circuit.half_open_max_calls == 1
        assert circuit.state == CircuitState.CLOSED

    def test_allow_request_closed_state(self):
        """Test that requests are allowed in CLOSED state."""
        circuit = CircuitBreaker("test-circuit")

        assert circuit.allow_request() is True
        assert circuit.state == CircuitState.CLOSED
        assert circuit._total_requests == 1

    def test_record_success_closed_state(self):
        """Test recording success in CLOSED state."""
        circuit = CircuitBreaker("test-circuit")

        circuit.record_success()

        assert circuit._successful_requests == 1
        assert circuit.failure_count == 0
        assert circuit.state == CircuitState.CLOSED

    def test_record_failure_closed_state(self):
        """Test recording failures in CLOSED state."""
        circuit = CircuitBreaker("test-circuit", failure_threshold=3)

        # Record failures but not enough to trip
        circuit.record_failure()
        circuit.record_failure()

        assert circuit.failure_count == 2
        assert circuit.state == CircuitState.CLOSED
        assert circuit._failed_requests == 2

    def test_circuit_trips_after_threshold(self):
        """Test that circuit trips to OPEN after failure threshold."""
        circuit = CircuitBreaker("test-circuit", failure_threshold=3)

        # Trip the circuit
        for _ in range(3):
            circuit.record_failure()

        assert circuit.state == CircuitState.OPEN
        assert circuit.failure_count == 3

    def test_circuit_open_rejects_requests(self):
        """Test that OPEN circuit rejects requests."""
        circuit = CircuitBreaker("test-circuit", failure_threshold=2)

        # Trip the circuit
        circuit.record_failure()
        circuit.record_failure()
        assert circuit.state == CircuitState.OPEN

        # Requests should be rejected
        assert circuit.allow_request() is False
        assert circuit._rejected_requests == 1

    def test_circuit_transitions_to_half_open(self):
        """Test transition from OPEN to HALF_OPEN after timeout."""
        circuit = CircuitBreaker(
            "test-circuit", failure_threshold=2, recovery_timeout=0.1
        )

        # Trip the circuit
        circuit.record_failure()
        circuit.record_failure()
        assert circuit.state == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(0.2)

        # Next request should transition to HALF_OPEN
        assert circuit.allow_request() is True
        assert circuit.state == CircuitState.HALF_OPEN

    def test_half_open_success_closes_circuit(self, caplog):
        """Test that success in HALF_OPEN state closes the circuit."""
        caplog.set_level(logging.INFO)

        circuit = CircuitBreaker(
            "test-circuit", failure_threshold=2, recovery_timeout=0.1
        )

        # Trip the circuit
        circuit.record_failure()
        circuit.record_failure()

        # Wait and transition to HALF_OPEN
        time.sleep(0.2)
        circuit.allow_request()
        assert circuit.state == CircuitState.HALF_OPEN

        # Success should close the circuit
        circuit.record_success()
        assert circuit.state == CircuitState.CLOSED
        assert circuit.failure_count == 0
        assert "closed after successful test" in caplog.text

    def test_half_open_failure_reopens_circuit(self, caplog):
        """Test that failure in HALF_OPEN state reopens the circuit."""
        caplog.set_level(logging.WARNING)

        circuit = CircuitBreaker(
            "test-circuit", failure_threshold=2, recovery_timeout=0.1
        )

        # Trip the circuit
        circuit.record_failure()
        circuit.record_failure()

        # Wait and transition to HALF_OPEN
        time.sleep(0.2)
        circuit.allow_request()
        assert circuit.state == CircuitState.HALF_OPEN

        # Failure should reopen the circuit
        circuit.record_failure()
        assert circuit.state == CircuitState.OPEN
        assert "reopened after test failure" in caplog.text

    def test_half_open_max_calls_limit(self):
        """Test that HALF_OPEN state limits number of calls."""
        circuit = CircuitBreaker(
            "test-circuit",
            failure_threshold=2,
            recovery_timeout=0.1,
            half_open_max_calls=2,
        )

        # Trip the circuit
        circuit.record_failure()
        circuit.record_failure()

        # Wait and transition to HALF_OPEN
        time.sleep(0.2)

        # First two calls should be allowed
        assert circuit.allow_request() is True
        assert circuit.allow_request() is True

        # Third call should be rejected
        assert circuit.allow_request() is False
        assert circuit._rejected_requests == 1

    def test_circuit_reset(self, caplog):
        """Test resetting a circuit breaker."""
        caplog.set_level(logging.INFO)

        circuit = CircuitBreaker("test-circuit", failure_threshold=2)

        # Trip the circuit
        circuit.record_failure()
        circuit.record_failure()
        assert circuit.state == CircuitState.OPEN

        # Reset the circuit
        circuit.reset()

        assert circuit.state == CircuitState.CLOSED
        assert circuit.failure_count == 0
        assert circuit.last_failure_time == 0.0
        assert circuit.half_open_calls == 0
        assert "reset to CLOSED state" in caplog.text

    def test_circuit_statistics(self):
        """Test circuit breaker statistics calculation."""
        circuit = CircuitBreaker("test-circuit")

        # Generate some activity
        circuit.allow_request()  # 1 total
        circuit.record_success()  # 1 success

        circuit.allow_request()  # 2 total
        circuit.record_failure()  # 1 failure

        stats = circuit.get_stats()

        assert stats["name"] == "test-circuit"
        assert stats["state"] == "closed"
        assert stats["total_requests"] == 2
        assert stats["successful_requests"] == 1
        assert stats["failed_requests"] == 1
        assert stats["rejected_requests"] == 0
        assert stats["failure_rate"] == 0.5
        assert stats["success_rate"] == 0.5

    def test_failure_rate_calculation(self):
        """Test failure rate calculation with various scenarios."""
        circuit = CircuitBreaker("test-circuit")

        # No requests yet
        assert circuit.failure_rate == 0.0
        assert circuit.success_rate == 0.0

        # All successes (need to simulate real requests with allow_request)
        circuit.allow_request()  # 1 total
        circuit.record_success()  # 1 success
        circuit.allow_request()  # 2 total
        circuit.record_success()  # 2 success

        assert circuit.failure_rate == 0.0  # 0 failures / 2 total
        assert circuit.success_rate == 1.0  # 2 successes / 2 total

        # Mix of success and failure
        circuit.allow_request()  # 3 total
        circuit.record_failure()  # 1 failure

        assert circuit.failure_rate == pytest.approx(
            0.333, rel=1e-2
        )  # 1 failure / 3 total
        assert circuit.success_rate == pytest.approx(
            0.667, rel=1e-2
        )  # 2 successes / 3 total


class TestCircuitBreakerDecorator:
    """Test the @with_circuit_breaker decorator."""

    def setup_method(self):
        """Reset circuit breakers before each test."""
        clear_circuit_breakers()

    @pytest.mark.asyncio
    async def test_async_decorator_success(self):
        """Test decorator with successful async function."""
        circuit = CircuitBreaker("test-circuit")

        @with_circuit_breaker(circuit)
        async def test_func():
            return "success"

        result = await test_func()
        assert result == "success"
        assert circuit._successful_requests == 1
        assert circuit.state == CircuitState.CLOSED

    def test_sync_decorator_success(self):
        """Test decorator with successful sync function."""
        circuit = CircuitBreaker("test-circuit")

        @with_circuit_breaker(circuit)
        def test_func():
            return "success"

        result = test_func()
        assert result == "success"
        assert circuit._successful_requests == 1

    @pytest.mark.asyncio
    async def test_async_decorator_failure(self):
        """Test decorator with failing async function."""
        circuit = CircuitBreaker("test-circuit", failure_threshold=2)

        @with_circuit_breaker(circuit)
        async def test_func():
            raise ValueError("test error")

        # First failure
        with pytest.raises(ValueError):
            await test_func()

        assert circuit.failure_count == 1
        assert circuit.state == CircuitState.CLOSED

        # Second failure trips circuit
        with pytest.raises(ValueError):
            await test_func()

        assert circuit.failure_count == 2
        assert circuit.state == CircuitState.OPEN

    def test_sync_decorator_failure(self):
        """Test decorator with failing sync function."""
        circuit = CircuitBreaker("test-circuit", failure_threshold=2)

        @with_circuit_breaker(circuit)
        def test_func():
            raise ValueError("test error")

        # First failure
        with pytest.raises(ValueError):
            test_func()

        # Second failure trips circuit
        with pytest.raises(ValueError):
            test_func()

        assert circuit.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_async_decorator_circuit_open(self):
        """Test decorator behavior when circuit is open."""
        circuit = CircuitBreaker("test-circuit", failure_threshold=1)

        @with_circuit_breaker(circuit)
        async def test_func():
            raise ValueError("test error")

        # Trip the circuit
        with pytest.raises(ValueError):
            await test_func()

        assert circuit.state == CircuitState.OPEN

        # Next call should raise CircuitOpenError
        with pytest.raises(CircuitOpenError, match="Circuit test-circuit is open"):
            await test_func()

    def test_sync_decorator_circuit_open(self):
        """Test sync decorator behavior when circuit is open."""
        circuit = CircuitBreaker("test-circuit", failure_threshold=1)

        @with_circuit_breaker(circuit)
        def test_func():
            raise ValueError("test error")

        # Trip the circuit
        with pytest.raises(ValueError):
            test_func()

        # Next call should raise CircuitOpenError
        with pytest.raises(CircuitOpenError):
            test_func()


class TestCircuitBreakerRegistry:
    """Test circuit breaker registry functions."""

    def setup_method(self):
        """Reset circuit breakers before each test."""
        clear_circuit_breakers()

    def test_get_circuit_breaker_creates_new(self):
        """Test that get_circuit_breaker creates new circuit if it doesn't exist."""
        circuit = get_circuit_breaker("new-circuit", failure_threshold=10)

        assert circuit.name == "new-circuit"
        assert circuit.failure_threshold == 10

    def test_get_circuit_breaker_returns_existing(self):
        """Test that get_circuit_breaker returns existing circuit."""
        circuit1 = get_circuit_breaker("existing-circuit")
        circuit2 = get_circuit_breaker("existing-circuit")

        assert circuit1 is circuit2
        assert circuit1.name == "existing-circuit"

    def test_get_all_circuit_breakers(self):
        """Test getting all circuit breakers."""
        circuit1 = get_circuit_breaker("circuit-1")
        circuit2 = get_circuit_breaker("circuit-2")

        all_circuits = get_all_circuit_breakers()

        assert len(all_circuits) == 2
        assert "circuit-1" in all_circuits
        assert "circuit-2" in all_circuits
        assert all_circuits["circuit-1"] is circuit1
        assert all_circuits["circuit-2"] is circuit2

    def test_reset_circuit_breaker(self):
        """Test resetting a specific circuit breaker."""
        circuit = get_circuit_breaker("reset-test", failure_threshold=2)

        # Trip the circuit
        circuit.record_failure()
        circuit.record_failure()
        assert circuit.state == CircuitState.OPEN

        # Reset using registry function
        result = reset_circuit_breaker("reset-test")

        assert result is True
        assert circuit.state == CircuitState.CLOSED
        assert circuit.failure_count == 0

    def test_reset_nonexistent_circuit_breaker(self):
        """Test resetting a non-existent circuit breaker."""
        result = reset_circuit_breaker("nonexistent")
        assert result is False

    def test_reset_all_circuit_breakers(self):
        """Test resetting all circuit breakers."""
        circuit1 = get_circuit_breaker("circuit-1", failure_threshold=1)
        circuit2 = get_circuit_breaker("circuit-2", failure_threshold=1)

        # Trip both circuits
        circuit1.record_failure()
        circuit2.record_failure()

        assert circuit1.state == CircuitState.OPEN
        assert circuit2.state == CircuitState.OPEN

        # Reset all
        reset_all_circuit_breakers()

        assert circuit1.state == CircuitState.CLOSED
        assert circuit2.state == CircuitState.CLOSED

    def test_remove_circuit_breaker(self):
        """Test removing a circuit breaker from registry."""
        get_circuit_breaker("remove-test")
        assert "remove-test" in get_all_circuit_breakers()

        result = remove_circuit_breaker("remove-test")

        assert result is True
        assert "remove-test" not in get_all_circuit_breakers()

    def test_remove_nonexistent_circuit_breaker(self):
        """Test removing a non-existent circuit breaker."""
        result = remove_circuit_breaker("nonexistent")
        assert result is False

    def test_clear_circuit_breakers(self):
        """Test clearing all circuit breakers."""
        get_circuit_breaker("circuit-1")
        get_circuit_breaker("circuit-2")

        assert len(get_all_circuit_breakers()) == 2

        clear_circuit_breakers()

        assert len(get_all_circuit_breakers()) == 0


class TestCircuitBreakerIntegration:
    """Test circuit breaker integration scenarios."""

    def setup_method(self):
        """Reset circuit breakers before each test."""
        clear_circuit_breakers()

    @pytest.mark.asyncio
    async def test_multiple_concurrent_requests(self):
        """Test circuit breaker with concurrent requests."""
        circuit = CircuitBreaker("concurrent-test", failure_threshold=3)

        @with_circuit_breaker(circuit)
        async def test_func(should_fail=False):
            if should_fail:
                raise ValueError("test error")
            return "success"

        # Run concurrent successful requests
        tasks = [test_func() for _ in range(5)]
        results = await asyncio.gather(*tasks)

        assert all(result == "success" for result in results)
        assert circuit._successful_requests == 5
        assert circuit.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_recovery_after_timeout(self):
        """Test circuit recovery after timeout period."""
        circuit = CircuitBreaker(
            "recovery-test", failure_threshold=2, recovery_timeout=0.1
        )

        @with_circuit_breaker(circuit)
        async def test_func(should_fail=False):
            if should_fail:
                raise ValueError("test error")
            return "success"

        # Trip the circuit
        with pytest.raises(ValueError):
            await test_func(should_fail=True)
        with pytest.raises(ValueError):
            await test_func(should_fail=True)

        assert circuit.state == CircuitState.OPEN

        # Requests should be rejected
        with pytest.raises(CircuitOpenError):
            await test_func()

        # Wait for recovery timeout
        time.sleep(0.2)

        # Next request should succeed and close circuit
        result = await test_func(should_fail=False)
        assert result == "success"
        assert circuit.state == CircuitState.CLOSED

    def test_circuit_breaker_with_different_error_types(self):
        """Test circuit breaker behavior with different error types."""
        circuit = CircuitBreaker("error-types-test", failure_threshold=3)

        @with_circuit_breaker(circuit)
        def test_func(error_type):
            if error_type == "value":
                raise ValueError("value error")
            elif error_type == "runtime":
                raise RuntimeError("runtime error")
            elif error_type == "type":
                raise TypeError("type error")
            return "success"

        # Different error types should all count as failures
        with pytest.raises(ValueError):
            test_func("value")

        with pytest.raises(RuntimeError):
            test_func("runtime")

        with pytest.raises(TypeError):
            test_func("type")

        assert circuit.state == CircuitState.OPEN
        assert circuit.failure_count == 3

    def test_circuit_statistics_comprehensive(self):
        """Test comprehensive circuit statistics tracking."""
        circuit = CircuitBreaker("stats-test", failure_threshold=3)

        # Simulate various operations
        circuit.allow_request()  # 1 total
        circuit.record_success()  # 1 success

        circuit.allow_request()  # 2 total
        circuit.record_failure()  # 1 failure

        circuit.allow_request()  # 3 total
        circuit.record_failure()  # 2 failures

        circuit.allow_request()  # 4 total
        circuit.record_failure()  # 3 failures (trips circuit)

        # Circuit should be open now
        assert circuit.state == CircuitState.OPEN

        # Try more requests (should be rejected)
        circuit.allow_request()  # 5 total, 1 rejected
        circuit.allow_request()  # 6 total, 2 rejected

        stats = circuit.get_stats()

        assert stats["total_requests"] == 6
        assert stats["successful_requests"] == 1
        assert stats["failed_requests"] == 3
        assert stats["rejected_requests"] == 2
        assert stats["failure_rate"] == 0.5  # 3 failures / 6 total
        assert stats["success_rate"] == pytest.approx(
            0.167, rel=1e-2
        )  # 1 success / 6 total
        assert stats["state"] == "open"
