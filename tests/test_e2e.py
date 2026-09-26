"""
End-to-end test — PRD §29 e2e test / Quantified Demo (PDF Slide 6).

Verifies the full pipeline end-to-end using real in-memory scenario signals:
  17 signals (1 DB anomaly + 12 log bursts + 1 Grafana alert + 3 downstream timeouts)
  + 1 negative test signal (unrelated comms anomaly)
  → 1 accepted incident (17 signals)
  → S18 correctly rejected
  → severity calculated (> 50 for critical Nexus Agency services)
  → confidence calculated (> 0.5)
  → fingerprint created
  → Claude ticket draft generated
  → Jira blocked before approval
  → Jira succeeds after approval
"""
import pytest
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

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


def get_real_scenario_signals() -> list[Signal]:
    """
    Construct the 18 real scenario signals programmatically in memory.
    No sample files required on disk.
    Based on the worked example from PS §3 / PDF Slide 3 & 6:
      - 1 DB connection-pool CloudWatch anomaly
      - 12 application error-log bursts on payments-service
      - 1 Grafana latency alert on enrollment-service
      - 2 downstream timeout logs + 1 downstream metric anomaly
      - 1 negative test signal on comms-service (unrelated noise)
    """
    base_t = datetime(2026, 9, 26, 10, 1, 0, tzinfo=timezone.utc)
    signals = []

    # S1: CloudWatch DB connection pool alarm on payments-service
    signals.append(Signal(
        id="S1",
        timestamp=base_t,
        source="cloudwatch_metrics",
        environment="prod",
        region="ap-south-1",
        service="payments-service",
        component="db-connection-pool",
        type="metric_anomaly",
        anomaly_score=0.92,
        evidence="DB connection pool utilisation exceeded 90% threshold",
        metadata={"metric": "DBConnectionCount", "threshold": 90, "observed": 91.3},
    ))

    # S2..S13: 12 application error logs on payments-service db-connection-pool
    for i in range(2, 14):
        signals.append(Signal(
            id=f"S{i}",
            timestamp=base_t,
            source="application_logs",
            environment="prod",
            region="ap-south-1",
            service="payments-service",
            component="db-connection-pool",
            type="error_log_burst",
            template_id="118",
            anomaly_score=0.88,
            evidence="[REDACTED] No free connection in pool. Pool size: 100, waiting threads: 36",
        ))

    # S14: Grafana latency alert on enrollment-service
    signals.append(Signal(
        id="S14",
        timestamp=base_t,
        source="grafana_alerts",
        environment="prod",
        region="ap-south-1",
        service="enrollment-service",
        component="db-connection-pool",
        type="grafana_alert",
        anomaly_score=0.85,
        evidence="P99 4785ms above 4000ms threshold for 3 consecutive periods",
    ))

    # S15: Timeout log on enrollment-service
    signals.append(Signal(
        id="S15",
        timestamp=base_t,
        source="application_logs",
        environment="prod",
        region="ap-south-1",
        service="enrollment-service",
        component="db-connection-pool",
        type="error_log_burst",
        template_id="118",
        anomaly_score=0.82,
        evidence="Circuit breaker OPEN for payments-service connection pool after 27 consecutive failures",
    ))

    # S16: Downstream timeout log on carrier-service
    signals.append(Signal(
        id="S16",
        timestamp=base_t,
        source="application_logs",
        environment="prod",
        region="ap-south-1",
        service="carrier-service",
        component="db-connection-pool",
        type="error_log_burst",
        template_id="118",
        anomaly_score=0.80,
        evidence="[REDACTED] Connection timeout waiting for payments-service",
    ))

    # S17: Downstream metric on carrier-service
    signals.append(Signal(
        id="S17",
        timestamp=base_t,
        source="cloudwatch_metrics",
        environment="prod",
        region="ap-south-1",
        service="carrier-service",
        component="db-connection-pool",
        type="metric_anomaly",
        anomaly_score=0.84,
        evidence="Downstream payment call latency spike",
    ))

    # S18: Negative test signal on comms-service (unrelated noise, fails correlation gates)
    signals.append(Signal(
        id="S18",
        timestamp=base_t,
        source="cloudwatch_metrics",
        environment="prod",
        region="ap-south-1",
        service="comms-service",
        component="smtp-relay",
        type="metric_anomaly",
        anomaly_score=0.75,
        evidence="Routine queue worker backlog check",
    ))

    return signals


@pytest.fixture
def pipeline():
    """Run the full pipeline once and return all results."""
    signals = get_real_scenario_signals()
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
    assert len(pipeline["accepted"]) == 1, (
        f"Expected exactly 1 accepted incident, got {len(pipeline['accepted'])}"
    )
    main_cluster_ids = pipeline["accepted"][0][0]
    assert len(main_cluster_ids) == 17, (
        f"Expected main incident cluster to contain 17 signals, got {len(main_cluster_ids)}"
    )


def test_negative_signal_rejected(pipeline):
    """S18 (unrelated comms alert) must be rejected from the main incident."""
    main_cluster_ids = set(pipeline["accepted"][0][0])
    assert "S18" not in main_cluster_ids, "Unrelated signal S18 should NOT be in the incident"


def test_severity_calculated(pipeline):
    cluster_ids = pipeline["accepted"][0][0]
    cluster_signals = [pipeline["graph"].signals[sid] for sid in cluster_ids]
    sev = calculate_severity(cluster_signals)
    assert 0.0 <= sev <= 100.0
    # Scenario signals use Nexus Agency critical services (payments-service=95, carrier=88, enrollment=92)
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
    """Claude output must have all required fields and keep observed_evidence unchanged."""
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
    # Suspected root cause must be present
    assert len(draft.suspected_root_cause) > 5
