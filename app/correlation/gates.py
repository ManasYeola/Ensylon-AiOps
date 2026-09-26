"""
Four Validation Gates — every candidate cluster must pass all four (PRD §5/G5 / §16).

Gate results are always exposed so the UI can explain accept/reject decisions.

Gate 1 — Strong Edge:     At least one strong edge (>= threshold) must exist in the cluster.
Gate 2 — Env Consistency: All signals must share the same environment.
Gate 3 — Coherence:       Average internal edge score must be above floor; strong-edge ratio above floor.
Gate 4 — Bridge Check:    A signal that bridges two sub-clusters must have a strong edge to BOTH sides.
"""
from dataclasses import dataclass, field
from app.config import get_correlation_cfg, get_validation_cfg
from app.correlation.graph import EvidenceGraph
from app.models.signal import Signal


@dataclass
class GateResult:
    passed: bool
    reason: str = ""


@dataclass
class ValidationResult:
    accepted: bool
    gates: dict[str, GateResult] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "accepted": self.accepted,
            "gates": {
                name: {"passed": r.passed, "reason": r.reason}
                for name, r in self.gates.items()
            },
            "reasons": [r.reason for r in self.gates.values() if not r.passed],
        }


# ---------------------------------------------------------------------------
# Gate 1 — Strong Edge
# ---------------------------------------------------------------------------

def validate_strong_edge(
    cluster: list[str],
    graph: EvidenceGraph,
    threshold: float | None = None,
) -> GateResult:
    """At least one pair inside the cluster must have a strong edge."""
    cfg = get_correlation_cfg()
    t = threshold or cfg["strong_edge_threshold"]

    internal_edges = graph.edges_within_cluster(cluster)
    strong = [e for e in internal_edges if e.correlation_score >= t]

    if len(cluster) == 1:
        # Single-signal clusters trivially fail the strong-edge gate
        return GateResult(False, "Single-signal cluster has no edges")
    if strong:
        return GateResult(True)
    return GateResult(
        False,
        f"No strong edges found (threshold={t}); "
        f"max score={max((e.correlation_score for e in internal_edges), default=0):.3f}",
    )


# ---------------------------------------------------------------------------
# Gate 2 — Environment Consistency
# ---------------------------------------------------------------------------

def validate_environment_consistency(
    cluster: list[str],
    signals: dict[str, Signal],
) -> GateResult:
    """All signals in the cluster must share the same environment (PRD §5/G5)."""
    envs = {signals[sid].environment for sid in cluster}
    if len(envs) == 1:
        return GateResult(True)
    return GateResult(
        False,
        f"Environment mismatch across cluster: {envs}",
    )


# ---------------------------------------------------------------------------
# Gate 3 — Coherence
# ---------------------------------------------------------------------------

def validate_coherence(
    cluster: list[str],
    graph: EvidenceGraph,
    avg_threshold: float | None = None,
    strong_ratio: float | None = None,
) -> GateResult:
    """
    The cluster must be internally coherent:
    - Average internal edge score >= avg_threshold
    - Ratio of strong edges / total edges >= strong_ratio
    Thresholds from config.yaml.
    """
    val_cfg = get_validation_cfg()
    corr_cfg = get_correlation_cfg()

    avg_t = avg_threshold or val_cfg["coherence_avg_threshold"]
    ratio_t = strong_ratio or val_cfg["coherence_strong_ratio"]
    strong_t = corr_cfg["strong_edge_threshold"]

    internal = graph.edges_within_cluster(cluster)
    if not internal:
        if len(cluster) == 1:
            return GateResult(False, "Single-signal cluster cannot be coherent")
        return GateResult(False, "No internal edges found for coherence check")

    avg_score = sum(e.correlation_score for e in internal) / len(internal)
    strong_count = sum(1 for e in internal if e.correlation_score >= strong_t)
    ratio = strong_count / len(internal)

    if avg_score < avg_t:
        return GateResult(
            False,
            f"Average internal score {avg_score:.3f} < threshold {avg_t}",
        )
    if ratio < ratio_t:
        return GateResult(
            False,
            f"Strong-edge ratio {ratio:.2f} < threshold {ratio_t}",
        )
    return GateResult(True)


# ---------------------------------------------------------------------------
# Gate 4 — Bridge Check
# ---------------------------------------------------------------------------

def validate_bridge(
    cluster: list[str],
    graph: EvidenceGraph,
    threshold: float | None = None,
) -> GateResult:
    """
    Prevent weak transitive chains from creating false mega-incidents.

    A signal is a "bridge" if removing it splits the cluster's strong-edge graph.
    If a bridge exists, it must have a strong edge (>= threshold) to the coherent
    core on BOTH sides of the split.

    For MVP: we check that no signal is only weakly connected (< threshold)
    to both sides of any partition, i.e. no pure weak-chain bridges exist.
    """
    val_cfg = get_validation_cfg()
    corr_cfg = get_correlation_cfg()
    t = threshold or val_cfg["bridge_strong_threshold"]
    strong_t = corr_cfg["strong_edge_threshold"]

    if len(cluster) < 3:
        # Bridge check is only meaningful with 3+ signals
        return GateResult(True)

    cluster_set = set(cluster)

    for candidate in cluster:
        rest = cluster_set - {candidate}
        # Check connectivity of the remaining set using only strong edges
        if not rest:
            continue

        # BFS on strong edges among 'rest'
        start = next(iter(rest))
        visited = {start}
        queue = [start]
        while queue:
            curr = queue.pop(0)
            for nid, edge in graph.get_neighbors(curr).items():
                if nid in rest and nid not in visited and edge.correlation_score >= strong_t:
                    visited.add(nid)
                    queue.append(nid)

        if len(visited) < len(rest):
            # Candidate is a bridge — check it has strong edges to BOTH components
            component_a = visited
            component_b = rest - visited

            def best_score_to(node: str, group: set) -> float:
                best = 0.0
                for n in group:
                    e = graph.get_edge(node, n) or graph.get_edge(n, node)
                    if e:
                        best = max(best, e.correlation_score)
                return best

            sa = best_score_to(candidate, component_a)
            sb = best_score_to(candidate, component_b)

            if sa < t or sb < t:
                return GateResult(
                    False,
                    f"Signal {candidate} is a bridge but has weak edges "
                    f"(scores: {sa:.3f} to comp-A, {sb:.3f} to comp-B; threshold={t})",
                )

    return GateResult(True)


# ---------------------------------------------------------------------------
# Aggregate validator
# ---------------------------------------------------------------------------

def validate_cluster(
    cluster: list[str],
    graph: EvidenceGraph,
) -> ValidationResult:
    """
    Run all four gates. Returns structured ValidationResult with per-gate details.
    PRD §16
    """
    signals = graph.signals

    g1 = validate_strong_edge(cluster, graph)
    g2 = validate_environment_consistency(cluster, signals)
    g3 = validate_coherence(cluster, graph)
    g4 = validate_bridge(cluster, graph)

    gates = {
        "strong_edge": g1,
        "environment_consistency": g2,
        "coherence": g3,
        "bridge_check": g4,
    }
    accepted = all(g.passed for g in gates.values())

    return ValidationResult(accepted=accepted, gates=gates)
