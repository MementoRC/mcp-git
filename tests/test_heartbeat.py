import asyncio
import pytest

from mcp_server_git.session import SessionManager, HeartbeatManager


@pytest.mark.asyncio
class TestHeartbeatManager:
    @pytest.fixture
    async def session_manager(self):
        mgr = SessionManager(idle_timeout=100, heartbeat_timeout=10)
        yield mgr
        await mgr.shutdown()

    @pytest.fixture
    async def heartbeat_manager(self, session_manager):
        hb = HeartbeatManager(
            session_manager, heartbeat_interval=0.05, missed_threshold=2
        )
        await hb.start()
        yield hb
        await hb.stop()

    @pytest.mark.asyncio
    async def test_heartbeat_record_and_metrics(
        self, session_manager, heartbeat_manager
    ):
        session = await session_manager.create_session("hb-test")
        await heartbeat_manager.record_heartbeat("hb-test")
        last = heartbeat_manager.get_last_heartbeat("hb-test")
        assert last is not None
        await session.handle_heartbeat()
        metrics = session.get_metrics()
        assert metrics["heartbeat_count"] == 1

    @pytest.mark.asyncio
    async def test_missed_heartbeat_triggers_cleanup(self, session_manager):
        hb = HeartbeatManager(
            session_manager, heartbeat_interval=0.05, missed_threshold=1
        )
        await hb.start()
        await session_manager.create_session("missed-hb")
        await hb.record_heartbeat("missed-hb")
        # Wait for heartbeat loop to detect missed heartbeat
        await asyncio.sleep(0.2)
        # Session should be closed and removed
        s = await session_manager.get_session("missed-hb")
        assert s is None
        await hb.stop()

    @pytest.mark.asyncio
    async def test_concurrent_heartbeats(self, session_manager, heartbeat_manager):
        sessions = []
        for i in range(5):
            s = await session_manager.create_session(f"concurrent-{i}")
            sessions.append(s)
            await heartbeat_manager.record_heartbeat(f"concurrent-{i}")
        await asyncio.sleep(0.1)
        for i in range(5):
            assert heartbeat_manager.get_last_heartbeat(f"concurrent-{i}") is not None

    @pytest.mark.asyncio
    async def test_heartbeat_metrics_increment(
        self, session_manager, heartbeat_manager
    ):
        session = await session_manager.create_session("metrics-hb")
        for _ in range(3):
            await heartbeat_manager.record_heartbeat("metrics-hb")
            await session.handle_heartbeat()
        metrics = session.get_metrics()
        assert metrics["heartbeat_count"] == 3

    @pytest.mark.asyncio
    async def test_heartbeat_manager_stop(self, session_manager):
        hb = HeartbeatManager(
            session_manager, heartbeat_interval=0.05, missed_threshold=1
        )
        await hb.start()
        await hb.stop()
        assert not hb._running

    @pytest.mark.asyncio
    async def test_heartbeat_cleanup_on_shutdown(self, session_manager):
        hb = HeartbeatManager(
            session_manager, heartbeat_interval=0.05, missed_threshold=1
        )
        session_manager.heartbeat_manager = hb  # Associate the heartbeat manager
        await hb.start()
        await session_manager.create_session("shutdown-hb")
        await hb.record_heartbeat("shutdown-hb")
        await session_manager.shutdown()
        # After shutdown, session should be closed and heartbeat manager stopped
        s = await session_manager.get_session("shutdown-hb")
        assert s is None
        assert not hb._running
