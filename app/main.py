"""
Ensylon AIOps FastAPI Application — HTML §7 (What You Must Build).

Pipeline (per signal):
    Ingestion / normalisation (Member 1)
    → C2  Anomaly Detection   (this module — stateful windows)
    → filter (anomaly_score ≥ threshold)
    → C3  Correlation Engine  (EvidenceGraph + union-find)
    → C4  Validation Gates    (4 gates)
    → C4  Scoring             (Impact Severity + Correlation Confidence, kept separate)
    → C5  Incident exposure   (LLM draft → human review → ticket write)

Endpoints implemented:
    POST   /api/signals               ingest one normalised Signal, run detection
    POST   /api/signals/batch         batch ingest + full pipeline
    GET    /api/signals               list all ingested signals
    GET    /api/signals/{id}          fetch single signal
    GET    /api/incidents             list all accepted incidents
    GET    /api/incidents/{id}        fetch single incident
    GET    /api/incidents/{id}/graph  evidence graph for incident
    GET    /api/incidents/{id}/fingerprint
    POST   /api/incidents/{id}/draft  generate LLM draft
    GET    /api/incidents/{id}/draft  fetch existing draft
    POST   /api/incidents/{id}/review human review decision
    POST   /api/jira/tickets          publish approved ticket
    GET    /api/jira/tickets          list mock Jira tickets
    GET    /api/health
    GET    /api/config
    GET    /api/health
    GET    /api/config
"""
import uuid
import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.models.signal import Signal
from app.models.incident import Incident
from app.models.ticket import TicketDraft
from app.correlation.graph import EvidenceGraph
from app.correlation.union_find import build_candidate_clusters
from app.correlation.gates import validate_cluster
from app.scoring.severity import calculate_severity
from app.scoring.confidence import calculate_confidence
from app.fingerprint.fingerprint import generate_fingerprint, fingerprint_hash
from app.llm.ticket import generate_ticket_draft
from app.review.review import review_ticket, is_approved
from app.jira.mock_jira import publish_to_jira, get_mock_tickets, JiraError
from app.config import load_config, get_detection_cfg
from app.detection.metrics import score_metric_signal
from app.detection.logs import score_log_signal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory stores  (replace with SQLite / Redis in next iteration)
# ---------------------------------------------------------------------------

# Normalised signals (all, including non-anomalous)
_signals: dict[str, Signal] = {}

# Accepted incidents
_incidents: dict[str, Incident] = {}

# Fingerprints and evidence graphs
_fingerprints: dict[str, object] = {}
_graphs: dict[str, EvidenceGraph] = {}

# LLM drafts awaiting or past review
_drafts: dict[str, TicketDraft] = {}

# ── Anomaly detection state ─────────────────────────────────────────────────
# metric_history: (service, component) → rolling list of observed metric values
#   Used by the z-score / EWMA scorer.
_metric_history: dict[tuple[str, str], list[float]] = defaultdict(list)

# log_frequency: (service,) → {template_id: count}
#   Counts within the current sliding window.
_log_frequency: dict[str, dict[str, int]] = defaultdict(dict)

# log_baseline: (service,) → {template_id: expected_count_per_window}
#   Populated from the first N observations, then frozen for MVP.
_log_baseline: dict[str, dict[str, float]] = defaultdict(dict)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Ensylon AIOps",
    description="Intelligent incident correlation and ticket drafting — HTML §7",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# C2 — Anomaly Detection
# ---------------------------------------------------------------------------

_GRAFANA_SIGNAL_TYPES = {"grafana_alert", "latency_alert", "grafana"}
_MAX_HISTORY = 200       # cap per-key history lists to avoid unbounded growth


