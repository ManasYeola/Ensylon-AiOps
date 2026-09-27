"""
Union-Find (Disjoint Set Union) for candidate incident clustering.
Unions signals that share a strong edge (correlation_score >= threshold).

IMPORTANT: Union-Find proposes candidate groups only.
Candidates must still pass all four validation gates (PRD §4/G4).
"""
from app.config import get_correlation_cfg
from app.correlation.graph import EvidenceGraph


class UnionFind:
    """Path-compressed, union-by-rank disjoint set union. PRD §15."""

    def __init__(self, items: list[str]):
        self.parent: dict[str, str] = {x: x for x in items}
        self.rank: dict[str, int] = {x: 0 for x in items}

    def find(self, x: str) -> str:
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])   # path compression
        return self.parent[x]

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            self.parent[ra] = rb
        elif self.rank[ra] > self.rank[rb]:
            self.parent[rb] = ra
        else:
            self.parent[rb] = ra
            self.rank[ra] += 1


def build_candidate_clusters(
    graph: EvidenceGraph,
    threshold: float | None = None,
) -> list[list[str]]:
    """
    Run Union-Find over all strong edges in the graph.
    Returns a list of candidate clusters (each = list of signal IDs).
    These are CANDIDATES — they must still pass all validation gates.
    """
    cfg = get_correlation_cfg()
    t = threshold or cfg["strong_edge_threshold"]

    signal_ids = sorted(graph.signals.keys())
    uf = UnionFind(signal_ids)

    for edge in graph.get_strong_edges(t):
        uf.union(edge.source_signal, edge.target_signal)

    # Collect groups
    groups: dict[str, list[str]] = {}
    for sid in signal_ids:
        root = uf.find(sid)
        groups.setdefault(root, []).append(sid)

    return list(groups.values())
