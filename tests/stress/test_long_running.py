"""Long-running stability tests for MCP Git Server."""

import asyncio
import logging
import random
import time
import uuid
from datetime import datetime

import pytest


logger = logging.getLogger(__name__)


@pytest.mark.stress
@pytest.mark.ci_skip  # Skip this long test in CI
@pytest.mark.asyncio
@pytest.mark.timeout(3600)  # 1 hour timeout for safety
async def test_48_hour_stability_simulation(
    stress_session_manager,
    mock_client,
    stress_test_config,
    memory_monitor,
    metrics_collector,
):
    """
    Test server stability over a simulated 48-hour period.

    Uses time acceleration to complete in CI-friendly timeframe while
    maintaining realistic operation patterns and stress levels.
    """
    config = stress_test_config["long_running"]
    test_duration_hours = 48
    scaled_duration_minutes = config["duration_minutes"]

    # Scale factor for accelerated testing
    scale_factor = (test_duration_hours * 60) / scaled_duration_minutes

    # Connect client
    await mock_client.connect()

    # Create a session in the manager
    session = await stress_session_manager.create_session(
        mock_client.session_id, user="stress_test_user"
    )

    # Track metrics
    start_time = time.time()
    end_time = start_time + (scaled_duration_minutes * 60)
    operation_count = 0
    cancel_count = 0
    error_count = 0
    reconnection_count = 0

    # Take initial memory sample
    initial_memory = memory_monitor.take_sample("initial")

    logger.info(f"Starting {test_duration_hours}-hour stability test")
    logger.info(f"Scaled to {scaled_duration_minutes} minutes")
    logger.info(f"Start time: {datetime.now().isoformat()}")
    logger.info(f"Initial memory: {initial_memory:.2f} MB")

    try:
        iteration = 0
        while time.time() < end_time:
            iteration += 1

            # Simulate a mix of realistic operations
            operation_type = random.randint(1, 100)

            if operation_type <= 30:
                # Standard ping operations (30%)
                try:
                    await mock_client.ping()
                    await session.handle_heartbeat()
                except Exception as e:
                    error_count += 1
                    logger.warning(f"Ping failed: {e}")

            elif operation_type <= 50:
                # Start and potentially cancel operations (20%)
                op_id = str(uuid.uuid4())
                try:
                    await mock_client.start_operation(op_id)
                    operation_count += 1

                    # 40% chance to cancel after a brief delay
                    if random.random() < 0.4:
                        await asyncio.sleep(random.uniform(0.1, 1.0))
                        await mock_client.cancel_operation(op_id)
                        cancel_count += 1

                except Exception as e:
                    error_count += 1
                    logger.warning(f"Operation failed: {e}")

            elif operation_type <= 60:
                # Batch message processing (10%)
                try:
                    batch_size = random.randint(5, 20)
                    await mock_client.send_batch_messages(batch_size)
                except Exception as e:
                    error_count += 1
                    logger.warning(f"Batch processing failed: {e}")

            elif operation_type <= 70:
                # Simulate client reconnection (10%)
                try:
                    await mock_client.disconnect()
                    await asyncio.sleep(random.uniform(0.5, 2.0))
                    await mock_client.connect()

                    # Create new session after reconnection
                    await session.close()
                    session = await stress_session_manager.create_session(
                        mock_client.session_id, user="stress_test_user"
                    )
                    reconnection_count += 1

                except Exception as e:
                    error_count += 1
                    logger.warning(f"Reconnection failed: {e}")

            elif operation_type <= 80:
                # Deliberate error injection (10%)
                try:
                    await mock_client.send_invalid_message()
                except Exception:
                    # Expected to fail
                    pass

            else:
                # Idle periods (20%)
                await asyncio.sleep(random.uniform(0.1, 2.0))

            # Memory and progress monitoring
            if iteration % 100 == 0:
                current_memory = memory_monitor.take_sample(f"iteration_{iteration}")
                elapsed = time.time() - start_time
                simulated_hours = (elapsed / 60) * scale_factor / 60
                progress_percent = (elapsed / (scaled_duration_minutes * 60)) * 100

                logger.info(
                    f"Progress: {progress_percent:.1f}% ({simulated_hours:.2f} simulated hours)"
                )
                logger.info(f"Memory: {current_memory:.2f} MB")
                logger.info(
                    f"Stats - Operations: {operation_count}, Cancellations: {cancel_count}"
                )
                logger.info(
                    f"Stats - Errors: {error_count}, Reconnections: {reconnection_count}"
                )
                logger.info(f"Messages sent: {mock_client.message_count}")

                # Get session metrics
                session_metrics = session.get_metrics()
                logger.info(
                    f"Session metrics: active_time={session_metrics.get('uptime', 0):.1f}s"
                )

                # Check for memory growth issues
                memory_growth = memory_monitor.get_memory_growth()
                if memory_growth > 100:  # More than 100MB growth
                    logger.warning(
                        f"High memory growth detected: {memory_growth:.2f} MB"
                    )

            # Small delay between operations to prevent overwhelming
            await asyncio.sleep(0.01)

    finally:
        # Cleanup
        if mock_client.connected:
            await mock_client.disconnect()
        if session and not session.is_closed:
            await stress_session_manager.close_session(session.session_id)

    # Final memory sample and analysis
    memory_monitor.take_sample("final")
    memory_growth = memory_monitor.get_memory_growth()
    memory_slope = memory_monitor.get_memory_slope()

    # Log final statistics
    elapsed_real = time.time() - start_time
    simulated_hours = (elapsed_real / 60) * scale_factor / 60

    logger.info(f"Test completed at {datetime.now().isoformat()}")
    logger.info(f"Real duration: {elapsed_real / 60:.2f} minutes")
    logger.info(f"Simulated duration: {simulated_hours:.2f} hours")
    logger.info(f"Total operations: {operation_count}")
    logger.info(f"Total cancellations: {cancel_count}")
    logger.info(f"Total errors: {error_count}")
    logger.info(f"Total reconnections: {reconnection_count}")
    logger.info(f"Total messages: {mock_client.message_count}")
    logger.info(f"Memory growth: {memory_growth:.2f} MB")
    logger.info(f"Memory slope: {memory_slope:.6f} MB/sample")

    # Get final metrics from collector
    final_metrics = metrics_collector.get_stats()
    logger.info(f"Final system metrics: {final_metrics}")

    # Assertions for test success

    # Memory constraints
    assert memory_growth < 200, f"Excessive memory growth: {memory_growth:.2f} MB"
    assert abs(memory_slope) < 0.5, f"Memory leak detected: slope={memory_slope:.6f}"

    # Error rate should be reasonable
    total_operations = operation_count + mock_client.message_count
    if total_operations > 0:
        error_rate = error_count / total_operations
        assert error_rate < 0.05, f"Error rate too high: {error_rate:.2%}"

    # Should have completed significant work
    assert operation_count > 100, f"Too few operations completed: {operation_count}"
    assert (
        mock_client.message_count > 500
    ), f"Too few messages sent: {mock_client.message_count}"

    # Simulated time should be close to target
    assert (
        simulated_hours >= 40
    ), f"Test duration too short: {simulated_hours:.2f} hours"

    logger.info("✅ 48-hour stability test completed successfully")


