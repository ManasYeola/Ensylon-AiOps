"""
Metric anomaly detection.
Implements rolling z-score, EWMA, and the composite detect_metric_anomaly() function.
All thresholds loaded from config.yaml (PRD §11).
"""
from typing import Optional
import math
from app.config import get_detection_cfg


def calculate_rolling_zscore(values: list[float], window_size: Optional[int] = None) -> float:
    """
    Calculate z-score of the most recent value relative to a rolling window.
    Returns 0.0 if the window is too small to compute a baseline.
    """
    cfg = get_detection_cfg()
    w = window_size or cfg["window_size"]
    window = values[-w:] if len(values) >= w else values

    if len(window) < 2:
        return 0.0

    n = len(window)
    mean = sum(window) / n
    variance = sum((x - mean) ** 2 for x in window) / (n - 1)
    std = math.sqrt(variance)

    if std == 0:
        return 0.0

    latest = values[-1]
    return abs((latest - mean) / std)


def calculate_ewma(values: list[float], alpha: Optional[float] = None) -> float:
    """
    Exponentially weighted moving average of the value series.
    Returns the EWMA at the last data point.
    """
    cfg = get_detection_cfg()
    a = alpha or cfg["ewma_alpha"]

    if not values:
        return 0.0

    ewma = values[0]
    for v in values[1:]:
        ewma = a * v + (1 - a) * ewma
    return ewma


def detect_metric_anomaly(
    values: list[float],
    current_value: float,
    window_size: Optional[int] = None,
    zscore_threshold: Optional[float] = None,
) -> bool:
    """
    Returns True if the current metric value is anomalous.
    Uses rolling z-score as the primary detector.
    """
    cfg = get_detection_cfg()
    threshold = zscore_threshold or cfg["zscore_threshold"]
    all_values = values + [current_value]
    zscore = calculate_rolling_zscore(all_values, window_size)
    return zscore >= threshold
