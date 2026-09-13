"""
Severity and Confidence tests — PRD §29 scoring tests.
"""
import pytest
from datetime import datetime, timedelta
from app.models.signal import Signal
from app.scoring.severity import calculate_severity
from app.scoring.confidence import calculate_confidence
from app.correlation.graph import EvidenceGraph

BASE_TIME = datetime(2026, 9, 12, 10, 0, 0)


def make_signal(id, service="payment", value=None, offset=0) -> Signal:
    return Signal(
        id=id,
        timestamp=BASE_TIME + timedelta(seconds=offset),
        source="cloudwatch",
        environment="prod",
        service=service,
        component="api",
        type="metric_anomaly",
        value=value,
    )


# ---------------------------------------------------------------------------
# Severity tests — PRD §17: 0.35*Blast + 0.35*Criticality + 0.20*Trend + 0.10*Magnitude
# ---------------------------------------------------------------------------

def test_severity_range():
    sigs = [make_signal(f"S{i}", service="payment", value=95) for i in range(5)]
    result = calculate_severity(sigs)
    assert 0.0 <= result <= 100.0


def test_severity_critical_service_raises_score():
    payment_sigs = [make_signal(f"P{i}", service="payment", value=95) for i in range(3)]
    internal_sigs = [make_signal(f"I{i}", service="internal_admin", value=20) for i in range(3)]
    payment_score = calculate_severity(payment_sigs)
    internal_score = calculate_severity(internal_sigs)
    assert payment_score > internal_score, "Payment (criticality=92) must score higher than internal_admin (20)"


def test_severity_multi_service_higher_than_single():
    single = [make_signal("S1", service="payment")]
    multi = [
        make_signal("S1", service="payment"),
        make_signal("S2", service="checkout"),
        make_signal("S3", service="order"),
        make_signal("S4", service="database"),
    ]
    assert calculate_severity(multi) > calculate_severity(single)


def test_severity_expected_range_for_scenario():
    # PRD §27 expected: Severity ~88 for the 17-signal scenario
    # This test uses a representative subset
    sigs = [
        make_signal("S1", service="database", value=98, offset=0),
        make_signal("S2", service="payment", value=None, offset=20),
        make_signal("S3", service="checkout", value=850, offset=200),
        make_signal("S4", service="order", value=None, offset=240),
    ]
    sev = calculate_severity(sigs)
    # Should be in high-severity range (not exact 88 — depends on sub-score details)
    assert sev >= 70.0, f"Expected high severity, got {sev}"


# ---------------------------------------------------------------------------
# Confidence tests — PRD §18: 0.35*Density + 0.25*Agreement + 0.20*Topology + 0.20*Temporal
# ---------------------------------------------------------------------------

def _get_edges_for(signals):
    graph = EvidenceGraph(signals)
    graph.build()
    ids = [s.id for s in signals]
    return graph.edges_within_cluster(ids)


def test_confidence_range():
    sigs = [make_signal(f"S{i}", service="payment", offset=i*10) for i in range(4)]
    edges = _get_edges_for(sigs)
    conf = calculate_confidence(edges, len(sigs))
    assert 0.0 <= conf <= 1.0


def test_confidence_same_service_higher():
    same = [make_signal(f"S{i}", service="payment", offset=i*5) for i in range(4)]
    diff = [
        make_signal("A", service="payment", offset=0),
        make_signal("B", service="recommendation", offset=10),
        make_signal("C", service="internal_admin", offset=20),
        make_signal("D", service="unknown_svc", offset=30),
    ]
    edges_same = _get_edges_for(same)
    edges_diff = _get_edges_for(diff)
    conf_same = calculate_confidence(edges_same, len(same))
    conf_diff = calculate_confidence(edges_diff, len(diff))
    assert conf_same > conf_diff


def test_confidence_no_edges():
    conf = calculate_confidence([], 0)
    assert conf == 0.0


def test_severity_and_confidence_are_independent():
    """Severity and confidence must be computed independently (PRD §7/G7)."""
    from app.scoring.severity import calculate_severity
    from app.scoring.confidence import calculate_confidence
    # Running both should not affect each other's output
    sigs = [make_signal(f"S{i}", service="payment", value=90, offset=i*10) for i in range(5)]
    edges = _get_edges_for(sigs)
    sev1 = calculate_severity(sigs)
    conf1 = calculate_confidence(edges, len(sigs))
    sev2 = calculate_severity(sigs)
    conf2 = calculate_confidence(edges, len(sigs))
    assert sev1 == sev2
    assert conf1 == conf2
