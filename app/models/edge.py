from pydantic import BaseModel


class EvidenceEdge(BaseModel):
    """
    Weighted edge between two Signal nodes in the Evidence Graph.
    Each dimension is scored independently; correlation_score is the weighted sum.
    PRD §8 / §13
    """
    source_signal: str
    target_signal: str

    # Individual dimension scores (0.0 – 1.0 each)
    temporal: float
    service: float
    component: float
    topology: float
    evidence_similarity: float

    # Weighted composite score — PRD formula:
    # C = 0.25*T + 0.25*S + 0.15*C + 0.20*D + 0.15*E
    correlation_score: float
