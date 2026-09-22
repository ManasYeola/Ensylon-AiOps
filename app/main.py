"""
Ensylon AIOps FastAPI Application — PRD §26 API endpoints.

Endpoints implemented:
    POST   /api/signals
    POST   /api/signals/batch
    GET    /api/incidents
    GET    /api/incidents/{id}
    GET    /api/incidents/{id}/graph
    GET    /api/incidents/{id}/fingerprint
    POST   /api/incidents/{id}/draft
    GET    /api/incidents/{id}/draft
    POST   /api/incidents/{id}/review
    POST   /api/jira/tickets
    GET    /api/health
    POST   /api/demo/run
"""
import uuid
import json
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
from app.config import load_config
from app.ingestion.cloudwatch import ingest_cloudwatch_alarms
from app.ingestion.grafana import ingest_grafana_alerts

# ---------------------------------------------------------------------------
# In-memory stores (replace with SQLite in next iteration)
# ---------------------------------------------------------------------------
_signals: dict[str, Signal] = {}
_incidents: dict[str, Incident] = {}
_fingerprints: dict[str, object] = {}
_graphs: dict[str, EvidenceGraph] = {}
_drafts: dict[str, TicketDraft] = {}

app = FastAPI(
    title="Ensylon AIOps",
    description="Intelligent incident correlation and ticket drafting",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helper — run the full correlation pipeline on a set of signals
# ---------------------------------------------------------------------------

def _run_pipeline(signals: list[Signal]) -> list[dict]:
    """
    Build evidence graph, cluster, validate, score, fingerprint.
    Returns a list of accepted incident dicts.
    """
    graph = EvidenceGraph(signals)
    graph.build()

    candidates = build_candidate_clusters(graph)
    results = []

    for cluster_ids in candidates:
        validation = validate_cluster(cluster_ids, graph)
        if not validation.accepted:
            continue

        cluster_signals = [graph.signals[sid] for sid in cluster_ids]
        internal_edges = graph.edges_within_cluster(cluster_ids)

        sev = calculate_severity(cluster_signals)
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

        fp = generate_fingerprint(cluster_signals, sev, conf)
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
    """Ingest a single normalized signal. PRD §10."""
    _signals[signal.id] = signal
    return {"status": "accepted", "signal_id": signal.id}


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
    Load a batch of replay signals, run the full pipeline, and return accepted incidents.
    PRD §10
    """
    for s in signals:
        _signals[s.id] = s

    incidents = _run_pipeline(signals)
    return {
        "status": "processed",
        "signals_ingested": len(signals),
        "incidents_created": len(incidents),
        "incidents": incidents,
    }


@app.post("/api/demo/run")
def run_demo_batch() -> dict:
    """Load sample_signals.json and run the full pipeline. PRD optional endpoint."""
    sample_path = Path(__file__).parent.parent / "data" / "sample_signals.json"
    with open(sample_path, "r") as f:
        raw = json.load(f)
    signals = [Signal(**item) for item in raw]
    return ingest_batch(signals)


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
# Draft endpoints
# ---------------------------------------------------------------------------

class DraftRequest(BaseModel):
    pass  # body currently empty — incident data comes from stored incident


@app.post("/api/incidents/{incident_id}/draft", status_code=status.HTTP_201_CREATED)
def create_draft(incident_id: str) -> dict:
    """Generate LLM ticket draft from stored incident evidence. PRD §20."""
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
# Review endpoint
# ---------------------------------------------------------------------------

class ReviewRequest(BaseModel):
    action: str          # approve | edit | reject
    edited_draft: Optional[dict] = None


@app.post("/api/incidents/{incident_id}/review")
def review_incident(incident_id: str, body: ReviewRequest) -> dict:
    """Apply human review decision. PRD §21."""
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
    Publish to Mock Jira. BLOCKED unless the draft has been approved.
    PRD §22
    """
    draft = _drafts.get(incident_id)
    if not draft:
        raise HTTPException(status_code=404, detail="No draft — POST /draft first")
    try:
        ticket = publish_to_jira(draft)
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
    return {"status": "ok", "signals": len(_signals), "incidents": len(_incidents)}


@app.get("/api/config")
def get_config() -> dict:
    return load_config()


# ---------------------------------------------------------------------------
# Webhook endpoints — live CloudWatch + Grafana ingestion
# ---------------------------------------------------------------------------

import base64


@app.post("/webhooks/cloudwatch", status_code=status.HTTP_200_OK)
async def cloudwatch_webhook(request: Request) -> dict:
    """
    Receive AWS SNS notifications for CloudWatch alarms.

    Two message types are handled:
      - SubscriptionConfirmation  → returns the SubscribeURL so SNS confirms the subscription
      - Notification              → parses alarm payload and runs the pipeline

    Setup on AWS side:
      1. Create an SNS topic.
      2. Create CloudWatch alarm → Actions → "Send notification to SNS topic".
      3. Add HTTP/HTTPS subscription pointing to:
         http://<your-server>/webhooks/cloudwatch
      4. AWS will POST a SubscriptionConfirmation — this endpoint auto-confirms it.
    """
    import httpx
    body = await request.json()
    msg_type = request.headers.get("x-amz-sns-message-type", "")

    # Auto-confirm the SNS subscription
    if msg_type == "SubscriptionConfirmation":
        confirm_url = body.get("SubscribeURL")
        if confirm_url:
            async with httpx.AsyncClient() as client:
                await client.get(confirm_url)
        return {"status": "subscription_confirmed"}

    # Parse the nested Message JSON that SNS wraps around the alarm
    import json as _json
    raw_message = body.get("Message", "{}")
    try:
        alarm = _json.loads(raw_message)
    except Exception:
        alarm = {}

    # Map SNS alarm fields to what ingest_cloudwatch_alarms expects
    event = {
        "AlarmName": alarm.get("AlarmName", body.get("Subject", "unknown")),
        "AlarmArn": alarm.get("AlarmArn", ""),
        "AlarmDescription": alarm.get("AlarmDescription", ""),
        "Namespace": alarm.get("Trigger", {}).get("Namespace", "AWS/Unknown"),
        "MetricName": alarm.get("Trigger", {}).get("MetricName", "unknown"),
        "Timestamp": alarm.get("StateChangeTime", ""),
        "Trigger": alarm.get("Trigger", {}),
        "environment": "prod",  # override via alarm description tag or custom field
    }

    signals = ingest_cloudwatch_alarms([event])
    if not signals:
        return {"status": "skipped", "reason": "parse failed"}

    for s in signals:
        _signals[s.id] = s

    # Run pipeline over all buffered signals
    incidents = _run_pipeline(list(_signals.values()))
    return {
        "status": "processed",
        "signals_ingested": len(signals),
        "new_incidents": len(incidents),
    }


@app.post("/webhooks/grafana", status_code=status.HTTP_200_OK)
async def grafana_webhook(request: Request) -> dict:
    """
    Receive Grafana Alertmanager webhook payloads.

    Setup on Grafana side:
      1. Alerting -> Contact points -> Add contact point
      2. Type: Webhook
      3. URL: http://<your-server>/webhooks/grafana
      4. (Optional) Add HTTP header: X-Grafana-Secret: <GRAFANA_WEBHOOK_SECRET from .env>
    """
    import os
    expected_secret = os.getenv("GRAFANA_WEBHOOK_SECRET", "")
    if expected_secret:
        received = request.headers.get("X-Grafana-Secret", "")
        if received != expected_secret:
            raise HTTPException(status_code=403, detail="Invalid webhook secret")

    body = await request.json()
    signals = ingest_grafana_alerts(body)
    if not signals:
        return {"status": "skipped", "reason": "no alerts parsed"}

    for s in signals:
        _signals[s.id] = s

    incidents = _run_pipeline(list(_signals.values()))
    return {
        "status": "processed",
        "signals_ingested": len(signals),
        "new_incidents": len(incidents),
    }


@app.post("/webhooks/test", status_code=status.HTTP_200_OK)
async def test_webhook(payload: dict) -> dict:
    """
    Local testing endpoint — POST any raw CloudWatch or Grafana payload here
    without needing a real AWS/Grafana connection.

    Usage:
        curl -X POST http://localhost:8000/webhooks/test \
             -H 'Content-Type: application/json' \
             -d @data/sample_cloudwatch_alarm.json
    """
    source = payload.get("source", "cloudwatch").lower()
    if source == "grafana" or "alerts" in payload:
        signals = ingest_grafana_alerts(payload)
    else:
        signals = ingest_cloudwatch_alarms([payload])

    for s in signals:
        _signals[s.id] = s

    incidents = _run_pipeline(list(_signals.values()))
    return {
        "status": "processed",
        "signals_ingested": len(signals),
        "new_incidents": len(incidents),
        "incidents": incidents,
    }


# ---------------------------------------------------------------------------
# Static frontend serving (if built)
# ---------------------------------------------------------------------------
from fastapi.staticfiles import StaticFiles

_frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")