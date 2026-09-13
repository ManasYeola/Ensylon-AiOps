import json
from pathlib import Path

from app.models.signal import Signal


def load_signals(file_path: str) -> list[Signal]:
    path = Path(file_path)

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    signals = [Signal(**item) for item in data]

    return signals