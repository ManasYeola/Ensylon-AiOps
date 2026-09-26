"""
Ensylon AIOps FastAPI Application — HTML §7 (What You Must Build).

Pipeline (per signal):
    Ingestion / normalisation (Member 1 — SSE streams via lifespan tasks)
    → C2  Anomaly Detection   (this module — stateful windows)
    → filter (anomaly_score ≥ threshold)
    → C3  Correlation Engine  (EvidenceGraph + union-find, windowed)
    → C4  Validation Gates    (4 gates)
    → C4  Scoring             (Impact Severity + Correlation Confidence, kept separate)
    → C5  Incident exposure   (LLM draft → human review → ticket write)

Stream startup:
    Three SSE consumer tasks (aiops-logs, aiops-cloudwatch, aiops-grafana) are
    launched as background asyncio tasks during the FastAPI lifespan.  Each task
    runs consume_sse_stream() which handles reconnects with Last-Event-ID and
    ignores :keepalive comments.  Every signal that comes off the stream is
    handed to _ingest_signal() which runs detection and triggers windowed
    pipeline.  No separate runner script is needed.

Endpoints:
    POST   /api/signals               ingest one pre-normalised Signal
    POST   /api/signals/batch         batch ingest + forced pipeline run
    GET    /api/signals               list all ingested signals
    GET    /api/signals/{id}          fetch single signal
    GET    /api/incidents             list accepted incidents
    GET    /api/incidents/{id}        fetch single incident
    GET    /api/incidents/{id}/graph  evidence graph
    GET    /api/incidents/{id}/fingerprint
    POST   /api/incidents/{id}/draft  generate LLM draft
    GET    /api/incidents/{id}/draft  fetch existing draft
    POST   /api/incidents/{id}/review human review decision
    POST   /api/jira/tickets          publish approved ticket
    GET    /api/jira/tickets          list mock Jira tickets
    GET    /api/health                pipeline health + stream status
    GET    /api/config
    GET    /api/streams/status        SSE stream connection status for UI
"""
import os
import asyncio
import uuid
import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
import httpx

from fastapi import FastAPI, HTTPException, status
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
from app.fingerprint.fingerprint import generate_fingerprint, fingerprint_hash, similarity_score
from app.llm.ticket import generate_ticket_draft
from app.review.review import review_ticket, is_approved
from app.jira import publish_to_jira, get_mock_tickets, get_jira_config, JiraError
from app.config import load_config, get_detection_cfg, get_correlation_cfg, get_fingerprint_cfg
from app.detection.metrics import score_metric_signal
from app.detection.logs import score_log_signal, LogWindowState, make_log_window_state
from app.ingestion.sse_client import consume_sse_stream, SIMULATOR_STREAMS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------

# All normalised + scored signals, keyed by signal.id
_signals: dict[str, Signal] = {}

# Accepted incidents, keyed by incident id
_incidents: dict[str, Incident] = {}

# Fingerprint hash → incident_id   (for deduplication)
_fp_to_incident: dict[str, str] = {}

# Fingerprint objects and evidence graphs
_fingerprints: dict[str, object] = {}
_graphs: dict[str, EvidenceGraph] = {}

# LLM drafts awaiting or past review
_drafts: dict[str, TicketDraft] = {}

# In-flight draft tasks: incident_id -> asyncio.Task (prevents duplicate LLM calls)
_draft_tasks: dict[str, asyncio.Task] = {}

# ── Anomaly detection state ─────────────────────────────────────────────────
_metric_history: dict[tuple[str, str], list[float]] = defaultdict(list)

# Per-service sliding-window frequency state for log burst detection.
# Each service gets its own LogWindowState so burst counts don't cross
# service boundaries and window expiry is per-service.
_log_window_state: dict[str, LogWindowState] = {}

_MAX_HISTORY = 200

# ── Correlation window state ─────────────────────────────────────────────────
# Tracks the last time the full correlation pipeline ran, so that
# individual signal ingests can coalesce into a window-triggered run
# instead of running correlation on every single signal (O(N²) per signal).
_last_pipeline_run_ts: float = 0.0   # epoch seconds
_pending_pipeline = False            # flag: a run is scheduled

