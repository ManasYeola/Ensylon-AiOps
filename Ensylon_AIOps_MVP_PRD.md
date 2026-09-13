# PRD — Ensylon Intelligent AIOps Incident Correlation & Ticket Drafting

## 1. Product Overview

### Product Name
**Ensylon Intelligent AIOps**

### Objective

Build an end-to-end AIOps system that:

1. Ingests telemetry from multiple sources.
2. Detects anomalous signals independently.
3. Correlates related anomalies into a single incident.
4. Scores incident severity and correlation confidence separately.
5. Creates an incident fingerprint for continuity.
6. Uses an evidence-grounded LLM to draft a structured Jira ticket.
7. Requires human approval before Jira publication.

Core hackathon scenario:

```text
17 raw signals
      ↓
Correlation
      ↓
1 accepted incident
      ↓
1 Jira ticket draft
      ↓
Human review
      ↓
Jira
```

The system must not automatically publish tickets. Infrastructure access is read-only, and sensitive information must be redacted before processing/storage.

---

## 2. Problem

Modern cloud systems produce thousands of telemetry signals. A single underlying failure can generate many apparently independent alerts.

Example:

```text
Database connection-pool exhaustion
            ↓
 ┌──────────┼───────────┐
 ↓          ↓           ↓
DB alarm   App errors   Latency alert
                         ↓
                  Downstream timeouts
```

The SRE should receive one coherent incident rather than many separate alerts.

Hackathon example:

- 1 DB connection-pool anomaly
- 12 application error-log bursts
- 1 Grafana latency alert
- 3 downstream timeout alerts

Total = **17 signals representing 1 underlying incident**.

---

# 3. Goals

## G1 — Multi-source ingestion

Support normalized ingestion of:

- CloudWatch-style metrics
- JSON application logs
- Grafana alerts

For the MVP, replay/sample JSON data is sufficient. Live connectors are optional stretch work.

---

## G2 — Anomaly detection

### Metrics

Implement:

- Rolling baseline
- Rolling z-score
- EWMA

### Logs

Implement:

- Drain3 log templates
- Template frequency tracking
- Burst detection

### Grafana

Implement:

- Alert normalization
- Alert deduplication

Detection answers:

> **"Is something abnormal?"**

---

## G3 — Intelligent correlation

Build an Evidence Graph.

- Each anomaly is a node.
- Each evidentiary relationship is a weighted edge.

Correlation dimensions:

1. Temporal relationship
2. Service relationship
3. Component relationship
4. Dependency/topology relationship
5. Evidence similarity

Correlation formula:

```text
C(A,B) =
0.25*T
+ 0.25*S
+ 0.15*C
+ 0.20*D
+ 0.15*E
```

The weights must be configurable.

Default strong-edge threshold:

```text
C >= 0.70
```

Important principle:

> **The time window generates candidates; evidence decides membership.**

---

## G4 — Candidate clustering

Use Union-Find / Disjoint Set Union to create candidate incident clusters from strong edges.

Important:

```text
Union-Find ≠ final incident decision
```

Union-Find only proposes candidate groups. Candidates must pass all validation gates.

---

## G5 — Validation

Every candidate cluster must pass four gates:

1. Strong Edge
2. Environment Consistency
3. Coherence
4. Bridge Check

Expose the result of every gate so the UI can explain why a candidate was accepted or rejected.

### Gate 1 — Strong Edge

Require sufficient strong correlation edges.

Default:

```text
score >= 0.70
```

### Gate 2 — Environment Consistency

Do not merge production and staging signals unless there is an explicit relationship.

### Gate 3 — Coherence

Validate that the candidate is internally coherent.

Check:

- Average internal edge score
- Strong core

Thresholds must be configurable.

### Gate 4 — Bridge Check

A bridge signal may connect two otherwise separate sub-clusters only if it has a strong edge:

```text
>= 0.70
```

to the coherent core of both sides.

This prevents weak transitive chains from creating false mega-incidents.

---

## G6 — Severity

Calculate severity using:

```text
Severity =
0.35*Blast
+ 0.35*Criticality
+ 0.20*Trend
+ 0.10*Magnitude
```

