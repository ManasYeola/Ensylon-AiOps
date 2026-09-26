"""
Ingestion package — Parsing, Normalization, PII Redaction & SSE Streams.
Matches Sections 2, 3, 4, and 5 of the Technical Problem Statement.
"""
from .cloudwatch import (
    ingest_cloudwatch_alarms,
    normalize_cloudwatch,
    parse_cloudwatch_event,
)
from .grafana import (
    ingest_grafana_alerts,
    normalize_grafana,
    parse_grafana_alert,
)
from .logs import (
    load_signals,
    normalize_log,
    parse_log_line,
)
from .sse_client import (
    SIMULATOR_STREAMS,
    consume_sse_stream,
    normalize_event_by_source,
)

__all__ = [
    # CloudWatch
    "parse_cloudwatch_event",
    "normalize_cloudwatch",
    "ingest_cloudwatch_alarms",
    # Application Logs
    "parse_log_line",
    "normalize_log",
    "load_signals",
    # Grafana
    "parse_grafana_alert",
    "normalize_grafana",
    "ingest_grafana_alerts",
    # SSE Stream Client
    "consume_sse_stream",
    "normalize_event_by_source",
    "SIMULATOR_STREAMS",
]
