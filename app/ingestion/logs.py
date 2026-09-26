import json
from pathlib import Path

from app.models.signal import Signal
from app.redaction.pii import redact


def load_signals(file_path: str) -> list[Signal]:
    """
    Load pre-recorded signals from a JSON file.
    PII is redacted from free-text fields before Signal is constructed (PRD §24).
    """
    path = Path(file_path)

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    signals = []
    for item in data:
        # Redact free-text fields that may contain PII (PRD §24)
        if item.get("message"):
            item["message"] = redact(item["message"])
        if item.get("component"):
            item["component"] = redact(item["component"])
        signals.append(Signal(**item))

    return signals