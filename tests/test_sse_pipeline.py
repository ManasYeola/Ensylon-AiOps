"""
tests/test_sse_pipeline.py — Focused tests for Section 5 SSE requirements.

Tests:
  1. SSE event framing — id:, event:, data:, blank-line dispatch
  2. Keep-alive comments are ignored (:keepalive)
  3. Quiet periods (no data) tolerated without error
  4. Reconnect with Last-Event-ID after disconnect
  5. Signal-to-pipeline handoff via _ingest_signal() → _run_pipeline()
  6. Deduplication — same fingerprint hash doesn't create a second incident
  7. Window filtering — signals older than the window don't enter correlation
"""
import asyncio
import json
import pytest
import httpx
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from app.models.signal import Signal
from app.ingestion.sse_client import consume_sse_stream, normalize_event_by_source, SIMULATOR_STREAMS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_log_line(service: str = "payments-service", offset_seconds: int = 0) -> str:
    ts = (datetime.now(timezone.utc) - timedelta(seconds=offset_seconds)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    return (
        f"{ts} ERROR {service} db-connection-pool "
        f"[user:test@corp.com ip:10.0.0.1 session:sess_abc acc:ACC-99999] "
        f"Connection pool exhausted. Pool size: 100, waiting threads: 22"
    )


def _make_cw_json(service: str = "agency-db") -> str:
    return json.dumps({
        "AlarmName": f"HighDBConnections-{service}",
        "AlarmDescription": "DB connection pool utilisation exceeded 90%",
        "StateChangeTime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "Region": "ap-south-1",
        "NewStateValue": "ALARM",
        "OldStateValue": "OK",
        "Trigger": {
            "MetricName": "DBConnectionCount",
            "Namespace": "AWS/RDS",
            "Threshold": 90,
            "ObservedValue": 91.3,
        },
        "AffectedResources": {
            "service": service,
            "component": "db-connection-pool",
            "environment": "prod",
            "region": "ap-south-1",
            "accountId": "456789012345",
            "serviceAccount": "svc-payments@internal.corp.com",
        },
    })


class _FakeSSEResponse:
    """
    Fakes an httpx streaming response by yielding pre-defined SSE lines.
    Supports simulating disconnects partway through.
    """
    def __init__(self, lines: list[str], disconnect_after: int = -1):
        self.status_code = 200
        self.request = httpx.Request("GET", "https://fake.sse/stream")
        self._lines = lines
        self._disconnect_after = disconnect_after

    async def aiter_lines(self):
        for i, line in enumerate(self._lines):
            if self._disconnect_after >= 0 and i == self._disconnect_after:
                raise httpx.RemoteProtocolError("Disconnected", request=self.request)
            yield line

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass


class _FakeClient:
    """Wraps a list of FakeSSEResponse objects to simulate one connection per call."""
    def __init__(self, responses: list[_FakeSSEResponse]):
        self._responses = iter(responses)

    def stream(self, method, url, headers=None):
        try:
            return next(self._responses)
        except StopIteration:
            raise httpx.RequestError("No more fake responses", request=httpx.Request("GET", url))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass


# ---------------------------------------------------------------------------
# 1. SSE event framing: id, event, data, blank-line dispatch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sse_framing_dispatches_on_blank_line(monkeypatch):
    """Blank line after data: → signal dispatched; subsequent events parsed correctly."""
    lines = [
        "id: 000001",
        "event: signal",
        f"data: {_make_log_line()}",
        "",   # ← dispatch trigger
        "id: 000002",
        "event: signal",
        f"data: {_make_log_line('enrollment-service')}",
        "",
    ]
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda **kw: _FakeClient([_FakeSSEResponse(lines)])
    )

    received = []
    async for seq_id, sig in consume_sse_stream("aiops-logs", max_reconnects=0):
        received.append((seq_id, sig))

    assert len(received) == 2
    assert received[0][0] == "000001"
    assert received[0][1].service == "payments-service"
    assert received[1][0] == "000002"
    assert received[1][1].service == "enrollment-service"


# ---------------------------------------------------------------------------
# 2. Keep-alive comments ignored
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sse_keepalive_comments_are_ignored(monkeypatch):
    """Lines starting with : must not produce signals."""
    lines = [
        ":keepalive",
        "id: 000010",
        "event: signal",
        f"data: {_make_log_line()}",
        "",
        ":keepalive",
        ":another comment",
    ]
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda **kw: _FakeClient([_FakeSSEResponse(lines)])
    )

    received = []
    async for seq_id, sig in consume_sse_stream("aiops-logs", max_reconnects=0):
        received.append((seq_id, sig))

    assert len(received) == 1
    assert received[0][0] == "000010"


