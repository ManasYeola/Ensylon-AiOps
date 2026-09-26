"""
Correlation + Union-Find tests — PRD §29 correlation and Union-Find tests.
"""
import pytest
from datetime import datetime, timedelta
from app.models.signal import Signal
from app.correlation.scoring import (
    calculate_temporal_score,
    calculate_service_score,
    calculate_component_score,
    calculate_topology_score,
    calculate_evidence_similarity,
    correlation_score,
)
from app.correlation.graph import EvidenceGraph
from app.correlation.union_find import UnionFind, build_candidate_clusters


BASE_TIME = datetime(2026, 9, 12, 10, 0, 0)


def make_signal(
    id="S1",
    service="payments-service",
    component="api",
    type="error_log_burst",
    template_id=None,
    environment="prod",
    offset_seconds=0,
    value=None,
) -> Signal:
    return Signal(
        id=id,
        timestamp=BASE_TIME + timedelta(seconds=offset_seconds),
        source="application_logs",
        environment=environment,
        service=service,
        component=component,
        type=type,
        template_id=template_id,
        value=value,
    )


# ---------------------------------------------------------------------------
# Temporal score
# ---------------------------------------------------------------------------

def test_temporal_same_time():
    a = make_signal("A")
    b = make_signal("B")
    assert calculate_temporal_score(a, b) == 1.0


def test_temporal_at_window_boundary():
    a = make_signal("A", offset_seconds=0)
    b = make_signal("B", offset_seconds=300)  # exactly 5 min
    score = calculate_temporal_score(a, b)
    assert score == 0.0


def test_temporal_weak():
    a = make_signal("A", offset_seconds=0)
    b = make_signal("B", offset_seconds=250)
    score = calculate_temporal_score(a, b)
    assert 0.0 < score < 0.3


# ---------------------------------------------------------------------------
# Service score
# ---------------------------------------------------------------------------

def test_service_same():
    a = make_signal("A", service="payments-service")
    b = make_signal("B", service="payments-service")
    assert calculate_service_score(a, b) == 1.0


def test_service_different():
    a = make_signal("A", service="payments-service")
    b = make_signal("B", service="comms-service")
    assert calculate_service_score(a, b) == 0.0


# ---------------------------------------------------------------------------
# Topology score — uses data/topology.json (HTML §6.1 Nexus Agency graph)
# Key edges: payments-service → agency-db (1 hop), enrollment-service → payments-service (1 hop)
# ---------------------------------------------------------------------------

def test_topology_same_service():
    a = make_signal("A", service="payments-service")
    b = make_signal("B", service="payments-service")
    assert calculate_topology_score(a, b) == 1.0


def test_topology_direct_neighbor():
    # payments-service → agency-db is a direct 1-hop dependency (HTML §6.1)
    a = make_signal("A", service="payments-service")
    b = make_signal("B", service="agency-db")
    score = calculate_topology_score(a, b)
    assert score >= 0.80


def test_topology_no_relationship():
    # In the Nexus Agency undirected graph most services connect through agency-db.
    # The scorer returns 0.0 only for pairs with hop-distance > 3.
    # comms-service is reachable from docforge in 3 hops (docforge→agency-db→carrier-service→comms-service)
    # so score = 0.30.  Two services with NO path at all would need an isolated node, which doesn't
    # exist in this graph.  We assert the score is strictly less than the strong-edge threshold (0.70).
    a = make_signal("A", service="docforge")
    b = make_signal("B", service="comms-service")
    score = calculate_topology_score(a, b)
    assert score < 0.70, f"Distant services should not have a strong topology score, got {score}"


# ---------------------------------------------------------------------------
# Evidence similarity
# ---------------------------------------------------------------------------

def test_evidence_same_type_same_template():
    a = make_signal("A", type="log_anomaly", template_id="T001")
    b = make_signal("B", type="log_anomaly", template_id="T001")
    assert calculate_evidence_similarity(a, b) == 1.0


def test_evidence_same_type_different_template():
    a = make_signal("A", type="log_anomaly", template_id="T001")
    b = make_signal("B", type="log_anomaly", template_id="T002")
    score = calculate_evidence_similarity(a, b)
    assert 0 < score < 1.0


def test_evidence_different_type():
    a = make_signal("A", type="log_anomaly")
    b = make_signal("B", type="metric_anomaly")
    assert calculate_evidence_similarity(a, b) == 0.0


# ---------------------------------------------------------------------------
# Union-Find
# ---------------------------------------------------------------------------

def test_union_find_basic():
    uf = UnionFind(["A", "B", "C", "D"])
    uf.union("A", "B")
    uf.union("B", "C")
    # A-B-C should be in same group
    assert uf.find("A") == uf.find("B") == uf.find("C")
    # D remains separate
    assert uf.find("D") != uf.find("A")


def test_union_find_strong_edges_cluster():
    """
    PRD §29 Union-Find test: A-B=0.90, B-C=0.85, C-D=0.30
    Expected candidate: {A,B,C}; D remains separate.
    """
    # Build signals where A-B and B-C are strongly correlated (same service, same time)
    # and C-D are weakly correlated (different service, no topology)
    a = make_signal("A", service="payments-service", template_id="T001", offset_seconds=0)
    b = make_signal("B", service="payments-service", template_id="T001", offset_seconds=10)
    c = make_signal("C", service="payments-service", template_id="T001", offset_seconds=20)
    d = make_signal("D", service="comms-service", type="metric_anomaly", offset_seconds=30)

    graph = EvidenceGraph([a, b, c, d])
    graph.build()

    clusters = build_candidate_clusters(graph)
    # Find which cluster contains A
    cluster_with_a = next((cl for cl in clusters if "A" in cl), [])
    assert "A" in cluster_with_a
    assert "B" in cluster_with_a
    assert "C" in cluster_with_a
    # D should NOT be in the same cluster as A
    assert "D" not in cluster_with_a
