"""
Metric anomaly detection.
Implements rolling z-score, EWMA, and the composite score_metric_signal() function.
All thresholds loaded from config.yaml (HTML §C2).

Key public API
--------------
score_metric_signal(history, current_value, ...)  → float  (0.0–1.0 anomaly_score)
detect_metric_anomaly(...)                         → bool   (legacy gate; kept for tests)

Scoring strategy for CloudWatch metric signals
----------------------------------------------
CloudWatch already made the alarm/OK decision; we respect that signal and
translate it into the 0.0–1.0 anomaly_score scale used by C3.

  - alarm_state == "OK"    → 0.0  immediately (recovery / no-fault)
  - alarm_state == "ALARM" with observed > threshold:
        breach_ratio dominates (weight 0.55); z-score and EWMA
        contribute when history is available but are NOT required.
  - No alarm_state / no threshold → pure z-score + EWMA path (unchanged).
"""
from typing import Optional
import math
from app.config import get_detection_cfg


def calculate_rolling_zscore(values: list[float], window_size: Optional[int] = None) -> float:
    """
    Calculate z-score of the most recent value relative to a rolling window.
    Returns 0.0 if the window is too small to compute a baseline (< 2 samples).
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


def _breach_ratio(observed: float, threshold: float) -> float:
    """
    Fraction by which the observed value exceeds the threshold.

    Returns a value in [0.0, ∞):
      - 0.0  when observed ≤ threshold (no breach)
      - 0.014 for 91.3 vs threshold 90  (1.4% over)
      - 1.0  when observed is 2× the threshold

    Callers should clamp with min(..., 1.0).
    """
    if threshold <= 0:
        return 0.0
    return max((observed - threshold) / threshold, 0.0)


def score_metric_signal(
    history: list[float],
    current_value: float,
    window_size: Optional[int] = None,
    threshold_value: Optional[float] = None,
    pct_threshold: Optional[float] = None,
    alarm_state: Optional[str] = None,
) -> float:
    """
    Compute anomaly_score (0.0–1.0) for a metric signal.

    Parameters
    ----------
    history        : Previously observed values for this (service, component) key.
                     May be empty for the very first event.
    current_value  : The metric value observed in this event (ObservedValue from Trigger).
    window_size    : Rolling window size; defaults to config detection.window_size.
    threshold_value: The alarm threshold (Trigger.Threshold from CloudWatch payload).
                     When provided together with alarm_state the breach score is computed.
    pct_threshold  : DEPRECATED — ignored; kept for call-site compatibility.
                     The breach ratio is always computed from observed / threshold internally.
    alarm_state    : "ALARM" | "OK" | None.
                     "OK"    → score is 0.0 immediately (recovery / no-fault event).
                     "ALARM" → breach ratio is the primary signal; history optional.
                     None    → pure statistical path (z-score + EWMA).

    Scoring strategy
    ----------------
    With alarm_state == "ALARM" and threshold_value available:
        w_breach = 0.55, w_z = 0.30, w_ewma = 0.15
        When no history: breach score dominates; z/EWMA contribute 0.

    Without alarm_state / threshold_value:
        w_z = 0.70, w_ewma = 0.30  (unchanged behaviour for non-CW sources)
    """
    # ── Fast path: OK / recovery events are never anomalous ─────────────────
    if alarm_state is not None and alarm_state.upper() == "OK":
        return 0.0

    cfg = get_detection_cfg()
    w = window_size or cfg["window_size"]
    z_cap = cfg.get("zscore_cap", 6.0)

    all_values = history + [current_value]

    # ── Component 1: normalised z-score (0.0 when history < 2) ──────────────
    zscore = calculate_rolling_zscore(all_values, w)
    z_score_norm = min(zscore / z_cap, 1.0)

    # ── Component 2: EWMA deviation ─────────────────────────────────────────
    # Use only the prior history as the EWMA baseline.
    # With empty history EWMA baseline = 0, deviation = 0 → ewma_score = 0.
    if history:
        ewma_val = calculate_ewma(history, cfg["ewma_alpha"])
        if ewma_val != 0:
            ewma_dev = abs(current_value - ewma_val) / abs(ewma_val)
        else:
            ewma_dev = 0.0
    else:
        ewma_dev = 0.0
    ewma_score = min(ewma_dev, 1.0)

    # ── Component 3: threshold breach score (0.0 when no threshold) ─────────
    breach_score = 0.0
    if threshold_value is not None:
        breach_score = min(_breach_ratio(current_value, threshold_value), 1.0)

    # ── Blend (weights, then floor) ──────────────────────────────────────────
    if breach_score > 0.0:
        # Threshold info available — breach dominates (ALARM) or assists (no state)
        w_b, w_z, w_e = 0.55, 0.30, 0.15
        blended = w_b * breach_score + w_z * z_score_norm + w_e * ewma_score
    else:
        # No threshold info — pure statistics path
        w_z, w_e = 0.70, 0.30
        blended = w_z * z_score_norm + w_e * ewma_score

    # For confirmed ALARM events apply a hard floor of 0.55 so that even a
    # marginal breach (e.g. 91.3 vs threshold 90) is always treated as anomalous.
    # CloudWatch evaluated multiple consecutive periods before firing — that
    # evaluation adds confidence the stat-only path cannot replicate cold.
    if (
        alarm_state is not None
        and alarm_state.upper() == "ALARM"
        and threshold_value is not None
        and current_value > threshold_value
    ):
        blended = max(blended, 0.55)

    return round(min(blended, 1.0), 4)