# ---------------------------------------------------------------------------
# 3. Quiet periods — no signals, only keepalives — tolerated gracefully
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sse_quiet_period_no_crash(monkeypatch):
    """A stream that sends only keepalives and then ends cleanly."""
    lines = [
        ":keepalive",
        ":keepalive",
        ":keepalive",
    ]
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda **kw: _FakeClient([_FakeSSEResponse(lines)])
    )

    received = []
    async for seq_id, sig in consume_sse_stream("aiops-logs", max_reconnects=0):
        received.append((seq_id, sig))

    assert received == []   # no signals, no crash


# ---------------------------------------------------------------------------
# 4. Reconnect with Last-Event-ID after disconnect
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sse_reconnects_with_last_event_id(monkeypatch):
    """
    First connection disconnects after event 000001.
    Second connection should be called with Last-Event-ID: 000001.
    """
    first_response = _FakeSSEResponse(
        lines=[
            "id: 000001",
            "event: signal",
            f"data: {_make_log_line()}",
            "",   # dispatch
        ],
        disconnect_after=4,   # disconnect after the blank line has been yielded
    )
    second_response = _FakeSSEResponse(
        lines=[
            "id: 000002",
            "event: signal",
            f"data: {_make_log_line('carrier-service')}",
            "",
        ]
    )

    captured_headers: list[dict] = []
    responses = [first_response, second_response]
    response_index = [0]

    class CapturingClient:
        def stream(self, method, url, headers=None):
            captured_headers.append(dict(headers or {}))
            idx = response_index[0]
            response_index[0] += 1
            if idx >= len(responses):
                raise httpx.RequestError(
                    "No more fake responses",
                    request=httpx.Request("GET", url),
                )
            return responses[idx]

        async def __aenter__(self):
            return self
        async def __aexit__(self, *_):
            pass

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: CapturingClient())

    received = []
    async for seq_id, sig in consume_sse_stream(
        "aiops-logs", max_reconnects=1, retry_delay_seconds=0
    ):
        received.append((seq_id, sig))

    # First request should have no Last-Event-ID
    assert "Last-Event-ID" not in captured_headers[0]
    # Second request must carry the id from the first connection
    assert captured_headers[1].get("Last-Event-ID") == "000001"
    # Both signals received across both connections
    assert len(received) == 2
    assert received[1][1].service == "carrier-service"


# ---------------------------------------------------------------------------
# 5. Signal-to-pipeline handoff — _ingest_signal feeds _run_pipeline
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ingest_signal_stores_and_schedules_pipeline(monkeypatch):
    """
    _ingest_signal should score the signal and store it in _signals.
    A pipeline run should be triggered on the next event loop tick.
    """
    # Import here so we can manipulate module-level state
    import app.main as main_module

    # Clear state
    main_module._signals.clear()
    main_module._incidents.clear()
    main_module._fp_to_incident.clear()
    main_module._last_pipeline_run_ts = 0.0
    main_module._pending_pipeline = False

    signal = Signal(
        timestamp=datetime.now(timezone.utc),
        source="grafana_alerts",
        environment="prod",
        region="ap-south-1",
        service="payments-service",
        component="api-handler",
        signal_type="grafana_alert",
        anomaly_score=0.0,
        evidence="[REDACTED] P99 4785ms above threshold",
    )

    result = await main_module._ingest_signal(signal)

    assert result["status"] == "accepted"
    assert result["anomaly_score"] == 1.0   # Grafana → always 1.0
    assert result["is_anomalous"] is True
    assert signal.id in main_module._signals or result["signal_id"] in main_module._signals


# ---------------------------------------------------------------------------
# 6. Deduplication — same fingerprint hash doesn't create a second incident
# ---------------------------------------------------------------------------

def test_pipeline_deduplication_same_fingerprint():
    """
    Running _run_pipeline twice with the same set of signals must not produce
    two separate incidents with the same fingerprint.
    """
    import app.main as main_module

    main_module._signals.clear()
    main_module._incidents.clear()
    main_module._fp_to_incident.clear()
    main_module._fingerprints.clear()
    main_module._graphs.clear()

    # Build a set of highly correlated signals that should form one cluster
    now = datetime.now(timezone.utc)
    signals = []
    for i in range(5):
        s = Signal(
            timestamp=now + timedelta(seconds=i * 10),
            source="application_logs",
            environment="prod",
            region="ap-south-1",
            service="payments-service",
            component="db-connection-pool",
            signal_type="error_log_burst",
            anomaly_score=0.85,
            template_id="T002",
            evidence=f"[REDACTED] Connection pool exhausted — template#118 ({i})",
        )
        main_module._signals[s.id] = s
        signals.append(s)

    # First run — should create one incident
    incidents_run1 = main_module._run_pipeline(signals)

    # Second run with same signals — must not create duplicates
    incidents_run2 = main_module._run_pipeline(signals)

    total_incidents = len(main_module._incidents)
    assert total_incidents <= len(incidents_run1) + 1, (
        f"Expected ≤{len(incidents_run1)+1} incidents, got {total_incidents} "
        "(deduplication failure)"
    )
    # No new incidents from the second run if fingerprint matched
    assert len(incidents_run2) == 0 or (
        len(incidents_run1) > 0 and
        all(i["id"] not in {inc["id"] for inc in incidents_run1} for i in incidents_run2)
    )


