"""Formats an async stream of events as Server-Sent Events.

See docs/adr/0007-sse-streaming.md.
"""

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

logger = logging.getLogger(__name__)


def format_sse_event(event_type: str, data: dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


async def sse_event_stream(events: AsyncIterator[dict[str, Any]]) -> AsyncIterator[str]:
    """Format each `{"type": ..., ...}` event as SSE text.

    A `StreamingResponse` has already sent its headers by the time an
    error could occur mid-stream, so an exception here can't become an
    HTTP error response -- it's caught and sent as a final `error` SSE
    event instead, so the client at least learns the stream failed
    rather than the connection just dying.
    """
    try:
        async for event in events:
            payload = dict(event)
            event_type = payload.pop("type")
            yield format_sse_event(event_type, payload)
    except Exception:
        logger.exception("Error while streaming an SSE response")
        yield format_sse_event("error", {"detail": "Internal server error"})