def _detect_and_score(signal: Signal) -> Signal:
    """
    Run C2 anomaly detection on a single normalised Signal.
    Returns the signal with anomaly_score populated.
    Grafana alerts are always fully anomalous (score = 1.0).
    """
    sig_type = (signal.type or "").lower()
    source   = (signal.source or "").lower()

    # ── Grafana alerts: bypass detection, always anomalous ──────────────────
    if sig_type in _GRAFANA_SIGNAL_TYPES or source in ("grafana", "grafana_alerts"):
        return signal.model_copy(update={
            "anomaly_score": 1.0,
            "evidence": signal.evidence or signal.message or signal.component,
        })

    # ── Metric signals: z-score + EWMA scorer ───────────────────────────────
    if sig_type in ("metric_anomaly", "cloudwatch_metrics", "cloudwatch") or source in (
        "cloudwatch", "cloudwatch_metrics"
    ):
        key = (signal.service, signal.component)
        history = _metric_history[key]

        current_value = signal.value
        if current_value is None:
            # No numeric value — treat as zero-score; still store
            return signal.model_copy(update={"anomaly_score": 0.0})

        # Compute pct_threshold from metadata if available
        meta = signal.metadata or {}
        threshold_val = meta.get("threshold")
        pct_breach = None
        if threshold_val and threshold_val > 0:
            pct_breach = max((current_value - threshold_val) / threshold_val, 0.0)

        score = score_metric_signal(
            history=list(history),
            current_value=current_value,
            threshold_value=threshold_val,
            pct_threshold=pct_breach,
        )

        # Update rolling history
        history.append(current_value)
        if len(history) > _MAX_HISTORY:
            _metric_history[key] = history[-_MAX_HISTORY:]

        evidence = signal.evidence or (
            f"{signal.component} observed {current_value}"
            + (f" (threshold {threshold_val})" if threshold_val else "")
        )
        return signal.model_copy(update={"anomaly_score": score, "evidence": evidence})

    # ── Log signals: template burst detection ────────────────────────────────
    if sig_type in ("error_log_burst", "application_logs", "log") or source in (
        "application_logs", "logs"
    ):
        message = signal.evidence or signal.message or ""
        if not message:
            return signal.model_copy(update={"anomaly_score": 0.0})

        freq = _log_frequency[signal.service]
        baseline = _log_baseline[signal.service]

        score, tid, template_text = score_log_signal(
            message=message,
            frequency_counter=freq,
            baseline=baseline,
        )

        # Seed baseline from first observation of each template
        if tid not in baseline:
            _log_baseline[signal.service][tid] = max(freq.get(tid, 1), 1)

        evidence = signal.evidence or f"[REDACTED] {template_text}"
        return signal.model_copy(update={
            "anomaly_score": score,
            "template_id": signal.template_id or tid,
            "evidence": evidence,
        })

    # ── Unknown type: pass through with score 0 ──────────────────────────────
    return signal.model_copy(update={"anomaly_score": 0.0})


def _is_anomalous(signal: Signal) -> bool:
    """Return True if the signal should enter the correlation pipeline."""
    cfg = get_detection_cfg()
    threshold = cfg.get("anomaly_threshold", 0.40)
    return signal.anomaly_score >= threshold


# ---------------------------------------------------------------------------
# C3 + C4 — Correlation, Validation & Scoring pipeline
# ---------------------------------------------------------------------------

