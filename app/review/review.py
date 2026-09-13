"""
Human review workflow — PRD §10/G10 / §21.

Workflow:
    LLM Draft → Human Reviewer → Approve / Edit / Reject → Jira

There must be NO automatic publishing. Only an approved ticket can reach Jira (PRD §10/G10).

Allowed actions: approve | edit | reject
"""
from datetime import datetime
from app.models.ticket import TicketDraft


class ReviewError(Exception):
    pass


def review_ticket(
    draft: TicketDraft,
    action: str,
    edited_draft: dict | None = None,
    reviewer: str = "human",
) -> TicketDraft:
    """
    Apply a review decision to a TicketDraft.

    action must be one of: "approve" | "edit" | "reject"
    For "edit", edited_draft must contain the fields to update.
    Returns the updated TicketDraft.
    """
    action = action.lower().strip()
    allowed = {"approve", "edit", "reject"}

    if action not in allowed:
        raise ReviewError(f"Invalid action '{action}'. Must be one of: {allowed}")

    if action == "approve":
        return draft.model_copy(update={
            "review_status": "approved",
            "edited_by": reviewer,
        })

    elif action == "edit":
        if not edited_draft:
            raise ReviewError("action='edit' requires edited_draft to contain field updates")
        updates = {k: v for k, v in edited_draft.items() if k in TicketDraft.model_fields}
        updates["review_status"] = "approved"
        updates["edited_by"] = reviewer
        return draft.model_copy(update=updates)

    elif action == "reject":
        return draft.model_copy(update={
            "review_status": "rejected",
            "edited_by": reviewer,
        })


def is_approved(draft: TicketDraft) -> bool:
    """Returns True only if a human has explicitly approved the draft."""
    return draft.review_status == "approved"
