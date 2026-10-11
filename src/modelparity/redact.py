"""Redaction and secret-scanning utilities for ModelParity.

Ensures that API keys, bearer tokens, and other sensitive data are never
written to run artifacts, reports, or log output.

Design goals
------------
* Strip ``Authorization`` headers completely (replace value with ``[REDACTED]``).
* Remove ``api_key`` / ``key`` query parameters from URLs.
* Remove user-info (``user:pass@``) from URLs.
* Scan free-text strings for known secret patterns (Bearer tokens, sk-* keys).
* Preserve all non-sensitive headers unchanged.
"""

from __future__ import annotations

import re
from urllib.parse import urlencode, urlparse, urlunparse, parse_qs

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REDACTED = "[REDACTED]"

#: Header names that must always be fully redacted (case-insensitive).
_SENSITIVE_HEADERS: frozenset[str] = frozenset(
    {
        "authorization",
        "x-api-key",
        "api-key",
        "x-auth-token",
        "x-secret-key",
        "proxy-authorization",
    }
)

#: Query parameter names that should be stripped from URLs.
_SENSITIVE_QUERY_PARAMS: frozenset[str] = frozenset(
    {
        "api_key",
        "apikey",
        "key",
        "token",
        "secret",
        "access_token",
        "client_secret",
    }
)

#: Regex patterns that detect secret-like strings in free text.
_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"sk-[A-Za-z0-9]{20,}", re.ASCII),          # OpenAI-style keys
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]{20,}", re.ASCII | re.IGNORECASE),
    re.compile(r"Basic\s+[A-Za-z0-9+/=]{20,}", re.ASCII | re.IGNORECASE),
    re.compile(r"[A-Za-z0-9]{32,}(?=['\"\s,]|$)", re.ASCII),  # long opaque tokens
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    """Return a copy of *headers* with sensitive values replaced by ``[REDACTED]``.

    Parameters
    ----------
    headers:
        Mapping of HTTP header names to values.

    Returns
    -------
    dict[str, str]
        New dictionary safe for inclusion in run artifacts.

    Examples
    --------
    >>> redact_headers({"Authorization": "Bearer sk-abc123", "Content-Type": "application/json"})
    {'Authorization': '[REDACTED]', 'Content-Type': 'application/json'}
    """
    result: dict[str, str] = {}
    for name, value in headers.items():
        if name.lower() in _SENSITIVE_HEADERS:
            result[name] = REDACTED
        else:
            result[name] = value
    return result


def redact_url(url: str) -> str:
    """Return a sanitised copy of *url* with credentials and secret params removed.

    Removes:
    * ``user:password@`` user-info component.
    * Query parameters whose name matches :data:`_SENSITIVE_QUERY_PARAMS`.

    Parameters
    ----------
    url:
        The original URL string.

    Returns
    -------
    str
        Sanitised URL string.

    Examples
    --------
    >>> redact_url("https://user:pass@api.example.com/v1?api_key=secret&model=gpt-4")
    'https://api.example.com/v1?model=gpt-4'
    """
    try:
        parsed = urlparse(url)
    except Exception:  # noqa: BLE001
        return url

    # Strip user-info
    netloc = parsed.hostname or ""
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"

    # Strip sensitive query params
    qs = parse_qs(parsed.query, keep_blank_values=True)
    clean_qs = {k: v for k, v in qs.items() if k.lower() not in _SENSITIVE_QUERY_PARAMS}
    new_query = urlencode(clean_qs, doseq=True)

    clean = parsed._replace(netloc=netloc, query=new_query)
    return urlunparse(clean)


def scan_text_for_secrets(text: str) -> list[str]:
    """Scan *text* for patterns that look like secrets.

    Returns a list of human-readable descriptions of any matches found.
    Callers should log warnings but *not* include the matched values.

    Parameters
    ----------
    text:
        Arbitrary string to scan.

    Returns
    -------
    list[str]
        Descriptions of any potential secrets found, or an empty list.
    """
    findings: list[str] = []
    for pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            findings.append(f"Pattern matched: {pattern.pattern!r}")
    return findings


def redact_text(text: str) -> str:
    """Replace secret-like substrings in *text* with ``[REDACTED]``.

    This is a best-effort heuristic suitable for logging and report content.
    It is **not** a cryptographic guarantee.

    Parameters
    ----------
    text:
        Text that may contain embedded secrets.

    Returns
    -------
    str
        Text with detected secrets replaced by ``[REDACTED]``.
    """
    result = text
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub(REDACTED, result)
    return result
