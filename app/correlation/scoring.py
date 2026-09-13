"""
Correlation scoring — five independent dimension functions + weighted composite.

PRD §13 formula:
    C(A,B) = 0.25*T + 0.25*S + 0.15*C + 0.20*D + 0.15*E

All weights are loaded from config.yaml; never hardcoded here.
"""
from app.models.signal import Signal
from app.models.edge import EvidenceEdge
from app.config import get_correlation_cfg
from app.correlation.topology import get_hop_distance


# ---------------------------------------------------------------------------
# Individual dimension scorers
# ---------------------------------------------------------------------------

def calculate_temporal_score(a: Signal, b: Signal, window_seconds: int | None = None) -> float:
    """
    T — temporal proximity score.
    1.0 = same instant, 0.0 = at or beyond the window boundary.
    PRD: 5-minute correlation window is configurable.
    """
    cfg = get_correlation_cfg()
    w = window_seconds or (cfg["window_minutes"] * 60)
    delta = abs((a.timestamp - b.timestamp).total_seconds())
    if delta >= w:
        return 0.0
    return 1.0 - (delta / w)


def calculate_service_score(a: Signal, b: Signal) -> float:
    """
    S — service relationship score.
    1.0 = same service, 0.0 = no relationship.
    """
    if a.service == b.service:
        return 1.0
    return 0.0


def calculate_component_score(a: Signal, b: Signal) -> float:
    """
    C — component relationship score.
    1.0 = same component within the same service.
    0.5 = same component name across different services (shared infrastructure).
    0.0 = different components.
    """
    if a.component == b.component:
        return 1.0 if a.service == b.service else 0.5
    return 0.0


def calculate_topology_score(a: Signal, b: Signal) -> float:
    """
    D — topology/dependency score.
    Decays linearly with hop distance; 0 hops = 1.0, 3 hops = 0.25, beyond = 0.0.
    """
    if a.service == b.service:
        return 1.0
    hops = get_hop_distance(a.service, b.service)
    if hops == 1:
        return 0.85
    if hops == 2:
        return 0.55
    if hops == 3:
        return 0.25
    return 0.0


def calculate_evidence_similarity(a: Signal, b: Signal) -> float:
    """
    E — evidence/template similarity score.
    Same type + same template = 1.0.
    Same type, no template = 0.5.
    Different type = 0.0.
    """
    if a.type != b.type:
        return 0.0
    if a.template_id and b.template_id:
        return 1.0 if a.template_id == b.template_id else 0.3
    # same type but no template info
    return 0.5


# ---------------------------------------------------------------------------
# Weighted composite — PRD §13
# ---------------------------------------------------------------------------

def correlation_score(a: Signal, b: Signal) -> EvidenceEdge:
    """
    Compute the full EvidenceEdge between signals a and b.
    Weights are always loaded from config.yaml.
    """
    cfg = get_correlation_cfg()
    w = cfg["weights"]

    t = calculate_temporal_score(a, b)
    s = calculate_service_score(a, b)
    c = calculate_component_score(a, b)
    d = calculate_topology_score(a, b)
    e = calculate_evidence_similarity(a, b)

    score = (
        w["temporal"] * t
        + w["service"] * s
        + w["component"] * c
        + w["topology"] * d
        + w["evidence_similarity"] * e
    )
    score = round(min(score, 1.0), 4)

    return EvidenceEdge(
        source_signal=a.id,
        target_signal=b.id,
        temporal=round(t, 4),
        service=round(s, 4),
        component=round(c, 4),
        topology=round(d, 4),
        evidence_similarity=round(e, 4),
        correlation_score=score,
    )
