"""
Live Jira Cloud integration and fallback persistence.
Supports Atlassian Jira Cloud REST API (v2) with Basic Auth.
Configured via .env or dynamic settings:
  JIRA_URL = https://your-domain.atlassian.net
  JIRA_EMAIL = your-email@example.com
  JIRA_API_TOKEN = your-atlassian-api-token
  JIRA_PROJECT_KEY = KAN (or your project key)
  JIRA_ISSUE_TYPE = Bug (or Task / Incident)
"""
import os
import json
import logging
import base64
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any
import httpx

from app.models.ticket import TicketDraft
from app.review.review import is_approved
from app.jira.mock_jira import publish_to_jira as publish_to_mock, JiraError, OUTPUT_DIR, _ensure_output_dir

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


def get_jira_config() -> Dict[str, Any]:
    """Retrieve Jira Cloud configuration from environment."""
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)
    except Exception:
        pass

    url = os.getenv("JIRA_URL", "").strip().rstrip("/")
    email = os.getenv("JIRA_EMAIL", "").strip()
    token = os.getenv("JIRA_API_TOKEN", "").strip()
    project = os.getenv("JIRA_PROJECT_KEY", "").strip()
    issue_type = os.getenv("JIRA_ISSUE_TYPE", "Bug").strip()

    is_configured = bool(url and email and token and project)
    return {
        "is_configured": is_configured,
        "jira_url": url,
        "jira_email": email,
        "jira_project_key": project,
        "jira_issue_type": issue_type,
        "has_token": bool(token),
    }


def format_jira_description(draft: TicketDraft, incident_id: Optional[str] = None) -> str:
    """Format structured TicketDraft into clean Jira markup description."""
    lines = [
        "h2. Incident Summary",
        draft.summary or "No summary provided.",
        "",
        "h2. Suspected Root Cause",
        draft.suspected_root_cause or "Under investigation.",
        "",
    ]

    if draft.observed_evidence:
        lines.append("h2. Observed Evidence")
        for ev in draft.observed_evidence:
            lines.append(f"* {ev}")
        lines.append("")

    if draft.investigation_steps:
        lines.append("h2. Recommended Runbook & Investigation Steps")
        for idx, step in enumerate(draft.investigation_steps, 1):
            lines.append(f"# {step}")
        lines.append("")

    if draft.timeline:
        lines.append("h2. Signal Timeline (IST)")
        for item in draft.timeline:
            lines.append(f"* {item}")
        lines.append("")

    now_ist = datetime.now(timezone.utc).astimezone(IST)
    lines.extend([
        "h2. AIOps Metadata",
        f"* *Incident ID*: {incident_id or 'N/A'}",
        f"* *Severity Score*: {draft.severity}",
        f"* *Confidence*: {draft.confidence}",
        f"* *Affected Services*: {', '.join(draft.affected_services) if draft.affected_services else 'None'}",
        f"* *Reviewed By*: {draft.edited_by or 'AI-Ops System'}",
        f"* *Generated At*: {now_ist.strftime('%Y-%m-%d %I:%M:%S %p IST')}",
    ])

    return "\n".join(lines)


def publish_to_jira(draft: TicketDraft, incident_id: Optional[str] = None) -> dict:
    """
    Publish an approved TicketDraft to Live Atlassian Jira Cloud if configured,
    otherwise fallback to local Mock Jira store.
    """
    if not is_approved(draft):
        raise JiraError(
            f"Cannot publish to Jira: ticket review_status='{draft.review_status}'. "
            "Human approval is required before publication (PRD §22)."
        )

    config = get_jira_config()

    # If Live Jira is configured, send to Atlassian REST API
    if config["is_configured"]:
        return _publish_to_atlassian_jira(draft, incident_id, config)

    # Fallback to Mock Jira
    ticket = publish_to_mock(draft, incident_id=incident_id)
    ticket["is_real_jira"] = False
    ticket["url"] = None
    ticket["message"] = (
        "Saved to local Jira store. Configure JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN, "
        "and JIRA_PROJECT_KEY in .env to publish live to Atlassian Jira Cloud."
    )
    return ticket


