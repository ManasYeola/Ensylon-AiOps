from pydantic import BaseModel, field_validator


class IncidentFingerprint(BaseModel):
    """
    Deterministic fingerprint of an accepted incident.
    Used for continuation matching — new signals arriving after the correlation
    window can attach to an existing incident if similarity is high enough.
    PRD §8 / §19
    """
    environment: str
    service_path: list[str]      # ordered list of services in causal chain
    components: list[str]
    topology: dict               # subgraph of topology that was traversed
    template_ids: list[str]      # Drain3 template IDs observed
    temporal_pattern: list[str]  # ISO timestamps of signal burst
    severity: float
    confidence: float

    @field_validator("template_ids", mode="before")
    @classmethod
    def coerce_template_ids(cls, v):
        if isinstance(v, (list, set, tuple)):
            return [str(x) for x in v]
        return v
