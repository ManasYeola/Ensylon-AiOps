"""
AWS CloudWatch Alarm Ingestion & Normalization.
Matches Section 3.1 & Section 4 of the Technical Problem Statement.
"""
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Union
import uuid

from app.models.signal import Signal
from app.redaction.pii import redact_dict, redact_text

logger = logging.getLogger(__name__)


def parse_cloudwatch_event(raw: Union[Dict[str, Any], str]) -> Dict[str, Any]:
    """
    Parse a single raw CloudWatch alarm payload from JSON string or dict.
    """
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception as e:
            logger.error("Failed to decode CloudWatch JSON: %s", e)
            raise ValueError(f"Invalid CloudWatch JSON payload: {e}") from e
    elif isinstance(raw, dict):
        return raw
    raise TypeError(f"Expected dict or JSON string, got {type(raw).__name__}")


def normalize_cloudwatch(raw: Union[Dict[str, Any], str]) -> Signal:
    """
    Redact PII and normalize a single raw CloudWatch event into a canonical Signal.
    Redaction occurs before any storage or further processing (Section 2 & 3.1).
    """
    event = parse_cloudwatch_event(raw)

    # 1. PII Redaction across all fields before processing
    redacted_event = redact_dict(event)

    # 2. Extract timestamp
    ts_raw = redacted_event.get("StateChangeTime") or redacted_event.get("Timestamp") or ""
    try:
        ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
    except Exception:
        ts = datetime.now(timezone.utc)

    # 3. Extract affected resources and trigger info
    affected = redacted_event.get("AffectedResources", {})
    if not isinstance(affected, dict):
        affected = {}

    trigger = redacted_event.get("Trigger", {})
    if not isinstance(trigger, dict):
        trigger = {}

    alarm_name = str(redacted_event.get("AlarmName", "unknown-alarm"))
    description = redacted_event.get("AlarmDescription") or ""

    # Service & component resolution
    service = affected.get("service")
    if not service:
        service = trigger.get("Namespace") or redacted_event.get("Namespace") or "unknown-service"

    component = affected.get("component")
    if not component:
        component = trigger.get("MetricName") or redacted_event.get("MetricName") or "unknown-component"

    environment = affected.get("environment") or redacted_event.get("environment") or "prod"
    region = affected.get("region") or redacted_event.get("Region") or "ap-south-1"

    # ── Alarm state ─────────────────────────────────────────────────────────
    # Read from redacted event (values like "ALARM", "OK", "INSUFFICIENT_DATA")
    alarm_state: str = str(redacted_event.get("NewStateValue") or "UNKNOWN").upper()

    # ── Numeric values ───────────────────────────────────────────────────────
    # ObservedValue is what the metric actually measured this period;
    # Threshold is the configured alarm boundary.
    obs_val: Union[float, None] = None
    threshold_val: Union[float, None] = None
    try:
        raw_obs = trigger.get("ObservedValue")
        if raw_obs is not None:
            obs_val = float(raw_obs)
    except (ValueError, TypeError):
        pass
    try:
        raw_thr = trigger.get("Threshold")
        if raw_thr is not None:
            threshold_val = float(raw_thr)
    except (ValueError, TypeError):
        pass

    # signal.value = the observed metric reading (used by z-score scorer)
    value: Union[float, None] = obs_val if obs_val is not None else threshold_val

    # ── Evidence string ──────────────────────────────────────────────────────
    if alarm_state == "OK":
        # For OK/recovery events, the AlarmDescription field is the text that was
        # set when the alarm was created (it describes the fault condition, not
        # the recovery).  Always generate a state-specific evidence string here.
        evidence = (
            f"{alarm_name} recovered"
            + (f" — {component} now {obs_val}" if obs_val is not None else "")
            + (f" (threshold {threshold_val})" if threshold_val is not None else "")
        )
    elif description:
        evidence = description
    else:
        # ALARM or INSUFFICIENT_DATA — no description available
        evidence = (
            f"{alarm_name} ({component} in {alarm_state})"
            + (f" — observed {obs_val}" if obs_val is not None else "")
            + (f" vs threshold {threshold_val}" if threshold_val is not None else "")
        )

    # ── Metadata (redacted; preserved for downstream scoring + evidence) ─────
    metadata = {
        "alarm_name": alarm_name,
        # alarm_state is the key detection consumes to know OK vs ALARM
        "alarm_state": alarm_state,
        "new_state": alarm_state,
        "old_state": str(redacted_event.get("OldStateValue") or "").upper(),
        "observed_value": obs_val,
        "threshold_value": threshold_val,
        # Full trigger dict kept for downstream context (already PII-redacted)
        "trigger": trigger,
        "affected_resources": affected,
    }

    return Signal(
        signal_id=str(uuid.uuid4()),
        timestamp=ts,
        source="cloudwatch_metrics",
        environment=environment,
        region=region,
        service=service,
        component=component,
        signal_type="metric_anomaly",
        anomaly_score=0.0,
        evidence=evidence,
        metadata=metadata,
        value=value,
    )


def ingest_cloudwatch_alarms(raw_events: List[Dict[str, Any]]) -> List[Signal]:
    """
    Batch ingestion for CloudWatch alarms (preserves backward compatibility).
    """
    signals: List[Signal] = []
    for event in raw_events:
        try:
            signals.append(normalize_cloudwatch(event))
        except Exception as e:
            logger.error("Failed to normalize CloudWatch event: %s", e)
    return signals
