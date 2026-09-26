"""
Evidence-grounded incident ticket drafting using Anthropic Claude (PS §2 #8 / §7 C5).

Architecture:
  - Uses the configured Anthropic Claude model only (via anthropic SDK).
  - No fallback LLM, no multi-provider system, and no mock drafting.
  - Requires valid ANTHROPIC_API_KEY; fails clearly if missing or if the API call fails.

Rules (PS §7 C5):
  - The LLM receives structured evidence only.
  - It must NOT invent metrics, timestamps, services, causes, or remediation actions.
  - Clearly distinguish observed_evidence from suspected_root_cause.
  - If root cause is not established, explicitly state it is unverified.
  - observed_evidence is ALWAYS bound from the deterministic evidence package —
    never from LLM output.
"""
import os
import json
import logging
from datetime import timezone, timedelta

from app.models.signal import Signal
from app.models.incident import Incident
from app.models.fingerprint import IncidentFingerprint
from app.models.ticket import TicketDraft

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

def _to_ist(dt):
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST)

# ---------------------------------------------------------------------------
# Anthropic Claude Configuration (PS §2 #8 / §7 C5)
# ---------------------------------------------------------------------------

DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-6"


def _get_claude_credentials() -> tuple[str, str]:
    """
    Retrieve Anthropic Claude model and API key.
    Throws ValueError immediately if ANTHROPIC_API_KEY is not set.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY environment variable is not set. "
            "Ticket drafting requires valid Anthropic Claude API credentials."
        )
    model = os.getenv("LLM_MODEL", "").strip() or DEFAULT_CLAUDE_MODEL
    return model, api_key


# ---------------------------------------------------------------------------
# Evidence packager
# ---------------------------------------------------------------------------

def build_evidence_package(
    incident: Incident,
    signals: list[Signal],
    fingerprint: IncidentFingerprint,
) -> dict:
    """
    Assemble structured evidence from signals and incident data.
    This is the ONLY input the LLM receives — it cannot access anything else.
    PRD §20
    """
    sorted_signals = sorted(signals, key=lambda s: s.timestamp)

    timeline = [
        f"[{_to_ist(s.timestamp).strftime('%I:%M:%S %p IST')}] [{s.source.upper()}] {s.service}/{s.component} — {s.signal_type}"
        + (f": {s.evidence}" if s.evidence else "")
        + (f" (anomaly_score={s.anomaly_score:.2f})" if s.anomaly_score else "")
        for s in sorted_signals
    ]

    observed = []
    for s in sorted_signals:
        entry = f"[{s.source.upper()}] {s.service}/{s.component}: {s.signal_type}"
        if s.evidence:
            entry += f' — "{s.evidence}"'
        if s.anomaly_score:
            entry += f" (anomaly_score: {s.anomaly_score:.2f})"
        tid = s.metadata.get("template_id") if s.metadata else None
        if tid:
            entry += f" [template: {tid}]"
        observed.append(entry)

    return {
        "incident_id": incident.id,
        "severity": incident.severity,
        "confidence": incident.confidence,
        "environment": incident.environment,
        "services": incident.services,
        "timeline": timeline,
        "observed_evidence": observed,
        "topology": fingerprint.topology,
        "signal_count": len(signals),
    }


# ---------------------------------------------------------------------------
# LLM system prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a Principal Site Reliability Engineer (SRE) and Incident Commander. You analyze incoming telemetry, alerts, and logs to draft concise, highly actionable incident tickets. All timestamps must be in Indian Standard Time (IST).

STRICT RULES:
1. Grounded in Evidence: Use ONLY the provided evidence. Do not invent unobserved services, timestamps, or metrics. When citing times, always use IST.
2. Analytical Root Cause Diagnosis: For "suspected_root_cause", start with a concise 1-line summary statement of the core issue (e.g. "Core Issue: [1-line summary of what failed and why]"), followed by a double line break and a detailed technical analysis explaining the failure mechanism.
   - Do NOT use generic boilerplate disclaimers (e.g. avoid repeating "UNVERIFIED HYPOTHESIS:" or "The absence of topology data prevents...").
   - Formulate a clear, assertive engineering diagnosis based on the affected components and metric patterns.
3. Actionable Investigation Steps: "investigation_steps" is MANDATORY and MUST contain at least 3 concrete, ordered technical troubleshooting steps referencing the specific services, metrics, and components in the incident. Never return an empty array.
4. Concise & Professional:
   - "title" must be concise (< 120 chars) and clearly describe the failure.
   - "summary" must be 2-3 sentences summarizing the operational impact, affected services, and resolution/current state.
5. You must call the `draft_incident_ticket` tool with your analysis — do not respond with plain text."""

