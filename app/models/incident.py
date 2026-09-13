from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class Incident(BaseModel):
    """
    Accepted incident — produced after passing all four validation gates.
    PRD §8
    """
    id: str
    signal_ids: list[str]

    environment: str
    services: list[str]

    severity: float          # 0–100
    confidence: float        # 0.00–1.00

    status: str = "open"     # open | reviewing | resolved

    fingerprint_id: Optional[str] = None

    # Gate results — exposed for UI transparency (PRD §16)
    gate_results: Optional[dict] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
