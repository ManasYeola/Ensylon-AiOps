"""
Grafana alert webhook ingestion — normalizes Grafana alertmanager payloads to Signal model.
PII is redacted from all string fields before the Signal is constructed (PRD §24).
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.models.signal import Signal
from app.redaction.pii import redact

logger = logging.getLogger(__name__)


def ingest_grafana_alerts(payload: Dict[str, Any]) -> List[Signal]:
    """
    Ingest webhook alerts from Grafana alertmanager.
    The PS states Grafana sends one alert per event as a flat dictionary.
    All string fields are PII-redacted before the Signal is constructed.
    """
    # Try to handle both standard webhook (with "alerts" list) and single alert payload.
    if "alerts" in payload:
        alerts = payload["alerts"]
    else:
        alerts = [payload]

    signals = []
    for alert in alerts:
        try:
            # According to PS, metrics are inside evalMatches
            eval_matches = alert.get("evalMatches", [])
            tags = alert.get("tags", {})
            
            # If the evalMatches has tags, they override/supplement the main tags
            if eval_matches and "tags" in eval_matches[0]:
                tags.update(eval_matches[0]["tags"])

            ts_str = alert.get("startsAt", datetime.now(tz=timezone.utc).isoformat())
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except Exception:
                ts = datetime.now(tz=timezone.utc)

            # --- PII Redaction (PRD §24) -----------------------------------
            environment = redact(tags.get("environment", "prod"))
            service     = redact(tags.get("service", tags.get("job", "unknown-service")))
            component   = redact(tags.get("instance", tags.get("component", "unknown")))
            summary     = redact(alert.get("title", alert.get("ruleName", "")))
            fingerprint = redact(alert.get("fingerprint", str(uuid.uuid4())))
            message     = redact(alert.get("message", ""))

            raw_val = None
            if eval_matches and "value" in eval_matches[0]:
                raw_val = eval_matches[0]["value"]
            elif "value" in alert:
                raw_val = alert["value"]

            value: float | None = None
            try:
                value = float(raw_val) if raw_val is not None else None
            except (ValueError, TypeError):
                value = None

            evidence = f"{summary}: {message}" if message else summary

            signal = Signal(
                id=f"grafana-{fingerprint[:8]}-{uuid.uuid4().hex[:6]}",
                timestamp=ts,
                source="grafana_alerts",
                environment=environment,
                service=service,
                component=component,
                type="grafana_alert",
                value=value,
                message=evidence,
                evidence=evidence,
            )
            signals.append(signal)
        except Exception as e:
            logger.error("Failed to parse Grafana alert: %s", e)
    return signals
