"""Error injection and resilience tests for MCP Git Server."""

import asyncio
import logging
import random
import uuid

import pytest

from mcp_server_git.session import SessionState


logger = logging.getLogger(__name__)


@pytest.mark.stress
@pytest.mark.asyncio
async def test_comprehensive_error_injection(
    stress_session_manager, mock_client, error_scenarios, stress_test_config
):
    """
    Test server resilience with comprehensive error injection.

    Injects various types of errors and validates that the server
    remains stable and responsive after each error scenario.
    """
    config = stress_test_config["error_injection"]
    recovery_check_interval = config["recovery_check_interval"]

    await mock_client.connect()
    session = await stress_session_manager.create_session(
        mock_client.session_id, user="error_injection_user"
    )

    logger.info("Starting comprehensive error injection test")
    logger.info(f"Error scenarios: {len(error_scenarios)}")

    injection_count = 0
    recovery_failures = 0
    total_errors_injected = 0

    try:
        for iteration in range(len(error_scenarios) * 10):  # Repeat scenarios
            scenario_idx = iteration % len(error_scenarios)
            scenario = error_scenarios[scenario_idx]

            logger.debug(f"Injecting error scenario: {scenario['name']}")

            # Inject the error
            try:
                if isinstance(scenario["message"], str):
                    # Raw string message (malformed JSON)
                    await mock_client.send_raw_message(scenario["message"])
                else:
                    # Dictionary message
                    await mock_client.send_raw_message(scenario["message"])

            except Exception as e:
                # Errors are expected
                logger.debug(f"Expected error for {scenario['name']}: {e}")

            injection_count += 1
            total_errors_injected += 1

            # Verify server responsiveness after each injection
            if injection_count % recovery_check_interval == 0:
                recovery_success = await _verify_server_recovery(
                    mock_client, session, scenario["name"]
                )

                if not recovery_success:
                    recovery_failures += 1
                    logger.warning(f"Recovery failed after {scenario['name']}")

                logger.info(
                    f"Error injection progress: {injection_count} errors injected, "
                    f"{recovery_failures} recovery failures"
                )

            # Add some normal operations between errors
            if iteration % 3 == 0:
                try:
                    await mock_client.ping()
                    await session.handle_heartbeat()
                except Exception as e:
                    logger.warning(f"Normal operation failed: {e}")
                    recovery_failures += 1

            # Brief delay between injections
            await asyncio.sleep(0.01)

    finally:
        # Final recovery check
        final_recovery = await _verify_server_recovery(
            mock_client, session, "final_check"
        )

        # Cleanup
        if mock_client.connected:
            await mock_client.disconnect()
        if session and not session.is_closed:
            await stress_session_manager.close_session(session.session_id)

    # Calculate success rates
    recovery_success_rate = (injection_count - recovery_failures) / injection_count

    logger.info("Error injection test completed:")
    logger.info(f"Total errors injected: {total_errors_injected}")
    logger.info(f"Recovery checks: {injection_count // recovery_check_interval}")
    logger.info(f"Recovery failures: {recovery_failures}")
    logger.info(f"Recovery success rate: {recovery_success_rate:.2%}")
    logger.info(f"Final recovery: {'✅' if final_recovery else '❌'}")

    # Assertions
    assert (
        recovery_success_rate >= 0.95
    ), f"Recovery success rate too low: {recovery_success_rate:.2%}"
    assert final_recovery, "Server failed final recovery check"

    logger.info("✅ Error injection resilience verified")


