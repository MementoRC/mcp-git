"""Memory leak detection tests for MCP Git Server."""

import asyncio
import gc
import logging
import random
import time
import uuid

import pytest

from mcp_server_git.session import SessionState


logger = logging.getLogger(__name__)


@pytest.mark.stress
@pytest.mark.asyncio
async def test_memory_leak_detection_extended_operations(
    stress_session_manager, mock_client, memory_monitor, stress_test_config
):
    """
    Test for memory leaks during extended operation cycles.

    Performs a large number of operations while monitoring memory usage
    to detect potential leaks in session management, message processing,
    or resource cleanup.
    """
    config = stress_test_config["memory"]
    operation_count = 50000  # Large number of operations
    sample_interval = config["sample_interval"]
    max_growth_mb = config["max_growth_mb"]
    max_slope = config["max_slope"]

    # Get baseline memory
    initial_memory = memory_monitor.take_sample("baseline")
    logger.info(f"Starting memory leak test with {operation_count} operations")
    logger.info(f"Initial memory: {initial_memory:.2f} MB")

    await mock_client.connect()
    session = await stress_session_manager.create_session(
        mock_client.session_id, user="memory_test_user"
    )

    try:
        for i in range(operation_count):
            # Mix of different operations to stress different code paths
            operation_type = i % 6

            if operation_type == 0:
                # Standard ping
                await mock_client.ping()
                await session.handle_heartbeat()

            elif operation_type == 1:
                # Start and immediately cancel operation
                op_id = str(uuid.uuid4())
                await mock_client.start_operation(op_id)
                await mock_client.cancel_operation(op_id)

            elif operation_type == 2:
                # Batch operations
                await mock_client.send_batch_messages(5)

            elif operation_type == 3:
                # Session state changes
                if session.state == SessionState.ACTIVE:
                    await session.pause()
                    await session.resume()

            elif operation_type == 4:
                # Error scenarios (should not leak memory)
                try:
                    await mock_client.send_invalid_message()
                except Exception:
                    pass  # Expected

            else:
                # Brief idle with cleanup opportunity
                gc.collect()  # Give garbage collector a chance
                await asyncio.sleep(0.001)

            # Take memory samples at intervals
            if i % sample_interval == 0 and i > 0:
                current_memory = memory_monitor.take_sample(f"operation_{i}")

                if i % (sample_interval * 10) == 0:
                    memory_growth = memory_monitor.get_memory_growth()
                    logger.info(f"Progress: {i}/{operation_count} operations")
                    logger.info(f"Current memory: {current_memory:.2f} MB")
                    logger.info(f"Memory growth: {memory_growth:.2f} MB")

                    # Early warning if memory growth is excessive
                    if memory_growth > max_growth_mb * 2:
                        logger.warning(
                            f"High memory growth detected: {memory_growth:.2f} MB"
                        )

    finally:
        # Cleanup
        if mock_client.connected:
            await mock_client.disconnect()
        if session and not session.is_closed:
            await stress_session_manager.close_session(session.session_id)

    # Final cleanup and measurement
    gc.collect()
    await asyncio.sleep(0.5)  # Allow async cleanup
    gc.collect()

    final_memory = memory_monitor.take_sample("final_after_cleanup")

    # Analysis
    memory_growth = memory_monitor.get_memory_growth()
    memory_slope = memory_monitor.get_memory_slope()

    logger.info("Memory leak test completed:")
    logger.info(f"Operations completed: {operation_count}")
    logger.info(f"Initial memory: {initial_memory:.2f} MB")
    logger.info(f"Final memory: {final_memory:.2f} MB")
    logger.info(f"Total growth: {memory_growth:.2f} MB")
    logger.info(f"Growth slope: {memory_slope:.6f} MB/sample")

    # Log memory samples for analysis
    memory_monitor.log_samples()

    # Assertions
    assert (
        memory_growth < max_growth_mb
    ), f"Memory growth exceeds limit: {memory_growth:.2f} MB > {max_growth_mb} MB"

    assert (
        abs(memory_slope) < max_slope
    ), f"Memory leak detected: slope={memory_slope:.6f} > {max_slope}"

    logger.info("✅ No memory leaks detected")


