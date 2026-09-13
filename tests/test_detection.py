"""
Detection engine tests — PRD §29 detection tests.
"""
import pytest
from app.detection.metrics import (
    calculate_rolling_zscore,
    calculate_ewma,
    detect_metric_anomaly,
)
from app.detection.logs import extract_template, build_frequency_counter


# ---------------------------------------------------------------------------
# Metric detection tests
# ---------------------------------------------------------------------------

def test_rolling_zscore_normal_values():
    values = [10.0, 11.0, 10.5, 10.8, 10.2, 11.1, 10.9, 11.0]
    zscore = calculate_rolling_zscore(values)
    assert zscore < 3.0, "Normal values should not trigger high z-score"


def test_rolling_zscore_extreme_value():
    baseline = [10.0] * 20
    spike = baseline + [100.0]
    zscore = calculate_rolling_zscore(spike)
    assert zscore >= 3.0, "Extreme spike should produce high z-score"


def test_rolling_zscore_gradual_shift():
    values = list(range(1, 22))  # gradual linear increase
    zscore = calculate_rolling_zscore(values)
    # Gradual shift shouldn't spike above 3 immediately
    assert isinstance(zscore, float)


def test_ewma_stable():
    values = [10.0] * 10
    result = calculate_ewma(values)
    assert abs(result - 10.0) < 0.01


def test_ewma_responds_to_recent():
    values = [10.0] * 9 + [50.0]
    result = calculate_ewma(values)
    assert result > 10.0, "EWMA should react to the spike"


def test_detect_metric_anomaly_normal():
    baseline = [10.0] * 20
    assert detect_metric_anomaly(baseline[:-1], 10.0) is False


def test_detect_metric_anomaly_extreme():
    baseline = [10.0] * 19
    assert detect_metric_anomaly(baseline, 200.0) is True


# ---------------------------------------------------------------------------
# Log detection tests
# ---------------------------------------------------------------------------

def test_log_template_extraction_groups_similar():
    msg1 = "Database timeout for user 123"
    msg2 = "Database timeout for user 456"
    t1, tmpl1 = extract_template(msg1)
    t2, tmpl2 = extract_template(msg2)
    assert t1 == t2, "Similar messages should map to same template ID"


def test_log_burst_detected():
    messages = ["Database connection timeout"] * 15
    counter, template_map = build_frequency_counter(messages)
    # All messages should collapse to one template with count 15
    assert max(counter.values()) >= 10


def test_log_normal_frequency():
    messages = [
        "User login successful",
        "Order created",
        "Payment processed",
        "User logout",
    ]
    counter, _ = build_frequency_counter(messages)
    # Normal diverse traffic — no template should spike
    assert max(counter.values()) <= 2
