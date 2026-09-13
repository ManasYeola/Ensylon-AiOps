from pydantic import BaseModel
from typing import Optional


class TicketDraft(BaseModel):
    """
    Structured Jira ticket draft produced by the LLM from incident evidence.
    The LLM must only use supplied evidence — never invent metrics, timestamps,
    services, causes, or remediation actions.
    PRD §8 / §20
    """
    title: str
    severity: float
    confidence: float
    affected_services: list[str]
    summary: str
    timeline: list[str]

    # Strictly observed facts — must not be altered by LLM
    observed_evidence: list[str]

    # LLM hypothesis — clearly marked as unverified if root cause not established
    suspected_root_cause: str

    investigation_steps: list[str]

    # Review state — human must set to "approved" before Jira publication (PRD §21)
    review_status: Optional[str] = None   # None | "approved" | "rejected"
    edited_by: Optional[str] = None