@pytest.mark.stress
@pytest.mark.asyncio
async def test_session_creation_destruction_memory(
    stress_session_manager, memory_monitor, stress_test_config
):
    """Test memory usage during rapid session creation and destruction."""

    session_cycles = 5000
    sessions_per_cycle = 20

    memory_monitor.take_sample("session_test_start")
    logger.info(f"Testing {session_cycles} session creation/destruction cycles")
    logger.info(f"Sessions per cycle: {sessions_per_cycle}")

    for cycle in range(session_cycles):
        # Create multiple sessions
        sessions = []
        for i in range(sessions_per_cycle):
            session_id = f"session_{cycle}_{i}"
            session = await stress_session_manager.create_session(
                session_id, user=f"user_{cycle}_{i}"
            )
            sessions.append(session)

            # Brief activity
            await session.handle_heartbeat()

        # Destroy all sessions
        for session in sessions:
            await stress_session_manager.close_session(session.session_id)

        # Clear references
        sessions.clear()

        # Periodic memory monitoring
        if cycle % 100 == 0:
            gc.collect()
            current_memory = memory_monitor.take_sample(f"cycle_{cycle}")

            if cycle % 500 == 0:
                memory_growth = memory_monitor.get_memory_growth()
                logger.info(
                    f"Cycle {cycle}/{session_cycles}: {current_memory:.2f} MB "
                    f"(growth: {memory_growth:.2f} MB)"
                )

    # Final cleanup and measurement
    gc.collect()
    await asyncio.sleep(0.5)
    gc.collect()

    memory_monitor.take_sample("session_test_end")
    memory_growth = memory_monitor.get_memory_growth()
    memory_slope = memory_monitor.get_memory_slope()

    # Check final session manager state
    final_sessions = await stress_session_manager.get_all_sessions()

    logger.info("Session memory test completed:")
    logger.info(f"Total session cycles: {session_cycles}")
    logger.info(f"Total sessions created: {session_cycles * sessions_per_cycle}")
    logger.info(f"Memory growth: {memory_growth:.2f} MB")
    logger.info(f"Memory slope: {memory_slope:.6f} MB/sample")
    logger.info(f"Remaining sessions: {len(final_sessions)}")

    # Assertions
    assert memory_growth < 30, f"Session memory growth too high: {memory_growth:.2f} MB"
    assert abs(memory_slope) < 0.1, f"Session memory leak: slope={memory_slope:.6f}"
    assert (
        len(final_sessions) == 0
    ), f"Sessions not properly cleaned up: {len(final_sessions)}"

    logger.info("✅ Session memory management verified")


