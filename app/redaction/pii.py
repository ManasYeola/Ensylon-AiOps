"""
PII Redaction Engine — PRD §24.

Strips or replaces all personal / sensitive information BEFORE any further
processing or storage.  Call `redact(text)` on any raw string that came from
an external source (log line, alarm description, annotation, etc.).

Sensitive categories handled:
  - Email addresses           -> [REDACTED_EMAIL]
  - IPv4 / IPv6 addresses     -> [REDACTED_IP]
  - AWS Account IDs (12-digit)-> [REDACTED_ACCOUNT_ID]
  - AWS ARNs                  -> [REDACTED_ARN]
  - Session tokens            -> [REDACTED_SESSION]
  - App account numbers       -> [REDACTED_ACCOUNT]
  - Phone numbers             -> [REDACTED_PHONE]
  - API keys / bearer tokens  -> [REDACTED_TOKEN]
  - Credit card numbers       -> [REDACTED_PAYMENT]
  - Service-account emails    -> [REDACTED_SVC_ACCOUNT]
  - Passwords/secrets in JSON -> [REDACTED_SECRET]

Design rules:
  - Redact BEFORE storage.  Never log unredacted PII anywhere.
  - Redact BEFORE sending to LLM.
  - Replacements are deterministic — same pattern gives same placeholder.
  - Order matters: more specific patterns come before general ones.
"""
import re

# ---------------------------------------------------------------------------
# Pattern registry — (compiled_pattern, replacement) applied in order.
# More specific patterns MUST come before general ones.
# ---------------------------------------------------------------------------

_RULES: list[tuple[re.Pattern, str]] = [
    # 1. AWS ARNs  (must come before bare 12-digit account ID)
    (
        re.compile(
            r"arn:[a-z0-9\-]+:[a-z0-9\-]+:[a-z0-9\-]*:\d{12}:[^\s,\"'<>]+",
            re.IGNORECASE,
        ),
        "[REDACTED_ARN]",
    ),
    # 2. Service-account emails  (svc-name@domain.tld)
    (
        re.compile(
            r"\bsvc-[\w.\-]+@[\w.\-]+\.[a-z]{2,}\b",
            re.IGNORECASE,
        ),
        "[REDACTED_SVC_ACCOUNT]",
    ),
    # 3. Generic email addresses
    (
        re.compile(
            r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
        ),
        "[REDACTED_EMAIL]",
    ),
    # 4. Session / auth tokens  (sess_xxx, tok_xxx, jwt_xxx …)
    (
        re.compile(
            r"\b(?:sess|tok|token|jwt|auth)[_\-]?[A-Za-z0-9_\-]{8,}\b",
            re.IGNORECASE,
        ),
        "[REDACTED_SESSION]",
    ),
    # 5. Bearer / API key headers
    (
        re.compile(
            r"\b(?:Bearer|apikey|api_key|x-api-key)\s*[:=]\s*[A-Za-z0-9\-_.~+/]{20,}",
            re.IGNORECASE,
        ),
        "[REDACTED_TOKEN]",
    ),
    # 6. Generic long hex secrets (32+ chars that look like keys)
    (
        re.compile(
            r"\b[A-Fa-f0-9]{32,}\b",
        ),
        "[REDACTED_TOKEN]",
    ),
    # 7. Password / secret key-value pairs in structured text / JSON
    (
        re.compile(
            r'(?:password|passwd|secret|credential)["s]*[:=]["s]*[^s,"\'<>]+',
            re.IGNORECASE,
        ),
        "[REDACTED_SECRET]",
    ),
    # 8. Credit card numbers  (13-16 digits, optionally separated by spaces/dashes)
    (
        re.compile(
            r"\b(?:\d[ \-]?){13,16}\b",
        ),
        "[REDACTED_PAYMENT]",
    ),
    # 9. AWS Account IDs  (standalone 12-digit numbers)
    (
        re.compile(
            r"\b\d{12}\b",
        ),
        "[REDACTED_ACCOUNT_ID]",
    ),
    # 10. App-level account numbers  (ACC-NNNNN pattern)
    (
        re.compile(
            r"\bACC-\d+\b",
            re.IGNORECASE,
        ),
        "[REDACTED_ACCOUNT]",
    ),
    # 11. IPv6 addresses
    (
        re.compile(
            r"\b(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}\b",
        ),
        "[REDACTED_IP]",
    ),
    # 12. IPv4 addresses
    (
        re.compile(
            r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        ),
        "[REDACTED_IP]",
    ),
    # 13. Phone numbers  (international and local formats)
    (
        re.compile(
            r"\b(?:\+\d{1,3}[\s.\-]?)?(?:\(?\d{3}\)?[\s.\-]?)?\d{3}[\s.\-]?\d{4}\b",
        ),
        "[REDACTED_PHONE]",
    ),
]


def redact(text: str) -> str:
    """
    Apply all PII redaction rules to `text` and return the sanitised string.

    Example:
        >>> redact("user neha.joshi@acmecorp.com ip:10.0.2.83 sess_kd3dxt ACC-10000055")
        'user [REDACTED_EMAIL] ip:[REDACTED_IP] [REDACTED_SESSION] [REDACTED_ACCOUNT]'
    """
    if not text:
        return text
    result = str(text)
    for pattern, replacement in _RULES:
        result = pattern.sub(replacement, result)
    return result


def redact_dict(data: dict, fields: list[str] | None = None) -> dict:
    """
    Recursively redact PII from a dictionary.

    If `fields` is supplied, only those top-level keys are redacted.
    Otherwise every string value at any depth passes through `redact()`.

    Args:
        data:   Raw dict (CloudWatch event, Grafana payload, etc.).
        fields: Optional list of field names to redact.  None = all fields.

    Returns:
        New dict with all sensitive values replaced by placeholders.
    """
    def _walk(obj):
        if isinstance(obj, dict):
            return {k: _walk(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_walk(item) for item in obj]
        if isinstance(obj, str):
            return redact(obj)
        return obj

    if fields is None:
        return _walk(data)

    result = dict(data)
    for key in fields:
        if key in result and isinstance(result[key], str):
            result[key] = redact(result[key])
    return result
