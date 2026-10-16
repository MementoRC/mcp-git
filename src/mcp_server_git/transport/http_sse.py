"""Server-Sent Events support for the MCP HTTP transport."""

import asyncio
from collections.abc import AsyncGenerator

from fastapi.responses import StreamingResponse


async def heartbeat_events() -> AsyncGenerator[str, None]:
    """Generate SSE events.

    TODO: Expand to send actual MCP notifications:
    - Tool execution progress events
    - Repository state change notifications
    - Session health updates
    Currently only sends heartbeats for connection keepalive.
    """
    try:
        # Keep connection alive with periodic heartbeats
        while True:
            # Send heartbeat comment every 30 seconds
            yield ": heartbeat\n\n"
            await asyncio.sleep(30)
    except asyncio.CancelledError:
        pass


def build_sse_response() -> StreamingResponse:
    """Build the text/event-stream response for GET /mcp."""
    return StreamingResponse(
        heartbeat_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
