"""
PII Redaction Engine — PRD §24 & Problem Statement Section 2/3.

Strips or replaces all personal / sensitive information BEFORE any further
processing or storage. Call `redact_text(text)` or `redact_dict(data)` on
any raw string or payload from external monitoring streams.

Sensitive categories handled:
  - AWS ARNs                  -> [REDACTED_ARN]
  - Service-account emails    -> [REDACTED_SVC_ACCOUNT]
  - Customer emails           -> [REDACTED_EMAIL]
  - Session tokens            -> [REDACTED_SESSION]
  - Bearer / API keys         -> [REDACTED_TOKEN]
  - Credit card numbers       -> [REDACTED_PAYMENT]
  - Standalone Account IDs    -> [REDACTED_ACCOUNT_ID]
  - App account numbers       -> [REDACTED_ACCOUNT]
  - Customer personal names   -> [REDACTED_NAME]
  - IPv6 addresses            -> [REDACTED_IP]
  - IPv4 addresses            -> [REDACTED_IP]
  - Phone numbers             -> [REDACTED_PHONE]
"""
import re
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Pattern registry — (compiled_pattern, replacement) applied in order.
# More specific patterns MUST come before general ones.
# ---------------------------------------------------------------------------

_RULES: list[tuple[re.Pattern, str]] = [
    # 1. AWS ARNs (must come before bare 12-digit account ID)
    (
        re.compile(
            r"arn:[a-z0-9\-]+:[a-z0-9\-]+:[a-z0-9\-]*:\d{12}:[^\s,\"'<>]+",
            re.IGNORECASE,
        ),
        "[REDACTED_ARN]",
    ),
    # 2. Service-account emails (svc-name@domain.tld)
    (
        re.compile(
            r"\bsvc-[\w.\-]+@[\w.\-]+\.[a-z]{2,}\b",
            re.IGNORECASE,
        ),
        "[REDACTED_SVC_ACCOUNT]",
    ),
    # 3. Generic customer/user email addresses
    (
        re.compile(
            r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
        ),
        "[REDACTED_EMAIL]",
    ),
    # 4. Session / auth tokens (sess_xxx, tok_xxx, jwt_xxx, etc.)
    (
        re.compile(
            r"\b(?:sess|tok|token|jwt|auth)[_\-][A-Za-z0-9_\-]{4,}\b",
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
    # 6. Generic long hex secrets (32+ chars)
    (
        re.compile(
            r"\b[A-Fa-f0-9]{32,}\b",
        ),
        "[REDACTED_TOKEN]",
    ),
    # 7. Password / secret key-value pairs
    (
        re.compile(
            r'(?:password|passwd|secret|credential)["\s]*[:=]["\s]*[^\s,"\'<>]+',
            re.IGNORECASE,
        ),
        "[REDACTED_SECRET]",
    ),
    # 8. Credit card numbers (13-16 digits)
    (
        re.compile(
            r"\b(?:\d[ \-]?){13,16}\b",
        ),
        "[REDACTED_PAYMENT]",
    ),
    # 9. AWS Account IDs (standalone 12-digit numbers)
    (
        re.compile(
            r"\b\d{12}\b",
        ),
        "[REDACTED_ACCOUNT_ID]",
    ),
    # 10. App-level account numbers (ACC-NNNNN pattern)
    (
        re.compile(
            r"\bACC-\d+\b",
            re.IGNORECASE,
        ),
        "[REDACTED_ACCOUNT]",
    ),
    # 11. Customer personal full names (e.g. "Last affected user: John Doe")
    (
        re.compile(
            r"(\b(?:user|customer|name|affected user)\s*[:=]\s*)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b",
            re.IGNORECASE,
        ),
        r"\g<1>[REDACTED_NAME]",
    ),
    # 12. IPv6 addresses
    (
        re.compile(
            r"\b(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}\b",
        ),
        "[REDACTED_IP]",
    ),
    # 13. IPv4 addresses
    (
        re.compile(
            r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        ),
        "[REDACTED_IP]",
    ),
    # 14. Phone numbers
    (
        re.compile(
            r"\b(?:\+\d{1,3}[\s.\-]?)?(?:\(?\d{3}\)?[\s.\-]?)?\d{3}[\s.\-]?\d{4}\b",
        ),
        "[REDACTED_PHONE]",
    ),
]


def redact_text(text: str) -> str:
    """
    Apply all PII redaction rules to text and return the sanitized string.
    """
    if not text:
        return text
    result = str(text)
    for pattern, replacement in _RULES:
        result = pattern.sub(replacement, result)
    return result


# Standard alias
redact = redact_text


def redact_dict(data: Any, fields: Optional[List[str]] = None) -> Any:
    """
    Recursively redact PII from a dictionary, list, or primitive value.
    If fields is supplied, only those top-level keys in dictionaries are redacted.
    Otherwise every string value at any depth passes through redact_text.
    """
    def _walk(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: _walk(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_walk(item) for item in obj]
        if isinstance(obj, str):
            return redact_text(obj)
        return obj

    if not isinstance(data, dict):
        return _walk(data)

    if fields is None:
        return _walk(data)

    result = dict(data)
    for key in fields:
        if key in result and isinstance(result[key], str):
            result[key] = redact_text(result[key])
    return result
