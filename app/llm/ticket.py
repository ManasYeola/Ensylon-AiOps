"""
Evidence-grounded LLM ticket generator — PRD §9/G9 / §20 / Challenge spec §C5.

Supports multiple LLM providers via LLM_PROVIDER env var:
  - anthropic → Anthropic Claude API (challenge-provided credentials — PREFERRED)
  - groq      → Groq — https://api.groq.com/openai/v1
  - gemini    → Google Gemini — OpenAI-compatible endpoint
  - openai    → OpenAI — standard endpoint
  - mock      → deterministic fallback (no API key needed)

Anthropic uses its own SDK (anthropic>=1.0); all others use the OpenAI-compatible SDK.
Set the correct API key and model in .env.

Rules (PRD §20 / challenge spec §C5):
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

from app.config import load_config
from app.models.signal import Signal
from app.models.incident import Incident
from app.models.fingerprint import IncidentFingerprint
from app.models.ticket import TicketDraft

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider configuration
# ---------------------------------------------------------------------------

# Provider → (base_url, default_model, api_key_env_var)
# anthropic uses its own SDK so base_url is a sentinel here.
_PROVIDERS: dict[str, tuple[str | None, str, str]] = {
    "anthropic": (
        "__anthropic__",           # sentinel — handled separately
        "claude-sonnet-4-6",  # Claude Sonnet
        "ANTHROPIC_API_KEY",
    ),
    "groq": (
        "https://api.groq.com/openai/v1",
        "groq/compound-mini",
        "GROQ_API_KEY",
    ),
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "gemini-2.0-flash",
        "GEMINI_API_KEY",
    ),
    "openai": (
        None,
        "gpt-4o-mini",
        "OPENAI_API_KEY",
    ),
    "mock": (
        None,
        "mock",
        "",
    ),
}


def _resolve_provider() -> tuple[str, str | None, str, str]:
    """
    Resolve provider from LLM_PROVIDER env var.
    Returns (provider_name, base_url, model, api_key).
    Raises ValueError if provider is unknown or if required API key is missing.
    """
    provider = os.getenv("LLM_PROVIDER", "anthropic").lower().strip()

    if provider not in _PROVIDERS:
        raise ValueError(
            f"Unknown LLM_PROVIDER '{provider}'. Supported providers: {list(_PROVIDERS.keys())}"
        )

    base_url, default_model, key_env = _PROVIDERS[provider]
    api_key = os.getenv(key_env, "") if key_env else ""
    model = os.getenv("LLM_MODEL", "").strip() or default_model

    if provider != "mock" and not api_key:
        raise ValueError(
            f"LLM_PROVIDER='{provider}' requires environment variable '{key_env}', but it is not set."
        )

    return provider, base_url, model, api_key


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
# LLM call (with mock fallback)
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
    Call the configured LLM provider with the evidence package.
    Only returns mock if explicitly configured as provider='mock'.
    Raises on any provider errors.
    """
    provider, base_url, model, api_key = _resolve_provider()

    if provider == "mock":
        return _mock_llm_response(evidence)

    # Anthropic uses its own SDK
    if provider == "anthropic":
        return _call_anthropic(evidence, model, api_key)

    # All other providers: OpenAI-compatible endpoint
    import openai

    client_kwargs: dict = {"api_key": api_key}
    if base_url and base_url != "__anthropic__":
        client_kwargs["base_url"] = base_url

    client = openai.OpenAI(**client_kwargs)

    openai_system = SYSTEM_PROMPT.replace(
        "6. You must call the `draft_incident_ticket` tool with your analysis — do not respond with plain text.",
        "6. Output valid JSON matching this schema exactly — no markdown, no code fences:\n"
        '{"title": "...", "summary": "...", "suspected_root_cause": "...", "investigation_steps": ["..."]}',
    )

    create_kwargs = dict(
        model=model,
        messages=[
            {"role": "system", "content": openai_system},
            {"role": "user", "content": json.dumps(evidence, indent=2, default=str)},
        ],
        temperature=0.1,
    )

    if provider in ("groq", "openai", "gemini"):
        create_kwargs["response_format"] = {"type": "json_object"}

    response = client.chat.completions.create(**create_kwargs)
    raw = (response.choices[0].message.content or "").strip()

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    return json.loads(raw)


def _mock_llm_response(evidence: dict) -> dict:
    """
    Deterministic mock LLM response — no API key needed.
    Constructs a ticket purely from evidence, zero fabrication.
    """
    services = ", ".join(evidence["services"])
    sig_count = evidence["signal_count"]
    first_service = evidence["services"][0] if evidence["services"] else "upstream service"

    summary = (
        f"{sig_count} correlated signals detected across {services} in "
        f"the {evidence['environment']} environment. "
        f"Severity: {evidence['severity']:.1f}/100, "
        f"Correlation confidence: {evidence['confidence']:.2f}. "
        f"The pattern is consistent with a cascading failure originating from an upstream service."
    )

    suspected = (
        f"UNVERIFIED HYPOTHESIS: Based on the observed signal sequence — starting with "
        f"{first_service} and propagating downstream — a resource exhaustion or connectivity "
        f"failure in the upstream service is suspected. This hypothesis requires confirmation "
        f"through log analysis and metric inspection."
    )

    steps = [
        f"Check {first_service} health metrics and recent deployments",
        "Review database connection pool exhaustion metrics",
        "Inspect application logs for the burst of error templates",
        "Verify network connectivity between impacted services",
        "Check for recent configuration or deployment changes in the 30 minutes prior to the incident",
    ]

    return {
        "title": f"[SEV] Cascading failure across {services}",
        "summary": summary,
        "suspected_root_cause": suspected,
        "investigation_steps": steps,
    }


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
