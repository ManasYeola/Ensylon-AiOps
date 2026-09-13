"""
End-to-end demo script — PRD §27.
Runs the full pipeline: load → detect → correlate → validate → score → fingerprint → LLM → review → Jira.
Expected to produce the 8-step output format specified in PRD §27.

Usage:
    python scripts/run_demo.py
"""
import sys
import os
from pathlib import Path

# Allow running from any working directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Load .env BEFORE any app imports so os.getenv() picks up the keys
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(dotenv_path=_env_path)
except ImportError:
    pass  # python-dotenv not installed; rely on shell env vars

from datetime import datetime
from app.ingestion.logs import load_signals
from app.models.signal import Signal
from app.models.incident import Incident
from app.correlation.graph import EvidenceGraph
from app.correlation.union_find import build_candidate_clusters
from app.correlation.gates import validate_cluster
from app.scoring.severity import calculate_severity
from app.scoring.confidence import calculate_confidence
from app.fingerprint.fingerprint import generate_fingerprint, fingerprint_hash
from app.llm.ticket import generate_ticket_draft
from app.review.review import review_ticket, is_approved
from app.jira.mock_jira import publish_to_jira, JiraError


SEP = "=" * 50


def step(n: int, total: int, label: str, status: str = "OK"):
    print(f"[{n}/{total}] {label:<28} {status}")


def run_demo(signal_file: str = "data/sample_signals.json") -> None:
    print()
    print(SEP)
    print("  ENSYLON AIOPS DEMO")
    print(SEP)
    print()

    total_steps = 8

    # -----------------------------------------------------------------------
    # Step 1 — Load telemetry
    # -----------------------------------------------------------------------
    signals = load_signals(signal_file)
    step(1, total_steps, "Loading telemetry.............", "OK")
    print(f"      {len(signals)} signals\n")

    # -----------------------------------------------------------------------
    # Step 2 — Detect anomalies
    # (For replay data every signal is already an anomaly — they were detected
    #  by the source systems and included in the replay dataset as per PRD §11)
    # -----------------------------------------------------------------------
    anomalies: list[Signal] = signals   # All 18 replay signals are anomalies
    step(2, total_steps, "Detecting anomalies...........", "OK")
    print(f"      {len(anomalies)} anomalies\n")

    # -----------------------------------------------------------------------
    # Step 3 — Build evidence graph
    # -----------------------------------------------------------------------
    graph = EvidenceGraph(anomalies)
    graph.build()
    strong_edges = graph.get_strong_edges()
    step(3, total_steps, "Building evidence graph.......", "OK")
    print(f"      {len(graph.edges)} total edges, {len(strong_edges)} strong\n")

    # -----------------------------------------------------------------------
    # Step 4 — Correlation / Union-Find
    # -----------------------------------------------------------------------
    candidates = build_candidate_clusters(graph)
    step(4, total_steps, "Correlation...................", "OK")
    print(f"      {len(candidates)} candidate cluster(s)\n")

    # -----------------------------------------------------------------------
    # Step 5 — Validate through 4 gates
    # -----------------------------------------------------------------------
    accepted = []
    rejected_clusters = []
    rejected_signals = []

    for cluster in candidates:
        result = validate_cluster(cluster, graph)
        if result.accepted:
            accepted.append(cluster)
        else:
            # Identify which signals were rejected and why
            rejected_clusters.append((cluster, result))
            rejected_signals.extend(cluster)

    step(5, total_steps, "Validation....................", "OK")
    print(f"      {len(accepted)} accepted incident(s)")
    print(f"      {len(rejected_clusters)} rejected cluster(s)\n")

    if not accepted:
        print("  ⚠  No incidents accepted. Check signal data and thresholds.")
        return

    # -----------------------------------------------------------------------
    # Step 6 — Severity + Confidence
    # -----------------------------------------------------------------------
    # Work with the largest accepted cluster (primary incident)
    main_cluster_ids = max(accepted, key=len)
    main_signals = [graph.signals[sid] for sid in main_cluster_ids]
    internal_edges = graph.edges_within_cluster(main_cluster_ids)

    severity = calculate_severity(main_signals)
    confidence = calculate_confidence(internal_edges, len(main_signals))

    step(6, total_steps, "Scoring.......................", "OK")
    print(f"      Severity: {severity:.1f}")
    print(f"      Confidence: {confidence:.2f}\n")

    # -----------------------------------------------------------------------
    # Create Incident object
    # -----------------------------------------------------------------------
    incident = Incident(
        id="INC-001",
        signal_ids=main_cluster_ids,
        environment=main_signals[0].environment,
        services=sorted({s.service for s in main_signals}),
        severity=severity,
        confidence=confidence,
        status="open",
        gate_results={
            "accepted": True,
            "cluster_size": len(main_cluster_ids),
        },
    )

    # -----------------------------------------------------------------------
    # Create fingerprint
    # -----------------------------------------------------------------------
    fp = generate_fingerprint(main_signals, severity=severity, confidence=confidence)
    fp_hash = fingerprint_hash(fp)
    incident = incident.model_copy(update={"fingerprint_id": fp_hash})

    # -----------------------------------------------------------------------
    # Step 7 — Generate LLM ticket draft
    # -----------------------------------------------------------------------
    draft = generate_ticket_draft(incident, main_signals, fp)
    step(7, total_steps, "Generating ticket.............", "OK")

    # -----------------------------------------------------------------------
    # Step 8 — Human review (interactive)
    # -----------------------------------------------------------------------
    step(8, total_steps, "Human review..................", "WAITING")
    print()
    print(SEP)
    print(f"  INCIDENT {incident.id}")
    print(f"  {len(main_signals)} signals -> 1 incident")
    print(f"  Severity: {severity:.1f}")
    print(f"  Confidence: {confidence:.2f}")
    print(f"  Fingerprint: {fp_hash}")
    print(f"  Services: {', '.join(incident.services)}")
    print(SEP)
    print()
    print("------------------------------------------------")
    print(f"Title:    {draft.title}")
    print(f"Summary:  {draft.summary}")
    print()
    print("Observed Evidence:")
    for e in draft.observed_evidence[:5]:
        print(f"  - {e}")
    if len(draft.observed_evidence) > 5:
        print(f"  ... and {len(draft.observed_evidence) - 5} more")
    print()
    print(f"Suspected Root Cause:")
    print(f"  {draft.suspected_root_cause}")
    print()
    print("Investigation Steps:")
    for i, s in enumerate(draft.investigation_steps, 1):
        print(f"  {i}. {s}")
    print("------------------------------------------------")

    # Rejected signals summary
    if rejected_signals:
        rejected_ids = [sid for sid in rejected_signals if sid not in main_cluster_ids]
        if rejected_ids:
            print()
            print(f"  [REJECTED] {', '.join(rejected_ids)}")

    print()
    print("Review options: [approve] [reject]")
    try:
        action = input("Your decision: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        action = "approve"   # non-interactive mode defaults to approve for CI

    if not action:
        action = "approve"

    reviewed = review_ticket(draft, action, reviewer="demo-reviewer")

    if is_approved(reviewed):
        try:
            ticket = publish_to_jira(reviewed)
            print(f"\n[OK] Ticket published: {ticket['id']} -- {ticket['title']}")
        except JiraError as e:
            print(f"\n[ERR] Jira rejected: {e}")
    else:
        print(f"\n[--] Ticket {reviewed.review_status}. Not published to Jira.")

    print()
    print(SEP)
    print("  DEMO COMPLETE")
    print(SEP)
    print()


if __name__ == "__main__":
    run_demo()
