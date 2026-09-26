"""
Comprehensive test suite for Ingestion, PII Redaction, Normalization,
and SSE Stream Handling according to Sections 2, 3, 4, and 5 of Problem Statement.
"""
import asyncio
import json
import pytest
from datetime import datetime, timezone
import httpx

from app.models.signal import Signal, CanonicalSignal
from app.redaction.pii import redact_text, redact_dict
from app.ingestion.cloudwatch import parse_cloudwatch_event, normalize_cloudwatch
from app.ingestion.logs import parse_log_dict, parse_log_line, normalize_log
from app.ingestion.grafana import parse_grafana_alert, normalize_grafana
from app.ingestion.sse_client import consume_sse_stream, normalize_event_by_source


# ===========================================================================
# 1. PII Redaction Tests (Section 2 & Section 3)
# ===========================================================================

def test_pii_redaction_email_and_svc_account():
    text = "Error for neha.joshi@acmecorp.com handled by svc-payments@internal.corp.com"
    redacted = redact_text(text)
    assert "neha.joshi@acmecorp.com" not in redacted
    assert "svc-payments@internal.corp.com" not in redacted
    assert "[REDACTED_EMAIL]" in redacted
    assert "[REDACTED_SVC_ACCOUNT]" in redacted


def test_pii_redaction_sessions_and_accounts():
    text = "user session:sess_kd3dxt and session: sess_58917o with acc: ACC-10000181"
    redacted = redact_text(text)
    assert "sess_kd3dxt" not in redacted
    assert "sess_58917o" not in redacted
    assert "ACC-10000181" not in redacted
    assert "[REDACTED_SESSION]" in redacted
    assert "[REDACTED_ACCOUNT]" in redacted


def test_pii_redaction_ip_and_account_id():
    text = "Connecting from 10.0.2.83 for AWS account 456789012345"
    redacted = redact_text(text)
    assert "10.0.2.83" not in redacted
    assert "456789012345" not in redacted
    assert "[REDACTED_IP]" in redacted
    assert "[REDACTED_ACCOUNT_ID]" in redacted


def test_pii_redaction_customer_name():
    text = "Last affected user: Priya Sharma encountered failure"
    redacted = redact_text(text)
    assert "Priya Sharma" not in redacted
    assert "[REDACTED_NAME]" in redacted


def test_redact_dict_recursive():
    payload = {
        "service": "agency-db",
        "affected": {
            "accountId": "456789012345",
            "serviceAccount": "svc-payments@internal.corp.com",
            "ips": ["10.0.4.56"],
        },
        "description": "Notice for user:priya@test.com",
    }
    redacted = redact_dict(payload)
    assert redacted["service"] == "agency-db"
    assert redacted["affected"]["accountId"] == "[REDACTED_ACCOUNT_ID]"
    assert redacted["affected"]["serviceAccount"] == "[REDACTED_SVC_ACCOUNT]"
    assert redacted["affected"]["ips"][0] == "[REDACTED_IP]"
    assert "[REDACTED_EMAIL]" in redacted["description"]


# ===========================================================================
# 2. CloudWatch Normalization Tests (Section 3.1 & Section 4)
# ===========================================================================

