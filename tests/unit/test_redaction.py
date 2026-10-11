"""Unit tests for secret redaction policy."""

from modelparity.redaction import RedactionPolicy


def test_authorization_header_redacted():
    policy = RedactionPolicy()
    headers = {
        "Authorization": "Bearer sk-secret12345",
        "X-API-KEY": "secret-api-key",
        "Content-Type": "application/json",
    }
    redacted = policy.redact_headers(headers)
    assert redacted["Authorization"] == "[REDACTED]"
    assert redacted["X-API-KEY"] == "[REDACTED]"
    assert redacted["Content-Type"] == "application/json"


def test_url_query_params_stripped():
    policy = RedactionPolicy()
    url = "https://api.example.com/v1/chat?api_key=secret_in_url&model=test"
    cleaned = policy.redact_url(url)
    assert "secret_in_url" not in cleaned
    assert cleaned == "https://api.example.com/v1/chat"


def test_url_userinfo_stripped():
    policy = RedactionPolicy()
    url = "https://admin:superpassword@api.example.com:8000/v1"
    cleaned = policy.redact_url(url)
    assert "superpassword" not in cleaned
    assert "[REDACTED]@api.example.com:8000" in cleaned


def test_known_secret_scanned_in_text():
    policy = RedactionPolicy()
    secret = "sk-live-abcdef123456789"
    text = f"An error occurred with key {secret} when contacting backend."
    scrubbed = policy.scan_for_secrets(text, [secret])
    assert secret not in scrubbed
    assert "[REDACTED]" in scrubbed


def test_non_sensitive_headers_preserved():
    policy = RedactionPolicy()
    headers = {
        "User-Agent": "ModelParity/0.1.0",
        "Accept": "application/json",
    }
    redacted = policy.redact_headers(headers)
    assert redacted == headers
