import asyncio
import time
from typing import Any, Dict, Optional
from collections import defaultdict


class MetricsCollector:
    """
    Global metrics collector for MCP Git Server.
    Aggregates server-wide metrics, performance, and health.
    Thread-safe for async operations.
    """

    def __init__(self):
        self._lock = asyncio.Lock()
        self._metrics = {
            "messages_processed": 0,
            "operations": defaultdict(int),
            "errors": defaultdict(int),
            "message_durations_ms": [],
            "operation_durations_ms": [],
            "active_sessions": 0,
            "session_events": defaultdict(int),
            "last_health_check": None,
            "startup_time": time.time(),
        }

    async def record_message(self, message_type: str, duration_ms: float):
        async with self._lock:
            self._metrics["messages_processed"] += 1
            self._metrics["operations"][message_type] += 1
            self._metrics["message_durations_ms"].append(duration_ms)

    async def record_session_event(self, event_type: str):
        async with self._lock:
            self._metrics["session_events"][event_type] += 1
            if event_type == "session_started":
                self._metrics["active_sessions"] += 1
            elif event_type in ("session_closed", "session_terminated"):
                self._metrics["active_sessions"] = max(
                    0, self._metrics["active_sessions"] - 1
                )

    async def record_operation(
        self, operation_type: str, success: bool, duration_ms: Optional[float] = None
    ):
        async with self._lock:
            self._metrics["operations"][operation_type] += 1
            if not success:
                self._metrics["errors"][operation_type] += 1
            if duration_ms is not None:
                self._metrics["operation_durations_ms"].append(duration_ms)

    async def record_error(self, error_type: str):
        async with self._lock:
            self._metrics["errors"][error_type] += 1

    async def get_metrics(self) -> Dict[str, Any]:
        async with self._lock:
            # Compute summary stats
            durations = self._metrics["message_durations_ms"]
            op_durations = self._metrics["operation_durations_ms"]
            avg_msg_duration = sum(durations) / len(durations) if durations else 0
            avg_op_duration = (
                sum(op_durations) / len(op_durations) if op_durations else 0
            )
            return {
                "messages_processed": self._metrics["messages_processed"],
                "operations": dict(self._metrics["operations"]),
                "errors": dict(self._metrics["errors"]),
                "active_sessions": self._metrics["active_sessions"],
                "session_events": dict(self._metrics["session_events"]),
                "avg_message_duration_ms": avg_msg_duration,
                "avg_operation_duration_ms": avg_op_duration,
                "uptime_sec": time.time() - self._metrics["startup_time"],
            }

    async def get_health_status(self) -> Dict[str, Any]:
        async with self._lock:
            health = {
                "uptime_sec": time.time() - self._metrics["startup_time"],
                "active_sessions": self._metrics["active_sessions"],
                "messages_processed": self._metrics["messages_processed"],
                "error_count": sum(self._metrics["errors"].values()),
                "last_health_check": time.time(),
            }
            self._metrics["last_health_check"] = health["last_health_check"]
            return health

    async def reset(self):
        async with self._lock:
            self._metrics = {
                "messages_processed": 0,
                "operations": defaultdict(int),
                "errors": defaultdict(int),
                "message_durations_ms": [],
                "operation_durations_ms": [],
                "active_sessions": 0,
                "session_events": defaultdict(int),
                "last_health_check": None,
                "startup_time": time.time(),
            }


# Singleton instance for global use
global_metrics_collector = MetricsCollector()
