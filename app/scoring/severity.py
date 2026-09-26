"""
Severity engine — HTML §7 / C4.

Formula (weights from config.yaml, all on 0–100 scale):
    Severity = 0.35*Blast + 0.35*Criticality + 0.20*Trend + 0.10*Magnitude

Business criticality is loaded from data/criticality_map.json (HTML §6.2).
Services NOT in the map receive a neutral default score of 50 (HTML §6.2 explicit rule).
"""
import json
from functools import lru_cache
from pathlib import Path

from app.config import get_severity_cfg
from app.models.signal import Signal


CRITICALITY_MAP_PATH = Path(__file__).parent.parent.parent / "data" / "criticality_map.json"


@lru_cache(maxsize=1)
def _load_criticality_map() -> dict[str, float]:
    """
    Load data/criticality_map.json once.  Falls back to the config.yaml
    service_criticality block so existing tests still pass if the JSON file
    is missing (e.g. in CI before the data file is committed).
    """
    if CRITICALITY_MAP_PATH.exists():
        with open(CRITICALITY_MAP_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return {k.lower(): float(v) for k, v in raw.items()}

    # Fallback: read from config.yaml (legacy path)
    cfg = get_severity_cfg()
    return {k.lower(): float(v) for k, v in cfg.get("service_criticality", {}).items()}


def get_service_criticality(service: str) -> float:
    """
    Look up business criticality for a service (0–100 scale).
    Unknown services → neutral default of 50 (HTML §6.2 explicit rule).
    """
    mapping = _load_criticality_map()
    return mapping.get(service.lower(), 50.0)


def calculate_blast_radius(signals: list[Signal]) -> float:
    """
    Blast radius score (0–100): how many distinct services are impacted.
    1 service = 25, 2 = 50, 3 = 75, 4 = 88, 5+ = 100.
    """
    n = len({s.service for s in signals})
    mapping = {1: 25.0, 2: 50.0, 3: 75.0, 4: 88.0}
    return mapping.get(n, 100.0)


def calculate_criticality(signals: list[Signal]) -> float:
    """
    Criticality score (0–100): max business criticality across all impacted services.
    """
    return max(get_service_criticality(s.service) for s in signals)


def calculate_trend(signals: list[Signal]) -> float:
    """
    Trend score (0–100): is the signal rate increasing over the window?
    100 = accelerating, 50 = steady, 0 = decelerating.
    """
    if len(signals) < 2:
        return 50.0
    sorted_sigs = sorted(signals, key=lambda s: s.timestamp)
    mid = len(sorted_sigs) // 2
    first_half = sorted_sigs[:mid]
    second_half = sorted_sigs[mid:]

    if not first_half:
        return 50.0

    rate_first = len(first_half)
    rate_second = len(second_half)

    if rate_second > rate_first:
        return 100.0
    elif rate_second == rate_first:
        return 50.0
    else:
        return 0.0


def calculate_magnitude(signals: list[Signal]) -> float:
    """
    Magnitude score (0–100): driven by the highest anomaly_score in the cluster.
    anomaly_score is always 0.0–1.0, so we scale to 0–100.
    Falls back to raw metric value normalisation if anomaly_score is absent.
    """
    # Prefer anomaly_score (0.0–1.0) — scale to 0–100
    scores = [s.anomaly_score for s in signals if s.anomaly_score > 0.0]
    if scores:
        return round(min(max(scores) * 100.0, 100.0), 2)

    # Legacy fallback: raw numeric value
    values = [s.value for s in signals if s.value is not None]
    if not values:
        return 50.0

    max_val = max(values)
    if max_val <= 100:
        return round(min(max_val, 100.0), 2)
    return round(min(max_val / 10.0, 100.0), 2)


def calculate_severity(signals: list[Signal]) -> float:
    """
    HTML §7 formula:
        Severity = 0.35*Blast + 0.35*Criticality + 0.20*Trend + 0.10*Magnitude
    Returns a float clamped to 0–100.
    """
    cfg = get_severity_cfg()

    blast       = calculate_blast_radius(signals)
    criticality = calculate_criticality(signals)
    trend       = calculate_trend(signals)
    magnitude   = calculate_magnitude(signals)

    score = (
        cfg["blast"]       * blast
        + cfg["criticality"] * criticality
        + cfg["trend"]       * trend
        + cfg["magnitude"]   * magnitude
    )
    return round(min(max(score, 0.0), 100.0), 2)