@pytest.mark.stress
@pytest.mark.asyncio
async def test_resource_cleanup_after_errors(
    stress_session_manager, mock_client, memory_monitor
):
    """Test that resources are properly cleaned up after various error scenarios."""

    error_cycles = 1000
    memory_monitor.take_sample("error_cleanup_start")

    logger.info(f"Testing resource cleanup through {error_cycles} error scenarios")

    await mock_client.connect()

    for cycle in range(error_cycles):
        # Create session
        session_id = f"error_session_{cycle}"
        session = await stress_session_manager.create_session(
            session_id, user=f"error_user_{cycle}"
        )

        # Generate various error scenarios
        error_type = cycle % 5

        try:
            if error_type == 0:
                # Invalid message
                await mock_client.send_invalid_message()
            elif error_type == 1:
                # Malformed operation
                await mock_client.send_raw_message({"invalid": "message"})
            elif error_type == 2:
                # Force session error state
                # Simulate by directly changing session state
                session.state = SessionState.ERROR
                await session.handle_heartbeat()
            elif error_type == 3:
                # Client disconnect during operation
                op_id = str(uuid.uuid4())
                await mock_client.start_operation(op_id)
                await mock_client.disconnect()
                await mock_client.connect()
            else:
                # Timeout simulation
                await session.pause()
                await asyncio.sleep(0.01)
                await session.resume()

        except Exception:
            # Errors are expected
            pass

        # Clean up session
        try:
            await stress_session_manager.close_session(session.session_id)
        except Exception:
            pass

        # Periodic memory check
        if cycle % 100 == 0:
            gc.collect()
            current_memory = memory_monitor.take_sample(f"error_cycle_{cycle}")

            if cycle % 200 == 0:
                memory_growth = memory_monitor.get_memory_growth()
                logger.info(
                    f"Error cycle {cycle}/{error_cycles}: {current_memory:.2f} MB "
                    f"(growth: {memory_growth:.2f} MB)"
                )

    # Final cleanup
    if mock_client.connected:
        await mock_client.disconnect()

    gc.collect()
    await asyncio.sleep(0.5)
    gc.collect()

    memory_monitor.take_sample("error_cleanup_end")
    memory_growth = memory_monitor.get_memory_growth()

    # Check system state
    final_sessions = await stress_session_manager.get_all_sessions()

    logger.info("Error cleanup test completed:")
    logger.info(f"Error cycles completed: {error_cycles}")
    logger.info(f"Memory growth: {memory_growth:.2f} MB")
    logger.info(f"Remaining sessions: {len(final_sessions)}")

    # Assertions - errors should not cause memory leaks
    assert (
        memory_growth < 20
    ), f"Error scenarios caused memory leak: {memory_growth:.2f} MB"
    assert (
        len(final_sessions) <= 1
    ), f"Error scenarios left sessions: {len(final_sessions)}"

    logger.info("✅ Resource cleanup after errors verified")


@pytest.mark.stress
@pytest.mark.asyncio
async def test_garbage_collection_effectiveness(
    stress_session_manager, mock_client, memory_monitor
):
    """Test that garbage collection effectively reclaims memory."""

    # Allocate significant resources
    initial_memory = memory_monitor.take_sample("gc_test_start")
    logger.info("Testing garbage collection effectiveness")

    await mock_client.connect()

    # Create many objects that should be garbage collected
    large_objects = []
    sessions = []

    for i in range(5000):
        # Create session with data
        session = await stress_session_manager.create_session(
            f"gc_session_{i}", user=f"gc_user_{i}"
        )
        sessions.append(session)

        # Create some large temporary objects
        large_data = {
            "data": "x" * 10000,  # 10KB per object
            "id": i,
            "metadata": {"created": time.time(), "purpose": "gc_test"},
            "extra_data": ["x" * 1000 for _ in range(10)],  # Additional 10KB
        }
        large_objects.append(large_data)

        # Some activity
        await session.handle_heartbeat()
        await mock_client.ping()

    # Memory should have grown
    peak_memory = memory_monitor.take_sample("gc_test_peak")

    # Clear references to enable garbage collection
    for session in sessions:
        await session.close()

    sessions.clear()
    large_objects.clear()

    if mock_client.connected:
        await mock_client.disconnect()

    # Force garbage collection
    for _ in range(3):
        gc.collect()
        await asyncio.sleep(0.1)

    # Memory should have decreased significantly
    post_gc_memory = memory_monitor.take_sample("gc_test_post_gc")

    initial_to_peak = peak_memory - initial_memory
    peak_to_post_gc = peak_memory - post_gc_memory
    gc_efficiency = peak_to_post_gc / initial_to_peak if initial_to_peak > 0 else 0

    logger.info("Garbage collection test completed:")
    logger.info(f"Initial memory: {initial_memory:.2f} MB")
    logger.info(f"Peak memory: {peak_memory:.2f} MB")
    logger.info(f"Post-GC memory: {post_gc_memory:.2f} MB")
    logger.info(f"Memory growth: {initial_to_peak:.2f} MB")
    logger.info(f"Memory reclaimed: {peak_to_post_gc:.2f} MB")
    logger.info(f"GC efficiency: {gc_efficiency:.2%}")

    # Assertions
    assert initial_to_peak > 5, "Test did not allocate enough memory to be meaningful"
    assert gc_efficiency > 0.7, f"Garbage collection not effective: {gc_efficiency:.2%}"
    assert post_gc_memory < peak_memory, "Garbage collection did not reclaim any memory"

    logger.info("✅ Garbage collection effectiveness verified")


