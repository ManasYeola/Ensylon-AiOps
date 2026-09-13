"""
Severity engine — PRD §6/G6 / §17.

Formula:
    Severity = 0.35*Blast + 0.35*Criticality + 0.20*Trend + 0.10*Magnitude

Output: 0–100 (clamped)

All weights and service criticality values loaded from config.yaml.
"""
from app.config import get_severity_cfg
from app.models.signal import Signal


def get_service_criticality(service: str) -> float:
    """
    Look up business criticality for a service (0–100 scale).
    Unknown services → neutral (50) and must be flagged for reviewer confirmation (PRD §6).
    """
    cfg = get_severity_cfg()
    mapping = cfg.get("service_criticality", {})
    value = mapping.get(service.lower())
    if value is None:
        return mapping.get("unknown", 50)
    return float(value)


def calculate_blast_radius(signals: list[Signal]) -> float:
    """
    Blast radius score (0–100): how many distinct services are impacted.
    1 service = 25, 2 = 50, 3 = 75, 4+ = 100.
    Normalized to 0–100 scale.
    """
    n = len({s.service for s in signals})
    return min(n * 25.0, 100.0)


def calculate_criticality(signals: list[Signal]) -> float:
    """
    Criticality score (0–100): max business criticality across all impacted services.
    """
    return max(get_service_criticality(s.service) for s in signals)


def calculate_trend(signals: list[Signal]) -> float:
    """
    Trend score (0–100): is the signal rate increasing over the window?
    Compares first-half vs second-half signal density.
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

    # Simple rate comparison
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
    Magnitude score (0–100): highest observed metric value relative to normal expectation.
    If no numeric values are present, falls back to 50.
    """
    values = [s.value for s in signals if s.value is not None]
    if not values:
        return 50.0
    # Normalise: assume values > 90 are critical on a 0–100 scale
    return min(max(values) / 100.0 * 100.0, 100.0)


def calculate_severity(signals: list[Signal]) -> float:
    """
    PRD §17 formula:
        Severity = 0.35*Blast + 0.35*Criticality + 0.20*Trend + 0.10*Magnitude
    Returns a float clamped to 0–100.
    """
    cfg = get_severity_cfg()

    blast = calculate_blast_radius(signals)
    criticality = calculate_criticality(signals)
    trend = calculate_trend(signals)
    magnitude = calculate_magnitude(signals)

    score = (
        cfg["blast"] * blast
        + cfg["criticality"] * criticality
        + cfg["trend"] * trend
        + cfg["magnitude"] * magnitude
    )
    return round(min(max(score, 0.0), 100.0), 2)
