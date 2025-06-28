"""
Session management module for MCP Git Server.

- Manages session lifecycle, health, and metrics.
- Integrates with error_handling (ErrorContext, CircuitBreaker).
- Compatible with MCP ServerSession and async/await patterns.
"""

import asyncio
import logging
import time
from enum import Enum, auto
from typing import Optional, Dict, Any
from pathlib import Path
from dataclasses import dataclass, field

from mcp.server.session import ServerSession

from .error_handling import (
    ErrorContext,
    classify_error,
    CircuitBreaker,
    get_circuit_breaker,
)

logger = logging.getLogger(__name__)


class SessionState(Enum):
    CREATED = auto()
    ACTIVE = auto()
    PAUSED = auto()
    ERROR = auto()
    CLOSING = auto()
    CLOSED = auto()


@dataclass
class SessionMetrics:
    start_time: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    error_count: int = 0
    command_count: int = 0
    idle_timeouts: int = 0
    heartbeat_timeouts: int = 0
    heartbeat_count: int = 0
    state_transitions: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "start_time": self.start_time,
            "last_active": self.last_active,
            "last_heartbeat": self.last_heartbeat,
            "error_count": self.error_count,
            "command_count": self.command_count,
            "idle_timeouts": self.idle_timeouts,
            "heartbeat_timeouts": self.heartbeat_timeouts,
            "heartbeat_count": self.heartbeat_count,
            "state_transitions": self.state_transitions,
            "uptime": time.time() - self.start_time,
            "idle_time": time.time() - self.last_active,
            "heartbeat_age": time.time() - self.last_heartbeat,
        }


class Session:
    """
    Represents a single MCP Git Server session.
    Manages lifecycle, health, error handling, and metrics.
    """

    def __init__(
        self,
        session_id: str,
        user: Optional[str] = None,
        repository: Optional[Path] = None,
        idle_timeout: float = 900.0,  # 15 minutes default
        heartbeat_timeout: float = 60.0,  # 1 minute default
    ):
        self.session_id = session_id
        self.user = user
        self.repository = repository
        self.state = SessionState.CREATED
        self.metrics = SessionMetrics()
        self._lock = asyncio.Lock()
        self._error_context: Optional[ErrorContext] = None
        self._circuit: CircuitBreaker = get_circuit_breaker(f"session-{session_id}")
        self._idle_timeout = idle_timeout
        self._heartbeat_timeout = heartbeat_timeout
        self._cleanup_task: Optional[asyncio.Task] = None
        self._server_session: Optional[ServerSession] = None
        self._closed_event = asyncio.Event()
        logger.info(f"Session {self.session_id} created")

    @property
    def is_active(self) -> bool:
        return self.state == SessionState.ACTIVE

    @property
    def is_closed(self) -> bool:
        return self.state == SessionState.CLOSED

    def attach_server_session(self, server_session: ServerSession):
        self._server_session = server_session

    async def start(self):
        async with self._lock:
            if self.state in (SessionState.CLOSED, SessionState.CLOSING):
                logger.warning(
                    f"Session {self.session_id} cannot be started (already closed)"
                )
                return
            self.state = SessionState.ACTIVE
            self.metrics.state_transitions += 1
            now = time.time()
            self.metrics.last_active = now
            self.metrics.last_heartbeat = now
            logger.info(f"Session {self.session_id} started")
            if not self._cleanup_task:
                self._cleanup_task = asyncio.create_task(self._idle_cleanup_loop())

    async def pause(self):
        async with self._lock:
            if self.state != SessionState.ACTIVE:
                logger.warning(
                    f"Session {self.session_id} cannot be paused (not active)"
                )
                return
            self.state = SessionState.PAUSED
            self.metrics.state_transitions += 1
            logger.info(f"Session {self.session_id} paused")

    async def resume(self):
        async with self._lock:
            if self.state != SessionState.PAUSED:
                logger.warning(
                    f"Session {self.session_id} cannot be resumed (not paused)"
                )
                return
            self.state = SessionState.ACTIVE
            self.metrics.state_transitions += 1
            self.metrics.last_active = time.time()
            logger.info(f"Session {self.session_id} resumed")

    async def close(self, reason: Optional[str] = None):
        async with self._lock:
            if self.state in (SessionState.CLOSING, SessionState.CLOSED):
                return
            self.state = SessionState.CLOSING
            self.metrics.state_transitions += 1
            logger.info(
                f"Session {self.session_id} closing..."
                + (f" Reason: {reason}" if reason else "")
            )
            if self._cleanup_task:
                self._cleanup_task.cancel()
                try:
                    await self._cleanup_task
                except asyncio.CancelledError:
                    pass
            self.state = SessionState.CLOSED
            self.metrics.state_transitions += 1
            self._closed_event.set()
            logger.info(f"Session {self.session_id} closed")

    async def wait_closed(self):
        await self._closed_event.wait()

    async def handle_command(self, command_name: str, *args, **kwargs):
        """
        Handle a command within the session, with error handling and metrics.
        """
        async with self._lock:
            if self.state != SessionState.ACTIVE:
                logger.warning(
                    f"Session {self.session_id} is not active (state={self.state})"
                )
                raise RuntimeError("Session is not active")
            self.metrics.command_count += 1
            self.metrics.last_active = time.time()
        try:
            if not self._circuit.allow_request():
                raise RuntimeError(
                    f"Session circuit breaker is open for {self.session_id}"
                )
            # Placeholder: actual command handling logic should be injected/called here
            logger.debug(f"Session {self.session_id} handling command: {command_name}")
            # Simulate command execution
            await asyncio.sleep(0)
        except Exception as e:
            self.metrics.error_count += 1
            error_ctx = classify_error(e, operation=command_name)
            self._error_context = error_ctx
            self._circuit.record_failure()
            logger.error(
                f"Session {self.session_id} error in command '{command_name}': {e}"
            )
            # Optionally: escalate or handle error context
            raise
        else:
            self._circuit.record_success()

    async def _idle_cleanup_loop(self):
        """
        Periodically checks for idle and heartbeat timeouts and closes the session if needed.
        """
        try:
            while self.state not in (SessionState.CLOSING, SessionState.CLOSED):
                await asyncio.sleep(1.0)
                now = time.time()
                idle_time = now - self.metrics.last_active
                heartbeat_age = now - self.metrics.last_heartbeat
                if idle_time > self._idle_timeout:
                    logger.info(
                        f"Session {self.session_id} idle for {idle_time:.1f}s, closing due to idle timeout"
                    )
                    self.metrics.idle_timeouts += 1
                    await self.close(reason="idle timeout")
                    break
                if (
                    self._heartbeat_timeout > 0
                    and heartbeat_age > self._heartbeat_timeout
                ):
                    logger.info(
                        f"Session {self.session_id} heartbeat timeout ({heartbeat_age:.1f}s > {self._heartbeat_timeout:.1f}s), closing"
                    )
                    self.metrics.heartbeat_timeouts += 1
                    await self.close(reason="heartbeat timeout")
                    break
        except asyncio.CancelledError:
            logger.debug(f"Session {self.session_id} idle cleanup task cancelled")
        except Exception as e:
            logger.error(f"Session {self.session_id} idle cleanup error: {e}")

    async def handle_heartbeat(self):
        """
        Handle a heartbeat signal for this session.
        Updates heartbeat metrics and last_heartbeat timestamp.
        """
        async with self._lock:
            if self.state in (SessionState.CLOSING, SessionState.CLOSED):
                logger.warning(
                    f"Session {self.session_id} received heartbeat but is closed"
                )
                return
            now = time.time()
            self.metrics.last_heartbeat = now
            self.metrics.heartbeat_count += 1
            logger.debug(f"Session {self.session_id} heartbeat received at {now}")

    def get_metrics(self) -> Dict[str, Any]:
        return self.metrics.as_dict()

    def get_state(self) -> str:
        return self.state.name

    def get_error_context(self) -> Optional[ErrorContext]:
        return self._error_context

    def get_circuit_stats(self) -> Dict[str, Any]:
        return self._circuit.get_stats()

    def __repr__(self):
        return (
            f"<Session id={self.session_id} state={self.state.name} user={self.user}>"
        )


