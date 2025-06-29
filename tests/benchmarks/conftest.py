import os
import time
import uuid
from typing import Any, Dict, Optional

import pytest
import psutil
import gc

# Define MockMCPClient directly to avoid import issues


class MockMCPClient:
    """Mock MCP client for benchmark testing."""

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

    async def send_batch_messages(self, count: int = 10):
        """Send a batch of messages quickly."""
        results = []
        for _ in range(count):
            result = await self.ping()
            results.append(result)
        return results

# Import SessionManager and HeartbeatManager for a lightweight session fixture
from mcp_server_git.session import SessionManager, HeartbeatManager


@pytest.fixture
async def benchmark_session_manager():
    """
    Create a lightweight session manager for benchmarks.
    Uses minimal timeouts and heartbeat intervals to keep tests fast.
    """
    manager = SessionManager(
        idle_timeout=1.0,  # Very short timeout for quick cleanup
        heartbeat_timeout=1.0,  # Very short timeout
    )

    # Initialize heartbeat manager with minimal intervals if not already set
    if manager.heartbeat_manager is None:
        manager.heartbeat_manager = HeartbeatManager(
            session_manager=manager,
            heartbeat_interval=0.1,  # Check every 0.1 seconds
            missed_threshold=1,
        )
        await manager.heartbeat_manager.start()

    yield manager

    # Cleanup: Ensure the session manager and its heartbeat manager are shut down
    await manager.shutdown()


@pytest.fixture
async def mock_client():
    """
    Create a mock MCP client for testing. Reuses the one from stress tests.
    """
    client = MockMCPClient()
    yield client

    # Cleanup: Disconnect the client if it's still connected
    if client.connected:
        await client.disconnect()


@pytest.fixture
def memory_monitor():
    """
    Memory monitoring utilities for leak detection, redefined for independence
    from the stress test conftest.
    """
    class MemoryMonitor:
        def __init__(self):
            self.process = psutil.Process()
            self.samples = []

        def take_sample(self, label: str = ""):
            """Take a memory usage sample."""
            gc.collect()  # Force garbage collection to get a more accurate reading
            memory_mb = self.process.memory_info().rss / 1024 / 1024
            self.samples.append(
                {"label": label, "memory_mb": memory_mb, "timestamp": time.time()}
            )
            return memory_mb

        def get_memory_growth(self) -> float:
            """Calculate total memory growth from the first to the last sample."""
            if len(self.samples) < 2:
                return 0.0
            return self.samples[-1]["memory_mb"] - self.samples[0]["memory_mb"]

        def get_memory_slope(self) -> float:
            """
            Calculate memory growth slope (trend) using simple linear regression.
            Requires at least 10 samples for a meaningful calculation.
            """
            if len(self.samples) < 10:
                return 0.0

            n = len(self.samples)
            x = list(range(n))  # Use sample index as x-values
            y = [sample["memory_mb"] for sample in self.samples]

            # Calculate sums for linear regression formula
            sum_x = sum(x)
            sum_y = sum(y)
            sum_xy = sum(x[i] * y[i] for i in range(n))
            sum_x_squared = sum(xi ** 2 for xi in x)

            denominator = (n * sum_x_squared - sum_x ** 2)
            if denominator == 0:
                return 0.0  # Avoid division by zero if all x values are identical (e.g., n=1)

            slope = (n * sum_xy - sum_x * sum_y) / denominator
            return slope

        def log_samples(self):
            """Log all collected memory samples to stdout."""
            print("\n--- Memory Samples ---")
            for i, sample in enumerate(self.samples):
                print(f"Sample {i}: {sample['memory_mb']:.2f} MB - {sample['label']}")
            print("----------------------")

    return MemoryMonitor()

