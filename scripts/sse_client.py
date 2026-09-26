"""
SSE Client for Ensylon AIOps Simulator.
Connects to the 3 live SSE streams, parses incoming raw events, and pushes
the normalised Signals into the AIOps pipeline via the REST API.
"""
import asyncio
import httpx
import json
import logging
import os
from typing import Optional

from app.ingestion.logs import parse_log_line
from app.ingestion.cloudwatch import ingest_cloudwatch_alarms
from app.ingestion.grafana import ingest_grafana_alerts

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger("sse_client")

SIMULATOR_BASE_URL = "https://logs.nonprod.nexus.ensylon.com/sim/stream"
API_URL = os.getenv("API_URL", "http://localhost:8000/api/signals")


async def push_to_api(client: httpx.AsyncClient, signal) -> None:
    try:
        payload = signal.model_dump(mode="json")
        resp = await client.post(API_URL, json=payload)
        resp.raise_for_status()
        logger.debug(f"Pushed signal {signal.id} to API")
    except Exception as e:
        logger.error(f"Failed to push signal {signal.id} to API: {e}")


async def process_sse_stream(stream_name: str, parser_func):
    url = f"{SIMULATOR_BASE_URL}/{stream_name}"
    logger.info(f"Connecting to {url}...")
    
    # We maintain our own httpx client for pushing to our backend API
    async with httpx.AsyncClient() as api_client:
        while True:
            try:
                async with httpx.AsyncClient(timeout=None) as sse_client:
                    async with sse_client.stream("GET", url) as response:
                        response.raise_for_status()
                        logger.info(f"Connected to {stream_name} stream.")
                        
                        buffer = ""
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                data = line[6:].strip()
                                if data == ":keepalive":
                                    continue
                                
                                # Parse the raw data
                                try:
                                    signals = parser_func(data)
                                    if not isinstance(signals, list):
                                        signals = [signals] if signals else []
                                    
                                    for s in signals:
                                        await push_to_api(api_client, s)
                                except Exception as e:
                                    logger.error(f"Error parsing data from {stream_name}: {e}")
            except httpx.RequestError as e:
                logger.warning(f"Connection dropped on {stream_name}: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Unexpected error on {stream_name}: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)


def parse_cloudwatch(data: str):
    try:
        raw = json.loads(data)
        return ingest_cloudwatch_alarms([raw])
    except json.JSONDecodeError:
        return []


def parse_grafana(data: str):
    try:
        raw = json.loads(data)
        return ingest_grafana_alerts(raw)
    except json.JSONDecodeError:
        return []


async def main():
    logger.info("Starting SSE clients for all 3 streams...")
    await asyncio.gather(
        process_sse_stream("aiops-logs", parse_log_line),
        process_sse_stream("aiops-cloudwatch", parse_cloudwatch),
        process_sse_stream("aiops-grafana", parse_grafana),
    )

if __name__ == "__main__":
    asyncio.run(main())
