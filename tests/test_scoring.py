"""
Severity and Confidence tests.

Uses the real Nexus Agency service names from data/criticality_map.json
(HTML §6.2) so the assertions reflect the actual business-criticality rankings.

Service criticality reference:
    payments-service     95
    enrollment-service   92
    carrier-service      88
    agency-gateway       85
    agency-db            80
    compensation-service 78
    rulesforge           75
    party-service        72
    distribution-service 65
    product-service      60
    comms-service        40
    docforge             30
    <unknown>            50  (default per HTML §6.2)
"""
import pytest
from datetime import datetime, timedelta
import json
from pathlib import Path
from app.models.signal import Signal
from app.scoring.severity import (
    calculate_severity,
    get_service_criticality,
    _load_criticality_map,
    CRITICALITY_MAP_PATH,
)
from app.scoring.confidence import calculate_confidence
from app.correlation.graph import EvidenceGraph
from app.config import load_config

BASE_TIME = datetime(2026, 9, 26, 10, 0, 0)


def make_signal(id, service="payments-service", value=None, offset=0, anomaly_score=0.0) -> Signal:
    return Signal(
        id=id,
        timestamp=BASE_TIME + timedelta(seconds=offset),
        source="cloudwatch_metrics",
        environment="prod",
        service=service,
        component="api",
        type="metric_anomaly",
        value=value,
        anomaly_score=anomaly_score,
    )


# ---------------------------------------------------------------------------
# Severity tests
# ---------------------------------------------------------------------------

def test_severity_range():
    sigs = [make_signal(f"S{i}", service="payments-service", value=95) for i in range(5)]
    result = calculate_severity(sigs)
    assert 0.0 <= result <= 100.0


def test_severity_critical_service_raises_score():
    """payments-service (95) must score higher than docforge (30)."""
    payment_sigs = [make_signal(f"P{i}", service="payments-service", value=95) for i in range(3)]
    low_sigs     = [make_signal(f"L{i}", service="docforge",          value=20) for i in range(3)]
    payment_score = calculate_severity(payment_sigs)
    low_score     = calculate_severity(low_sigs)
    assert payment_score > low_score, (
        f"payments-service (criticality=95) must score higher than docforge (30), "
        f"got {payment_score} vs {low_score}"
    )


def test_severity_multi_service_higher_than_single():
    single = [make_signal("S1", service="payments-service")]
    multi  = [
        make_signal("S1", service="payments-service"),
        make_signal("S2", service="enrollment-service"),
        make_signal("S3", service="carrier-service"),
        make_signal("S4", service="agency-db"),
    ]
    assert calculate_severity(multi) > calculate_severity(single)


def test_severity_expected_range_for_scenario():
    """High-impact multi-service scenario should produce severity >= 70."""
    sigs = [
        make_signal("S1", service="agency-db",        value=98,  offset=0,   anomaly_score=0.9),
        make_signal("S2", service="payments-service",  value=None, offset=20, anomaly_score=0.8),
        make_signal("S3", service="enrollment-service",value=850, offset=200, anomaly_score=0.7),
        make_signal("S4", service="carrier-service",   value=None, offset=240, anomaly_score=0.6),
    ]
    sev = calculate_severity(sigs)
    assert sev >= 70.0, f"Expected high severity, got {sev}"


def test_severity_unknown_service_gets_neutral_default():
    """Unknown services get criticality 50 — neither high nor trivial (HTML §6.2)."""
    known   = [make_signal("K1", service="payments-service")]
    unknown = [make_signal("U1", service="totally-unknown-svc")]
    known_score   = calculate_severity(known)
    unknown_score = calculate_severity(unknown)
    # unknown should be strictly less than payments-service (95) and non-zero
    assert 0 < unknown_score < known_score


def test_severity_magnitude_uses_anomaly_score():
    """
    When anomaly_score is set, magnitude should reflect it.
    Two clusters identical except one has higher anomaly_scores should differ in severity.
    """
    low  = [make_signal("L1", service="agency-db", anomaly_score=0.2)]
    high = [make_signal("H1", service="agency-db", anomaly_score=0.9)]
    assert calculate_severity(high) > calculate_severity(low)


def test_service_criticality_matches_criticality_map_json():
    """Verify that get_service_criticality pulls values exclusively from data/criticality_map.json."""
    with open(CRITICALITY_MAP_PATH, "r", encoding="utf-8") as f:
        expected_map = json.load(f)

    assert len(expected_map) > 0
    for svc_name, expected_val in expected_map.items():
        assert get_service_criticality(svc_name) == float(expected_val)
        # Test case-insensitivity
        assert get_service_criticality(svc_name.upper()) == float(expected_val)


def test_config_yaml_has_no_service_criticality():
    """Verify config.yaml has no redundant service_criticality section."""
    load_config.cache_clear()
    cfg = load_config()
    assert "service_criticality" not in cfg.get("severity", {})


def test_missing_criticality_map_raises_error(monkeypatch):
    """Verify there is no silent hardcoded fallback if criticality_map.json is missing."""
    _load_criticality_map.cache_clear()
    fake_path = Path("non_existent_dir/criticality_map.json")
    monkeypatch.setattr("app.scoring.severity.CRITICALITY_MAP_PATH", fake_path)
    with pytest.raises(FileNotFoundError):
        _load_criticality_map()
    _load_criticality_map.cache_clear()



# ---------------------------------------------------------------------------
# Confidence tests
# ---------------------------------------------------------------------------

def _get_edges_for(signals):
    graph = EvidenceGraph(signals)
    graph.build()
    ids = [s.id for s in signals]
    return graph.edges_within_cluster(ids)


def test_confidence_range():
    sigs = [make_signal(f"S{i}", service="payments-service", offset=i*10) for i in range(4)]
    edges = _get_edges_for(sigs)
    conf = calculate_confidence(edges, len(sigs))
    assert 0.0 <= conf <= 1.0


def test_confidence_same_service_higher():
    same = [make_signal(f"S{i}", service="payments-service", offset=i*5) for i in range(4)]
    diff = [
        make_signal("A", service="payments-service",  offset=0),
        make_signal("B", service="comms-service",     offset=10),
        make_signal("C", service="docforge",          offset=20),
        make_signal("D", service="unknown-svc-xyz",   offset=30),
    ]
    edges_same = _get_edges_for(same)
    edges_diff = _get_edges_for(diff)
    conf_same  = calculate_confidence(edges_same, len(same))
    conf_diff  = calculate_confidence(edges_diff, len(diff))
    assert conf_same > conf_diff


def test_confidence_no_edges():
    conf = calculate_confidence([], 0)
    assert conf == 0.0


def test_severity_and_confidence_are_independent():
    """Severity and confidence must be computed independently (HTML §C4)."""
    sigs  = [make_signal(f"S{i}", service="payments-service", value=90, offset=i*10) for i in range(5)]
    edges = _get_edges_for(sigs)
    sev1  = calculate_severity(sigs)
    conf1 = calculate_confidence(edges, len(sigs))
    sev2  = calculate_severity(sigs)
    conf2 = calculate_confidence(edges, len(sigs))
    assert sev1 == sev2
    assert conf1 == conf2
