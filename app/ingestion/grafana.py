"""
Grafana alert webhook ingestion — normalizes Grafana alertmanager payloads to Signal model.
PII is redacted from all string fields before the Signal is constructed (PRD §24).
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.models.signal import Signal
from app.redaction.pii import redact

logger = logging.getLogger(__name__)


def ingest_grafana_alerts(payload: Dict[str, Any]) -> List[Signal]:
    """
    Ingest webhook alerts from Grafana alertmanager.
    All string fields are PII-redacted before the Signal is constructed.
    """
    signals = []
    alerts = payload.get("alerts", [])
    for alert in alerts:
        try:
            labels      = alert.get("labels", {})
            annotations = alert.get("annotations", {})
            ts_str = alert.get("startsAt", datetime.now(tz=timezone.utc).isoformat())
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except Exception:
                ts = datetime.now(tz=timezone.utc)

            # --- PII Redaction (PRD §24) -----------------------------------
            environment = redact(labels.get("environment", "unknown"))
            service     = redact(labels.get("service", labels.get("job", "unknown-service")))
            component   = redact(labels.get("instance", labels.get("component", "unknown")))
            summary     = redact(annotations.get("summary", labels.get("alertname", "")))
            fingerprint = redact(alert.get("fingerprint", "unknown"))

            raw_val = annotations.get("value")
            value: float | None = None
            try:
                value = float(raw_val) if raw_val is not None else None
            except (ValueError, TypeError):
                value = None

            signal = Signal(
                id=f"grafana-{fingerprint}-{uuid.uuid4().hex[:6]}",
                timestamp=ts,
                source="grafana",
                environment=environment,
                service=service,
                component=component,
                type="latency_alert",
                value=value,
                message=summary or None,
            )
            signals.append(signal)
        except Exception as e:
            logger.error("Failed to parse Grafana alert: %s", e)
    return signals
