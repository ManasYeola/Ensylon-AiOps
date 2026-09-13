"""
Grafana alert webhook ingestion — normalizes Grafana alertmanager payloads to Signal model.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List
from app.models.signal import Signal

logger = logging.getLogger(__name__)


def ingest_grafana_alerts(payload: Dict[str, Any]) -> List[Signal]:
    """
    Ingest webhook alerts from Grafana alertmanager.
    """
    signals = []
    alerts = payload.get("alerts", [])
    for alert in alerts:
        try:
            labels = alert.get("labels", {})
            annotations = alert.get("annotations", {})
            ts_str = alert.get("startsAt", datetime.utcnow().isoformat())
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except Exception:
                ts = datetime.utcnow()

            signal = Signal(
                id=f"grafana-{alert.get('fingerprint', 'unknown')}",
                timestamp=ts,
                source="grafana",
                environment=labels.get("environment", "unknown"),
                service=labels.get("service", labels.get("job", "unknown-service")),
                component=labels.get("instance", labels.get("component", "unknown")),
                type="latency_alert",
                value=float(annotations.get("value", 0)) if annotations.get("value") else None,
                message=annotations.get("summary", labels.get("alertname")),
            )
            signals.append(signal)
        except Exception as e:
            logger.error("Failed to parse Grafana alert: %s", e)
    return signals
