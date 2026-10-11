"""Shared constants for ModelParity.

Defines test-result status codes, CLI exit codes, and endpoint capability
identifiers used throughout the tool.
"""

# ---------------------------------------------------------------------------
# Test-result status codes
# ---------------------------------------------------------------------------

STATUS_PASS = "PASS"
"""The test passed all assertions on both endpoints."""

STATUS_CONTRACT_FAIL = "CONTRACT_FAIL"
"""The endpoint response violated a structural contract (e.g. invalid JSON
when json_object format was requested)."""

STATUS_REQUEST_ERROR = "REQUEST_ERROR"
"""The HTTP request to the endpoint failed (network error, timeout, 4xx/5xx)."""

STATUS_BASELINE_FAIL = "BASELINE_FAIL"
"""The reference endpoint failed, making comparison against it meaningless."""

STATUS_INCONCLUSIVE = "INCONCLUSIVE"
"""The result cannot be determined conclusively (e.g. non-deterministic output
with no seed, or a capability not supported by the endpoint)."""

STATUS_SKIPPED = "SKIPPED"
"""The test was skipped (e.g. required capability not declared by endpoint)."""

ALL_STATUSES: frozenset[str] = frozenset(
    {
        STATUS_PASS,
        STATUS_CONTRACT_FAIL,
        STATUS_REQUEST_ERROR,
        STATUS_BASELINE_FAIL,
        STATUS_INCONCLUSIVE,
        STATUS_SKIPPED,
    }
)

# ---------------------------------------------------------------------------
# CLI exit codes
# ---------------------------------------------------------------------------

EXIT_OK = 0
"""All tests passed; no issues detected."""

EXIT_ASSERTION_FAIL = 1
"""One or more tests failed assertion checks."""

EXIT_INVALID_SUITE = 2
"""The suite file is invalid (schema or semantic validation failure)."""

EXIT_RUNNER_FAILURE = 3
"""An unexpected internal error occurred during the run."""

EXIT_INCONCLUSIVE = 4
"""All tests that ran were inconclusive (no hard failures, but no clean pass)."""

# ---------------------------------------------------------------------------
# Endpoint capability identifiers
# ---------------------------------------------------------------------------

CAP_CHAT_COMPLETIONS = "chat_completions"
"""Endpoint supports the /chat/completions API surface."""

CAP_TOOL_CALLS = "tool_calls"
"""Endpoint supports function/tool-call responses."""

CAP_JSON_SCHEMA = "json_schema"
"""Endpoint supports structured JSON output with a user-supplied JSON Schema."""

CAP_FINISH_REASON = "finish_reason"
"""Endpoint reliably returns a ``finish_reason`` field in its response."""

CAP_SEED = "seed"
"""Endpoint honours the ``seed`` parameter for reproducible outputs."""

CAP_USAGE_TOKENS = "usage_tokens"
"""Endpoint returns token-usage statistics in its response."""

ALL_CAPABILITIES: frozenset[str] = frozenset(
    {
        CAP_CHAT_COMPLETIONS,
        CAP_TOOL_CALLS,
        CAP_JSON_SCHEMA,
        CAP_FINISH_REASON,
        CAP_SEED,
        CAP_USAGE_TOKENS,
    }
)
