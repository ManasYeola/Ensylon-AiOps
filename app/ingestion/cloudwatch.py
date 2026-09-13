import logging
from datetime import datetime
from typing import Any, Dict, List
from app.models.signal import Signal

logger = logging.getLogger(__name__)


def ingest_cloudwatch_alarms(raw_events: List[Dict[str, Any]]) -> List[Signal]:
    """
    Parse AWS CloudWatch alarm payloads into standardized Signal models.
    """
    signals = []
    for event in raw_events:
        try:
            signal = Signal(
                id=f"cw-{event.get('AlarmArn', event.get('AlarmName', 'unknown'))}",
                timestamp=datetime.fromisoformat(event.get("Timestamp", datetime.utcnow().isoformat())),
                source="cloudwatch",
                environment=event.get("environment", "unknown"),
                service=event.get("Namespace", "unknown-service"),
                component=event.get("MetricName", "unknown"),
                type="metric_anomaly",
                value=event.get("Trigger", {}).get("Threshold"),
                message=event.get("AlarmDescription"),
            )
            signals.append(signal)
        except Exception as e:
            logger.error("Failed to parse CloudWatch event: %s", e)
    return signals