def test_cloudwatch_normalization_problem_statement_payload():
    cw_payload = {
        "AlarmName": "HighDBConnections-payments-service",
        "AlarmDescription": "DB connection pool utilisation exceeded 90% threshold — affects svc-payments@internal.corp.com",
        "StateChangeTime": "2026-09-26T10:01:00Z",
        "Region": "ap-south-1",
        "NewStateValue": "ALARM",
        "OldStateValue": "OK",
        "Trigger": {
            "MetricName": "DBConnectionCount",
            "Namespace": "AWS/RDS",
            "Dimensions": [{"name": "DBInstanceIdentifier", "value": "prod-payments-db"}],
            "Statistic": "AVERAGE",
            "Period": 60,
            "EvaluationPeriods": 3,
            "Threshold": 90,
            "ObservedValue": 91.3,
        },
        "AffectedResources": {
            "service": "agency-db",
            "component": "db-connection-pool",
            "environment": "prod",
            "region": "ap-south-1",
            "accountId": "456789012345",
            "serviceAccount": "svc-payments@internal.corp.com",
        },
    }

    signal = normalize_cloudwatch(cw_payload)

    # Validate Canonical Schema fields
    assert isinstance(signal.signal_id, str) and len(signal.signal_id) > 0
    assert signal.source == "cloudwatch_metrics"
    assert signal.environment == "prod"
    assert signal.region == "ap-south-1"
    assert signal.service == "agency-db"
    assert signal.component == "db-connection-pool"
    assert signal.signal_type == "metric_anomaly"
    assert signal.anomaly_score == 0.0
    assert signal.value == 91.3

    # Validate PII is redacted in evidence and metadata
    assert "svc-payments@internal.corp.com" not in signal.evidence
    assert "[REDACTED_SVC_ACCOUNT]" in signal.evidence
    assert signal.metadata["affected_resources"]["accountId"] == "[REDACTED_ACCOUNT_ID]"
    assert signal.metadata["affected_resources"]["serviceAccount"] == "[REDACTED_SVC_ACCOUNT]"

    # Compatibility check
    assert signal.id == signal.signal_id
    assert signal.type == signal.signal_type
    assert signal.message == signal.evidence


# ===========================================================================
# 3. Application Logs Normalization Tests (Section 3.2 & Section 4)
# ===========================================================================

def test_application_log_normalization_problem_statement_lines():
    line1 = "2026-09-26T10:01:05Z ERROR payments-service db-connection-pool [user:neha.joshi@acmecorp.com ip:10.0.2.83 session:sess_kd3dxt acc:ACC-10000055] Connection pool exhausted. Pool size: 100, waiting threads: 22"

    parsed = parse_log_dict(line1)
    assert parsed["level"] == "ERROR"
    assert parsed["service"] == "payments-service"
    assert parsed["component"] == "db-connection-pool"
    assert parsed["context"]["user"] == "neha.joshi@acmecorp.com"
    assert parsed["context"]["ip"] == "10.0.2.83"
    assert parsed["context"]["session"] == "sess_kd3dxt"
    assert parsed["context"]["acc"] == "ACC-10000055"

    parsed_sig = parse_log_line(line1)
    assert parsed_sig is not None
    assert parsed_sig.service == "payments-service"

    signal = normalize_log(line1)
    assert signal.source == "application_logs"
    assert signal.service == "payments-service"
    assert signal.component == "db-connection-pool"
    assert signal.signal_type == "error_log_burst"
    assert signal.anomaly_score == 0.0
    assert signal.metadata["log_level"] == "ERROR"

    # Context PII is redacted
    assert signal.metadata["context"]["user"] == "[REDACTED_EMAIL]"
    assert signal.metadata["context"]["ip"] == "[REDACTED_IP]"
    assert signal.metadata["context"]["session"] == "[REDACTED_SESSION]"
    assert signal.metadata["context"]["acc"] == "[REDACTED_ACCOUNT]"

    # Second example line
    line2 = "2026-09-26T10:01:48Z WARN enrollment-service api-handler [host:enrollment-prod-02] Circuit breaker OPEN for payments-service after 27 consecutive failures"
    signal2 = normalize_log(line2)
    assert signal2.service == "enrollment-service"
    assert signal2.component == "api-handler"
    assert signal2.metadata["host"] == "enrollment-prod-02"
    assert signal2.environment == "prod"


# ===========================================================================
# 4. Grafana Alert Normalization Tests (Section 3.3 & Section 4)
# ===========================================================================