@pytest.mark.stress
@pytest.mark.asyncio
async def test_malformed_message_flood(
    stress_session_manager, mock_client, stress_test_config
):
    """Test server stability under a flood of malformed messages."""

    malformed_message_count = 10000
    batch_size = 100

    await mock_client.connect()
    session = await stress_session_manager.create_session(
        mock_client.session_id, user="malformed_flood_user"
    )

    logger.info(f"Testing malformed message flood: {malformed_message_count} messages")

    malformed_messages = [
        # Various malformed message types
        "{invalid json",
        '{"incomplete": true',
        '{"type": null, "id": 123}',
        '{"type": "", "id": ""}',
        '{"type": "test", "id": null}',
        "{}",
        "",
        "not json at all",
        '{"type": "test", "id": "valid", "oversized": "' + "x" * 10000 + '"}',
        '{"nested": {"deeply": {"invalid": {"structure": null}}}}',
    ]

    successful_injections = 0
    processing_errors = 0
    recovery_checks = 0
    recovery_failures = 0

    try:
        for batch_start in range(0, malformed_message_count, batch_size):
            batch_end = min(batch_start + batch_size, malformed_message_count)

            # Send batch of malformed messages
            for i in range(batch_start, batch_end):
                message = malformed_messages[i % len(malformed_messages)]

                try:
                    # Attempt to send malformed message
                    await mock_client.send_raw_message(message)
                    successful_injections += 1
                except Exception:
                    # Expected for malformed messages
                    processing_errors += 1

            # Check server responsiveness after each batch
            recovery_checks += 1
            recovery_success = await _verify_server_recovery(
                mock_client, session, f"batch_{batch_start}"
            )

            if not recovery_success:
                recovery_failures += 1

            if batch_start % (batch_size * 10) == 0:
                logger.info(
                    f"Malformed flood progress: {batch_end}/{malformed_message_count}"
                )
                logger.info(
                    f"Processing errors: {processing_errors}, "
                    f"Recovery failures: {recovery_failures}"
                )

    finally:
        # Final recovery verification
        final_recovery = await _verify_server_recovery(
            mock_client, session, "flood_final"
        )

        # Cleanup
        if mock_client.connected:
            await mock_client.disconnect()
        if session and not session.is_closed:
            await stress_session_manager.close_session(session.session_id)

    recovery_success_rate = (recovery_checks - recovery_failures) / recovery_checks

    logger.info("Malformed message flood test completed:")
    logger.info(f"Messages sent: {malformed_message_count}")
    logger.info(f"Successful injections: {successful_injections}")
    logger.info(f"Processing errors: {processing_errors}")
    logger.info(f"Recovery checks: {recovery_checks}")
    logger.info(f"Recovery success rate: {recovery_success_rate:.2%}")
    logger.info(f"Final recovery: {'✅' if final_recovery else '❌'}")

    # Server should handle malformed messages gracefully
    assert (
        recovery_success_rate >= 0.98
    ), f"Server stability compromised: {recovery_success_rate:.2%}"
    assert final_recovery, "Server failed to recover from malformed message flood"

    logger.info("✅ Malformed message flood resilience verified")


