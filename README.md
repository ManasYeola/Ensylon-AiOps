# Ensylon AIOps

An intelligent incident correlation and root-cause analysis engine for cloud infrastructure and microservices.
Ingests live telemetry from multiple sources, detects anomalies, clusters related signals into incidents, and synthesises LLM-drafted tickets — end to end, automatically.

---

## Architecture & Directory Structure

```text
ensylon-aiops/
│
├── app/
│   ├── main.py                # FastAPI app — pipeline entrypoint & SSE consumer lifecycle
│   │
│   ├── models/                # Domain models (Signal, Incident, TicketDraft, Fingerprint)
│   │   ├── signal.py
│   │   ├── incident.py
│   │   ├── ticket.py
│   │   └── fingerprint.py
│   │
│   ├── ingestion/             # Multi-source SSE stream ingestion & normalisation
│   │   ├── sse_client.py      # Resilient SSE consumer (reconnect, Last-Event-ID)
│   │   ├── cloudwatch.py      # AWS CloudWatch metrics & alarms normaliser
│   │   ├── logs.py            # Application log stream normaliser
│   │   └── grafana.py         # Grafana alert stream normaliser
│   │
│   ├── detection/             # C2 — Anomaly detection
│   │   ├── metrics.py         # Rolling z-score + EWMA + threshold breach scoring (0.0–1.0)
│   │   └── logs.py            # Drain3 log template mining + sliding-window burst detection
│   │
│   ├── correlation/           # C3 — Correlation & clustering engine
│   │   ├── graph.py           # EvidenceGraph — weighted edges across 5 correlation dimensions
│   │   ├── union_find.py      # Union-Find (DSU) candidate cluster builder
│   │   ├── gates.py           # 4 validation gates (strong edge, env, coherence, bridge)
│   │   └── topology.py        # Service dependency topology loader
│   │
│   ├── scoring/               # C4 — Incident impact assessment
│   │   ├── severity.py        # Composite severity score (0–100); see formula below
│   │   └── confidence.py      # Correlation confidence score (0.0–1.0)
│   │
│   ├── fingerprint/           # Incident deduplication & continuation
│   │   └── fingerprint.py     # SHA-256 structural hash + Jaccard similarity matching
│   │
│   ├── llm/                   # C5 — AI synthesis
│   │   └── ticket.py          # Claude-powered incident ticket draft generation
│   │
│   ├── review/                # Human-in-the-loop review workflow
│   │   └── review.py          # Operator approve / reject / escalate
│   │
│   └── jira/                  # Ticket publication
│       └── __init__.py        # Mock Jira integration
│
├── data/
│   ├── criticality_map.json   # Business criticality scores per service (0–100)
│   └── topology.json          # Service dependency graph
│
├── tests/                     # 125 unit & integration tests (pytest)
├── config.yaml                # All tunable thresholds and weights
├── .env                       # Secrets (API keys, stream URLs)
├── requirements.txt           # Python dependencies
└── README.md
```

---

## Pipeline Overview

```
SSE Streams (logs / CloudWatch / Grafana)
    → C1  Ingestion & Normalisation     unified Signal schema
    → C2  Anomaly Detection             anomaly_score 0.0–1.0 per signal
    → filter  anomaly_score ≥ 0.40
    → C3  Correlation Engine            EvidenceGraph + Union-Find clusters
    → C4  Validation Gates              4 gates — all must pass
    → C4  Scoring                       severity_score + confidence_score
    → C5  LLM Ticket Draft              Claude-generated root-cause analysis
    →     Human Review                  approve / reject
    →     Jira Ticket Publication
```

### Correlation Dimensions (5)

| Dimension | Weight | Description |
|-----------|--------|-------------|
| Temporal | 0.25 | Signals within the correlation time window |
| Service | 0.25 | Same or topologically adjacent service |
| Component | 0.15 | Same component within a service |
| Topology | 0.20 | Hop distance in the service dependency graph |
| Evidence Similarity | 0.15 | Drain3 log template Jaccard similarity |

### Validation Gates (4)

All four gates must pass for a candidate cluster to become an accepted incident:

| Gate | Rule |
|------|------|
| **Strong Edge** | At least one edge in the cluster must score ≥ `strong_edge_threshold` |
| **Environment Consistency** | All signals must share the same environment (prod ≠ staging) |
| **Coherence** | Average internal edge score ≥ floor AND strong-edge ratio ≥ floor |
| **Bridge Check** | No signal may act as a weak transitive bridge between two sub-clusters |

### Severity Score (0–100)

Severity is a **continuous numeric score** on a 0–100 scale.
It is computed as a weighted composite of four factors:

```
Severity = 0.35 × Blast Radius
         + 0.35 × Business Criticality
         + 0.20 × Trend
         + 0.10 × Magnitude
```

| Factor | Description |
|--------|-------------|
| **Blast Radius** | Number of distinct impacted services: 1→25, 2→50, 3→75, 4→88, 5+→100 |
| **Business Criticality** | Max service criticality from `data/criticality_map.json` (0–100) |
| **Trend** | Signal rate acceleration: 100 = worsening, 50 = steady, 0 = recovering |
| **Magnitude** | Peak `anomaly_score` in the cluster, scaled to 0–100 |

### Confidence Score (0.0–1.0)

Separately computed from the correlation evidence quality:

```
Confidence = 0.35 × Edge Density
           + 0.25 × Score Agreement
           + 0.20 × Topology Coverage
           + 0.20 × Temporal Cohesion
```

---

## Getting Started

### 1. Install dependencies

```bash
python -m venv venv
venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — add ANTHROPIC_API_KEY and stream URLs
```

### 3. Start the backend

```bash
uvicorn app.main:app --reload --port 8000
```

### 4. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

### 5. Run tests

```bash
pytest -v   # 125 tests
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/signals` | Ingest a single normalised signal |
| `POST` | `/api/signals/batch` | Batch ingest + forced pipeline run |
| `GET` | `/api/signals` | List all ingested signals |
| `GET` | `/api/incidents` | List all accepted incidents |
| `GET` | `/api/incidents/{id}` | Fetch a single incident |
| `GET` | `/api/incidents/{id}/graph` | Evidence graph for an incident |
| `POST` | `/api/incidents/{id}/draft` | Generate LLM ticket draft |
| `GET` | `/api/incidents/{id}/draft` | Fetch existing draft |
| `POST` | `/api/incidents/{id}/review` | Submit human review decision |
| `POST` | `/api/jira/tickets` | Publish approved ticket to Jira |
| `GET` | `/api/health` | Pipeline health + stream status |
| `GET` | `/api/streams/status` | Live SSE stream connection status |