# ── SSE stream status (for UI / Member 3) ───────────────────────────────────
_stream_status: dict[str, dict] = {
    name: {"connected": False, "last_event_id": None, "events_received": 0, "last_error": None}
    for name in SIMULATOR_STREAMS
}

# ── Background tasks (kept so we can cancel them on shutdown) ────────────────
_stream_tasks: list[asyncio.Task] = []


# ---------------------------------------------------------------------------
# C2 — Anomaly Detection
# ---------------------------------------------------------------------------

_GRAFANA_SIGNAL_TYPES = {"grafana_alert", "latency_alert", "grafana"}


def _detect_and_score(signal: Signal) -> Signal:
    """
    Run C2 anomaly detection on a single normalised Signal.
    Returns the signal with anomaly_score populated.
    Grafana alerts are always fully anomalous (score = 1.0).
    """
    sig_type = (signal.type or signal.signal_type or "").lower()
    source   = (signal.source or "").lower()

    # ── Grafana alerts: bypass detection, always anomalous ──────────────────
    if sig_type in _GRAFANA_SIGNAL_TYPES or source in ("grafana_alerts",):
        return signal.model_copy(update={
            "anomaly_score": 1.0,
            "evidence": signal.evidence or signal.message or signal.component,
        })

    # ── Metric signals: z-score + EWMA scorer ───────────────────────────────
    if sig_type in ("metric_anomaly",) or source in ("cloudwatch_metrics",):
        key = (signal.service, signal.component)
        history = _metric_history[key]

        current_value = signal.value
        if current_value is None:
            return signal.model_copy(update={"anomaly_score": 0.0})

        meta = signal.metadata or {}

        # alarm_state is stored as a flat top-level key by normalize_cloudwatch().
        # Fall back to reading new_state for backward compat.
        alarm_state: Optional[str] = (
            meta.get("alarm_state")
            or meta.get("new_state")
        )

        # threshold_value is stored flat by the new normalizer.
        # Fall back to Trigger.Threshold for older payloads.
        threshold_val: Optional[float] = meta.get("threshold_value")
        if threshold_val is None:
            trigger = meta.get("trigger", {})
            if isinstance(trigger, dict):
                raw = trigger.get("Threshold")
                try:
                    threshold_val = float(raw) if raw is not None else None
                except (ValueError, TypeError):
                    threshold_val = None

        score = score_metric_signal(
            history=list(history),
            current_value=current_value,
            threshold_value=threshold_val,
            alarm_state=alarm_state,
        )

        # Only update history for non-OK states so recoveries don't
        # corrupt the baseline that subsequent ALARM events compare against.
        if alarm_state is None or alarm_state.upper() != "OK":
            history.append(current_value)
            if len(history) > _MAX_HISTORY:
                _metric_history[key] = history[-_MAX_HISTORY:]

        # Build evidence — preserve the normalizer's redacted description when
        # present; fall back to a concise computed string.
        evidence = signal.evidence or (
            f"{signal.component} observed {current_value}"
            + (f" vs threshold {threshold_val}" if threshold_val is not None else "")
            + (f" [{alarm_state}]" if alarm_state else "")
        )
        return signal.model_copy(update={"anomaly_score": score, "evidence": evidence})


    # ── Log signals: template burst detection (sliding window) ────────────────
    if sig_type in ("error_log_burst",) or source in ("application_logs",):
        message = signal.evidence or signal.message or ""
        if not message:
            return signal.model_copy(update={"anomaly_score": 0.0})

        # Get or create the per-service LogWindowState (config-driven parameters)
        if signal.service not in _log_window_state:
            _log_window_state[signal.service] = make_log_window_state()
        state = _log_window_state[signal.service]

        # PII has already been redacted by the ingestion layer before this point
        score, tid, template_text = score_log_signal(
            message=message,
            state=state,
            timestamp=signal.timestamp,
        )

        evidence = signal.evidence or f"[REDACTED] {template_text}"
        chosen_tid = signal.template_id or tid
        return signal.model_copy(update={
            "anomaly_score": score,
            "template_id": str(chosen_tid) if chosen_tid is not None else None,
            "evidence": evidence,
        })

    return signal.model_copy(update={"anomaly_score": 0.0})