def _run_pipeline(signals: list[Signal]) -> list[dict]:
    """
    Full pipeline for a set of signals:
        1. Filter to anomalous signals only
        2. Build EvidenceGraph (C3 correlation scoring across 5 dimensions)
        3. Union-Find candidate clusters (C3 candidate generation)
        4. Validate each cluster through 4 gates (C4 validation)
        5. Score accepted incidents: Impact Severity (0–100) + Confidence (0–1)
        6. Fingerprint and store
    Returns list of accepted incident dicts.
    """
    # 1. Filter
    anomalous = [s for s in signals if _is_anomalous(s)]
    if not anomalous:
        return []

    # 2. Build graph
    graph = EvidenceGraph(anomalous)
    graph.build()

    # 3. Candidate clusters via Union-Find
    candidates = build_candidate_clusters(graph)
    results = []

    for cluster_ids in candidates:
        # 4. Validate
        validation = validate_cluster(cluster_ids, graph)
        if not validation.accepted:
            continue

        cluster_signals = [graph.signals[sid] for sid in cluster_ids]
        internal_edges  = graph.edges_within_cluster(cluster_ids)

        # 5. Score — kept separate per HTML §C4 ("do not blend them")
        sev  = calculate_severity(cluster_signals)
        conf = calculate_confidence(internal_edges, len(cluster_signals))

        inc_id = f"INC-{uuid.uuid4().hex[:6].upper()}"
        incident = Incident(
            id=inc_id,
            signal_ids=cluster_ids,
            environment=cluster_signals[0].environment,
            services=sorted({s.service for s in cluster_signals}),
            severity=sev,
            confidence=conf,
            gate_results=validation.to_dict(),
        )

        # 6. Fingerprint
        fp    = generate_fingerprint(cluster_signals, sev, conf)
        fp_id = fingerprint_hash(fp)
        incident = incident.model_copy(update={"fingerprint_id": fp_id})

        _incidents[inc_id] = incident
        _fingerprints[fp_id] = fp
        _graphs[inc_id] = graph
        results.append(incident.model_dump())

    return results


# ---------------------------------------------------------------------------
# Signal endpoints
# ---------------------------------------------------------------------------

@app.post("/api/signals", status_code=status.HTTP_201_CREATED)
def ingest_signal(signal: Signal) -> dict:
    """
    Ingest a single normalised Signal.
    Runs C2 anomaly detection immediately and stores the scored signal.
    Returns whether the signal is anomalous and its score.
    """
    scored = _detect_and_score(signal)
    _signals[scored.id] = scored
    return {
        "status": "accepted",
        "signal_id": scored.id,
        "anomaly_score": scored.anomaly_score,
        "is_anomalous": _is_anomalous(scored),
    }


@app.get("/api/signals")
def list_signals() -> list[dict]:
    """List all ingested signals."""
    return [s.model_dump() for s in _signals.values()]


@app.get("/api/signals/{signal_id}")
def get_signal(signal_id: str) -> dict:
    """Fetch a specific ingested signal by ID."""
    s = _signals.get(signal_id)
    if not s:
        raise HTTPException(status_code=404, detail="Signal not found")
    return s.model_dump()


@app.post("/api/signals/batch", status_code=status.HTTP_201_CREATED)
def ingest_batch(signals: list[Signal]) -> dict:
    """
    Load a batch of signals, run C2 detection on each, then run the full pipeline.
    Returns accepted incidents.
    """
    scored_signals = []
    for s in signals:
        scored = _detect_and_score(s)
        _signals[scored.id] = scored
        scored_signals.append(scored)

    incidents = _run_pipeline(list(_signals.values()))
    return {
        "status": "processed",
        "signals_ingested": len(scored_signals),
        "anomalous_count": sum(1 for s in scored_signals if _is_anomalous(s)),
        "incidents_created": len(incidents),
        "incidents": incidents,
    }





# ---------------------------------------------------------------------------
# Incident endpoints
# ---------------------------------------------------------------------------

@app.get("/api/incidents")
def list_incidents() -> list[dict]:
    return [inc.model_dump() for inc in _incidents.values()]