@pytest.mark.stress
@pytest.mark.ci_skip  # Problematic in CI environment
@pytest.mark.asyncio
async def test_continuous_operation_under_load(
    stress_session_manager, mock_client, stress_test_config, memory_monitor
):
    """Minimal continuous operation test for CI."""

    config = stress_test_config["long_running"]
    import os

    is_ci = (
        os.getenv("CI", "false").lower() == "true"
        or os.getenv("GITHUB_ACTIONS", "false").lower() == "true"
        or os.getenv("PYTEST_CI", "false").lower() == "true"
    )
    # In CI, run for only 3 seconds, 1 message/sec
    duration_minutes = (
        0.05 if is_ci else min(config["duration_minutes"], 15)
    )  # 3 seconds
    message_rate = 1 if is_ci else config["message_rate"]

    await mock_client.connect()
    session = await stress_session_manager.create_session(
        mock_client.session_id, user="load_test_user"
    )

    start_time = time.time()
    end_time = start_time + (duration_minutes * 60)

    memory_monitor.take_sample("load_test_start")
    logger.info(
        f"Starting minimal continuous load test for {duration_minutes*60:.1f} seconds"
    )
    logger.info(f"Target rate: {message_rate} messages/second")

    message_count = 0
    error_count = 0

    try:
        if is_ci:
            # Extremely simple test for CI - just send a few messages quickly
            for _ in range(5):
                try:
                    await mock_client.ping()
                    message_count += 1
                    await session.handle_heartbeat()
                except Exception:
                    error_count += 1
                await asyncio.sleep(0.1)  # Small delay
        else:
            while time.time() < end_time:
                batch_start = time.time()

                for _ in range(message_rate):
                    try:
                        await mock_client.ping()
                        message_count += 1
                        if message_count % 5 == 0:
                            await session.handle_heartbeat()
                    except Exception:
                        error_count += 1

                batch_duration = time.time() - batch_start
                if batch_duration < 1.0:
                    await asyncio.sleep(1.0 - batch_duration)

    finally:
        if mock_client.connected:
            await mock_client.disconnect()
        if session and not session.is_closed:
            await stress_session_manager.close_session(session.session_id)

    memory_monitor.take_sample("load_test_end")
    actual_duration = time.time() - start_time
    actual_rate = message_count / actual_duration if actual_duration > 0 else 0
    memory_growth = memory_monitor.get_memory_growth()

    logger.info("Minimal load test completed:")
    logger.info(f"Duration: {actual_duration:.2f} seconds")
    logger.info(f"Messages sent: {message_count}")
    logger.info(f"Actual rate: {actual_rate:.2f} messages/second")
    logger.info(f"Error count: {error_count}")
    logger.info(f"Memory growth: {memory_growth:.2f} MB")

    # Minimal assertions for CI
    assert actual_rate >= 1, f"Rate too low: {actual_rate:.2f} < 1"
    error_rate = error_count / message_count if message_count > 0 else 0
    assert error_rate < 0.5, f"Error rate too high under load: {error_rate:.2%}"
    assert (
        memory_growth < 20
    ), f"Memory growth too high under load: {memory_growth:.2f} MB"

    logger.info("✅ Minimal continuous load test completed successfully")