Output:

```text
0–100
```

Example business criticality values:

```text
Checkout        95
Payment         92
Order           88
Internal Admin  20
Unknown         50
```

Unknown services should remain neutral and be flagged for reviewer confirmation.

Severity answers:

> **"How bad is the incident?"**

---

## G7 — Correlation Confidence

Calculate:

```text
Confidence =
0.35*Density
+ 0.25*Agreement
+ 0.20*Topology
+ 0.20*Temporal
```

Output:

```text
0.00–1.00
```

Confidence answers:

> **"How strong is the evidence that these signals belong to the same incident?"**

Do not treat confidence as root-cause prediction accuracy.

Severity and confidence must remain separate.

---

## G8 — Incident Fingerprint

Every accepted incident must have a fingerprint containing:

```text
Environment
Service path
Components
Topology
Log template IDs
Temporal pattern
Severity
Confidence
```

Purpose:

Allow later signals to attach to an active/recent incident instead of creating duplicate incidents.

Continuation flow:

```text
New signal
    ↓
Inside 5-minute window?
    ├── YES → normal correlation
    │
    └── NO
         ↓
Compare with active/recent fingerprints
         ↓
High similarity?
    ├── YES → attach to existing incident
    └── NO  → new incident
```

---

## G9 — Evidence-grounded LLM ticket

Generate a structured Jira draft containing:

```text
Title
Severity
Correlation Confidence
Affected Services
Summary
Timeline
Observed Evidence
Investigation Steps
Suspected / Unverified Root Cause
```

The LLM must only use supplied evidence.

Clearly distinguish:

```text
Observed evidence
```

from:

```text
Suspected / unverified root cause
```

If the root cause is not established, explicitly state that it is unverified.

---

## G10 — Human Review

Workflow:

```text
LLM Draft
   ↓
Human Reviewer
   ↓
Approve / Edit / Reject
   ↓
Jira
```

There must be no automatic publishing.

Only an approved ticket can reach Jira.

---

# 4. Non-goals for MVP

Do not build these initially:

- Kubernetes deployment
- Production CloudWatch authentication
- Production Grafana authentication
- Autonomous remediation
- Automatic Jira publishing
- Full distributed tracing
- Complex ML model training
- Kafka-based real-time pipeline
- Automatic root-cause certainty
- Enterprise RBAC/authentication

These can be stretch goals after the core pipeline works.

---

# 5. System Architecture

```text
                    ┌──────────────────┐
                    │   CloudWatch     │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ Metric Detection │
                    └────────┬─────────┘
                             │
┌──────────────┐    ┌────────▼─────────┐
│ Application  │───►│ Normalized       │
│ Logs         │    │ Signal Model     │
└──────────────┘    └────────┬─────────┘
                             │
┌──────────────┐             │
│ Grafana      │─────────────┤
└──────────────┘             │
                             ▼
                    ┌─────────────────┐
                    │ Evidence Graph  │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ Correlation     │
                    │ Scoring         │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ Union-Find      │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ 4 Validation    │
                    │ Gates           │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ Incident        │
                    │ Fingerprint     │
                    └────────┬────────┘
                             │
                    ┌────────┴────────┐
                    ▼                 ▼
              ┌───────────┐    ┌────────────┐
              │ Severity  │    │ Confidence │
              └─────┬─────┘    └──────┬─────┘
                    └────────┬─────────┘
                             ▼
                    ┌─────────────────┐
                    │ Evidence        │
                    │ Package         │
                    └────────┬────────┘
                             ▼
                    ┌─────────────────┐
                    │      LLM        │
                    └────────┬────────┘
                             ▼
                    ┌─────────────────┐
                    │ Jira Draft      │
                    └────────┬────────┘
                             ▼
                       HUMAN REVIEW
                             │
                    ┌────────┴────────┐
                    ▼                 ▼
                 Reject            Approve
                                      │
                                      ▼
                                    Jira
```

---

# 6. Technology Stack

## Backend

- Python
- FastAPI
- Pydantic

Reason:

- Fast REST API development
- Strong schema validation
- Good Python ecosystem for anomaly detection, Drain3 and LLM integration

## Database

