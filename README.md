# Ensylon AIOps

An intelligent incident correlation and root-cause analysis engine for cloud infrastructure and microservices.

## Architecture & Directory Structure

```text
ensylon-aiops/
│
├── app/
│   ├── main.py                # Pipeline entrypoint
│   │
│   ├── models/                # Domain models (Signal, Incident)
│   │   ├── signal.py
│   │   └── incident.py
│   │
│   ├── ingestion/             # Multi-source signal ingestion
│   │   ├── cloudwatch.py      # AWS CloudWatch alarms
│   │   ├── logs.py            # Log streams
│   │   └── grafana.py         # Grafana alertmanager webhooks
│   │
│   ├── detection/             # Anomaly detection routines
│   │   ├── metrics.py         # Metric threshold & deviation detection
│   │   └── logs.py            # Log error spike analysis
│   │
│   ├── correlation/           # Correlation & clustering engine
│   │   ├── graph.py           # Service topology dependency graph
│   │   ├── scoring.py         # Correlation affinity scoring
│   │   ├── union_find.py      # Disjoint-set clustering algorithm
│   │   └── gates.py           # Noise reduction and gating rules
│   │
│   ├── scoring/               # Incident impact & severity assessment
│   │   └── severity.py        # SEV1 - SEV4 calculator
│   │
│   ├── fingerprint/           # Incident signature deduplication
│   │   └── fingerprint.py     # Deterministic hashing
│   │
│   ├── llm/                   # AI synthesis & hypothesis generation
│   │   └── ticket.py          # Auto-generated incident summaries & tickets
│   │
│   └── review/                # Human-in-the-loop workflow
│       └── review.py          # Operator triage and feedback
│
├── data/
│   └── sample_signals.json    # Sample alerts & log anomaly inputs
│
├── tests/                     # Unit and integration tests
│
├── .env                       # Environment configuration
├── requirements.txt           # Python dependencies
└── README.md                  # Project documentation
```

## Getting Started

### 1. Installation

```bash
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### 2. Run the Pipeline

```bash
python -m app.main
```

### 3. Run Tests

```bash
pytest
```
