"""
Grafana Alert Ingestion & Normalization.
Matches Section 3.3 & Section 4 of the Technical Problem Statement.
"""
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional, Union
import uuid

from app.models.signal import Signal
from app.redaction.pii import redact_dict, redact_text

logger = logging.getLogger(__name__)


def parse_grafana_alert(raw: Union[Dict[str, Any], str]) -> Dict[str, Any]:
    """
    Parse a single raw Grafana alert payload from JSON string or dict.
    """
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception as e:
            logger.error("Failed to decode Grafana JSON: %s", e)
            raise ValueError(f"Invalid Grafana JSON payload: {e}") from e
    elif isinstance(raw, dict):
        return raw
    raise TypeError(f"Expected dict or JSON string, got {type(raw).__name__}")


def normalize_grafana(raw: Union[Dict[str, Any], str]) -> Signal:
    """
    Redact PII and normalize a single Grafana alert event into a canonical Signal.
    Redaction occurs before any storage or further processing (Section 2 & 3.3).
    """
    payload = parse_grafana_alert(raw)

    # 1. PII Redaction across all fields before processing
    redacted = redact_dict(payload)

    # 2. Extract timestamp
    ts_raw = (
        redacted.get("timestamp")
        or redacted.get("startsAt")
        or redacted.get("time")
        or ""
    )
    try:
        ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
    except Exception:
        ts = datetime.now(timezone.utc)

    # 3. Extract evaluation matches & tags
    eval_matches = redacted.get("evalMatches", [])
    first_match: Dict[str, Any] = eval_matches[0] if (isinstance(eval_matches, list) and len(eval_matches) > 0) else {}
    match_tags: Dict[str, Any] = first_match.get("tags", {}) if isinstance(first_match, dict) else {}
    top_tags: Dict[str, Any] = redacted.get("tags", {}) if isinstance(redacted.get("tags"), dict) else {}

    # Service resolution
    service = match_tags.get("service") or top_tags.get("service")
    if not service:
        title = redacted.get("title", "")
        if "—" in title:
            service = title.split("—")[-1].strip()
        elif "-" in title:
            service = title.split("-")[-1].strip()
        else:
            service = redacted.get("ruleName") or "unknown-service"

    # Component resolution
    component = match_tags.get("component") or first_match.get("metric") or match_tags.get("host") or "api-handler"

    # Environment & Region
    environment = match_tags.get("environment") or top_tags.get("environment") or "prod"
    region = match_tags.get("region") or top_tags.get("region") or "ap-south-1"

    # Evidence: message containing redacted details
    summary = redacted.get("title") or redacted.get("ruleName") or ""
    msg = redacted.get("message") or ""
    evidence = f"{summary}: {msg}".strip(": ") if summary and msg else (msg or summary or "Grafana Alert")

    # Value
    raw_val = first_match.get("value") if isinstance(first_match, dict) else None
    if raw_val is None and "value" in redacted:
        raw_val = redacted.get("value")

    value: Optional[float] = None
    if raw_val is not None:
        try:
            value = float(raw_val)
        except (ValueError, TypeError):
            value = None

    fingerprint = str(redacted.get("fingerprint") or uuid.uuid4().hex[:8])

    metadata = {
        "title": redacted.get("title"),
        "state": redacted.get("state"),
        "rule_name": redacted.get("ruleName"),
        "dashboard_id": redacted.get("dashboardId"),
        "panel_id": redacted.get("panelId"),
        "rule_url": redacted.get("ruleUrl"),
        "eval_matches": eval_matches,
        "tags": top_tags,
    }

    return Signal(
        id=f"grafana-{fingerprint[:8]}-{uuid.uuid4().hex[:6]}",
        signal_id=str(uuid.uuid4()),
        timestamp=ts,
        source="grafana_alerts",
        environment=environment,
        region=region,
        service=service,
        component=component,
        signal_type="grafana_alert",
        type="grafana_alert",
        anomaly_score=0.0,
        evidence=evidence,
        message=evidence,
        metadata=metadata,
        value=value,
    )


def ingest_grafana_alerts(payload: Dict[str, Any]) -> List[Signal]:
    """
    Ingest webhook alerts from Grafana (preserves backward compatibility).
    Supports both legacy alertmanager webhook payloads and Section 3.3 format.
    """
    alerts = payload.get("alerts", [payload]) if isinstance(payload, dict) else [payload]
    signals: List[Signal] = []
    for alert in alerts:
        try:
            signals.append(normalize_grafana(alert))
        except Exception as e:
            logger.error("Failed to parse Grafana alert: %s", e)
    return signals
