"""Concurrent client and high-load stress tests for MCP Git Server."""

import asyncio
import logging
import random
import time
import uuid

import pytest


logger = logging.getLogger(__name__)


@pytest.mark.stress
@pytest.mark.asyncio
async def test_massive_concurrent_clients(stress_session_manager, stress_test_config):
    """Minimal concurrent client test for CI."""

    import os

    is_ci = (
        os.getenv("CI", "false").lower() == "true"
        or os.getenv("GITHUB_ACTIONS", "false").lower() == "true"
        or os.getenv("PYTEST_CI", "false").lower() == "true"
    )

    config = stress_test_config["concurrent"]
    client_count = config["client_count"]
    messages_per_client = config["messages_per_client"]
    connection_delay = config["connection_delay"]

    # In CI, use only 1 client, 5 messages, minimal delay
    if is_ci:
        client_count = 1
        messages_per_client = 5
        connection_delay = 0.001

    logger.info(f"Testing {client_count} concurrent clients (CI minimal)")
    logger.info(f"Messages per client: {messages_per_client}")

    from .conftest import MockMCPClient

    clients = [MockMCPClient(f"stress_client_{i}") for i in range(client_count)]
    sessions = []

    total_messages_sent = 0
    total_errors = 0

    async def client_lifecycle(client_idx: int):
        nonlocal total_messages_sent, total_errors

        client = clients[client_idx]
        session = None
        client_messages = 0
        client_errors = 0

        try:
            await asyncio.sleep(client_idx * connection_delay)
            await client.connect()
            session = await stress_session_manager.create_session(
                client.session_id, user=f"concurrent_user_{client_idx}"
            )
            sessions.append(session)

            for message_idx in range(messages_per_client):
                try:
                    await client.ping()
                    client_messages += 1
                except Exception as e:
                    client_errors += 1
                    logger.debug(f"Client {client_idx} error: {e}")

            total_messages_sent += client_messages
            total_errors += client_errors

            return client_idx, client_messages, client_errors

        finally:
            try:
                if client.connected:
                    await client.disconnect()
                if session and not session.is_closed:
                    await stress_session_manager.close_session(session.session_id)
            except Exception:
                pass

    start_time = time.time()

    try:
        tasks = [client_lifecycle(i) for i in range(client_count)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successful_clients = 0
        failed_clients = 0

        for result in results:
            if isinstance(result, Exception):
                failed_clients += 1
                logger.error(f"Client task exception: {result}")
            else:
                client_idx, messages, errors = result
                if messages > 0:
                    successful_clients += 1
                else:
                    failed_clients += 1

    finally:
        for client in clients:
            if client.connected:
                try:
                    await client.disconnect()
                except Exception:
                    pass

    elapsed_time = time.time() - start_time
    success_rate = successful_clients / client_count
    error_rate = total_errors / total_messages_sent if total_messages_sent > 0 else 0

    final_sessions = await stress_session_manager.get_all_sessions()

    logger.info("Concurrent clients test completed (CI minimal):")
    logger.info(f"Total clients: {client_count}")
    logger.info(f"Successful clients: {successful_clients}")
    logger.info(f"Failed clients: {failed_clients}")
    logger.info(f"Success rate: {success_rate:.2%}")
    logger.info(f"Total messages: {total_messages_sent}")
    logger.info(f"Error rate: {error_rate:.2%}")
    logger.info(f"Test duration: {elapsed_time:.2f} seconds")
    logger.info(f"Remaining sessions: {len(final_sessions)}")

    # Assertions: only basic functionality in CI
    assert success_rate >= 1.0, f"Client success rate too low: {success_rate:.2%}"
    assert error_rate < 0.2, f"Error rate too high: {error_rate:.2%}"
    assert (
        len(final_sessions) <= 2
    ), f"Too many lingering sessions: {len(final_sessions)}"

    logger.info("✅ Minimal concurrent clients test passed")


@pytest.mark.stress
@pytest.mark.ci_skip  # Too intensive for CI
@pytest.mark.asyncio
async def test_high_throughput_message_processing(
    stress_session_manager, stress_test_config
):
    """Test high-throughput message processing with multiple clients."""

    client_count = 10
    messages_per_second = 1000  # Target total throughput
    test_duration_seconds = 30

    from .conftest import MockMCPClient

    logger.info(
        f"Testing high throughput: {messages_per_second} msg/sec for {test_duration_seconds}s"
    )
    logger.info(f"Using {client_count} clients")

    # Create clients and sessions
    clients = [MockMCPClient(f"throughput_client_{i}") for i in range(client_count)]
    sessions = []

    for i, client in enumerate(clients):
        await client.connect()
        session = await stress_session_manager.create_session(
            client.session_id, user=f"throughput_user_{i}"
        )
        sessions.append(session)

    # Calculate per-client rate
    messages_per_client_per_second = messages_per_second // client_count

    async def high_throughput_client(client_idx: int):
        """Generate high-throughput messages for a single client."""
        client = clients[client_idx]
        session = sessions[client_idx]

        messages_sent = 0
        errors = 0
        start_time = time.time()

        try:
            while time.time() - start_time < test_duration_seconds:
                second_start = time.time()

                # Send target number of messages in this second
                for _ in range(messages_per_client_per_second):
                    try:
                        message_type = random.randint(1, 4)

                        if message_type == 1:
                            await client.ping()
                        elif message_type == 2:
                            await session.handle_heartbeat()
                        elif message_type == 3:
                            op_id = str(uuid.uuid4())
                            await client.start_operation(op_id)
                            await client.cancel_operation(op_id)
                        else:
                            await client.send_batch_messages(2)
                            messages_sent += 1  # Batch counts as extra

                        messages_sent += 1

                    except Exception as e:
                        errors += 1
                        logger.debug(f"Throughput client {client_idx} error: {e}")

                # Wait for remainder of second
                elapsed = time.time() - second_start
                if elapsed < 1.0:
                    await asyncio.sleep(1.0 - elapsed)

        except Exception as e:
            logger.error(f"Throughput client {client_idx} failed: {e}")

        return client_idx, messages_sent, errors

    # Run high-throughput test
    start_time = time.time()

    try:
        tasks = [high_throughput_client(i) for i in range(client_count)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Aggregate results
        total_messages = 0
        total_errors = 0
        successful_clients = 0

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Throughput client exception: {result}")
            else:
                client_idx, messages, errors = result
                total_messages += messages
                total_errors += errors
                if messages > 0:
                    successful_clients += 1
                logger.info(
                    f"Client {client_idx}: {messages} messages, {errors} errors"
                )

    finally:
        # Cleanup
        for client in clients:
            if client.connected:
                await client.disconnect()
        for session in sessions:
            if session and not session.is_closed:
                await session.close()

    actual_duration = time.time() - start_time
    actual_throughput = total_messages / actual_duration
    target_throughput = messages_per_second
    throughput_ratio = actual_throughput / target_throughput
    error_rate = total_errors / total_messages if total_messages > 0 else 0

    logger.info("High throughput test completed:")
    logger.info(f"Target throughput: {target_throughput:.1f} msg/sec")
    logger.info(f"Actual throughput: {actual_throughput:.1f} msg/sec")
    logger.info(f"Throughput ratio: {throughput_ratio:.2%}")
    logger.info(f"Total messages: {total_messages}")
    logger.info(f"Total errors: {total_errors}")
    logger.info(f"Error rate: {error_rate:.2%}")
    logger.info(f"Successful clients: {successful_clients}/{client_count}")

    # Performance assertions
    assert throughput_ratio >= 0.8, f"Throughput too low: {throughput_ratio:.2%}"
    assert (
        error_rate < 0.02
    ), f"Error rate too high at high throughput: {error_rate:.2%}"
    assert (
        successful_clients >= client_count * 0.9
    ), f"Too many client failures: {successful_clients}/{client_count}"

    logger.info("✅ High throughput test passed")


@pytest.mark.stress
@pytest.mark.ci_skip  # Too intensive for CI
@pytest.mark.asyncio
async def test_connection_churn_stability(stress_session_manager, stress_test_config):
    """Test stability under rapid client connections and disconnections."""

    import os

    is_ci = (
        os.getenv("CI", "false").lower() == "true"
        or os.getenv("GITHUB_ACTIONS", "false").lower() == "true"
        or os.getenv("PYTEST_CI", "false").lower() == "true"
    )

    connection_cycles = 10 if is_ci else 2000
    concurrent_connections = 2 if is_ci else 20
    max_connection_time = 1.0 if is_ci else 5.0  # seconds

    from .conftest import MockMCPClient

    logger.info(f"Testing connection churn: {connection_cycles} cycles")
    logger.info(f"Concurrent connections: {concurrent_connections}")

    successful_cycles = 0
    connection_errors = 0
    session_errors = 0

    async def connection_churn_cycle(cycle_id: int):
        """Single connection/disconnection cycle."""
        nonlocal successful_cycles, connection_errors, session_errors

        client = MockMCPClient(f"churn_client_{cycle_id}")
        session = None

        try:
            # Connect
            await client.connect()

            # Create session
            session = await stress_session_manager.create_session(
                client.session_id, user=f"churn_user_{cycle_id}"
            )

            # Brief activity
            connection_duration = random.uniform(0.1, max_connection_time)
            end_time = time.time() + connection_duration

            while time.time() < end_time:
                try:
                    activity_type = random.randint(1, 3)

                    if activity_type == 1:
                        await client.ping()
                    elif activity_type == 2:
                        await session.handle_heartbeat()
                    else:
                        op_id = str(uuid.uuid4())
                        await client.start_operation(op_id)
                        await asyncio.sleep(0.01)
                        await client.cancel_operation(op_id)

                    await asyncio.sleep(0.05)

                except Exception:
                    # Minor errors during activity are acceptable
                    pass

            successful_cycles += 1

        except Exception as e:
            if "connect" in str(e).lower():
                connection_errors += 1
            else:
                session_errors += 1
            logger.debug(f"Connection churn cycle {cycle_id} failed: {e}")

        finally:
            # Cleanup
            try:
                if client.connected:
                    await client.disconnect()
                if session and not session.is_closed:
                    await stress_session_manager.close_session(session.session_id)
            except Exception:
                pass

    # Run connection churn in batches
    start_time = time.time()

    for batch_start in range(0, connection_cycles, concurrent_connections):
        batch_end = min(batch_start + concurrent_connections, connection_cycles)

        # Create batch of connection cycles
        tasks = [connection_churn_cycle(i) for i in range(batch_start, batch_end)]
        await asyncio.gather(*tasks, return_exceptions=True)

        if batch_start % (concurrent_connections * 5) == 0:
            logger.info(f"Connection churn progress: {batch_end}/{connection_cycles}")
            logger.info(
                f"Successful: {successful_cycles}, Errors: {connection_errors + session_errors}"
            )

    elapsed_time = time.time() - start_time
    success_rate = successful_cycles / connection_cycles
    connection_rate = connection_cycles / elapsed_time

    # Check final server state
    final_sessions = await stress_session_manager.get_all_sessions()

    logger.info("Connection churn test completed:")
    logger.info(f"Total cycles: {connection_cycles}")
    logger.info(f"Successful cycles: {successful_cycles}")
    logger.info(f"Connection errors: {connection_errors}")
    logger.info(f"Session errors: {session_errors}")
    logger.info(f"Success rate: {success_rate:.2%}")
    logger.info(f"Connection rate: {connection_rate:.1f} conn/sec")
    logger.info(f"Test duration: {elapsed_time:.2f} seconds")
    logger.info(f"Remaining sessions: {len(final_sessions)}")

    # Stability assertions
    assert (
        success_rate >= 0.95
    ), f"Connection churn success rate too low: {success_rate:.2%}"
    assert (
        len(final_sessions) <= 10
    ), f"Too many lingering sessions: {len(final_sessions)}"
    assert (
        connection_rate > 50
    ), f"Connection processing rate too low: {connection_rate:.1f} conn/sec"

    logger.info("✅ Connection churn stability verified")


@pytest.mark.stress
@pytest.mark.ci_skip  # Too intensive for CI
@pytest.mark.asyncio
async def test_mixed_load_scenarios(stress_session_manager, stress_test_config):
    """Test server under mixed realistic load scenarios."""

    import os

    is_ci = (
        os.getenv("CI", "false").lower() == "true"
        or os.getenv("GITHUB_ACTIONS", "false").lower() == "true"
        or os.getenv("PYTEST_CI", "false").lower() == "true"
    )

    # Different client types with different behaviors
    scenarios = [
        {
            "name": "burst_client",
            "count": 1 if is_ci else 5,
            "message_rate": 5 if is_ci else 50,
            "burst_interval": 2 if is_ci else 10,
        },
        {
            "name": "steady_client",
            "count": 1 if is_ci else 10,
            "message_rate": 2 if is_ci else 10,
            "burst_interval": 0,
        },
        {
            "name": "idle_client",
            "count": 1 if is_ci else 15,
            "message_rate": 1,
            "burst_interval": 0,
        },
        {
            "name": "operation_heavy",
            "count": 1 if is_ci else 3,
            "message_rate": 2 if is_ci else 20,
            "operation_ratio": 0.8,
        },
        {
            "name": "error_prone",
            "count": 1 if is_ci else 2,
            "message_rate": 1 if is_ci else 5,
            "error_rate": 0.1,
        },
    ]

    test_duration = 5 if is_ci else 60  # seconds

    from .conftest import MockMCPClient

    logger.info(f"Testing mixed load scenarios for {test_duration} seconds")

    # Create clients for each scenario
    all_clients = []
    all_sessions = []
    scenario_stats = {}

    for scenario in scenarios:
        scenario_clients = []
        scenario_sessions = []

        for i in range(scenario["count"]):
            client_id = f"{scenario['name']}_{i}"
            client = MockMCPClient(client_id)
            await client.connect()

            session = await stress_session_manager.create_session(
                client.session_id, user=f"mixed_load_{client_id}"
            )

            scenario_clients.append(client)
            scenario_sessions.append(session)

        all_clients.extend(scenario_clients)
        all_sessions.extend(scenario_sessions)

        scenario_stats[scenario["name"]] = {
            "clients": scenario_clients,
            "sessions": scenario_sessions,
            "messages_sent": 0,
            "errors": 0,
            "config": scenario,
        }

    async def run_scenario_client(scenario_name: str, client_idx: int):
        """Run a single client according to its scenario."""
        stats = scenario_stats[scenario_name]
        config = stats["config"]
        client = stats["clients"][client_idx]
        session = stats["sessions"][client_idx]

        messages_sent = 0
        errors = 0

        start_time = time.time()
        last_burst = start_time

        try:
            while time.time() - start_time < test_duration:
                # Determine if this is a burst period
                is_burst = False
                if config.get("burst_interval", 0) > 0:
                    if time.time() - last_burst >= config["burst_interval"]:
                        is_burst = True
                        last_burst = time.time()

                # Calculate message rate for this period
                current_rate = config["message_rate"]
                if is_burst:
                    current_rate *= 5  # 5x burst rate

                # Send messages for this second
                second_start = time.time()

                for _ in range(current_rate):
                    try:
                        # Determine operation type based on scenario
                        if (
                            config.get("error_rate", 0) > 0
                            and random.random() < config["error_rate"]
                        ):
                            # Inject error
                            await client.send_invalid_message()
                        elif config.get("operation_ratio", 0.5) > random.random():
                            # Operation lifecycle
                            op_id = str(uuid.uuid4())
                            await client.start_operation(op_id)
                            if random.random() < 0.6:
                                await client.cancel_operation(op_id)
                        else:
                            # Regular ping
                            await client.ping()

                        messages_sent += 1

                        # Occasional heartbeat
                        if messages_sent % 20 == 0:
                            await session.handle_heartbeat()

                    except Exception as e:
                        errors += 1
                        logger.debug(
                            f"Mixed load {scenario_name}[{client_idx}] error: {e}"
                        )

                # Wait for remainder of second
                elapsed = time.time() - second_start
                if elapsed < 1.0:
                    await asyncio.sleep(1.0 - elapsed)

        except Exception as e:
            logger.error(f"Mixed load {scenario_name}[{client_idx}] failed: {e}")
            errors += 1

        # Update scenario stats
        stats["messages_sent"] += messages_sent
        stats["errors"] += errors

        return scenario_name, client_idx, messages_sent, errors

    # Run all scenarios concurrently
    start_time = time.time()

    try:
        tasks = []
        for scenario_name, stats in scenario_stats.items():
            for client_idx in range(len(stats["clients"])):
                task = run_scenario_client(scenario_name, client_idx)
                tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Mixed load task exception: {result}")

    finally:
        # Cleanup all clients and sessions
        for client in all_clients:
            if client.connected:
                await client.disconnect()
        for session in all_sessions:
            if session and not session.is_closed:
                await stress_session_manager.close_session(session.session_id)

    actual_duration = time.time() - start_time

    # Calculate overall statistics
    total_messages = sum(stats["messages_sent"] for stats in scenario_stats.values())
    total_errors = sum(stats["errors"] for stats in scenario_stats.values())
    total_clients = sum(len(stats["clients"]) for stats in scenario_stats.values())

    overall_message_rate = total_messages / actual_duration
    overall_error_rate = total_errors / total_messages if total_messages > 0 else 0

    # Check final server state
    final_sessions = await stress_session_manager.get_all_sessions()

    logger.info("Mixed load test completed:")
    logger.info(f"Test duration: {actual_duration:.2f} seconds")
    logger.info(f"Total clients: {total_clients}")
    logger.info(f"Total messages: {total_messages}")
    logger.info(f"Total errors: {total_errors}")
    logger.info(f"Message rate: {overall_message_rate:.1f} msg/sec")
    logger.info(f"Error rate: {overall_error_rate:.2%}")
    logger.info(f"Remaining sessions: {len(final_sessions)}")

    # Log per-scenario statistics
    for scenario_name, stats in scenario_stats.items():
        rate = stats["messages_sent"] / actual_duration
        error_rate = (
            stats["errors"] / stats["messages_sent"]
            if stats["messages_sent"] > 0
            else 0
        )
        logger.info(
            f"Scenario {scenario_name}: {stats['messages_sent']} messages, "
            f"{rate:.1f} msg/sec, {error_rate:.2%} error rate"
        )

    # Mixed load assertions
    assert (
        overall_message_rate > 200
    ), f"Overall message rate too low: {overall_message_rate:.1f} msg/sec"
    assert (
        overall_error_rate < 0.05
    ), f"Overall error rate too high: {overall_error_rate:.2%}"
    assert (
        len(final_sessions) <= 10
    ), f"Too many lingering sessions: {len(final_sessions)}"

    # Each scenario should have reasonable performance
    for scenario_name, stats in scenario_stats.items():
        scenario_error_rate = (
            stats["errors"] / stats["messages_sent"]
            if stats["messages_sent"] > 0
            else 0
        )
        expected_error_rate = stats["config"].get("error_rate", 0)

        # Allow some tolerance for injected errors
        max_allowed_error_rate = max(expected_error_rate * 1.5, 0.1)
        assert (
            scenario_error_rate <= max_allowed_error_rate
        ), f"Scenario {scenario_name} error rate too high: {scenario_error_rate:.2%}"

    logger.info("✅ Mixed load scenarios test passed")