@pytest.mark.stress
@pytest.mark.asyncio
async def test_long_term_memory_stability(
    stress_session_manager, multiple_mock_clients, memory_monitor, stress_test_config
):
    """Test memory stability over extended periods with realistic usage patterns."""

    config = stress_test_config["memory"]
    duration_minutes = min(config.get("stability_duration_minutes", 20), 20)

    memory_monitor.take_sample("stability_start")
    logger.info(f"Testing memory stability for {duration_minutes} minutes")

    # Connect multiple clients
    for client in multiple_mock_clients[:5]:  # Use 5 clients
        await client.connect()

    # Create sessions for each client
    sessions = []
    for i, client in enumerate(multiple_mock_clients[:5]):
        session = await stress_session_manager.create_session(
            client.session_id, user=f"stability_user_{i}"
        )
        sessions.append(session)

    start_time = time.time()
    end_time = start_time + (duration_minutes * 60)

    try:
        iteration = 0
        while time.time() < end_time:
            iteration += 1

            # Realistic usage pattern
            client_idx = iteration % len(multiple_mock_clients[:5])
            client = multiple_mock_clients[client_idx]
            session = sessions[client_idx]

            activity_type = iteration % 10

            if activity_type < 6:
                # Normal operations (60%)
                await client.ping()
                await session.handle_heartbeat()
            elif activity_type < 8:
                # Batch processing (20%)
                await client.send_batch_messages(random.randint(3, 8))
            elif activity_type < 9:
                # Operation lifecycle (10%)
                op_id = str(uuid.uuid4())
                await client.start_operation(op_id)
                if random.random() < 0.5:
                    await asyncio.sleep(random.uniform(0.01, 0.1))
                    await client.cancel_operation(op_id)
            else:
                # Client reconnection (10%)
                await client.disconnect()
                await asyncio.sleep(random.uniform(0.1, 0.5))
                await client.connect()

                # Update session
                await stress_session_manager.close_session(session.session_id)
                session = await stress_session_manager.create_session(
                    client.session_id, user=f"stability_user_{client_idx}"
                )
                sessions[client_idx] = session

            # Memory monitoring
            if iteration % 1000 == 0:
                current_memory = memory_monitor.take_sample(f"stability_{iteration}")
                elapsed_minutes = (time.time() - start_time) / 60

                logger.info(
                    f"Stability test: {elapsed_minutes:.1f}/{duration_minutes} minutes"
                )
                logger.info(f"Memory: {current_memory:.2f} MB, Iteration: {iteration}")

                # Check for gradual leaks
                memory_growth = memory_monitor.get_memory_growth()
                if memory_growth > 100:  # More than 100MB growth
                    logger.warning(f"High memory growth: {memory_growth:.2f} MB")

            await asyncio.sleep(0.001)  # Small delay

    finally:
        # Cleanup all clients and sessions
        for client in multiple_mock_clients[:5]:
            if client.connected:
                await client.disconnect()

        for session in sessions:
            if session and not session.is_closed:
                await stress_session_manager.close_session(session.session_id)

    # Final memory measurement
    gc.collect()
    memory_monitor.take_sample("stability_end")

    memory_growth = memory_monitor.get_memory_growth()
    memory_slope = memory_monitor.get_memory_slope()
    actual_duration = (time.time() - start_time) / 60

    logger.info("Long-term stability test completed:")
    logger.info(f"Duration: {actual_duration:.2f} minutes")
    logger.info(f"Iterations: {iteration}")
    logger.info(f"Memory growth: {memory_growth:.2f} MB")
    logger.info(f"Memory slope: {memory_slope:.6f} MB/sample")

    # Stability assertions
    assert (
        memory_growth < 75
    ), f"Long-term memory growth too high: {memory_growth:.2f} MB"
    assert (
        abs(memory_slope) < 0.2
    ), f"Memory instability detected: slope={memory_slope:.6f}"

    logger.info("✅ Long-term memory stability verified")