def _is_anomalous(signal: Signal) -> bool:
    cfg = get_detection_cfg()
    threshold = cfg.get("anomaly_threshold", 0.40)
    return signal.anomaly_score >= threshold


# ---------------------------------------------------------------------------
# C3 + C4 — Correlation, Validation & Scoring
# ---------------------------------------------------------------------------

async def _get_or_create_draft(incident_id: str) -> TicketDraft:
    """
    Ensure exactly ONE draft is generated per incident.
    - If already generated, returns the cached draft immediately (0 LLM calls).
    - If currently in-flight, awaits the existing task (0 duplicate calls).
    - If not yet started, creates an asyncio task and caches the result.
    """
    if incident_id in _drafts:
        return _drafts[incident_id]

    inc = _incidents.get(incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")

    cluster_signals = [_signals[sid] for sid in inc.signal_ids if sid in _signals]
    fp = _fingerprints.get(inc.fingerprint_id)
    if not fp or not cluster_signals:
        raise HTTPException(status_code=422, detail="Missing signals or fingerprint")

    # If already in flight, wait for the existing task
    if incident_id in _draft_tasks and not _draft_tasks[incident_id].done():
        try:
            return await _draft_tasks[incident_id]
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"In-flight draft generation failed: {e}",
            )

    async def _runner():
        loop = asyncio.get_running_loop()
        d = await loop.run_in_executor(None, generate_ticket_draft, inc, cluster_signals, fp)
        _drafts[incident_id] = d
        return d

    task = asyncio.create_task(_runner())
    _draft_tasks[incident_id] = task

    try:
        return await task
    except Exception as e:
        logger.exception("Draft generation failed for incident %s", incident_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Draft generation failed: {e}",
        )

def _run_pipeline(signals: list[Signal]) -> list[dict]:
    """
    Full pipeline:
        1. Filter to anomalous signals inside the correlation window
        2. Build EvidenceGraph (C3 — 5 dimensions)
        3. Union-Find candidate clusters (C3)
        4. Validate through 4 gates (C4)
        5. Score: Impact Severity + Correlation Confidence separately (C4)
        6. Deduplication via fingerprint hash — skip clusters already active
        7. Fingerprint + store new incidents

    Returns list of newly accepted incident dicts (not already-existing ones).
    """
    cfg = get_correlation_cfg()
    window_minutes = cfg.get("window_minutes", 5)
    window_seconds = window_minutes * 60

    if not signals:
        return []

    # 1. Filter: anomalous AND inside temporal window
    # Anchor to event stream reference time so slight host clock skew / simulator replay
    # doesn't drop signals prematurely, while falling back to system clock.
    latest_signal_ts = max((s.timestamp.timestamp() for s in signals), default=time.time())
    now = time.time()
    ref_ts = latest_signal_ts if abs(latest_signal_ts - now) < 86400 else now

    anomalous = [
        s for s in signals
        if _is_anomalous(s) and (ref_ts - s.timestamp.timestamp()) <= window_seconds
    ]
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

        # 5. Score — kept separate per HTML §C4
        sev  = calculate_severity(cluster_signals)
        conf = calculate_confidence(internal_edges, len(cluster_signals))

        # 6. Deduplication & Continuation: compute fingerprint hash and check similarity
        fp    = generate_fingerprint(cluster_signals, sev, conf)
        fp_id = fingerprint_hash(fp)

        # Check exact hash first
        matched_incident_id = _fp_to_incident.get(fp_id)

        # If not an exact hash match, check structural similarity against active fingerprints (PRD §8 / §19)
        if not matched_incident_id and _fingerprints:
            fp_cfg = get_fingerprint_cfg()
            sim_threshold = fp_cfg.get("similarity_threshold", 0.70)
            best_score = 0.0
            best_fp_id = None
            for existing_fp_id, existing_fp in _fingerprints.items():
                score = similarity_score(fp, existing_fp)
                if score > best_score:
                    best_score = score
                    best_fp_id = existing_fp_id

            if best_fp_id and best_score >= sim_threshold:
                matched_incident_id = _fp_to_incident.get(best_fp_id)

        if matched_incident_id and matched_incident_id in _incidents:
            # Same structural fingerprint or high similarity → extend the existing incident's signal set
            existing = _incidents[matched_incident_id]
            merged_ids = list(dict.fromkeys(existing.signal_ids + cluster_ids))
            _incidents[matched_incident_id] = existing.model_copy(
                update={"signal_ids": merged_ids}
            )
            # Map this fingerprint variant to the same incident for O(1) subsequent lookups
            _fp_to_incident[fp_id] = matched_incident_id
            _fingerprints[fp_id] = fp
            continue  # Don't produce a new incident dict

        inc_id = f"INC-{uuid.uuid4().hex[:6].upper()}"
        incident = Incident(
            id=inc_id,
            signal_ids=cluster_ids,
            environment=cluster_signals[0].environment,
            services=sorted({s.service for s in cluster_signals}),
            severity=sev,
            confidence=conf,
            gate_results=validation.to_dict(),
            fingerprint_id=fp_id,
        )

        _incidents[inc_id]    = incident
        _fingerprints[fp_id]  = fp
        _fp_to_incident[fp_id] = inc_id
        _graphs[inc_id]       = graph
        results.append(incident.model_dump())
        # Draft scheduling is handled by _windowed_pipeline_run on the event loop
        # after this function returns — do NOT call asyncio.get_running_loop() here
        # because _run_pipeline may be called from a thread executor.

    return results