def test_grafana_normalization_problem_statement_payload():
    grafana_payload = {
        "title": "High Latency — enrollment-service",
        "state": "alerting",
        "ruleName": "HighLatency-enrollment",
        "orgId": 1,
        "dashboardId": 12,
        "panelId": 7,
        "evalMatches": [
            {
                "metric": "response_time_p99",
                "value": 4785,
                "tags": {
                    "service": "enrollment-service",
                    "environment": "prod",
                    "region": "ap-south-1",
                    "host": "10.0.4.56",
                },
            }
        ],
        "message": "P99 4785ms above the 4000ms threshold for 3 consecutive periods. Last affected user: priya.sharma@acmecorp.com (acc: ACC-10000181, session: sess_58917o)",
        "tags": {"environment": "prod", "region": "ap-south-1"},
        "imageUrl": None,
        "ruleUrl": "http://grafana.internal/d/dash-12/enrollment-service",
    }

    signal = normalize_grafana(grafana_payload)

    assert signal.source == "grafana_alerts"
    assert signal.service == "enrollment-service"
    assert signal.component == "response_time_p99"
    assert signal.signal_type == "grafana_alert"
    assert signal.environment == "prod"
    assert signal.region == "ap-south-1"
    assert signal.anomaly_score == 0.0
    assert signal.value == 4785.0

    # PII in message and host must be redacted
    assert "priya.sharma@acmecorp.com" not in signal.evidence
    assert "sess_58917o" not in signal.evidence
    assert "ACC-10000181" not in signal.evidence
    assert "[REDACTED_EMAIL]" in signal.evidence
    assert "[REDACTED_SESSION]" in signal.evidence
    assert "[REDACTED_ACCOUNT]" in signal.evidence

    eval_match = signal.metadata["eval_matches"][0]
    assert eval_match["tags"]["host"] == "[REDACTED_IP]"


# ===========================================================================
# 5. SSE Client Parsing & Last-Event-ID Tests (Section 5)
# ===========================================================================

@pytest.mark.asyncio
async def test_sse_stream_consumption_and_keepalive(monkeypatch):
    sse_wire_content = [
        ":keepalive\n",
        "id: 000041\n",
        "event: signal\n",
        "data: 2026-09-26T10:01:05Z ERROR payments-service db-connection-pool [user:test@corp.com] Connection failed\n\n",
        ":keepalive\n",
        "id: 000042\n",
        "event: signal\n",
        "data: 2026-09-26T10:01:06Z WARN payments-service db-connection-pool [ip:10.0.0.1] Pool degraded\n\n",
    ]

    class FakeResponse:
        status_code = 200
        request = httpx.Request("GET", "https://fake.stream")

        async def aiter_lines(self):
            for chunk in sse_wire_content:
                for line in chunk.splitlines(keepends=False):
                    yield line

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def stream(self, method, url, headers=None):
            return FakeResponse()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    signals_received = []
    async for seq_id, sig in consume_sse_stream("https://logs.nonprod.nexus.ensylon.com/sim/stream/aiops-logs", max_reconnects=0):
        signals_received.append((seq_id, sig))

    assert len(signals_received) == 2
    seq1, sig1 = signals_received[0]
    seq2, sig2 = signals_received[1]

    assert seq1 == "000041"
    assert sig1.service == "payments-service"
    assert "[REDACTED_EMAIL]" in sig1.metadata["context"]["user"]

    assert seq2 == "000042"
    assert sig2.metadata["context"]["ip"] == "[REDACTED_IP]"


# ===========================================================================
# 6. Canonical Signal Schema & Serialization
# ===========================================================================

def test_canonical_signal_dict_serialization():
    sig = CanonicalSignal(
        timestamp=datetime(2026, 9, 26, 10, 1, 0, tzinfo=timezone.utc),
        source="cloudwatch_metrics",
        environment="prod",
        region="ap-south-1",
        service="payments-service",
        component="db-connection-pool",
        signal_type="metric_anomaly",
        anomaly_score=0.0,
        evidence="[REDACTED] connection pool exhausted",
        metadata={"threshold": 90},
    )

    data = sig.model_dump()
    assert "signal_id" in data
    assert data["source"] == "cloudwatch_metrics"
    assert data["anomaly_score"] == 0.0
    assert data["evidence"] == "[REDACTED] connection pool exhausted"
    # Legacy compatibility fields are also populated
    assert data["id"] == data["signal_id"]
    assert data["type"] == "metric_anomaly"
    assert data["message"] == data["evidence"]