Start with SQLite.

Design models so migration to PostgreSQL is straightforward.

Store:

```text
signals
edges
incidents
fingerprints
ticket_drafts
review_actions
```

Sensitive fields must be redacted before persistence.

## Log processing

Use Drain3 for template extraction.

Example:

```text
Database timeout for user 123
Database timeout for user 456
Database timeout for user 789
```

becomes:

```text
Database timeout for user <*>
```

## Correlation

Pure Python implementation:

```text
EvidenceGraph
CorrelationScorer
UnionFind
ValidationGates
```

## LLM

Use the configured OpenAI-compatible LLM API.

The model receives structured incident evidence and returns a structured TicketDraft.

## Frontend

React.

Main screens:

1. Dashboard
2. Incident Details
3. Evidence Graph
4. Ticket Review

## Jira

MVP:

- Mock Jira

Stretch:

- Real Jira REST API

---

# 7. Project Structure

```text
ensylon-aiops/
│
├── app/
│   ├── main.py
│   │
│   ├── models/
│   │   ├── signal.py
│   │   ├── edge.py
│   │   ├── incident.py
│   │   ├── fingerprint.py
│   │   └── ticket.py
│   │
│   ├── ingestion/
│   │   ├── cloudwatch.py
│   │   ├── logs.py
│   │   └── grafana.py
│   │
│   ├── detection/
│   │   ├── metrics.py
│   │   └── logs.py
│   │
│   ├── correlation/
│   │   ├── graph.py
│   │   ├── scoring.py
│   │   ├── union_find.py
│   │   └── gates.py
│   │
│   ├── scoring/
│   │   ├── severity.py
│   │   └── confidence.py
│   │
│   ├── fingerprint/
│   │   └── fingerprint.py
│   │
│   ├── llm/
│   │   └── ticket.py
│   │
│   ├── review/
│   │   └── review.py
│   │
│   └── jira/
│       └── mock_jira.py
│
├── frontend/
│
├── data/
│   ├── sample_signals.json
│   └── topology.json
│
├── scripts/
│   └── run_demo.py
│
├── tests/
│
├── config.yaml
├── requirements.txt
├── .env.example
└── README.md
```

---

# 8. Data Models

## Signal

```python
class Signal(BaseModel):
    id: str
    timestamp: datetime

    source: str
    environment: str

    service: str
    component: str

    type: str

    value: Optional[float] = None
    template_id: Optional[str] = None
    message: Optional[str] = None
```

## Evidence Edge

```python
class EvidenceEdge(BaseModel):
    source_signal: str
    target_signal: str

    temporal: float
    service: float
    component: float
    topology: float
    evidence_similarity: float

    correlation_score: float
```

## Incident

```python
class Incident(BaseModel):
    id: str
    signal_ids: list[str]

    environment: str
    services: list[str]

    severity: float
    confidence: float

    status: str

    fingerprint_id: str
```

## Incident Fingerprint

```python
class IncidentFingerprint(BaseModel):
    environment: str
    service_path: list[str]
    components: list[str]
    topology: dict
    template_ids: list[str]
    temporal_pattern: list[str]
    severity: float
    confidence: float
```

## Ticket Draft

```python
class TicketDraft(BaseModel):
    title: str
    severity: float
    confidence: float
    affected_services: list[str]
    summary: str
    timeline: list[str]
    observed_evidence: list[str]
    suspected_root_cause: str
    investigation_steps: list[str]
```

---

# 9. Sample 17-Signal Scenario

Create a replay dataset containing:

```text
S1
DB connection-pool anomaly

S2-S13
12 payment/application error bursts

S14
Grafana checkout latency alert

S15-S17
3 downstream order/payment timeout anomalies
```

All signals should be production signals and occur within approximately five minutes.

Also include an unrelated recommendation-service CPU anomaly in the negative-test dataset.

Expected:

```text
17 related signals
      ↓
1 accepted incident

Recommendation CPU anomaly
      ↓
Rejected from incident
```

---

# 10. Ingestion API

Implement:

```http
POST /api/signals
```

and:

```http
POST /api/signals/batch
```

The batch endpoint should load replay data and create normalized Signal objects.

