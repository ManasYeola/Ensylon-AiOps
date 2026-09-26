"""
Server-Sent Events (SSE) Client for Signal Simulator Streams.
Matches Section 5 of the Technical Problem Statement.
"""
import asyncio
import logging
from typing import Any, AsyncIterator, Callable, Dict, Optional, Tuple, Union
import httpx

from app.models.signal import Signal
from app.ingestion.cloudwatch import normalize_cloudwatch
from app.ingestion.logs import normalize_log
from app.ingestion.grafana import normalize_grafana

logger = logging.getLogger(__name__)

SIMULATOR_STREAMS: Dict[str, str] = {
    "logs": "https://logs.nonprod.nexus.ensylon.com/sim/stream/aiops-logs",
    "grafana": "https://logs.nonprod.nexus.ensylon.com/sim/stream/aiops-grafana",
    "cloudwatch": "https://logs.nonprod.nexus.ensylon.com/sim/stream/aiops-cloudwatch",
}


def normalize_event_by_source(source_type: str, data: str) -> Signal:
    """
    Route raw payload string to appropriate normalizer.
    Redaction occurs before any Signal construction.
    """
    src = source_type.lower()
    if "cloudwatch" in src:
        return normalize_cloudwatch(data)
    elif "grafana" in src:
        return normalize_grafana(data)
    elif "log" in src:
        return normalize_log(data)
    else:
        raise ValueError(f"Unknown or unsupported source_type '{source_type}' for event payload.")


async def consume_sse_stream(
    url: str,
    source_type: Optional[str] = None,
    last_event_id: Optional[str] = None,
    max_reconnects: int = -1,
    retry_delay_seconds: float = 2.0,
    persist_to_db: bool = False,
    on_signal: Optional[Callable[[Signal, str], Any]] = None,
) -> AsyncIterator[Tuple[str, Signal]]:
    """
    Connect to an SSE stream over HTTPS, process signals, and automatically resume
    with Last-Event-ID if disconnected.

    Args:
        url: Full SSE stream URL or key in SIMULATOR_STREAMS.
        source_type: Optional source identifier ('logs', 'grafana', 'cloudwatch').
                     Inferred from url if omitted.
        last_event_id: Initial sequence ID to resume from.
        max_reconnects: Maximum reconnection attempts (-1 for indefinite).
        retry_delay_seconds: Delay before reconnecting.
        on_signal: Optional callback invoked for each signal.

    Yields:
        Tuple of (sequence_id, CanonicalSignal).
    """
    stream_url = SIMULATOR_STREAMS.get(url, url)
    if not source_type:
        for key in ("cloudwatch", "grafana", "logs"):
            if key in stream_url:
                source_type = key
                break
        if not source_type:
            source_type = "logs"

    current_last_id = last_event_id
    reconnect_attempts = 0

    while True:
        headers = {
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
        }
        if current_last_id:
            headers["Last-Event-ID"] = str(current_last_id)

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=None)) as client:
                async with client.stream("GET", stream_url, headers=headers) as response:
                    if response.status_code != 200:
                        logger.error("SSE stream returned HTTP %d", response.status_code)
                        raise httpx.HTTPStatusError("Bad SSE status", request=response.request, response=response)

                    reconnect_attempts = 0
                    event_id: Optional[str] = None
                    event_type: str = "message"
                    data_lines: list[str] = []

                    async for line in response.aiter_lines():
                        # SSE keepalive comment or empty heartbeat
                        if not line:
                            # End of SSE block: dispatch if data accumulated
                            if data_lines:
                                payload = "\n".join(data_lines)
                                data_lines = []
                                current_id = event_id or current_last_id or ""
                                if event_id:
                                    current_last_id = event_id

                                signal = normalize_event_by_source(source_type, payload)
                                if persist_to_db:
                                    from app.storage.db import save_signal
                                    save_signal(signal)

                                if on_signal:
                                    res = on_signal(signal, current_id)
                                    if asyncio.iscoroutine(res):
                                        await res
                                yield current_id, signal

                            event_id = None
                            event_type = "message"
                            continue

                        # Comments (e.g. :keepalive every 15s)
                        if line.startswith(":"):
                            continue

                        if line.startswith("id:"):
                            event_id = line[3:].strip()
                        elif line.startswith("event:"):
                            event_type = line[6:].strip()
                        elif line.startswith("data:"):
                            data_lines.append(line[5:].lstrip())

                    # Stream closed normally by server / end of generator
                    if max_reconnects == 0:
                        break
                    reconnect_attempts += 1
                    if 0 <= max_reconnects < reconnect_attempts:
                        break
                    await asyncio.sleep(retry_delay_seconds)

        except (httpx.RequestError, httpx.HTTPStatusError, asyncio.CancelledError) as exc:
            if isinstance(exc, asyncio.CancelledError):
                logger.info("SSE consumption cancelled for %s", stream_url)
                raise

            reconnect_attempts += 1
            if 0 <= max_reconnects < reconnect_attempts:
                logger.warning("Max reconnects (%d) reached for %s", max_reconnects, stream_url)
                break

            logger.warning(
                "SSE stream connection lost (%s). Reconnecting in %.1fs with Last-Event-ID=%s...",
                exc,
                retry_delay_seconds,
                current_last_id,
            )
            await asyncio.sleep(retry_delay_seconds)