# ---------------------------------------------------------------------------
# Core ingest function — shared by API endpoint AND SSE consumer
# ---------------------------------------------------------------------------

# Maximum number of signals to keep in memory.
# Old signals are pruned to prevent the correlation pipeline from growing O(all-time).
_MAX_SIGNAL_STORE = 2000


def _prune_signal_store() -> None:
    """
    Evict the oldest signals beyond _MAX_SIGNAL_STORE to keep correlation O(window).
    Signals that are part of an existing incident are retained.
    """
    if len(_signals) <= _MAX_SIGNAL_STORE:
        return
    # Collect signal IDs that are locked into incidents
    incident_signal_ids: set[str] = set()
    for inc in _incidents.values():
        incident_signal_ids.update(inc.signal_ids)

    # Sort by timestamp, oldest first; evict non-incident signals
    sorted_ids = sorted(
        _signals.keys(),
        key=lambda sid: _signals[sid].timestamp,
    )
    evict_count = len(_signals) - _MAX_SIGNAL_STORE
    evicted = 0
    for sid in sorted_ids:
        if evicted >= evict_count:
            break
        if sid not in incident_signal_ids:
            del _signals[sid]
            evicted += 1


async def _ingest_signal(signal: Signal) -> dict:
    """
    Score (C2), store, and schedule a windowed pipeline run.
    Used by both POST /api/signals and the SSE background tasks.
    """
    global _last_pipeline_run_ts, _pending_pipeline

    scored = _detect_and_score(signal)
    _signals[scored.id] = scored

    # Prune the signal store periodically to prevent O(all-time) correlation cost.
    # Only runs when the store exceeds the cap, so normal ingestion has zero overhead.
    if len(_signals) > _MAX_SIGNAL_STORE:
        _prune_signal_store()

    # Schedule a pipeline run. When an anomalous signal arrives, trigger correlation
    # with a short debounce (5s) so incidents populate promptly without stalling 5 minutes.
    cfg = get_correlation_cfg()
    window_seconds = cfg.get("window_minutes", 5) * 60
    elapsed_since_last_run = time.time() - _last_pipeline_run_ts
    is_anomaly = _is_anomalous(scored)
    min_interval = 5.0 if is_anomaly else window_seconds

    if not _pending_pipeline and elapsed_since_last_run >= min_interval:
        _pending_pipeline = True
        asyncio.get_event_loop().call_soon(lambda: asyncio.ensure_future(_windowed_pipeline_run()))

    return {
        "status": "accepted",
        "signal_id": scored.id,
        "anomaly_score": scored.anomaly_score,
        "is_anomalous": _is_anomalous(scored),
    }


