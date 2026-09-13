"""
Validation Gate tests — PRD §29 gate tests.
"""
import pytest
from datetime import datetime, timedelta
from app.models.signal import Signal
from app.correlation.graph import EvidenceGraph
from app.correlation.gates import (
    validate_strong_edge,
    validate_environment_consistency,
    validate_coherence,
    validate_bridge,
    validate_cluster,
)

BASE_TIME = datetime(2026, 9, 12, 10, 0, 0)


def make_signal(id, service="payment", component="api", environment="prod",
                type="log_anomaly", template_id="T001", offset=0) -> Signal:
    return Signal(
        id=id,
        timestamp=BASE_TIME + timedelta(seconds=offset),
        source="application_log",
        environment=environment,
        service=service,
        component=component,
        type=type,
        template_id=template_id,
    )


def build_graph(*signals) -> EvidenceGraph:
    g = EvidenceGraph(list(signals))
    g.build()
    return g


# ---------------------------------------------------------------------------
# Gate 1 — Strong Edge
# ---------------------------------------------------------------------------

def test_gate1_passes_with_strong_edge():
    a = make_signal("A")
    b = make_signal("B", offset=5)
    graph = build_graph(a, b)
    result = validate_strong_edge(["A", "B"], graph)
    assert result.passed


def test_gate1_fails_single_signal():
    a = make_signal("A")
    graph = build_graph(a)
    result = validate_strong_edge(["A"], graph)
    assert not result.passed


def test_gate1_fails_weak_only():
    # recommendation service → no topology to payment → score will be weak
    a = make_signal("A", service="payment", template_id="T001", offset=0)
    b = make_signal("B", service="recommendation", type="metric_anomaly", template_id=None, offset=250)
    graph = build_graph(a, b)
    result = validate_strong_edge(["A", "B"], graph)
    assert not result.passed


# ---------------------------------------------------------------------------
# Gate 2 — Environment Consistency
# ---------------------------------------------------------------------------

def test_gate2_passes_same_env():
    a = make_signal("A", environment="prod")
    b = make_signal("B", environment="prod")
    graph = build_graph(a, b)
    result = validate_environment_consistency(["A", "B"], graph.signals)
    assert result.passed


def test_gate2_fails_mixed_env():
    a = make_signal("A", environment="prod")
    b = make_signal("B", environment="staging")
    graph = build_graph(a, b)
    result = validate_environment_consistency(["A", "B"], graph.signals)
    assert not result.passed


# ---------------------------------------------------------------------------
# Gate 3 — Coherence
# ---------------------------------------------------------------------------

def test_gate3_passes_coherent_cluster():
    sigs = [make_signal(f"S{i}", offset=i*5) for i in range(4)]
    graph = build_graph(*sigs)
    ids = [s.id for s in sigs]
    result = validate_coherence(ids, graph)
    assert result.passed


def test_gate3_fails_single():
    a = make_signal("A")
    graph = build_graph(a)
    result = validate_coherence(["A"], graph)
    assert not result.passed


# ---------------------------------------------------------------------------
# Gate 4 — Bridge Check
# ---------------------------------------------------------------------------

def test_gate4_passes_fully_connected():
    sigs = [make_signal(f"S{i}", offset=i*5) for i in range(3)]
    graph = build_graph(*sigs)
    ids = [s.id for s in sigs]
    result = validate_bridge(ids, graph)
    assert result.passed


# ---------------------------------------------------------------------------
# Full cluster validation — PRD §29 gate tests
# ---------------------------------------------------------------------------

def test_full_validation_accepts_coherent_cluster():
    sigs = [make_signal(f"S{i}", offset=i*10) for i in range(5)]
    graph = build_graph(*sigs)
    ids = [s.id for s in sigs]
    result = validate_cluster(ids, graph)
    assert result.accepted


def test_full_validation_rejects_env_mismatch():
    a = make_signal("A", environment="prod")
    b = make_signal("B", environment="staging", offset=5)
    graph = build_graph(a, b)
    result = validate_cluster(["A", "B"], graph)
    assert not result.accepted
    assert not result.gates["environment_consistency"].passed


def test_gate_results_expose_all_four_gates():
    sigs = [make_signal(f"S{i}", offset=i*5) for i in range(3)]
    graph = build_graph(*sigs)
    ids = [s.id for s in sigs]
    result = validate_cluster(ids, graph)
    gate_dict = result.to_dict()
    assert "strong_edge" in gate_dict["gates"]
    assert "environment_consistency" in gate_dict["gates"]
    assert "coherence" in gate_dict["gates"]
    assert "bridge_check" in gate_dict["gates"]