---

# 11. Detection Engine

## Metric Detection

Implement:

```python
calculate_rolling_zscore()
calculate_ewma()
detect_metric_anomaly()
```

Configuration:

```yaml
detection:
  zscore_threshold: 3.0
  window_size: 20
  ewma_alpha: 0.3
```

## Log Detection

Pipeline:

```text
Raw log
 ↓
Drain3
 ↓
Template ID
 ↓
Frequency counter
 ↓
Baseline
 ↓
Burst detection
 ↓
Anomaly signal
```

---

# 12. Correlation Engine

Only compare signals within the configurable correlation window.

Default:

```yaml
correlation:
  window_minutes: 5
```

Important:

```text
5-minute window ≠ same incident
```

---

# 13. Correlation Dimensions

Implement independent scoring functions:

```python
calculate_temporal_score(a, b)
calculate_service_score(a, b)
calculate_component_score(a, b)
calculate_topology_score(a, b)
calculate_evidence_similarity(a, b)
```

Then:

```python
def correlation_score(a, b):
    return (
        0.25 * temporal +
        0.25 * service +
        0.15 * component +
        0.20 * topology +
        0.15 * evidence_similarity
    )
```

Weights must be loaded from configuration.

---

# 14. Topology

For MVP, use static configuration.

Example:

```json
{
  "database": ["payment"],
  "payment": ["checkout"],
  "checkout": ["order"]
}
```

This represents:

```text
database
   ↓
payment
   ↓
checkout
   ↓
order
```

Do not attempt automatic topology discovery for the MVP.

---

# 15. Union-Find

Implement:

```python
class UnionFind:
    def find(self, x):
        ...

    def union(self, a, b):
        ...
```

For every strong edge:

```text
correlation_score >= 0.70
```

union the two signals.

After processing all strong edges, candidate groups are generated.

These candidates must still pass all validation gates.

---

# 16. Validation Gate API

Implement:

```python
validate_strong_edge(cluster)
validate_environment_consistency(cluster)
validate_coherence(cluster)
validate_bridge(cluster)
```

Then:

```python
validate_cluster(cluster)
```

must return something like:

```json
{
  "accepted": true,
  "gates": {
    "strong_edge": true,
    "environment_consistency": true,
    "coherence": true,
    "bridge_check": true
  },
  "reasons": []
}
```

For rejected clusters, return useful explanations.

---

# 17. Severity Engine

Implement:

```python
def calculate_severity(
    blast,
    criticality,
    trend,
    magnitude
):
    return (
        0.35 * blast +
        0.35 * criticality +
        0.20 * trend +
        0.10 * magnitude
    )
```

Clamp result to:

```text
0–100
```

---

# 18. Confidence Engine

Implement:

```python
def calculate_confidence(
    density,
    agreement,
    topology,
    temporal
):
    return (
        0.35 * density +
        0.25 * agreement +
        0.20 * topology +
        0.20 * temporal
    )
```

Clamp result to:

```text
0.00–1.00
```

---

# 19. Fingerprint Matching

When a new signal arrives after the normal correlation window:

1. Find active/recent incidents.
2. Compare the new signal to incident fingerprints.
3. Compare:
   - service path
   - components
   - topology
   - template IDs
   - temporal continuity
4. Attach the signal to the best matching incident if similarity is sufficiently high.
5. Otherwise create a new incident.

Do not create duplicate incidents for continuing failures.

---

# 20. LLM Ticket Generation

Endpoint:

```http
POST /api/incidents/{incident_id}/draft
```

Input should be structured evidence:

```json
{
  "incident_id": "INC-001",
  "severity": 88,
  "confidence": 0.93,
  "environment": "prod",
  "services": [
    "database",
    "payment",
    "checkout",
    "order"
  ],
  "timeline": [],
  "observed_evidence": [],
  "topology": []
}
```

Output:

```json
{
  "title": "...",
  "severity": 88,
  "confidence": 0.93,
  "affected_services": [],
  "summary": "...",
  "timeline": [],
  "observed_evidence": [],
  "suspected_root_cause": "...",
  "investigation_steps": []
}
```

LLM rules:

