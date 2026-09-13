"""
Correlation Confidence engine — PRD §7/G7 / §18.

Formula:
    Confidence = 0.35*Density + 0.25*Agreement + 0.20*Topology + 0.20*Temporal

Output: 0.00–1.00 (clamped)

Confidence answers: "How strong is the evidence that these signals belong to the same incident?"
It must NOT be treated as root-cause prediction accuracy (PRD §7/G7).
"""
from app.config import get_confidence_cfg, get_correlation_cfg
from app.models.edge import EvidenceEdge


def calculate_density(edges: list[EvidenceEdge], n_signals: int) -> float:
    """
    Density = actual_strong_edges / max_possible_edges.
    High density means most pairs have strong evidence of being related.
    """
    if n_signals < 2:
        return 0.0

    cfg = get_correlation_cfg()
    t = cfg["strong_edge_threshold"]
    max_edges = n_signals * (n_signals - 1) / 2
    strong = sum(1 for e in edges if e.correlation_score >= t)
    return min(strong / max_edges, 1.0)


def calculate_agreement(edges: list[EvidenceEdge]) -> float:
    """
    Agreement = average correlation_score across all internal edges.
    Measures how consistently the dimensions agree with each other.
    """
    if not edges:
        return 0.0
    return sum(e.correlation_score for e in edges) / len(edges)


def calculate_topology_coverage(edges: list[EvidenceEdge]) -> float:
    """
    Topology coverage = fraction of edges that have a non-zero topology score.
    High coverage means the signals trace a known dependency path.
    """
    if not edges:
        return 0.0
    covered = sum(1 for e in edges if e.topology > 0)
    return covered / len(edges)


def calculate_temporal_tightness(edges: list[EvidenceEdge]) -> float:
    """
    Temporal tightness = average temporal score across all edges.
    Higher = signals are tightly co-incident in time.
    """
    if not edges:
        return 0.0
    return sum(e.temporal for e in edges) / len(edges)


def calculate_confidence(
    edges: list[EvidenceEdge],
    n_signals: int,
) -> float:
    """
    PRD §18 formula:
        Confidence = 0.35*Density + 0.25*Agreement + 0.20*Topology + 0.20*Temporal
    Returns a float clamped to 0.00–1.00.
    """
    cfg = get_confidence_cfg()

    density = calculate_density(edges, n_signals)
    agreement = calculate_agreement(edges)
    topology = calculate_topology_coverage(edges)
    temporal = calculate_temporal_tightness(edges)

    score = (
        cfg["density"] * density
        + cfg["agreement"] * agreement
        + cfg["topology"] * topology
        + cfg["temporal"] * temporal
    )
    return round(min(max(score, 0.0), 1.0), 4)
