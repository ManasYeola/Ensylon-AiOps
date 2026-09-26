"""
Mock Jira integration + file persistence — PRD §22 / Challenge spec §C5.

Rules:
  - The Jira endpoint MUST reject requests unless the incident has an approved review state.
  - Upon approval, the ticket is written to output/tickets/<ticket_id>.json.
  - Ticket IDs follow the ENS-NNN pattern.
"""
import json
import logging
from datetime import datetime
from pathlib import Path

from app.models.ticket import TicketDraft
from app.review.review import is_approved

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Output directory — challenge spec requires output/tickets/
# ---------------------------------------------------------------------------

OUTPUT_DIR = Path(__file__).parent.parent.parent / "output" / "tickets"


def _ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class JiraError(Exception):
    pass


# In-memory store for mock tickets (also persisted to disk)
_tickets: list[dict] = []
_counter = 100


def publish_to_jira(draft: TicketDraft, incident_id: str | None = None) -> dict:
    """
    Publish an approved TicketDraft to Mock Jira.
    Raises JiraError if the draft has not been approved by a human reviewer.
    PRD §22 / Challenge spec §C5: only approved tickets can reach Jira.
    Also writes the ticket to output/tickets/<ticket_id>.json.
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
        "id":                   ticket_id,
        "incident_id":          incident_id,          # required for frontend matching
        "title":                draft.title,
        "severity":             draft.severity,
        "confidence":           draft.confidence,
        "affected_services":    draft.affected_services,
        "summary":              draft.summary,
        "timeline":             draft.timeline,
        "observed_evidence":    draft.observed_evidence,
        "suspected_root_cause": draft.suspected_root_cause,
        "investigation_steps":  draft.investigation_steps,
        "reviewed_by":          draft.edited_by,
        "status":               "Open",
        "published_at":         datetime.utcnow().isoformat() + "Z",
    }
    _tickets.append(ticket)

    # ---- Write to output/tickets/<ticket_id>.json (challenge requirement) ----
    try:
        _ensure_output_dir()
        out_path = OUTPUT_DIR / f"{ticket_id}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(ticket, f, indent=2, ensure_ascii=False)
        logger.info("Ticket written to %s", out_path)
    except Exception as e:
        logger.warning("Could not write ticket to disk: %s", e)

    return ticket


def get_mock_tickets() -> list[dict]:
    """Return all mock Jira tickets published so far."""
    return list(_tickets)
