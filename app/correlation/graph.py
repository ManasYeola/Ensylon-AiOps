"""
Evidence Graph — nodes are Signals, edges are EvidenceEdges.
The graph is the core data structure for all downstream correlation logic.
PRD §3/G3
"""
from app.models.signal import Signal
from app.models.edge import EvidenceEdge
from app.config import get_correlation_cfg
from app.correlation.scoring import correlation_score


class EvidenceGraph:
    """
    Directed weighted graph of anomaly signals.
    Only pairs within the correlation time window are candidates.
    """

    def __init__(self, signals: list[Signal]):
        self.signals: dict[str, Signal] = {s.id: s for s in signals}
        self.edges: list[EvidenceEdge] = []
        self._adj: dict[str, dict[str, EvidenceEdge]] = {s.id: {} for s in signals}

    def build(self) -> None:
        """
        Score all pairs within the correlation window and add edges.
        Note: 5-minute window generates candidates; evidence decides membership (PRD §3/G3).
        """
        cfg = get_correlation_cfg()
        window_sec = cfg["window_minutes"] * 60
        signal_list = list(self.signals.values())

        for i in range(len(signal_list)):
            for j in range(i + 1, len(signal_list)):
                a, b = signal_list[i], signal_list[j]
                delta = abs((a.timestamp - b.timestamp).total_seconds())
                if delta > window_sec:
                    continue   # outside time window — not even a candidate

                edge = correlation_score(a, b)
                self.edges.append(edge)
                self._adj[a.id][b.id] = edge
                self._adj[b.id][a.id] = edge

    def get_edge(self, sig_a: str, sig_b: str) -> EvidenceEdge | None:
        return self._adj.get(sig_a, {}).get(sig_b)

    def get_strong_edges(self, threshold: float | None = None) -> list[EvidenceEdge]:
        """Return all edges whose correlation_score >= threshold."""
        cfg = get_correlation_cfg()
        t = threshold or cfg["strong_edge_threshold"]
        return [e for e in self.edges if e.correlation_score >= t]

    def get_neighbors(self, signal_id: str) -> dict[str, EvidenceEdge]:
        return self._adj.get(signal_id, {})

    def edges_within_cluster(self, signal_ids: list[str]) -> list[EvidenceEdge]:
        """Return all internal edges for a set of signal IDs."""
        id_set = set(signal_ids)
        return [
            e for e in self.edges
            if e.source_signal in id_set and e.target_signal in id_set
        ]
