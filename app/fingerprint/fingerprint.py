"""
Incident fingerprint generator — PRD §8 / §19.

A fingerprint captures the structural identity of an incident so that:
- Later signals can be attached to an existing incident instead of creating duplicates.
- Incidents with the same root cause pattern are recognizable across time.

Continuation flow (PRD §19):
  New signal → inside 5-min window? → YES: normal correlation
                                     → NO: compare with active fingerprints
                                          → high similarity? → attach to existing
                                                             → else: new incident
"""
import hashlib
import json
from app.models.signal import Signal
from app.models.fingerprint import IncidentFingerprint
from app.correlation.topology import load_topology, get_hop_distance


def _build_service_path(signals: list[Signal]) -> list[str]:
    """
    Build the causal service path by topological ordering of impacted services.
    Starts from the service that appears earliest (upstream in topology).
    """
    topo = load_topology()
    services = sorted({s.service for s in signals})

    # Sort by upstream position: service with no incoming edges from our set first
    def upstream_count(svc: str) -> int:
        """Count how many OTHER impacted services are upstream of this one."""
        count = 0
        for other in services:
            if other != svc and get_hop_distance(other, svc) <= 3:
                count += 1
        return count

    return sorted(services, key=upstream_count)


def _build_topology_subgraph(services: list[str]) -> dict:
    """Extract the relevant subgraph for the impacted services."""
    topo = load_topology()
    subgraph = {}
    service_set = set(services)
    for svc in services:
        neighbors = [n for n in topo.get(svc, []) if n in service_set]
        if neighbors:
            subgraph[svc] = neighbors
    return subgraph


def generate_fingerprint(
    signals: list[Signal],
    severity: float,
    confidence: float,
) -> IncidentFingerprint:
    """
    Build a deterministic IncidentFingerprint from the accepted incident's signals.
    PRD §8 — contains environment, service_path, components, topology,
    template_ids, temporal_pattern, severity, confidence.
    """
    environment = signals[0].environment if signals else "unknown"
    service_path = _build_service_path(signals)
    components = sorted({s.component for s in signals})
    topology = _build_topology_subgraph(service_path)
    template_ids = sorted({str(s.template_id) for s in signals if s.template_id})
    temporal_pattern = [
        s.timestamp.isoformat()
        for s in sorted(signals, key=lambda x: x.timestamp)
    ]

    return IncidentFingerprint(
        environment=environment,
        service_path=service_path,
        components=components,
        topology=topology,
        template_ids=template_ids,
        temporal_pattern=temporal_pattern,
        severity=severity,
        confidence=confidence,
    )


def fingerprint_hash(fp: IncidentFingerprint) -> str:
    """
    Stable SHA-256 hash of the structural fingerprint fields (excludes severity/confidence).
    Used for deduplication — two incidents with the same structure get the same hash.
    """
    structural = {
        "environment": fp.environment,
        "service_path": fp.service_path,
        "components": fp.components,
        "template_ids": fp.template_ids,
    }
    raw = json.dumps(structural, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def similarity_score(fp_a: IncidentFingerprint, fp_b: IncidentFingerprint) -> float:
    """
    Compute structural similarity between two fingerprints (0.0–1.0).
    Used for continuation matching (PRD §19).

    Dimensions:
    - Shared services in path: 0.40 weight
    - Shared components:       0.25 weight
    - Shared template IDs:     0.25 weight
    - Same environment:        0.10 weight
    """
    def jaccard(a: list, b: list) -> float:
        sa, sb = set(a), set(b)
        union = sa | sb
        if not union:
            return 1.0
        return len(sa & sb) / len(union)

    service_sim = jaccard(fp_a.service_path, fp_b.service_path)
    component_sim = jaccard(fp_a.components, fp_b.components)
    template_sim = jaccard(fp_a.template_ids, fp_b.template_ids)
    env_sim = 1.0 if fp_a.environment == fp_b.environment else 0.0

    return (
        0.40 * service_sim
        + 0.25 * component_sim
        + 0.25 * template_sim
        + 0.10 * env_sim
    )