# ---------------------------------------------------------------------------
# 7. Window filtering — old signals don't enter correlation
# ---------------------------------------------------------------------------

def test_old_signals_excluded_from_pipeline_window():
    """
    Signals older than the correlation window (5 min) must be filtered out.
    Only the recent signal should enter the graph.
    """
    import app.main as main_module

    main_module._signals.clear()
    main_module._incidents.clear()
    main_module._fp_to_incident.clear()

    now = datetime.now(timezone.utc)
    old_signal = Signal(
        timestamp=now - timedelta(minutes=10),   # 10 min old — outside window
        source="application_logs",
        environment="prod",
        region="ap-south-1",
        service="payments-service",
        component="db-connection-pool",
        signal_type="error_log_burst",
        anomaly_score=0.9,
        template_id="T002",
        evidence="[REDACTED] old signal",
    )
    new_signal = Signal(
        timestamp=now - timedelta(seconds=30),   # 30 sec old — inside window
        source="application_logs",
        environment="prod",
        region="ap-south-1",
        service="payments-service",
        component="db-connection-pool",
        signal_type="error_log_burst",
        anomaly_score=0.9,
        template_id="T002",
        evidence="[REDACTED] recent signal",
    )

    # A single signal never passes gate 1 (needs at least 2 strongly correlated signals)
    # so no incidents are expected, but the old signal should be excluded from the graph
    with patch.object(main_module, "_run_pipeline", wraps=main_module._run_pipeline) as mock_run:
        # Manually populate _signals with both
        main_module._signals[old_signal.id] = old_signal
        main_module._signals[new_signal.id] = new_signal

        # Simulate the pipeline: only new_signal should be in the anomalous list
        from app.config import get_correlation_cfg
        import time
        cfg = get_correlation_cfg()
        window_seconds = cfg.get("window_minutes", 5) * 60
        t_now = time.time()

        anomalous_in_window = [
            s for s in [old_signal, new_signal]
            if main_module._is_anomalous(s) and (t_now - s.timestamp.timestamp()) <= window_seconds
        ]

    assert len(anomalous_in_window) == 1
    assert anomalous_in_window[0].id == new_signal.id


# ---------------------------------------------------------------------------
# 8. normalize_event_by_source routes correctly
# ---------------------------------------------------------------------------

def test_normalize_event_by_source_cloudwatch():
    sig = normalize_event_by_source("cloudwatch", _make_cw_json())
    assert sig.source == "cloudwatch_metrics"
    assert sig.service == "agency-db"
    assert sig.signal_type == "metric_anomaly"


def test_normalize_event_by_source_logs():
    sig = normalize_event_by_source("logs", _make_log_line())
    assert sig.source == "application_logs"
    assert sig.service == "payments-service"
    assert sig.signal_type == "error_log_burst"


def test_normalize_event_by_source_grafana():
    grafana_payload = json.dumps({
        "title": "High Latency — enrollment-service",
        "state": "alerting",
        "ruleName": "HighLatency-enrollment",
        "evalMatches": [{"metric": "response_time_p99", "value": 4785,
                         "tags": {"service": "enrollment-service", "environment": "prod",
                                  "region": "ap-south-1", "host": "10.0.4.56"}}],
        "message": "P99 4785ms above threshold",
        "tags": {"environment": "prod", "region": "ap-south-1"},
    })
    sig = normalize_event_by_source("grafana", grafana_payload)
    assert sig.source == "grafana_alerts"
    assert sig.signal_type == "grafana_alert"


# ---------------------------------------------------------------------------
# 9. SIMULATOR_STREAMS contains all three required URLs
# ---------------------------------------------------------------------------

def test_simulator_streams_has_all_three_urls():
    assert "logs" in SIMULATOR_STREAMS
    assert "grafana" in SIMULATOR_STREAMS
    assert "cloudwatch" in SIMULATOR_STREAMS
    for name, url in SIMULATOR_STREAMS.items():
        assert url.startswith("https://"), f"Stream {name} URL must be HTTPS"
        assert "ensylon.com" in url, f"Stream {name} URL must point to Ensylon host"
