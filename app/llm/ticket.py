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

from app.models.signal import Signal
from app.models.incident import Incident
from app.models.fingerprint import IncidentFingerprint
from app.models.ticket import TicketDraft

logger = logging.getLogger(__name__)

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
        f"[{s.timestamp.strftime('%H:%M:%S')}] [{s.source.upper()}] {s.service}/{s.component} — {s.signal_type}"
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

SYSTEM_PROMPT = """You are an SRE incident analyst. You will receive structured incident evidence.

STRICT RULES:
1. Use ONLY the evidence provided. Do not invent metrics, timestamps, services, causes, or remediation steps.
2. The "suspected_root_cause" must be clearly marked as UNVERIFIED if it cannot be directly proven from the evidence. Begin with "UNVERIFIED HYPOTHESIS:" if uncertain.
3. The "investigation_steps" must be actionable and reference only the observed services and components.
4. Do not speculate beyond what the topology and signal evidence directly support.
5. "title" must be concise (< 120 chars). "summary" must be 2-3 sentences of factual prose.
6. You must call the `draft_incident_ticket` tool with your analysis — do not respond with plain text."""

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
                    "Hypothesised root cause. Must begin with 'UNVERIFIED HYPOTHESIS:' "
                    "if not directly proven by the evidence."
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
    return TicketDraft(
        title=llm_output.get("title", f"Incident {incident.id}"),
        severity=incident.severity,
        confidence=incident.confidence,
        affected_services=incident.services,
        summary=llm_output.get("summary", ""),
        timeline=evidence["timeline"],
        observed_evidence=evidence["observed_evidence"],  # deterministic, never LLM
        suspected_root_cause=llm_output.get("suspected_root_cause", "UNVERIFIED: Unknown"),
        investigation_steps=llm_output.get("investigation_steps", []),
        review_status=None,
    )