async def _windowed_pipeline_run() -> None:
    """
    Run the full correlation pipeline over all stored signals.
    _run_pipeline is sync + CPU-bound, so it runs in a thread executor to avoid
    blocking the asyncio event loop and freezing the three SSE stream consumers.
    Draft creation is scheduled here (on the event loop) after the executor returns.
    """
    global _last_pipeline_run_ts, _pending_pipeline
    try:
        loop = asyncio.get_running_loop()

        # Pre-filter to only signals within the correlation window BEFORE handing to the
        # thread executor. graph.build() is O(N²) over anomalous signals — passing all
        # historical signals (e.g. the 600-event startup buffer) would re-score every pair
        # on every pipeline run. Filtering here keeps N = anomalous signals in the window,
        # which stays bounded by the window size regardless of total signal history.
        cfg = get_correlation_cfg()
        window_seconds = cfg.get("window_minutes", 5) * 60
        ref_ts = max(
            (s.timestamp.timestamp() for s in _signals.values()),
            default=time.time(),
        )
        signals_snapshot = [
            s for s in _signals.values()
            if (ref_ts - s.timestamp.timestamp()) <= window_seconds
        ]
        new_incidents = await loop.run_in_executor(None, _run_pipeline, signals_snapshot)
        _last_pipeline_run_ts = time.time()

        # Schedule auto-draft generation here (on the event loop) for each new incident.
        # _run_pipeline can't do this itself when running inside a thread executor
        # because asyncio.get_running_loop() raises RuntimeError in worker threads.
        for inc_dict in new_incidents:
            inc_id = inc_dict.get("id")
            if inc_id and inc_id not in _drafts and inc_id not in _draft_tasks:
                asyncio.create_task(_get_or_create_draft(inc_id))
    except Exception:
        logger.exception("Windowed pipeline run failed")
    finally:
        _pending_pipeline = False


# ---------------------------------------------------------------------------
# SSE background consumer (launched by lifespan)
# ---------------------------------------------------------------------------

async def _get_latest_stream_seqs() -> dict[str, str]:
    """Fetch current latest sequence IDs from the simulator to avoid replaying past buffers."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("https://logs.nonprod.nexus.ensylon.com/sim/stream")
            if resp.status_code == 200:
                return {
                    item["channel"]: str(item["lastSeq"])
                    for item in resp.json()
                    if "channel" in item and "lastSeq" in item
                }
    except Exception as exc:
        logger.warning("Failed to fetch latest stream sequences: %s", exc)
    return {}


async def _consume_stream(stream_name: str, url: str) -> None:
    """
    Long-running background task: consume one SSE stream and feed each
    signal into the pipeline. Handles reconnect with Last-Event-ID.
    """
    status_entry = _stream_status[stream_name]
    last_id = None

    # By default, replay the simulator's historical buffer on startup for fast initial
    # signal ingestion. Use REPLAY_STREAM_HISTORY=false to start at live HEAD instead
    # (e.g. after calling /api/reset, where you want a clean slate with no backlog).
    replay_history = os.getenv("REPLAY_STREAM_HISTORY", "true").lower() not in ("false", "0", "no")
    if not replay_history:
        stream_channel = f"aiops-{stream_name}" if not stream_name.startswith("aiops-") else stream_name
        latest_seqs = await _get_latest_stream_seqs()
        last_id = latest_seqs.get(stream_channel) or latest_seqs.get(stream_name)
        if last_id:
            logger.info(
                "Initializing stream %s at live HEAD (lastSeq=%s) — signals start at 0",
                stream_name, last_id,
            )
            status_entry["last_event_id"] = last_id

    while True:
        try:
            status_entry["connected"] = True
            async for event_id, signal in consume_sse_stream(
                url,
                source_type=stream_name,
                last_event_id=last_id,
                max_reconnects=-1,   # indefinite reconnects
            ):
                last_id = event_id
                status_entry["last_event_id"] = event_id
                status_entry["events_received"] += 1
                try:
                    await _ingest_signal(signal)
                except Exception:
                    logger.exception(
                        "Pipeline error processing signal from %s (event %s)",
                        stream_name, event_id,
                    )
        except asyncio.CancelledError:
            logger.info("SSE consumer for %s cancelled", stream_name)
            status_entry["connected"] = False
            return
        except Exception as exc:
            status_entry["connected"] = False
            status_entry["last_error"] = str(exc)
            logger.warning(
                "SSE consumer for %s crashed: %s — restarting in 5s", stream_name, exc
            )
            await asyncio.sleep(5)


# ---------------------------------------------------------------------------
# FastAPI lifespan — starts stream tasks, cleans up on shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start SSE consumer tasks when the app starts; cancel on shutdown."""
    enable_streams = os.getenv("ENABLE_SSE_STREAMS", "true").lower() not in ("false", "0", "no")
    if enable_streams:
        for name, url in SIMULATOR_STREAMS.items():
            task = asyncio.create_task(_consume_stream(name, url), name=f"sse-{name}")
            _stream_tasks.append(task)
            logger.info("Started SSE consumer task for %s → %s", name, url)
    else:
        logger.info("SSE background streams disabled via ENABLE_SSE_STREAMS=false")

    yield

    logger.info("Shutting down SSE consumer tasks...")
    for task in _stream_tasks:
        task.cancel()
    await asyncio.gather(*_stream_tasks, return_exceptions=True)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Ensylon AIOps",
    description="Intelligent incident correlation and ticket drafting — HTML §7",
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Signal endpoints
# ---------------------------------------------------------------------------

