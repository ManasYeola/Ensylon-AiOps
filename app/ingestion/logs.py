"""
Application Log Ingestion & Normalization.
Matches Section 3.2 & Section 4 of the Technical Problem Statement.
"""
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Union
import uuid

from app.models.signal import Signal
from app.redaction.pii import redact_dict, redact_text

logger = logging.getLogger(__name__)

# Matches standard simulator log line format:
# <timestamp> <level> <service> <component> [<context>] <message>
LOG_LINE_REGEX = re.compile(
    r"^(?P<timestamp>\S+)\s+"
    r"(?P<level>[A-Z]+)\s+"
    r"(?P<service>[^\s\[]+)\s+"
    r"(?P<component>[^\s\[]+)"
    r"(?:\s+\[(?P<context>[^\]]*)\])?"
    r"\s*(?P<message>.*)$"
)


def parse_log_dict(raw: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Parse a single raw application log line (or JSON log) into a structured dictionary.
    """
    if isinstance(raw, dict):
        return raw

    line = raw.strip()
    if not line:
        raise ValueError("Empty log line")

    # If log is JSON-formatted
    if line.startswith("{") and line.endswith("}"):
        try:
            return json.loads(line)
        except Exception:
            pass  # Fall back to regex parsing

    match = LOG_LINE_REGEX.match(line)
    if not match:
        parts = line.split(" ", 4)
        return {
            "timestamp": parts[0] if len(parts) > 0 else datetime.now(timezone.utc).isoformat(),
            "level": parts[1] if len(parts) > 1 else "INFO",
            "service": parts[2] if len(parts) > 2 else "unknown-service",
            "component": parts[3] if len(parts) > 3 else "unknown-component",
            "context": {},
            "message": parts[4] if len(parts) > 4 else line,
        }

    groups = match.groupdict()
    context_str = groups.get("context") or ""
    context_dict: Dict[str, str] = {}
    if context_str:
        # Context block holds key:value pairs, e.g. user:... ip:... session:... acc:... host:...
        pairs = re.findall(r"([A-Za-z0-9_\-]+):([^\s\]]+)", context_str)
        for k, v in pairs:
            context_dict[k] = v

    return {
        "timestamp": groups["timestamp"],
        "level": groups["level"],
        "service": groups["service"],
        "component": groups["component"],
        "context": context_dict,
        "message": groups["message"],
    }


def normalize_log(raw: Union[str, Dict[str, Any]]) -> Signal:
    """
    Redact PII and normalize a single application log event into a canonical Signal.
    Redaction occurs before any storage or further processing (Section 2 & 3.2).
    """
    parsed = parse_log_dict(raw)

    # 1. PII Redaction across all fields before processing
    redacted_message = redact_text(str(parsed.get("message", "")))
    redacted_context = redact_dict(parsed.get("context", {}))
    service = redact_text(str(parsed.get("service", "unknown-service")))
    component = redact_text(str(parsed.get("component", "unknown-component")))
    level = str(parsed.get("level", "INFO")).upper()

    # 2. Extract timestamp
    ts_raw = parsed.get("timestamp", "")
    try:
        ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
    except Exception:
        ts = datetime.now(timezone.utc)

    # 3. Derive environment & region
    host = redacted_context.get("host", "")
    environment = parsed.get("environment") or redacted_context.get("env") or "prod"
    if "staging" in host.lower() or "stage" in host.lower():
        environment = "staging"
    elif "dev" in host.lower():
        environment = "dev"

    region = parsed.get("region") or redacted_context.get("region") or "ap-south-1"

    metadata = {
        "level": level,
        "log_level": level,
        "context": redacted_context,
        "host": host,
    }

    evidence = f"{level} {redacted_message}".strip()

    return Signal(
        id=f"log-{uuid.uuid4().hex[:8]}",
        signal_id=str(uuid.uuid4()),
        timestamp=ts,
        source="application_logs",
        environment=environment,
        region=region,
        service=service,
        component=component,
        signal_type="error_log_burst",
        type="error_log_burst",
        anomaly_score=0.0,
        evidence=evidence,
        message=redacted_message,
        metadata=metadata,
    )


def parse_log_line(raw_line: str) -> Optional[Signal]:
    """
    Parse a single raw log line into a canonical Signal with PII redacted.
    Used by scripts/sse_client.py.
    """
    try:
        return normalize_log(raw_line)
    except Exception as e:
        logger.warning(f"Failed to parse log line: {e}")
        return None


def load_signals(file_path: str) -> List[Signal]:
    """
    Load pre-recorded signals from a JSON file (preserves backward compatibility).
    PII is redacted from free-text fields before Signal is constructed (PRD §24).
    """
    path = Path(file_path)

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    signals: List[Signal] = []
    for item in data:
        if item.get("message"):
            item["message"] = redact_text(item["message"])
        if item.get("evidence"):
            item["evidence"] = redact_text(item["evidence"])
        if item.get("component"):
            item["component"] = redact_text(item["component"])
        signals.append(Signal(**item))

    return signals