@pytest.mark.stress
@pytest.mark.ci_skip  # Skip this intensive test in CI
@pytest.mark.asyncio
async def test_session_lifecycle_stress(stress_session_manager, stress_test_config):
    """Test rapid session creation and destruction."""

    import os

    is_ci = (
        os.getenv("CI", "false").lower() == "true"
        or os.getenv("GITHUB_ACTIONS", "false").lower() == "true"
        or os.getenv("PYTEST_CI", "false").lower() == "true"
    )
    session_count = 50 if is_ci else 1000
    concurrent_sessions = 5 if is_ci else 50

    logger.info(
        f"Testing {session_count} session lifecycles with {concurrent_sessions} concurrent"
    )

    created_sessions = []
    creation_errors = 0
    closure_errors = 0

    async def create_and_destroy_session(session_id: str):
        nonlocal creation_errors, closure_errors

        try:
            # Create session
            session = await stress_session_manager.create_session(
                session_id, user=f"user_{session_id}"
            )
            created_sessions.append(session)

            # Brief activity
            await session.handle_heartbeat()
            await asyncio.sleep(random.uniform(0.01, 0.1))

            # Close session through manager to ensure cleanup
            await stress_session_manager.close_session(session_id)

        except Exception as e:
            if "create" in str(e).lower():
                creation_errors += 1
            else:
                closure_errors += 1
            logger.warning(f"Session lifecycle error: {e}")

    # Run sessions in batches to control concurrency
    for batch_start in range(0, session_count, concurrent_sessions):
        batch_end = min(batch_start + concurrent_sessions, session_count)

        session_ids = [f"stress_session_{i}" for i in range(batch_start, batch_end)]

        tasks = [create_and_destroy_session(sid) for sid in session_ids]
        await asyncio.gather(*tasks, return_exceptions=True)

        if batch_start % 200 == 0:
            logger.info(f"Completed {batch_end}/{session_count} sessions")

            # Check manager state
            active_sessions = await stress_session_manager.get_all_sessions()
            logger.info(f"Active sessions: {len(active_sessions)}")

    # Final verification
    final_sessions = await stress_session_manager.get_all_sessions()

    logger.info("Session lifecycle stress test completed:")
    logger.info(f"Total sessions processed: {session_count}")
    logger.info(f"Creation errors: {creation_errors}")
    logger.info(f"Closure errors: {closure_errors}")
    logger.info(f"Final active sessions: {len(final_sessions)}")

    # Most sessions should succeed
    success_rate = (session_count - creation_errors - closure_errors) / session_count
    assert success_rate >= 0.95, f"Session success rate too low: {success_rate:.2%}"

    # Should not have lingering sessions (small tolerance for timing)
    assert (
        len(final_sessions) <= 5
    ), f"Too many lingering sessions: {len(final_sessions)}"

    logger.info("✅ Session lifecycle stress test completed successfully")