@app.post("/api/signals", status_code=status.HTTP_201_CREATED)
async def ingest_signal_endpoint(signal: Signal) -> dict:
    """
    Ingest a single pre-normalised Signal (e.g. from Member 1's ingestion layer).
    Runs C2 detection immediately. Schedules a windowed correlation run.
    """
    return await _ingest_signal(signal)


@app.get("/api/signals")
def list_signals() -> list[dict]:
    """List all ingested signals."""
    return [s.model_dump() for s in _signals.values()]


@app.get("/api/signals/{signal_id}")
def get_signal(signal_id: str) -> dict:
    s = _signals.get(signal_id)
    if not s:
        raise HTTPException(status_code=404, detail="Signal not found")
    return s.model_dump()


@app.post("/api/signals/batch", status_code=status.HTTP_201_CREATED)
async def ingest_batch(signals: list[Signal]) -> dict:
    """
    Batch-ingest signals and immediately run the full correlation pipeline.
    Use this for replay / testing; live data goes through SSE streams.
    """
    for s in signals:
        scored = _detect_and_score(s)
        _signals[scored.id] = scored

    incidents = _run_pipeline(list(_signals.values()))
    return {
        "status": "processed",
        "signals_ingested": len(signals),
        "anomalous_count": sum(1 for s in signals if _is_anomalous(_detect_and_score(s))),
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

    # Resolve signals belonging to this incident
    cluster_signals = [_signals[sid] for sid in inc.signal_ids if sid in _signals]

    graph = _graphs.get(incident_id)
    # If graph is missing or missing any of the current incident signals, build it dynamically
    if not graph or not all(sid in graph.signals for sid in inc.signal_ids):
        if cluster_signals:
            graph = EvidenceGraph(cluster_signals)
            graph.build()
            _graphs[incident_id] = graph

    edges = graph.edges_within_cluster(inc.signal_ids) if graph else []
    nodes_data = []
    for sid in inc.signal_ids:
        if sid in _signals:
            nodes_data.append(_signals[sid].model_dump())
        elif graph and sid in graph.signals:
            nodes_data.append(graph.signals[sid].model_dump())
        else:
            nodes_data.append({"id": sid})

    serialized_edges = []
    for e in edges:
        d = e.model_dump()
        d["weight"] = d.get("correlation_score", 0.0)
        serialized_edges.append(d)

    return {
        "incident_id": incident_id,
        "nodes": inc.signal_ids,
        "nodes_data": nodes_data,
        "edges": serialized_edges,
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
    pass


@app.post("/api/incidents/{incident_id}/draft", status_code=status.HTTP_201_CREATED)
async def create_draft(incident_id: str) -> dict:
    """Generate or retrieve LLM ticket draft for an incident (guaranteed exactly once)."""
    draft = await _get_or_create_draft(incident_id)
    return draft.model_dump()


@app.get("/api/incidents/{incident_id}/draft")
async def get_draft(incident_id: str) -> dict:
    """Fetch ticket draft, auto-generating if not yet cached (guaranteed exactly once)."""
    draft = await _get_or_create_draft(incident_id)
    return draft.model_dump()


# ---------------------------------------------------------------------------
# C5 — Review endpoint
# ---------------------------------------------------------------------------

class ReviewRequest(BaseModel):
    action: str                      # approve | edit | reject
    edited_draft: Optional[dict] = None


@app.post("/api/incidents/{incident_id}/review")
def review_incident(incident_id: str, body: ReviewRequest) -> dict:
    """Apply human review decision (HTML §C5)."""
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
    Publish to Mock Jira.
    BLOCKED unless the draft has been explicitly approved (HTML §C5).
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
    return get_mock_tickets()


class JiraConfigRequest(BaseModel):
    jira_url: str
    jira_email: str
    jira_api_token: str
    jira_project_key: str
    jira_issue_type: str = "Bug"


@app.get("/api/jira/config")
def get_jira_settings() -> dict:
    return get_jira_config()


@app.post("/api/jira/config")
def update_jira_settings(req: JiraConfigRequest) -> dict:
    if req.jira_url:
        os.environ["JIRA_URL"] = req.jira_url.strip().rstrip("/")
    if req.jira_email:
        os.environ["JIRA_EMAIL"] = req.jira_email.strip()
    if req.jira_api_token:
        os.environ["JIRA_API_TOKEN"] = req.jira_api_token.strip()
    if req.jira_project_key:
        os.environ["JIRA_PROJECT_KEY"] = req.jira_project_key.strip().upper()
    if req.jira_issue_type:
        os.environ["JIRA_ISSUE_TYPE"] = req.jira_issue_type.strip()
    return get_jira_config()


# ---------------------------------------------------------------------------
# Utility endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "signals_total": len(_signals),
        "anomalous_signals": sum(1 for s in _signals.values() if _is_anomalous(s)),
        "incidents": len(_incidents),
        "pending_reviews": sum(1 for d in _drafts.values() if not is_approved(d)),
        "streams": _stream_status,
    }


@app.get("/api/config")
def get_config() -> dict:
    return load_config()


@app.get("/api/streams/status")
def streams_status() -> dict:
    """
    SSE stream connection status — consumed by the frontend (Member 3).

    Response schema:
    {
      "streams": {
        "logs":       { "connected": bool, "last_event_id": str|null, "events_received": int, "last_error": str|null },
        "grafana":    { ... },
        "cloudwatch": { ... }
      }
    }
    """
    return {"streams": _stream_status}


@app.post("/api/reset")
async def reset_pipeline():
    """Reset all in-memory signals, incidents, graphs, and detection state to 0."""
    global _signals, _incidents, _fp_to_incident, _fingerprints, _graphs, _drafts, _draft_tasks, _metric_history, _log_window_state
    _signals.clear()
    _incidents.clear()
    _fp_to_incident.clear()
    _fingerprints.clear()
    _graphs.clear()
    _drafts.clear()
    _draft_tasks.clear()
    _metric_history.clear()
    _log_window_state.clear()

    latest_seqs = await _get_latest_stream_seqs()
    for name in _stream_status:
        channel = f"aiops-{name}" if not name.startswith("aiops-") else name
        if channel in latest_seqs:
            _stream_status[name]["last_event_id"] = latest_seqs[channel]
            _stream_status[name]["events_received"] = 0

    return {"status": "ok", "message": "Pipeline signals and incidents reset to 0"}


# ---------------------------------------------------------------------------
# Static frontend serving (if built)
# ---------------------------------------------------------------------------
from fastapi.staticfiles import StaticFiles  # noqa: E402

_frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")