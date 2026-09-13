"""
Mock Jira integration — PRD §22.

The Jira endpoint MUST reject requests unless the incident has an approved review state.
Ticket IDs follow the ENS-NNN pattern.
"""
from app.models.ticket import TicketDraft
from app.review.review import is_approved


class JiraError(Exception):
    pass


# In-memory store for mock tickets
_tickets: list[dict] = []
_counter = 100


def publish_to_jira(draft: TicketDraft) -> dict:
    """
    Publish an approved TicketDraft to Mock Jira.
    Raises JiraError if the draft has not been approved by a human reviewer.
    PRD §22: only approved tickets can reach Jira.
    """
    global _counter

    if not is_approved(draft):
        raise JiraError(
            f"Cannot publish to Jira: ticket review_status='{draft.review_status}'. "
            "Human approval is required before publication."
        )

    _counter += 1
    ticket_id = f"ENS-{_counter}"

    ticket = {
        "id": ticket_id,
        "title": draft.title,
        "severity": draft.severity,
        "confidence": draft.confidence,
        "affected_services": draft.affected_services,
        "summary": draft.summary,
        "timeline": draft.timeline,
        "observed_evidence": draft.observed_evidence,
        "suspected_root_cause": draft.suspected_root_cause,
        "investigation_steps": draft.investigation_steps,
        "reviewed_by": draft.edited_by,
        "status": "Open",
    }
    _tickets.append(ticket)
    return ticket


def get_mock_tickets() -> list[dict]:
    """Return all mock Jira tickets published so far."""
    return list(_tickets)
