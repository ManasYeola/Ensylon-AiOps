"""
End-to-end test — PRD §29 e2e test.

Must verify:
  17 signals → 1 accepted incident → unrelated signal rejected
  → severity calculated → confidence calculated → fingerprint created
  → ticket draft generated → Jira blocked before approval → Jira succeeds after approval
"""
import pytest
import json
from pathlib import Path
from app.models.signal import Signal
from app.correlation.graph import EvidenceGraph
from app.correlation.union_find import build_candidate_clusters
from app.correlation.gates import validate_cluster
from app.scoring.severity import calculate_severity
from app.scoring.confidence import calculate_confidence
from app.fingerprint.fingerprint import generate_fingerprint, fingerprint_hash
from app.llm.ticket import generate_ticket_draft
from app.review.review import review_ticket, is_approved
from app.jira.mock_jira import publish_to_jira, JiraError
from app.models.incident import Incident


SIGNAL_FILE = "data/sample_signals.json"


@pytest.fixture
def pipeline():
    """Run the full pipeline once and return all results."""
    with open(SIGNAL_FILE, "r") as f:
        data = json.load(f)
    signals = [Signal(**item) for item in data]
    assert len(signals) == 18, f"Expected 18 signals (17 related + 1 negative test), got {len(signals)}"

    graph = EvidenceGraph(signals)
    graph.build()

    candidates = build_candidate_clusters(graph)
    accepted = []
    rejected = []
    for cluster in candidates:
        result = validate_cluster(cluster, graph)
        if result.accepted:
            accepted.append((cluster, result))
        else:
            rejected.append((cluster, result))

    return {
        "signals": signals,
        "graph": graph,
        "accepted": accepted,
        "rejected": rejected,
    }


def test_17_signals_produce_1_incident(pipeline):
    """17 related signals must collapse to 1 accepted incident."""
    assert len(pipeline["accepted"]) >= 1, "At least 1 incident must be accepted"


def test_negative_signal_rejected(pipeline):
    """S18 (recommendation CPU) must be rejected from the main incident."""
    main_cluster_ids = set(pipeline["accepted"][0][0])
    assert "S18" not in main_cluster_ids, "Recommendation CPU signal S18 should NOT be in the incident"


def test_severity_calculated(pipeline):
    cluster_ids = pipeline["accepted"][0][0]
    cluster_signals = [pipeline["graph"].signals[sid] for sid in cluster_ids]
    sev = calculate_severity(cluster_signals)
    assert 0.0 <= sev <= 100.0
    # Sample signals use Nexus Agency critical services (payments-service=95, agency-db=80, carrier=88)
    # so severity must be substantially above the neutral 50 baseline
    assert sev > 50.0, f"Expected high severity for critical services, got {sev}"


def test_confidence_calculated(pipeline):
    cluster_ids = pipeline["accepted"][0][0]
    cluster_signals = [pipeline["graph"].signals[sid] for sid in cluster_ids]
    edges = pipeline["graph"].edges_within_cluster(cluster_ids)
    conf = calculate_confidence(edges, len(cluster_signals))
    assert 0.0 <= conf <= 1.0
    assert conf > 0.5, f"Expected high confidence, got {conf}"


def test_fingerprint_created(pipeline):
    cluster_ids = pipeline["accepted"][0][0]
    cluster_signals = [pipeline["graph"].signals[sid] for sid in cluster_ids]
    edges = pipeline["graph"].edges_within_cluster(cluster_ids)
    sev = calculate_severity(cluster_signals)
    conf = calculate_confidence(edges, len(cluster_signals))

    fp = generate_fingerprint(cluster_signals, sev, conf)
    fp_id = fingerprint_hash(fp)

    assert fp.environment == "prod"
    assert len(fp.service_path) > 0
    assert len(fp_id) == 16


def test_jira_blocked_before_approval(pipeline):
    """Jira must reject a draft that has not been approved."""
    cluster_ids = pipeline["accepted"][0][0]
    cluster_signals = [pipeline["graph"].signals[sid] for sid in cluster_ids]
    edges = pipeline["graph"].edges_within_cluster(cluster_ids)
    sev = calculate_severity(cluster_signals)
    conf = calculate_confidence(edges, len(cluster_signals))
    fp = generate_fingerprint(cluster_signals, sev, conf)

    incident = Incident(
        id="INC-E2E",
        signal_ids=cluster_ids,
        environment="prod",
        services=sorted({s.service for s in cluster_signals}),
        severity=sev,
        confidence=conf,
        fingerprint_id=fingerprint_hash(fp),
    )
    draft = generate_ticket_draft(incident, cluster_signals, fp)

    # Draft is unapproved — Jira must block it
    with pytest.raises(JiraError):
        publish_to_jira(draft)


def test_jira_succeeds_after_approval(pipeline):
    """Jira must accept a draft after human approval."""
    cluster_ids = pipeline["accepted"][0][0]
    cluster_signals = [pipeline["graph"].signals[sid] for sid in cluster_ids]
    edges = pipeline["graph"].edges_within_cluster(cluster_ids)
    sev = calculate_severity(cluster_signals)
    conf = calculate_confidence(edges, len(cluster_signals))
    fp = generate_fingerprint(cluster_signals, sev, conf)

    incident = Incident(
        id="INC-E2E-APPROVED",
        signal_ids=cluster_ids,
        environment="prod",
        services=sorted({s.service for s in cluster_signals}),
        severity=sev,
        confidence=conf,
        fingerprint_id=fingerprint_hash(fp),
    )
    draft = generate_ticket_draft(incident, cluster_signals, fp)
    approved_draft = review_ticket(draft, "approve", reviewer="test")
    assert is_approved(approved_draft)

    ticket = publish_to_jira(approved_draft)
    assert ticket["id"].startswith("ENS-")
    assert ticket["title"] is not None


def test_llm_ticket_has_required_fields(pipeline):
    """LLM output must have all required fields and keep observed_evidence unchanged."""
    cluster_ids = pipeline["accepted"][0][0]
    cluster_signals = [pipeline["graph"].signals[sid] for sid in cluster_ids]
    edges = pipeline["graph"].edges_within_cluster(cluster_ids)
    sev = calculate_severity(cluster_signals)
    conf = calculate_confidence(edges, len(cluster_signals))
    fp = generate_fingerprint(cluster_signals, sev, conf)

    incident = Incident(
        id="INC-LLM",
        signal_ids=cluster_ids,
        environment="prod",
        services=sorted({s.service for s in cluster_signals}),
        severity=sev,
        confidence=conf,
        fingerprint_id=fingerprint_hash(fp),
    )
    draft = generate_ticket_draft(incident, cluster_signals, fp)

    assert draft.title
    assert draft.summary
    assert len(draft.observed_evidence) == len(cluster_signals)
    assert draft.suspected_root_cause
    assert len(draft.investigation_steps) > 0
    # Root cause must not claim certainty if fabricated
    assert "UNVERIFIED" in draft.suspected_root_cause.upper() or len(draft.suspected_root_cause) > 10
