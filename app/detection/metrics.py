"""
Metric anomaly detection.
Implements rolling z-score, EWMA, and the composite score_metric_signal() function.
All thresholds loaded from config.yaml (HTML §C2).

Key public API
--------------
score_metric_signal(signal, history)  → float  (0.0–1.0 anomaly_score)
detect_metric_anomaly(...)            → bool   (legacy gate; kept for tests)
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


def score_metric_signal(
    history: list[float],
    current_value: float,
    window_size: Optional[int] = None,
    threshold_value: Optional[float] = None,
    pct_threshold: Optional[float] = None,
) -> float:
    """
    Compute anomaly_score (0.0–1.0) for a metric signal.

    Scoring strategy (all sub-scores blended):
    1. z-score distance:        how many std-devs beyond the rolling mean
    2. Threshold breach ratio:  how far above the configured alarm threshold (if provided)
    3. EWMA deviation:          current vs EWMA as a fraction of EWMA

    Returns 0.0 for signals with insufficient history.
    """
    cfg = get_detection_cfg()
    w = window_size or cfg["window_size"]

    all_values = history + [current_value]

    # ── Component 1: normalised z-score ──────────────────────────────────────
    zscore = calculate_rolling_zscore(all_values, w)
    z_cap = cfg.get("zscore_cap", 6.0)          # saturate at 6σ → 1.0
    z_score_norm = min(zscore / z_cap, 1.0)

    # ── Component 2: threshold breach ratio (optional) ───────────────────────
    breach_score = 0.0
    if threshold_value is not None and threshold_value > 0 and pct_threshold is not None:
        # pct_threshold is how far above threshold we are (ObservedValue/Threshold - 1)
        breach_score = min(pct_threshold, 1.0)

    # ── Component 3: EWMA deviation ──────────────────────────────────────────
    ewma_val = calculate_ewma(all_values[:-1] or [current_value], cfg["ewma_alpha"])
    if ewma_val != 0:
        ewma_dev = abs(current_value - ewma_val) / abs(ewma_val)
    else:
        ewma_dev = 0.0
    ewma_score = min(ewma_dev, 1.0)

    # ── Blend (weights sum to 1.0) ────────────────────────────────────────────
    w_z = 0.55
    w_b = 0.30
    w_e = 0.15

    if breach_score == 0.0:
        # Redistribute breach weight to z-score when no threshold info
        w_z, w_b, w_e = 0.70, 0.0, 0.30

    blended = w_z * z_score_norm + w_b * breach_score + w_e * ewma_score
    return round(min(blended, 1.0), 4)
