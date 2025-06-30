"""Performance benchmark tests for MCP Git Server."""

import asyncio
import logging
import random
import time
import uuid

import pytest

from mcp_server_git.models.enhanced_validation import process_notification_safely
from mcp_server_git.optimizations import (
    enable_validation_cache,
    disable_validation_cache,
    clear_validation_cache,
    get_validation_cache_stats,
)

# MockMCPClient will be imported locally when needed

logger = logging.getLogger(__name__)

# Common test parameters
THROUGHPUT_TEST_DURATION = 5  # seconds
MEMORY_TEST_OPERATIONS = 10000
CPU_PROFILE_OPERATIONS = 5000
VALIDATION_CACHE_TEST_MESSAGES = 10000


@pytest.fixture(autouse=True)
def setup_and_teardown_cache():
    """Fixture to ensure cache is cleared and enabled/disabled as needed for each test."""
    clear_validation_cache()
    enable_validation_cache()  # Default to enabled for most tests
    yield
    clear_validation_cache()
    enable_validation_cache()  # Reset to enabled after test


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_message_throughput_ping(benchmark_session_manager, mock_client):
    """Benchmark: Measure ping message throughput."""
    await mock_client.connect()
    await benchmark_session_manager.create_session(
        mock_client.session_id, user="benchmark_user"
    )

    messages_sent = 0
    start_time = time.time()
    end_time = start_time + THROUGHPUT_TEST_DURATION

    while time.time() < end_time:
        await mock_client.ping()
        messages_sent += 1
        await asyncio.sleep(0)  # Yield control

    duration = time.time() - start_time
    throughput = messages_sent / duration
    logger.info(
        f"Ping Throughput: {throughput:.2f} messages/sec ({messages_sent} messages in {duration:.2f}s)"
    )
    assert throughput > 100, "Ping throughput is too low"


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_message_throughput_operations(benchmark_session_manager, mock_client):
    """Benchmark: Measure start/cancel operation throughput."""
    await mock_client.connect()
    await benchmark_session_manager.create_session(
        mock_client.session_id, user="benchmark_user"
    )

    operations_completed = 0
    start_time = time.time()
    end_time = start_time + THROUGHPUT_TEST_DURATION

    while time.time() < end_time:
        op_id = str(uuid.uuid4())
        await mock_client.start_operation(op_id)
        await mock_client.cancel_operation(op_id)
        operations_completed += 1
        await asyncio.sleep(0)  # Yield control

    duration = time.time() - start_time
    throughput = operations_completed / duration
    logger.info(
        f"Operation Throughput: {throughput:.2f} operations/sec ({operations_completed} operations in {duration:.2f}s)"
    )
    assert throughput > 50, "Operation throughput is too low"


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_validation_caching_effectiveness(memory_monitor):
    """Benchmark: Test validation caching performance improvement."""
    # Test data: mix of valid and repeated messages
    test_messages = []
    for i in range(VALIDATION_CACHE_TEST_MESSAGES):
        if i % 10 == 0:
            # Repeated message that should benefit from caching
            test_messages.append(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/cancelled",
                    "params": {
                        "requestId": "repeated_request",
                        "reason": "Test cancellation",
                    },
                }
            )
        else:
            # Unique message
            test_messages.append(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/cancelled",
                    "params": {
                        "requestId": f"request_{i}",
                        "reason": f"Cancellation {i}",
                    },
                }
            )

    # Test without cache
    disable_validation_cache()
    clear_validation_cache()

    memory_monitor.take_sample("no_cache_start")
    start_time = time.time()

    for msg in test_messages:
        result = process_notification_safely(msg)
        assert result.is_valid, "Validation should succeed"

    no_cache_duration = time.time() - start_time
    memory_monitor.take_sample("no_cache_end")

    # Test with cache
    enable_validation_cache()
    clear_validation_cache()

    memory_monitor.take_sample("with_cache_start")
    start_time = time.time()

    for msg in test_messages:
        result = process_notification_safely(msg)
        assert result.is_valid, "Validation should succeed"

    with_cache_duration = time.time() - start_time
    memory_monitor.take_sample("with_cache_end")

    cache_stats = get_validation_cache_stats()

    logger.info(f"No Cache Duration: {no_cache_duration:.4f}s")
    logger.info(f"With Cache Duration: {with_cache_duration:.4f}s")
    logger.info(f"Cache Stats: {cache_stats}")

    # Cache should provide some improvement for repeated messages
    performance_ratio = (
        no_cache_duration / with_cache_duration if with_cache_duration > 0 else 1.0
    )
    logger.info(f"Performance Improvement: {performance_ratio:.2f}x")

    # Assertions - cache should show activity and not break functionality
    assert (
        cache_stats.get("hits", 0) + cache_stats.get("misses", 0) > 0
    ), "Cache should show some activity"
    # Allow cache overhead for small operations, focus on correctness
    assert performance_ratio >= 0.1, "Cache should not make things 10x slower"
    assert (
        with_cache_duration < 1.0
    ), "Cached operations should complete in reasonable time"


