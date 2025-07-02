import asyncio
import logging
import json
import pytest

from mcp_server_git.logging_config import StructuredLogFormatter
from mcp_server_git.metrics import MetricsCollector


def test_structured_log_formatter_basic():
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Test message",
        args=(),
        exc_info=None,
    )
    record.session_id = "sess-123"
    record.request_id = "req-456"
    record.duration_ms = 42
    formatter = StructuredLogFormatter()
    output = formatter.format(record)
    data = json.loads(output)
    assert data["level"] == "INFO"
    assert data["logger"] == "test_logger"
    assert data["message"] == "Test message"
    assert data["session_id"] == "sess-123"
    assert data["request_id"] == "req-456"
    assert data["duration_ms"] == 42


def test_structured_log_formatter_exception():
    try:
        raise ValueError("fail!")
    except Exception:
        import sys

        record = logging.LogRecord(
            name="test_logger",
            level=logging.ERROR,
            pathname=__file__,
            lineno=20,
            msg="Error occurred",
            args=(),
            exc_info=sys.exc_info(),
        )
        formatter = StructuredLogFormatter()
        output = formatter.format(record)
        data = json.loads(output)
        assert data["level"] == "ERROR"
        assert "exception" in data
        assert "ValueError" in data["exception"]


@pytest.mark.asyncio
async def test_metrics_collector_basic():
    metrics = MetricsCollector()
    await metrics.record_message("test_msg", 12.5)
    await metrics.record_operation("op1", True, 8.0)
    await metrics.record_operation("op1", False, 10.0)
    await metrics.record_session_event("session_started")
    await metrics.record_session_event("session_closed")
    await metrics.record_error("custom_error")
    stats = await metrics.get_metrics()
    assert stats["messages_processed"] == 1
    assert stats["operations"]["test_msg"] == 1
    assert stats["operations"]["op1"] == 2
    assert stats["errors"]["op1"] == 1
    assert stats["errors"]["custom_error"] == 1
    assert stats["active_sessions"] == 0
    assert stats["session_events"]["session_started"] == 1
    assert stats["session_events"]["session_closed"] == 1
    assert stats["avg_message_duration_ms"] > 0
    assert stats["avg_operation_duration_ms"] > 0


@pytest.mark.asyncio
async def test_metrics_collector_concurrent():
    metrics = MetricsCollector()

    async def worker():
        for _ in range(10):
            await metrics.record_message("msg", 1.0)
            await metrics.record_operation("op", True, 2.0)

    await asyncio.gather(*(worker() for _ in range(5)))
    stats = await metrics.get_metrics()
    assert stats["messages_processed"] == 50
    assert stats["operations"]["msg"] == 50
    assert stats["operations"]["op"] == 50


@pytest.mark.asyncio
async def test_metrics_collector_health_status():
    metrics = MetricsCollector()
    await metrics.record_session_event("session_started")
    await metrics.record_message("msg", 1.0)
    health = await metrics.get_health_status()
    assert "uptime_sec" in health
    assert health["active_sessions"] == 1
    assert health["messages_processed"] == 1
    assert "error_count" in health


@pytest.mark.asyncio
async def test_metrics_collector_reset():
    metrics = MetricsCollector()
    await metrics.record_message("msg", 1.0)
    await metrics.record_operation("op", False, 2.0)
    await metrics.record_session_event("session_started")
    await metrics.reset()
    stats = await metrics.get_metrics()
    assert stats["messages_processed"] == 0
    assert stats["operations"] == {}
    assert stats["errors"] == {}
    assert stats["active_sessions"] == 0


@pytest.mark.asyncio
async def test_metrics_collector_integration_with_session_metrics():
    # Simulate integration: session events and message/operation tracking
    metrics = MetricsCollector()
    await metrics.record_session_event("session_started")
    await metrics.record_operation("tool_call", True, 5.0)
    await metrics.record_session_event("session_closed")
    stats = await metrics.get_metrics()
    assert stats["active_sessions"] == 0
    assert stats["session_events"]["session_started"] == 1
    assert stats["session_events"]["session_closed"] == 1
    assert stats["operations"]["tool_call"] == 1
    assert stats["messages_processed"] == 0  # Only recorded operation, not message