```text
Use only supplied evidence.

Do not invent metrics, timestamps, services,
causes, or remediation actions.

Clearly distinguish observed evidence from
suspected or unverified root causes.

If root cause is not established, explicitly
state that it is unverified.
```

---

# 21. Human Review API

Implement:

```http
GET /api/incidents
GET /api/incidents/{id}
GET /api/incidents/{id}/draft
POST /api/incidents/{id}/review
```

Review request:

```json
{
  "action": "approve",
  "edited_draft": {}
}
```

Allowed:

```text
approve
edit
reject
```

Only approved drafts can reach Jira.

---

# 22. Mock Jira

Implement:

```http
POST /api/jira/tickets
```

Create mock ticket IDs:

```text
ENS-101
ENS-102
...
```

The Jira endpoint must reject requests unless the incident has an approved review state.

Stretch goal:

Integrate Jira REST API after the full MVP works.

---

# 23. Frontend

## Dashboard

Show:

```text
Signals: 17
Incidents: 1
Severity: 88
Confidence: 0.93
```

## Incident Details

Show:

- Incident ID
- Severity
- Confidence
- Number of signals
- Environment
- Affected services
- Timeline
- Evidence graph
- Correlation scores
- Validation gates
- Fingerprint

## Evidence Graph

Display:

```text
DB
 ●
 │ 0.92
 ▼
Payment
 ●
 │ 0.88
 ▼
Checkout
 ●
 │ 0.91
 ▼
Order
 ●
```

Clicking an edge should show:

```text
Correlation Score: 0.92

Temporal: 0.95
Service: 1.00
Component: 0.80
Topology: 1.00
Evidence: 0.75
```

## Ticket Review

Display the generated Jira draft with:

```text
[Edit]
[Approve]
[Reject]
```

---

# 24. Security

Implement sensitive-data redaction before processing/storage.

Potential sensitive values include:

```text
Email addresses
Phone numbers
Payment information
Credentials
API keys
Tokens
```

Example:

```text
"user_email": "user@example.com"
```

becomes:

```text
"user_email": "[REDACTED]"
```

Never store raw credentials, payment information, or other prohibited sensitive telemetry.

---

# 25. Configuration

Create `config.yaml`:

```yaml
correlation:
  window_minutes: 5
  strong_edge_threshold: 0.70

  weights:
    temporal: 0.25
    service: 0.25
    component: 0.15
    topology: 0.20
    evidence_similarity: 0.15

severity:
  blast: 0.35
  criticality: 0.35
  trend: 0.20
  magnitude: 0.10

confidence:
  density: 0.35
  agreement: 0.25
  topology: 0.20
  temporal: 0.20

detection:
  zscore_threshold: 3.0
  window_size: 20
  ewma_alpha: 0.3
```

Do not hardcode thresholds in business logic.

---

# 26. API Endpoints

Minimum API:

```text
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
```

Optional:

```text
GET /api/health
GET /api/config
POST /api/demo/run
```

---

# 27. End-to-End Demo

Create:

```bash
python scripts/run_demo.py
```

It should:

1. Load telemetry replay.
2. Normalize signals.
3. Detect anomalies.
4. Build evidence graph.
5. Calculate pairwise correlation.
6. Generate strong edges.
7. Run Union-Find.
8. Run four validation gates.
9. Create accepted incident(s).
10. Calculate severity.
11. Calculate confidence.
12. Create fingerprint.
13. Generate LLM ticket draft.
14. Present human review.
15. Publish to Mock Jira only after approval.

Expected output:

```text
========================================
ENSYLON AIOPS DEMO
========================================

[1/8] Loading telemetry............. OK
      17 signals

[2/8] Detecting anomalies........... OK
      17 anomalies

[3/8] Building evidence graph...... OK

[4/8] Correlation................... OK

[5/8] Validation.................... OK
      1 accepted incident
      1 rejected unrelated signal

[6/8] Scoring....................... OK
      Severity: ~88
      Confidence: ~0.93

[7/8] Generating ticket............. OK

[8/8] Human review.................. WAITING

========================================
INCIDENT INC-001
17 signals → 1 incident
Severity: 88
Confidence: 0.93
========================================
```

