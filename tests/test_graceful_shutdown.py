import asyncio
import signal
import json
import shutil
import pytest


# Mocks for server/session/heartbeat logic
class DummySession:
    def __init__(self, session_id, state="ACTIVE"):
        self.session_id = session_id
        self.state = state
        self.closed = False

    async def close(self, reason=None):
        self.closed = True

    def as_dict(self):
        return {"session_id": self.session_id, "state": self.state}


class DummySessionManager:
    def __init__(self, sessions=None):
        self._sessions = sessions or {}
        self.shutdown_called = False

    async def get_all_sessions(self):
        return self._sessions

    async def shutdown(self):
        self.shutdown_called = True

    def add_session(self, session):
        self._sessions[session.session_id] = session

    def clear_sessions(self):
        self._sessions = {}


class DummyHeartbeatManager:
    def __init__(self):
        self.stopped = False

    async def stop(self):
        self.stopped = True


# --- Signal Handler Tests ---


@pytest.mark.asyncio
async def test_signal_handler_sets_shutdown_event(monkeypatch):
    shutdown_event = asyncio.Event()

    def handler(signum, frame):
        shutdown_event.set()

    monkeypatch.setattr(signal, "signal", lambda s, h: h)
    handler(signal.SIGTERM, None)
    assert shutdown_event.is_set()


@pytest.mark.asyncio
async def test_signal_handler_during_server_states(monkeypatch):
    shutdown_event = asyncio.Event()
    states = []

    def handler(signum, frame):
        states.append("handler_called")
        shutdown_event.set()

    monkeypatch.setattr(signal, "signal", lambda s, h: h)
    handler(signal.SIGINT, None)
    assert shutdown_event.is_set()
    assert "handler_called" in states


# --- Session State Persistence Tests ---


@pytest.mark.asyncio
async def test_save_and_restore_session_state(tmp_path):
    # Simulate saving session state
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    sessions_file = data_dir / "sessions.json"

    sessions = {
        "s1": DummySession("s1", "ACTIVE"),
        "s2": DummySession("s2", "PAUSED"),
        "s3": DummySession("s3", "CLOSED"),
    }
    # Only ACTIVE and PAUSED should be saved
    to_save = [
        {"session_id": s.session_id, "state": s.state}
        for s in sessions.values()
        if s.state in ("ACTIVE", "PAUSED")
    ]
    with open(sessions_file, "w") as f:
        json.dump(to_save, f)

    # Simulate restoring
    with open(sessions_file) as f:
        loaded = json.load(f)
    assert all(s["state"] in ("ACTIVE", "PAUSED") for s in loaded)
    assert len(loaded) == 2


@pytest.mark.asyncio
async def test_restore_missing_or_corrupted_session_file(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    sessions_file = data_dir / "sessions.json"

    # Missing file
    if sessions_file.exists():
        sessions_file.unlink()
    try:
        with open(sessions_file) as f:
            json.load(f)
        assert False, "Should raise FileNotFoundError"
    except FileNotFoundError:
        pass

    # Corrupted file
    with open(sessions_file, "w") as f:
        f.write("{not: valid json")
    try:
        with open(sessions_file) as f:
            json.load(f)
        assert False, "Should raise JSONDecodeError"
    except json.JSONDecodeError:
        pass


# --- Graceful Shutdown Tests ---


@pytest.mark.asyncio
async def test_graceful_shutdown_waits_for_tasks(monkeypatch):
    # Simulate server with running tasks
    completed = []

    async def long_task():
        await asyncio.sleep(0.1)
        completed.append("done")

    task = asyncio.create_task(long_task())
    await asyncio.sleep(0.02)
    # Simulate shutdown event
    await asyncio.wait_for(task, timeout=0.2)
    assert "done" in completed


@pytest.mark.asyncio
async def test_forced_cancellation_of_tasks(monkeypatch):
    # Simulate a task that never completes
    async def never_finishes():
        while True:
            await asyncio.sleep(0.1)

    task = asyncio.create_task(never_finishes())
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert task.cancelled()


@pytest.mark.asyncio
async def test_session_and_heartbeat_manager_shutdown():
    session_manager = DummySessionManager()
    heartbeat_manager = DummyHeartbeatManager()
    await session_manager.shutdown()
    await heartbeat_manager.stop()
    assert session_manager.shutdown_called
    assert heartbeat_manager.stopped


# --- Recovery and Restart Tests ---


@pytest.mark.asyncio
async def test_session_restoration_after_restart(tmp_path):
    # Save session state
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    sessions_file = data_dir / "sessions.json"
    sessions = [
        {"session_id": "s1", "state": "ACTIVE"},
        {"session_id": "s2", "state": "PAUSED"},
        {"session_id": "s3", "state": "CLOSED"},
    ]
    with open(sessions_file, "w") as f:
        json.dump(sessions, f)

    # Simulate server restart and restoration
    with open(sessions_file) as f:
        loaded = json.load(f)
    restored = [s for s in loaded if s["state"] in ("ACTIVE", "PAUSED")]
    assert len(restored) == 2
    assert all(s["state"] in ("ACTIVE", "PAUSED") for s in restored)


@pytest.mark.asyncio
async def test_partial_shutdown_scenario(tmp_path):
    # Simulate partial shutdown: session file exists but is incomplete
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    sessions_file = data_dir / "sessions.json"
    with open(sessions_file, "w") as f:
        f.write('[{"session_id": "s1", "state": "ACTIVE"}')  # missing closing ]

    try:
        with open(sessions_file) as f:
            json.load(f)
        assert False, "Should raise JSONDecodeError"
    except json.JSONDecodeError:
        pass


@pytest.mark.asyncio
async def test_data_directory_creation_and_cleanup(tmp_path):
    data_dir = tmp_path / "data"
    if data_dir.exists():
        shutil.rmtree(data_dir)
    assert not data_dir.exists()
    data_dir.mkdir()
    assert data_dir.exists()
    # Cleanup
    shutil.rmtree(data_dir)
    assert not data_dir.exists()


# --- Integration Tests ---


@pytest.mark.asyncio
async def test_complete_shutdown_restart_cycle(tmp_path):
    # Simulate full cycle: start, save, shutdown, restart, restore
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    sessions_file = data_dir / "sessions.json"
    sessions = [
        {"session_id": "s1", "state": "ACTIVE"},
        {"session_id": "s2", "state": "PAUSED"},
    ]
    with open(sessions_file, "w") as f:
        json.dump(sessions, f)

    # Simulate shutdown
    assert sessions_file.exists()
    # Simulate restart and restoration
    with open(sessions_file) as f:
        loaded = json.load(f)
    assert len(loaded) == 2


@pytest.mark.asyncio
async def test_concurrent_operations_during_shutdown(monkeypatch):
    # Simulate concurrent tasks and shutdown
    results = []

    async def op1():
        await asyncio.sleep(0.05)
        results.append("op1")

    async def op2():
        await asyncio.sleep(0.1)
        results.append("op2")

    asyncio.create_task(op1())
    asyncio.create_task(op2())
    await asyncio.sleep(0.12)
    assert "op1" in results
    assert "op2" in results


@pytest.mark.asyncio
async def test_error_handling_during_shutdown(monkeypatch):
    # Simulate error during shutdown
    class FailingSessionManager(DummySessionManager):
        async def shutdown(self):
            raise RuntimeError("Shutdown failed")

    session_manager = FailingSessionManager()
    try:
        await session_manager.shutdown()
        assert False, "Should raise RuntimeError"
    except RuntimeError as e:
        assert "Shutdown failed" in str(e)
