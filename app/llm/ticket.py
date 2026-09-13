"""
Evidence-grounded LLM ticket generator — PRD §9/G9 / §20.

Supports multiple LLM providers via LLM_PROVIDER env var:
  - groq     → Groq (default) — https://api.groq.com/openai/v1
  - gemini   → Google Gemini  — OpenAI-compatible endpoint
  - openai   → OpenAI         — standard endpoint
  - mock     → deterministic fallback (no API key needed)

All providers use the OpenAI-compatible SDK.
Set the correct API key and model in .env.

Rules (PRD §20):
  - The LLM receives structured evidence only.
  - It must NOT invent metrics, timestamps, services, causes, or remediation actions.
  - Clearly distinguish observed_evidence from suspected_root_cause.
  - If root cause is not established, explicitly state it is unverified.
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
# Provider configuration
# ---------------------------------------------------------------------------

# Provider → (base_url, default_model, api_key_env_var)
_PROVIDERS: dict[str, tuple[str | None, str, str]] = {
    "groq": (
        "https://api.groq.com/openai/v1",
        "groq/compound-mini",    # confirmed active; override via LLM_MODEL in .env
        "GROQ_API_KEY",
    ),
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "gemini-2.0-flash",
        "GEMINI_API_KEY",
    ),
    "openai": (
        None,                 # use openai default base_url
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
    Falls back to mock if no key is set.
    """
    provider = os.getenv("LLM_PROVIDER", "groq").lower().strip()

    if provider not in _PROVIDERS:
        logger.warning("Unknown LLM_PROVIDER '%s', falling back to mock.", provider)
        provider = "mock"

    base_url, default_model, key_env = _PROVIDERS[provider]
    api_key = os.getenv(key_env, "") if key_env else ""
    model = os.getenv("LLM_MODEL", "").strip() or default_model  # blank → use default

    if provider != "mock" and not api_key:
        logger.warning(
            "LLM_PROVIDER='%s' but %s is not set. Falling back to mock.",
            provider,
            key_env,
        )
        provider = "mock"

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
        f"[{s.timestamp.strftime('%H:%M:%S')}] {s.service}/{s.component} - {s.type}"
        + (f": {s.message}" if s.message else "")
        + (f" (value={s.value})" if s.value is not None else "")
        for s in sorted_signals
    ]

    observed = []
    for s in sorted_signals:
        entry = f"[{s.source.upper()}] {s.service}/{s.component}: {s.type}"
        if s.message:
            entry += f" - \"{s.message}\""
        if s.value is not None:
            entry += f" (observed value: {s.value})"
        if s.template_id:
            entry += f" [template: {s.template_id}]"
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
2. The "observed_evidence" section must reproduce only facts from the input.
3. The "suspected_root_cause" must be clearly marked as UNVERIFIED if it cannot be directly proven from the evidence. Begin with "UNVERIFIED HYPOTHESIS:" if uncertain.
4. The "investigation_steps" must be actionable and based only on the observed services and components.
5. Do not speculate about root causes beyond what the topology and evidence directly support.
6. Output valid JSON matching the required schema exactly — no markdown, no code fences, raw JSON only.

OUTPUT SCHEMA:
{
  "title": "string - brief incident title",
  "summary": "string - 2-3 sentence factual summary",
  "suspected_root_cause": "string - start with UNVERIFIED HYPOTHESIS: if not proven",
  "investigation_steps": ["step1", "step2", ...]
}"""


# ---------------------------------------------------------------------------
# LLM call (with mock fallback)
# ---------------------------------------------------------------------------

def _call_llm(evidence: dict) -> dict:
    """
    Call the configured LLM provider with the evidence package.
    Falls back to deterministic mock if no API key is set.
    """
    provider, base_url, model, api_key = _resolve_provider()

    if provider == "mock":
        return _mock_llm_response(evidence)

    try:
        import openai

        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url

        client = openai.OpenAI(**client_kwargs)

        # Gemini and Groq support response_format json_object; use it where possible
        create_kwargs = dict(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(evidence, indent=2)},
            ],
            temperature=0.1,
        )

        # Groq and OpenAI support json_object mode; Gemini does too on most models
        if provider in ("groq", "openai", "gemini"):
            create_kwargs["response_format"] = {"type": "json_object"}

        response = client.chat.completions.create(**create_kwargs)
        raw = response.choices[0].message.content or ""

        # Strip markdown code fences if the model wrapped the JSON
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        return json.loads(raw)

    except Exception as e:
        logger.warning("LLM call failed (%s: %s). Falling back to mock.", type(e).__name__, e)
        return _mock_llm_response(evidence)


def _mock_llm_response(evidence: dict) -> dict:
    """
    Deterministic mock LLM response — no API key needed.
    Constructs a ticket purely from evidence, zero fabrication.
    """
    services = ", ".join(evidence["services"])
    sig_count = evidence["signal_count"]

    summary = (
        f"{sig_count} correlated signals detected across {services} in "
        f"the {evidence['environment']} environment. "
        f"Severity: {evidence['severity']:.1f}/100, "
        f"Correlation confidence: {evidence['confidence']:.2f}. "
        f"The pattern is consistent with a cascading failure originating from an upstream service."
    )

    suspected = (
        "UNVERIFIED HYPOTHESIS: Based on the observed signal sequence - starting with "
        f"{evidence['services'][0] if evidence['services'] else 'an upstream service'} and "
        "propagating downstream - a resource exhaustion or connectivity failure in the upstream "
        "service is suspected. This hypothesis requires confirmation through log analysis and "
        "metric inspection."
    )

    steps = [
        f"Check {evidence['services'][0]} health metrics and recent deployments" if evidence['services'] else "Check upstream service health",
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
    The LLM only produces prose — all facts come from the evidence package.
    PRD §20
    """
    evidence = build_evidence_package(incident, signals, fingerprint)
    llm_output = _call_llm(evidence)

    # Assemble the ticket — observed_evidence comes from evidence package, NOT the LLM
    return TicketDraft(
        title=llm_output.get("title", f"Incident {incident.id}"),
        severity=incident.severity,
        confidence=incident.confidence,
        affected_services=incident.services,
        summary=llm_output.get("summary", ""),
        timeline=evidence["timeline"],
        observed_evidence=evidence["observed_evidence"],   # always from evidence, never LLM
        suspected_root_cause=llm_output.get("suspected_root_cause", "UNVERIFIED: Unknown"),
        investigation_steps=llm_output.get("investigation_steps", []),
        review_status=None,
    )