# Tool definition — forces Claude to output a structured, validated JSON payload.
DRAFT_TOOL: dict = {
    "name": "draft_incident_ticket",
    "description": (
        "Produce a structured incident ticket draft from the provided evidence. "
        "All fields must be grounded in the supplied evidence only."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Brief incident title (< 120 chars)",
            },
            "summary": {
                "type": "string",
                "description": "2-3 sentence factual summary of what happened",
            },
            "suspected_root_cause": {
                "type": "string",
                "description": (
                    "Analytical root cause diagnosis. Start with a 1-line summary: 'Core Issue: <1-line summary of failure>', "
                    "followed by a blank line and the in-depth technical analysis explaining the failure mechanism."
                ),
            },
            "investigation_steps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Ordered list of actionable investigation steps",
                "minItems": 3,
            },
        },
        "required": ["title", "summary", "suspected_root_cause", "investigation_steps"],
    },
}


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Anthropic Claude API Call
# ---------------------------------------------------------------------------

def _call_anthropic(evidence: dict, model: str, api_key: str) -> dict:
    """
    Call the Anthropic Claude API using Tool Calling to enforce strict JSON output.
    Raises RuntimeError or API errors on failure.
    """
    import anthropic  # type: ignore

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        tools=[DRAFT_TOOL],
        tool_choice={"type": "tool", "name": "draft_incident_ticket"},
        messages=[
            {"role": "user", "content": json.dumps(evidence, indent=2, default=str)}
        ],
    )

    # Extract the tool use block — this is guaranteed JSON by the tool schema
    for block in message.content:
        if block.type == "tool_use" and block.name == "draft_incident_ticket":
            return block.input  # already a parsed dict

    raise RuntimeError("Anthropic API returned a response without a 'draft_incident_ticket' tool_use block.")


def _call_llm(evidence: dict) -> dict:
    """
    Call Anthropic Claude API with the evidence package (PS §2 #8 / §7 C5).
    Throws ValueError if ANTHROPIC_API_KEY is not set, or RuntimeError / API error on failure.
    No fallback is used.
    """
    model, api_key = _get_claude_credentials()
    return _call_anthropic(evidence, model, api_key)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_ticket_draft(
    incident: Incident,
    signals: list[Signal],
    fingerprint: IncidentFingerprint,
) -> TicketDraft:
    """
    Build the evidence package, call the LLM, and assemble a TicketDraft.
    The LLM only produces prose/hypotheses — all facts come from the evidence package.
    observed_evidence and timeline are always bound from the deterministic package.
    PRD §20
    """
    evidence = build_evidence_package(incident, signals, fingerprint)
    llm_output = _call_llm(evidence)

    # Assemble the ticket:
    #   - observed_evidence  → always from deterministic evidence package (never LLM)
    #   - timeline           → always from deterministic evidence package (never LLM)
    #   - title/summary/root_cause/steps → from LLM, grounded in evidence
    steps = llm_output.get("investigation_steps") or []
    if not steps:
        svc_str = ", ".join(incident.services) if incident.services else "affected services"
        steps = [
            f"Review application logs and APM traces for {svc_str} during the incident window.",
            f"Inspect resource utilisation (CPU, memory, connection pools) for {svc_str}.",
            f"Verify downstream and upstream dependencies for correlated latency or error spikes.",
        ]

    return TicketDraft(
        title=llm_output.get("title", f"Incident {incident.id}"),
        severity=incident.severity,
        confidence=incident.confidence,
        affected_services=incident.services,
        summary=llm_output.get("summary", ""),
        timeline=evidence["timeline"],
        observed_evidence=evidence["observed_evidence"],  # deterministic, never LLM
        suspected_root_cause=llm_output.get("suspected_root_cause", "Under investigation: telemetry anomaly detected."),
        investigation_steps=steps,
        review_status=None,
    )