def _publish_to_atlassian_jira(draft: TicketDraft, incident_id: Optional[str], config: Dict[str, Any]) -> dict:
    """Make HTTP POST to Atlassian Jira Cloud REST API v2."""
    jira_url = config["jira_url"]
    email = config["jira_email"]
    token = os.getenv("JIRA_API_TOKEN", "")
    project_key = config["jira_project_key"]
    issue_type_name = config.get("jira_issue_type") or "Task"

    auth_str = f"{email}:{token}"
    auth_bytes = base64.b64encode(auth_str.encode("utf-8")).decode("ascii")

    headers = {
        "Authorization": f"Basic {auth_bytes}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    description_text = format_jira_description(draft, incident_id)

    # Sanitize title for Jira summary (max 255 chars)
    summary = (draft.title or f"Incident {incident_id}")[:250]

    payload = {
        "fields": {
            "project": {
                "key": project_key,
            },
            "summary": summary,
            "description": description_text,
            "issuetype": {
                "name": issue_type_name,
            },
            "labels": [
                "ensylon-aiops",
                "automated-incident",
                *[s.replace(" ", "-") for s in (draft.affected_services or [])[:5]],
            ],
        }
    }

    url = f"{jira_url}/rest/api/2/issue"
    logger.info("Publishing ticket to Jira Cloud at %s ...", url)

    with httpx.Client(timeout=15.0) as client:
        resp = client.post(url, headers=headers, json=payload)

        # If issue type rejected, query project valid issue types and retry automatically
        if resp.status_code not in (200, 201) and ("issuetype" in resp.text.lower() or "issue type" in resp.text.lower()):
            try:
                proj_resp = client.get(f"{jira_url}/rest/api/2/project/{project_key}", headers=headers)
                if proj_resp.status_code == 200:
                    available_types = [it["name"] for it in proj_resp.json().get("issueTypes", []) if not it.get("subtask")]
                    for fallback_type in ["Task", "Story", "Incident", "Bug"] + available_types:
                        if fallback_type in available_types and fallback_type != issue_type_name:
                            logger.info("Retrying Jira ticket with valid project issue type '%s'...", fallback_type)
                            payload["fields"]["issuetype"]["name"] = fallback_type
                            retry_resp = client.post(url, headers=headers, json=payload)
                            if retry_resp.status_code in (200, 201):
                                resp = retry_resp
                                break
            except Exception as retry_err:
                logger.warning("Issue type fallback failed: %s", retry_err)

        if resp.status_code not in (200, 201):
            error_detail = resp.text
            try:
                err_json = resp.json()
                if "errorMessages" in err_json and err_json["errorMessages"]:
                    error_detail = "; ".join(err_json["errorMessages"])
                elif "errors" in err_json:
                    error_detail = json.dumps(err_json["errors"])
            except Exception:
                pass
            raise JiraError(f"Jira API error ({resp.status_code}): {error_detail}")

        data = resp.json()
        issue_key = data.get("key")
        issue_id = data.get("id")
        issue_url = f"{jira_url}/browse/{issue_key}"

        ticket = {
            "id": issue_key,
            "jira_id": issue_id,
            "incident_id": incident_id,
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
            "published_at": datetime.utcnow().isoformat() + "Z",
            "is_real_jira": True,
            "url": issue_url,
        }

        # Also persist to output/tickets
        try:
            _ensure_output_dir()
            out_path = OUTPUT_DIR / f"{issue_key}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(ticket, f, indent=2, ensure_ascii=False)
            logger.info("Live Jira ticket persisted locally to %s", out_path)
        except Exception as e:
            logger.warning("Could not persist ticket to disk: %s", e)

        return ticket