@app.get("/api/incidents/{incident_id}")
def get_incident(incident_id: str) -> dict:
    inc = _incidents.get(incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    return inc.model_dump()


@app.get("/api/incidents/{incident_id}/graph")
def get_evidence_graph(incident_id: str) -> dict:
    inc = _incidents.get(incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    graph = _graphs.get(incident_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Graph not found")

    edges = graph.edges_within_cluster(inc.signal_ids)
    nodes_data = []
    for sid in inc.signal_ids:
        if sid in _signals:
            nodes_data.append(_signals[sid].model_dump())
        elif sid in graph.signals:
            nodes_data.append(graph.signals[sid].model_dump())
        else:
            nodes_data.append({"id": sid})

    return {
        "incident_id": incident_id,
        "nodes": inc.signal_ids,
        "nodes_data": nodes_data,
        "edges": [e.model_dump() for e in edges],
    }


@app.get("/api/incidents/{incident_id}/fingerprint")
def get_fingerprint(incident_id: str) -> dict:
    inc = _incidents.get(incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    fp = _fingerprints.get(inc.fingerprint_id)
    if not fp:
        raise HTTPException(status_code=404, detail="Fingerprint not found")
    return fp.model_dump()


# ---------------------------------------------------------------------------
# C5 — Draft endpoints
# ---------------------------------------------------------------------------

class DraftRequest(BaseModel):
    pass  # incident data comes from stored incident


@app.post("/api/incidents/{incident_id}/draft", status_code=status.HTTP_201_CREATED)
def create_draft(incident_id: str) -> dict:
    """Generate LLM ticket draft from stored incident evidence (HTML §C5)."""
    inc = _incidents.get(incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")

    cluster_signals = [_signals[sid] for sid in inc.signal_ids if sid in _signals]
    fp = _fingerprints.get(inc.fingerprint_id)
    if not fp or not cluster_signals:
        raise HTTPException(status_code=422, detail="Missing signals or fingerprint")

    draft = generate_ticket_draft(inc, cluster_signals, fp)
    _drafts[incident_id] = draft
    return draft.model_dump()


@app.get("/api/incidents/{incident_id}/draft")
def get_draft(incident_id: str) -> dict:
    draft = _drafts.get(incident_id)
    if not draft:
        raise HTTPException(status_code=404, detail="No draft found — POST /draft first")
    return draft.model_dump()


# ---------------------------------------------------------------------------
# C5 — Review endpoint (ticket must NOT be published without explicit approval)
# ---------------------------------------------------------------------------

class ReviewRequest(BaseModel):
    action: str                      # approve | edit | reject
    edited_draft: Optional[dict] = None


@app.post("/api/incidents/{incident_id}/review")
def review_incident(incident_id: str, body: ReviewRequest) -> dict:
    """Apply human review decision (HTML §C5 — human-in-the-loop gate)."""
    draft = _drafts.get(incident_id)
    if not draft:
        raise HTTPException(status_code=404, detail="No draft to review — POST /draft first")
    try:
        reviewed = review_ticket(draft, body.action, body.edited_draft)
        _drafts[incident_id] = reviewed
        return reviewed.model_dump()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Jira endpoint
# ---------------------------------------------------------------------------

@app.post("/api/jira/tickets", status_code=status.HTTP_201_CREATED)
def publish_jira(incident_id: str) -> dict:
    """
    Publish to Mock Jira. BLOCKED unless the draft has been explicitly approved.
    Ticket is written to output/tickets/ only after human approval (HTML §C5).
    """
    draft = _drafts.get(incident_id)
    if not draft:
        raise HTTPException(status_code=404, detail="No draft — POST /draft first")
    try:
        ticket = publish_to_jira(draft, incident_id=incident_id)
        return ticket
    except JiraError as e:
        raise HTTPException(status_code=403, detail=str(e))


@app.get("/api/jira/tickets")
def list_jira_tickets() -> list[dict]:
    """List all published tickets in Mock Jira."""
    return get_mock_tickets()


# ---------------------------------------------------------------------------
# Utility endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "signals": len(_signals),
        "anomalous_signals": sum(1 for s in _signals.values() if _is_anomalous(s)),
        "incidents": len(_incidents),
        "pending_reviews": sum(
            1 for d in _drafts.values()
            if not is_approved(d)
        ),
    }


@app.get("/api/config")
def get_config() -> dict:
    return load_config()





# ---------------------------------------------------------------------------
# Static frontend serving (if built)
# ---------------------------------------------------------------------------
from fastapi.staticfiles import StaticFiles  # noqa: E402

_frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")