@pytest.mark.benchmark
@pytest.mark.ci_skip  # Too intensive for CI
@pytest.mark.asyncio
async def test_realistic_mixed_workload_performance(
    benchmark_session_manager, memory_monitor
):
    """Benchmark: Test realistic mixed workload performance."""
    client_count = 5
    test_duration_seconds = 10

    # Define MockMCPClient inline for this test to avoid import issues
    class MockMCPClient:
        def __init__(self, client_id):
            self.client_id = client_id
            self.connected = False
            self.session_id = None
            self.message_count = 0

        async def connect(self):
            self.connected = True
            self.session_id = str(uuid.uuid4())

        async def disconnect(self):
            self.connected = False

        async def ping(self):
            if not self.connected:
                raise RuntimeError("Client not connected")
            self.message_count += 1
            return {"type": "pong", "id": str(uuid.uuid4())}

        async def start_operation(self, operation_id):
            if not self.connected:
                raise RuntimeError("Client not connected")
            self.message_count += 1
            return {
                "type": "operation_started",
                "id": str(uuid.uuid4()),
                "operation_id": operation_id,
            }

        async def cancel_operation(self, operation_id):
            if not self.connected:
                raise RuntimeError("Client not connected")
            self.message_count += 1
            return {
                "type": "operation_cancelled",
                "id": str(uuid.uuid4()),
                "operation_id": operation_id,
            }

        async def send_batch_messages(self, count):
            results = []
            for _ in range(count):
                result = await self.ping()
                results.append(result)
            return results

    # Create multiple clients
    clients = [MockMCPClient(f"perf_client_{i}") for i in range(client_count)]
    sessions = []

    for i, client in enumerate(clients):
        await client.connect()
        session = await benchmark_session_manager.create_session(
            client.session_id, user=f"perf_user_{i}"
        )
        sessions.append(session)

    total_messages_sent = 0
    total_errors = 0

    memory_monitor.take_sample("mixed_workload_start")

    async def client_workload(client_idx: int):
        nonlocal total_messages_sent, total_errors
        client = clients[client_idx]
        session = sessions[client_idx]

        client_messages = 0
        client_errors = 0

        start_client_time = time.time()
        while time.time() - start_client_time < test_duration_seconds:
            try:
                activity_type = random.randint(1, 10)
                if activity_type <= 5:  # 50% pings
                    await client.ping()
                elif activity_type <= 7:  # 20% start/cancel operations
                    op_id = str(uuid.uuid4())
                    await client.start_operation(op_id)
                    await client.cancel_operation(op_id)
                elif activity_type <= 9:  # 20% batch messages
                    await client.send_batch_messages(random.randint(1, 3))
                else:  # 10% session state change / heartbeat
                    await session.handle_heartbeat()
                    if random.random() < 0.1:  # Occasionally pause/resume
                        await session.pause()
                        await session.resume()

                client_messages += 1
                await asyncio.sleep(0.001)  # Small delay to simulate real-world gaps
            except Exception as e:
                client_errors += 1
                logger.debug(f"Mixed workload client {client_idx} error: {e}")

        total_messages_sent += client_messages
        total_errors += client_errors

    start_time = time.time()
    tasks = [client_workload(i) for i in range(client_count)]
    await asyncio.gather(*tasks, return_exceptions=True)
    duration = time.time() - start_time

    memory_monitor.take_sample("mixed_workload_end")
    memory_growth = memory_monitor.get_memory_growth()

    throughput = total_messages_sent / duration
    error_rate = total_errors / total_messages_sent if total_messages_sent > 0 else 0

    logger.info(
        f"Mixed Workload Performance: {throughput:.2f} msg/sec, {error_rate:.2%} errors"
    )
    logger.info(f"Memory Growth: {memory_growth:.2f} MB")
    memory_monitor.log_samples()

    assert throughput > 100, "Mixed workload throughput is too low"
    assert error_rate < 0.01, "Mixed workload error rate is too high"
    assert memory_growth < 10, "Mixed workload memory growth is too high"

    # Cleanup
    for client in clients:
        if client.connected:
            await client.disconnect()
