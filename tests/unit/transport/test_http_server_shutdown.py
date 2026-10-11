"""Tests for HTTP server graceful shutdown configuration."""

import pytest

from mcp_server_git.transport.http_server import (
    GRACEFUL_SHUTDOWN_TIMEOUT_S,
    HTTPGitServer,
)


def test_run_passes_bounded_graceful_shutdown_timeout_when_starting_uvicorn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(
        "mcp_server_git.transport.http_server.uvicorn.run",
        lambda app, **kwargs: calls.append(kwargs),
    )

    HTTPGitServer(host="127.0.0.1", port=8765, api_key=None).run()

    assert len(calls) == 1
    timeout = calls[0]["timeout_graceful_shutdown"]
    assert timeout == GRACEFUL_SHUTDOWN_TIMEOUT_S
    # Must stay below the systemd unit's TimeoutStopSec=10
    assert 0 < timeout < 10
