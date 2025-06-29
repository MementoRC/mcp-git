"""Stress test fixtures and configuration for MCP Git Server."""

import os
import time
import uuid
from typing import Any, Dict, Optional

import pytest

from mcp_server_git.session import SessionManager
from mcp_server_git.metrics import global_metrics_collector


class MockMCPClient:
    """Mock MCP client for stress testing."""

    def __init__(self, client_id: Optional[str] = None):
        self.client_id = client_id or str(uuid.uuid4())
        self.connected = False
        self.session_id = None
        self.operations = {}
        self.message_count = 0
        self.error_count = 0

    async def connect(self):
        """Simulate client connection."""
        self.connected = True
        self.session_id = str(uuid.uuid4())
        self.message_count = 0
        self.error_count = 0

    async def disconnect(self):
        """Simulate client disconnection."""
        self.connected = False
        self.session_id = None

    async def ping(self) -> Dict[str, Any]:
        """Send a ping message."""
        if not self.connected:
            raise RuntimeError("Client not connected")

        self.message_count += 1
        return {"type": "pong", "id": str(uuid.uuid4())}

    async def start_operation(self, operation_id: str) -> Dict[str, Any]:
        """Start a long-running operation."""
        if not self.connected:
            raise RuntimeError("Client not connected")

        self.operations[operation_id] = {
            "id": operation_id,
            "status": "running",
            "start_time": time.time(),
        }
        self.message_count += 1

        return {
            "type": "operation_started",
            "id": str(uuid.uuid4()),
            "operation_id": operation_id,
        }

    async def cancel_operation(self, operation_id: str) -> Dict[str, Any]:
        """Cancel a running operation."""
        if not self.connected:
            raise RuntimeError("Client not connected")

        if operation_id in self.operations:
            self.operations[operation_id]["status"] = "cancelled"

        self.message_count += 1

        return {
            "type": "operation_cancelled",
            "id": str(uuid.uuid4()),
            "operation_id": operation_id,
        }

    async def send_invalid_message(self):
        """Send an intentionally invalid message."""
        if not self.connected:
            raise RuntimeError("Client not connected")

        self.error_count += 1
        # Simulate sending malformed JSON or invalid message type
        raise ValueError("Invalid message format")

    async def send_raw_message(self, message: Dict[str, Any]):
        """Send a raw message (for error injection)."""
        if not self.connected:
            raise RuntimeError("Client not connected")

        # Simulate processing of potentially invalid message
        if not message or "type" not in message:
            self.error_count += 1
            raise ValueError("Malformed message")

        self.message_count += 1

    async def send_batch_messages(self, count: int = 10):
        """Send a batch of messages quickly."""
        results = []
        for _ in range(count):
            result = await self.ping()
            results.append(result)
        return results


@pytest.fixture
async def stress_session_manager():
    """Create a session manager optimized for stress testing."""
    manager = SessionManager(
        idle_timeout=300.0,  # 5 minutes for stress tests
        heartbeat_timeout=60.0,  # 1 minute for stress tests
    )

    # Initialize heartbeat manager
    if manager.heartbeat_manager is None:
        from mcp_server_git.session import HeartbeatManager

        manager.heartbeat_manager = HeartbeatManager(
            session_manager=manager,
            heartbeat_interval=30.0,  # Check every 30 seconds
            missed_threshold=3,
        )
        await manager.heartbeat_manager.start()

    yield manager

    # Cleanup
    await manager.shutdown()


@pytest.fixture
async def mock_client():
    """Create a mock MCP client for testing."""
    client = MockMCPClient()
    yield client

    # Cleanup
    if client.connected:
        await client.disconnect()


@pytest.fixture
async def multiple_mock_clients():
    """Create multiple mock clients for concurrent testing."""
    clients = [MockMCPClient(f"client-{i}") for i in range(10)]
    yield clients

    # Cleanup all clients
    for client in clients:
        if client.connected:
            await client.disconnect()