---

# 28. Negative Test

Include:

```text
Recommendation Service
CPU = 95%
```

It occurs within the same five-minute window.

Expected:

```text
Temporal relationship → YES
Topology relationship → NO
Evidence similarity   → LOW
Strong core connection → NO

Result:
Rejected from Incident INC-001
```

This proves the system does not use:

```text
same time → same incident
```

---

# 29. Testing Requirements

## Signal tests

Test:

- Valid signal
- Invalid timestamp
- Missing required field

## Detection tests

Test:

- Normal metric
- Extreme metric
- Gradual metric shift
- Log template spike
- Normal log frequency

## Correlation tests

Test:

- Strong temporal relationship
- Weak temporal relationship
- Same service
- Different service
- Topology relationship
- No topology
- Similar templates
- Different templates

## Union-Find tests

Example:

```text
A-B = 0.90
B-C = 0.85
C-D = 0.30
```

Expected candidate:

```text
{A,B,C}
```

and D remains separate unless another strong relationship exists.

## Gate tests

Test:

- Strong edge
- Production/staging mismatch
- Incoherent cluster
- Invalid bridge
- Valid bridge

## Severity tests

Use known inputs and verify exact output.

## Confidence tests

Use known inputs and verify exact output.

## LLM tests

Mock the LLM and verify:

- Required fields exist.
- Observed evidence remains unchanged.
- Unsupported root cause isn't presented as fact.
- No fabricated timestamps or metrics.

## End-to-end test

Must verify:

```text
17 signals
→ 1 accepted incident
→ unrelated signal rejected
→ severity calculated
→ confidence calculated
→ fingerprint created
→ ticket draft generated
→ Jira blocked before approval
→ Jira succeeds after approval
```

---

# 30. Implementation Order

Build incrementally in this exact order:

```text
1. Project setup
        ↓
2. Signal model
        ↓
3. Sample 17 signals
        ↓
4. Ingestion
        ↓
5. Detection
        ↓
6. Topology
        ↓
7. Evidence scoring
        ↓
8. Evidence graph
        ↓
9. Union-Find
        ↓
10. Four gates
        ↓
11. Severity
        ↓
12. Confidence
        ↓
13. Fingerprint
        ↓
14. LLM ticket
        ↓
15. Human review
        ↓
16. Mock Jira
        ↓
17. FastAPI integration
        ↓
18. React UI
        ↓
19. End-to-end demo
        ↓
20. Tests
```

Do not start with the UI.

First make:

```text
17 signals
    ↓
1 incident
```

Then:

```text
1 incident
    ↓
Severity + Confidence
```

Then:

```text
Incident
    ↓
LLM
    ↓
Ticket
```

Then build the UI around the working backend.

---

# 31. Definition of Done

The MVP is complete when:

### Input

```text
17 signals
```

### Processing

```text
Detection
↓
Evidence Graph
↓
Correlation
↓
Union-Find
↓
Four Validation Gates
```

### Output

```text
1 accepted incident

Severity ≈ 88
Confidence ≈ 0.93

17 related signals grouped
Unrelated recommendation alert rejected
```

### AI

```text
Evidence
↓
LLM
↓
Structured Jira draft
```

### Safety

```text
Human approval required
↓
Mock Jira
```

---

# 32. Coding-Agent Instruction

If this PRD is given to a coding agent, use this instruction:

> Implement this project incrementally. Do not implement later phases until the current phase passes its tests. Preserve the specified correlation formula, severity formula, confidence formula, configurable thresholds, four validation gates, incident fingerprinting, evidence/LLM separation, and human-review gate. Do not replace the architecture with a simpler alert-grouping approach. Do not invent unsupported root-cause evidence. Keep the first implementation replay-based and make live integrations optional.

The coding agent must:

1. Create the repository structure.
2. Implement backend modules.
3. Implement tests for every module.
4. Run tests after every major phase.
5. Implement the end-to-end replay demo.
6. Implement the frontend only after backend functionality works.
7. Provide setup instructions.
8. Provide `.env.example`.
9. Provide sample data.
10. Provide a single command to run the complete demo.
