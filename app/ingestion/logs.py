import re
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from app.models.signal import Signal
from app.redaction.pii import redact

logger = logging.getLogger(__name__)

# Regex to parse the raw log line: TIMESTAMP LEVEL SERVICE COMPONENT [CONTEXT] MESSAGE
LOG_PATTERN = re.compile(r"^(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+\[(.*?)\]\s+(.*)$")


def parse_log_line(raw_line: str) -> Optional[Signal]:
    """
    Parse a single raw log line into a Signal object.
    PII is redacted from free-text fields before Signal is constructed.
    """
    match = LOG_PATTERN.match(raw_line.strip())
    if not match:
        logger.warning(f"Failed to parse log line: {raw_line}")
        return None

    ts_raw, level, service, component, context_str, message = match.groups()

    try:
        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
    except Exception:
        ts = datetime.now(tz=timezone.utc)

    # Redact PII (PRD §24)
    redacted_message = redact(message)
    redacted_service = redact(service)
    redacted_component = redact(component)

    signal = Signal(
        id=f"log-{uuid.uuid4().hex[:8]}",
        timestamp=ts,
        source="application_logs",
        environment="prod",  # Hardcoded or infer if possible, but logs usually don't have it explicitly here. We'll default to prod.
        service=redacted_service,
        component=redacted_component,
        type="error_log_burst",
        message=redacted_message,
        evidence=f"{level} {redacted_message}",
        metadata={"level": level, "context": redact(context_str)}
    )
    return signal