@pytest.fixture
def stress_test_config():
    """Configuration for stress tests, with CI overrides for speed."""

    # Detect CI environment
    is_ci = (
        os.getenv("CI", "false").lower() == "true"
        or os.getenv("GITHUB_ACTIONS", "false").lower() == "true"
        or os.getenv("PYTEST_CI", "false").lower() == "true"
    )

    # CI-friendly defaults
    ci_defaults = {
        "long_running": {
            "duration_minutes": 2,
            "message_rate": 5,
            "operation_rate": 2,
        },
        "memory": {
            "sample_interval": 50,
            "max_growth_mb": 10,
            "max_slope": 0.2,
        },
        "error_injection": {
            "error_rate": 0.1,
            "recovery_check_interval": 3,
        },
        "concurrent": {
            "client_count": 5,
            "messages_per_client": 50,
            "connection_delay": 0.01,
        },
    }

    if is_ci:
        config = ci_defaults
    else:
        config = {
            "long_running": {
                "duration_minutes": int(os.getenv("STRESS_DURATION_MINUTES", "30")),
                "message_rate": int(
                    os.getenv("STRESS_MESSAGE_RATE", "10")
                ),  # messages per second
                "operation_rate": int(
                    os.getenv("STRESS_OPERATION_RATE", "5")
                ),  # operations per minute
            },
            "memory": {
                "sample_interval": int(
                    os.getenv("STRESS_MEMORY_SAMPLE_INTERVAL", "100")
                ),  # operations
                "max_growth_mb": int(os.getenv("STRESS_MAX_MEMORY_GROWTH", "50")),
                "max_slope": float(os.getenv("STRESS_MAX_MEMORY_SLOPE", "0.1")),
            },
            "error_injection": {
                "error_rate": float(
                    os.getenv("STRESS_ERROR_RATE", "0.1")
                ),  # 10% of messages
                "recovery_check_interval": int(os.getenv("STRESS_RECOVERY_CHECK", "10")),
            },
            "concurrent": {
                "client_count": int(os.getenv("STRESS_CLIENT_COUNT", "20")),
                "messages_per_client": int(os.getenv("STRESS_MESSAGES_PER_CLIENT", "1000")),
                "connection_delay": float(os.getenv("STRESS_CONNECTION_DELAY", "0.1")),
            },
        }
    return config


@pytest.fixture
def error_scenarios():
    """Define various error scenarios for injection testing."""
    return [
        # Malformed messages
        {
            "name": "malformed_json",
            "message": "{invalid json",
            "expected_error": "JSONDecodeError",
        },
        {
            "name": "missing_required_fields",
            "message": {"id": str(uuid.uuid4())},  # Missing 'type'
            "expected_error": "ValidationError",
        },
        {
            "name": "invalid_field_types",
            "message": {
                "type": "notifications/cancelled",
                "id": 12345,  # Should be string
                "params": {"requestId": 67890},  # Should be string
            },
            "expected_error": "ValidationError",
        },
        {
            "name": "unknown_message_type",
            "message": {"type": "unknown/message_type", "id": str(uuid.uuid4())},
            "expected_error": "UnknownMessageType",
        },
        {"name": "empty_message", "message": {}, "expected_error": "ValidationError"},
        {
            "name": "oversized_message",
            "message": {
                "type": "oversized",
                "id": str(uuid.uuid4()),
                "data": "x" * 1000000,  # 1MB of data
            },
            "expected_error": "OversizedMessage",
        },
        {
            "name": "nested_invalid_structures",
            "message": {
                "type": "nested_invalid",
                "id": str(uuid.uuid4()),
                "data": {"nested": {"invalid": [1, 2, None, {"x": float("inf")}]}},
            },
            "expected_error": "ValidationError",
        },
    ]


@pytest.fixture
async def metrics_collector():
    """Provide access to the global metrics collector."""
    # Reset metrics before test
    global_metrics_collector.reset()
    yield global_metrics_collector
    # Optionally reset after test as well
    global_metrics_collector.reset()


@pytest.fixture
def memory_monitor():
    """Memory monitoring utilities for leak detection."""
    import psutil
    import gc

    class MemoryMonitor:
        def __init__(self):
            self.process = psutil.Process()
            self.samples = []

        def take_sample(self, label: str = ""):
            """Take a memory usage sample."""
            gc.collect()  # Force garbage collection
            memory_mb = self.process.memory_info().rss / 1024 / 1024
            self.samples.append(
                {"label": label, "memory_mb": memory_mb, "timestamp": time.time()}
            )
            return memory_mb

        def get_memory_growth(self) -> float:
            """Calculate total memory growth."""
            if len(self.samples) < 2:
                return 0.0
            return self.samples[-1]["memory_mb"] - self.samples[0]["memory_mb"]

        def get_memory_slope(self) -> float:
            """Calculate memory growth slope (trend)."""
            if len(self.samples) < 10:
                return 0.0

            # Simple linear regression
            n = len(self.samples)
            x = list(range(n))
            y = [sample["memory_mb"] for sample in self.samples]

            slope = (n * sum(x[i] * y[i] for i in range(n)) - sum(x) * sum(y)) / (
                n * sum(x[i] ** 2 for i in range(n)) - sum(x) ** 2
            )
            return slope

        def log_samples(self):
            """Log all memory samples."""
            for i, sample in enumerate(self.samples):
                print(f"Sample {i}: {sample['memory_mb']:.2f} MB - {sample['label']}")

    return MemoryMonitor()


def pytest_configure(config):
    """Configure pytest for stress tests."""
    config.addinivalue_line(
        "markers",
        "stress: marks tests as stress tests (long-running, resource intensive)",
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to handle stress test markers."""
    # Add stress marker to all tests in stress directory
    for item in items:
        if "stress" in str(item.fspath):
            item.add_marker(pytest.mark.stress)