class SessionManager:
    """
    Manages all active MCP Git Server sessions.
    Provides session creation, lookup, cleanup, and metrics.
    """

    def __init__(self, idle_timeout: float = 900.0, heartbeat_timeout: float = 60.0):
        self._sessions: Dict[str, Session] = {}
        self._lock = asyncio.Lock()
        self._idle_timeout = idle_timeout
        self._heartbeat_timeout = heartbeat_timeout

    async def create_session(
        self,
        session_id: str,
        user: Optional[str] = None,
        repository: Optional[Path] = None,
    ) -> Session:
        async with self._lock:
            if session_id in self._sessions:
                logger.warning(
                    f"Session {session_id} already exists, returning existing session"
                )
                return self._sessions[session_id]
            session = Session(
                session_id,
                user=user,
                repository=repository,
                idle_timeout=self._idle_timeout,
                heartbeat_timeout=self._heartbeat_timeout,
            )
            self._sessions[session_id] = session
            await session.start()
            logger.info(f"SessionManager: Created and started session {session_id}")
            return session

    async def get_session(self, session_id: str) -> Optional[Session]:
        async with self._lock:
            return self._sessions.get(session_id)

    async def close_session(self, session_id: str):
        async with self._lock:
            session = self._sessions.get(session_id)
            if session:
                await session.close()
                del self._sessions[session_id]
                logger.info(f"SessionManager: Closed and removed session {session_id}")

    async def cleanup_idle_sessions(self):
        """
        Closes sessions that are idle past the timeout.
        """
        async with self._lock:
            to_close = []
            now = time.time()
            for session_id, session in self._sessions.items():
                idle_time = now - session.metrics.last_active
                if (
                    session.state == SessionState.ACTIVE
                    and idle_time > self._idle_timeout
                ):
                    to_close.append(session_id)
            for session_id in to_close:
                logger.info(f"SessionManager: Cleaning up idle session {session_id}")
                await self._sessions[session_id].close()
                del self._sessions[session_id]

    async def get_all_sessions(self) -> Dict[str, Session]:
        async with self._lock:
            return dict(self._sessions)

    async def get_metrics(self) -> Dict[str, Any]:
        async with self._lock:
            return {
                sid: session.get_metrics() for sid, session in self._sessions.items()
            }

    async def shutdown(self):
        """
        Gracefully close all sessions.
        """
        async with self._lock:
            logger.info("SessionManager: Shutting down all sessions")
            for session in list(self._sessions.values()):
                await session.close()
            self._sessions.clear()
            logger.info("SessionManager: All sessions closed")