@pytest.mark.stress
@pytest.mark.asyncio
async def test_concurrent_error_injection(
    stress_session_manager, multiple_mock_clients, error_scenarios
):
    """Test error injection from multiple concurrent clients."""

    client_count = 5
    errors_per_client = 200

    # Use subset of clients
    clients = multiple_mock_clients[:client_count]

    logger.info(f"Testing concurrent error injection with {client_count} clients")
    logger.info(f"Errors per client: {errors_per_client}")

    # Connect all clients and create sessions
    sessions = []
    for i, client in enumerate(clients):
        await client.connect()
        session = await stress_session_manager.create_session(
            client.session_id, user=f"concurrent_error_user_{i}"
        )
        sessions.append(session)

    async def inject_errors_for_client(client_idx: int):
        """Inject errors for a single client."""
        client = clients[client_idx]
        session = sessions[client_idx]

        client_errors = 0
        client_recoveries = 0

        for error_idx in range(errors_per_client):
            scenario = error_scenarios[error_idx % len(error_scenarios)]

            try:
                # Inject error
                if isinstance(scenario["message"], str):
                    await client.send_raw_message(scenario["message"])
                else:
                    await client.send_raw_message(scenario["message"])

            except Exception:
                client_errors += 1

            # Periodic recovery check
            if error_idx % 50 == 0:
                recovery_success = await _verify_server_recovery(
                    client, session, f"client_{client_idx}_error_{error_idx}"
                )
                if recovery_success:
                    client_recoveries += 1

            # Small delay to prevent overwhelming
            await asyncio.sleep(0.005)

        return client_idx, client_errors, client_recoveries

    try:
        # Run error injection concurrently across all clients
        tasks = [inject_errors_for_client(i) for i in range(client_count)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Analyze results
        total_errors = 0
        total_recoveries = 0
        failed_tasks = 0

        for result in results:
            if isinstance(result, Exception):
                failed_tasks += 1
                logger.error(f"Client task failed: {result}")
            else:
                client_idx, client_errors, client_recoveries = result
                total_errors += client_errors
                total_recoveries += client_recoveries
                logger.info(
                    f"Client {client_idx}: {client_errors} errors, "
                    f"{client_recoveries} recoveries"
                )

        # Final system recovery check
        system_recovery_count = 0
        for i, client in enumerate(clients):
            if client.connected:
                recovery_success = await _verify_server_recovery(
                    client, sessions[i], f"final_client_{i}"
                )
                if recovery_success:
                    system_recovery_count += 1

    finally:
        # Cleanup all clients and sessions
        for client in clients:
            if client.connected:
                await client.disconnect()

        for session in sessions:
            if session and not session.is_closed:
                await session.close()

    # Calculate success metrics
    expected_total_errors = client_count * errors_per_client
    system_recovery_rate = system_recovery_count / client_count

    logger.info("Concurrent error injection test completed:")
    logger.info(f"Total errors expected: {expected_total_errors}")
    logger.info(f"Total errors processed: {total_errors}")
    logger.info(f"Failed client tasks: {failed_tasks}")
    logger.info(f"System recovery rate: {system_recovery_rate:.2%}")

    # Assertions
    assert failed_tasks <= 1, f"Too many client tasks failed: {failed_tasks}"
    assert (
        system_recovery_rate >= 0.8
    ), f"System recovery rate too low: {system_recovery_rate:.2%}"

    logger.info("✅ Concurrent error injection resilience verified")


@pytest.mark.stress
@pytest.mark.asyncio
async def test_error_recovery_under_load(
    stress_session_manager, mock_client, stress_test_config
):
    """Test error recovery while system is under normal load."""

    config = stress_test_config["error_injection"]
    error_rate = config["error_rate"]  # 10% of operations are errors
    total_operations = 5000

    await mock_client.connect()
    session = await stress_session_manager.create_session(
        mock_client.session_id, user="error_under_load_user"
    )

    logger.info("Testing error recovery under load")
    logger.info(f"Total operations: {total_operations}, Error rate: {error_rate:.1%}")

    normal_operations = 0
    error_operations = 0
    recovery_checks = 0
    recovery_failures = 0

    error_messages = [
        {"invalid": "structure"},
        "malformed json {",
        {},
        {"type": None, "id": 123},
    ]

    try:
        for operation in range(total_operations):
            # Decide whether to inject error
            if random.random() < error_rate:
                # Inject error
                error_message = random.choice(error_messages)
                try:
                    await mock_client.send_raw_message(error_message)
                except Exception:
                    pass  # Expected
                error_operations += 1

            else:
                # Normal operation
                operation_type = random.randint(1, 4)

                try:
                    if operation_type == 1:
                        await mock_client.ping()
                    elif operation_type == 2:
                        await session.handle_heartbeat()
                    elif operation_type == 3:
                        op_id = str(uuid.uuid4())
                        await mock_client.start_operation(op_id)
                        if random.random() < 0.3:
                            await mock_client.cancel_operation(op_id)
                    else:
                        await mock_client.send_batch_messages(3)

                    normal_operations += 1

                except Exception as e:
                    logger.warning(f"Normal operation failed: {e}")
                    recovery_failures += 1

            # Periodic recovery verification
            if operation % 100 == 0:
                recovery_checks += 1
                recovery_success = await _verify_server_recovery(
                    mock_client, session, f"load_operation_{operation}"
                )

                if not recovery_success:
                    recovery_failures += 1

                if operation % 500 == 0:
                    logger.info(f"Load test progress: {operation}/{total_operations}")
                    logger.info(
                        f"Normal: {normal_operations}, Errors: {error_operations}"
                    )
                    logger.info(f"Recovery failures: {recovery_failures}")

    finally:
        # Final recovery check
        final_recovery = await _verify_server_recovery(
            mock_client, session, "load_final"
        )

        # Cleanup
        if mock_client.connected:
            await mock_client.disconnect()
        if session and not session.is_closed:
            await stress_session_manager.close_session(session.session_id)

    # Calculate metrics
    actual_error_rate = error_operations / total_operations
    recovery_success_rate = (recovery_checks - recovery_failures) / recovery_checks
    normal_success_rate = normal_operations / (total_operations - error_operations)

    logger.info("Error recovery under load test completed:")
    logger.info(f"Total operations: {total_operations}")
    logger.info(f"Normal operations: {normal_operations}")
    logger.info(f"Error operations: {error_operations}")
    logger.info(f"Actual error rate: {actual_error_rate:.2%}")
    logger.info(f"Recovery checks: {recovery_checks}")
    logger.info(f"Recovery success rate: {recovery_success_rate:.2%}")
    logger.info(f"Normal operation success rate: {normal_success_rate:.2%}")
    logger.info(f"Final recovery: {'✅' if final_recovery else '❌'}")

    # Assertions
    assert (
        recovery_success_rate >= 0.95
    ), f"Recovery success rate under load too low: {recovery_success_rate:.2%}"
    assert (
        normal_success_rate >= 0.95
    ), f"Normal operations affected by errors: {normal_success_rate:.2%}"
    assert final_recovery, "System failed final recovery under load"

    logger.info("✅ Error recovery under load verified")


async def _verify_server_recovery(mock_client, session, context: str) -> bool:
    """
    Verify that the server is still responsive and functional.

    Returns True if server has recovered successfully, False otherwise.
    """
    try:
        # Test basic responsiveness
        ping_response = await mock_client.ping()
        if not ping_response or ping_response.get("type") != "pong":
            logger.warning(f"Recovery check failed - ping: {context}")
            return False

        # Test session functionality
        if session and not session.is_closed:
            await session.handle_heartbeat()

            # Check session state
            if session.state not in [SessionState.ACTIVE, SessionState.PAUSED]:
                logger.warning(f"Recovery check failed - session state: {context}")
                return False

        # Test operation lifecycle
        op_id = str(uuid.uuid4())
        await mock_client.start_operation(op_id)
        await asyncio.sleep(0.01)
        await mock_client.cancel_operation(op_id)

        return True

    except Exception as e:
        logger.warning(f"Recovery check failed - exception: {context}, {e}")
        return False
