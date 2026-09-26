import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.models.signal import Signal
from app.redaction.pii import redact

logger = logging.getLogger(__name__)


def ingest_cloudwatch_alarms(raw_events: List[Dict[str, Any]]) -> List[Signal]:
    """
    Parse AWS CloudWatch alarm payloads into standardized Signal models.
    PII is redacted from all string fields before the Signal is constructed (PRD §24).
    """
    signals = []
    for event in raw_events:
        try:
            # --- PII Redaction (PRD §24) -----------------------------------
            alarm_name = redact(event.get("AlarmArn", event.get("AlarmName", "unknown")))
            description = redact(event.get("AlarmDescription") or "")
            namespace   = redact(event.get("Namespace", "unknown-service"))
            metric_name = redact(event.get("MetricName", "unknown"))
            environment = redact(event.get("environment", "unknown"))

            ts_raw = event.get("Timestamp") or event.get("StateChangeTime", "")
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            except Exception:
                ts = datetime.now(tz=timezone.utc)

            threshold = event.get("Trigger", {}).get("Threshold")

            signal = Signal(
                id=f"cw-{alarm_name}-{uuid.uuid4().hex[:6]}",
                timestamp=ts,
                source="cloudwatch",
                environment=environment,
                service=namespace,
                component=metric_name,
                type="metric_anomaly",
                value=float(threshold) if threshold is not None else None,
                message=description or None,
            )
            signals.append(signal)
        except Exception as e:
            logger.error("Failed to parse CloudWatch event: %s", e)
    return signals
