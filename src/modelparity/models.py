"""Core shared data models for ModelParity.

These Pydantic models are the lingua franca that connects adapters,
assertions, the runner, the comparator, and the reporter.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


class RedactionPolicy(str, Enum):
    """Controls how sensitive fields are handled in manifests and reports."""

    REDACT_ALL = "redact_all"
    """Redact every potentially sensitive field (base_url, api_key_env)."""

    SHOW_BASE_URL = "show_base_url"
    """Show the base URL but still redact API key env var names."""

    SHOW_ALL = "show_all"
    """Show all non-secret fields (env-var *names* are shown; values never are)."""


# ---------------------------------------------------------------------------
# Normalized response
# ---------------------------------------------------------------------------


class ToolCall(BaseModel):
    """A single tool/function call returned by the model."""

    id: str = ""
    name: str
    arguments: str  # raw JSON string from the model


class NormalizedResponse(BaseModel):
    """Provider-agnostic representation of a single model response.

    This is what every adapter produces, regardless of the underlying
    API format. Downstream components only deal with this type.
    """

    test_id: str = ""
    """The test case ID that produced this response (set by the runner)."""

    content: str | None = None
    """The text content of the assistant message, if any."""

    tool_calls: list[ToolCall] = Field(default_factory=list)
    """Tool/function calls requested by the model."""

    finish_reason: str | None = None
    """e.g. 'stop', 'tool_calls', 'length', 'content_filter'."""

    model: str | None = None
    """Model identifier echoed back from the provider."""

    usage: dict[str, int] | None = None
    """Token usage dict, e.g. {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}."""

    raw: dict[str, Any] = Field(default_factory=dict)
    """The unmodified response body from the provider (for debugging)."""

    error: str | None = None
    """Non-None when the request itself failed (network error, HTTP 4xx/5xx, etc.)."""

    error_code: str | None = None
    """Machine-readable error code, e.g. 'REQUEST_ERROR', 'TIMEOUT'."""

    @property
    def is_error(self) -> bool:
        """True when this response represents a failed request."""
        return self.error is not None


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------


class AssertionResult(BaseModel):
    """Outcome of evaluating a single assertion against a NormalizedResponse."""

    assertion_id: str
    """Unique identifier for the assertion rule."""

    passed: bool
    """True if the assertion passed."""

    message: str = ""
    """Human-readable explanation of what was checked and why it passed/failed."""

    actual: Any = None
    """The actual value extracted from the response (for diagnostics)."""

    expected: Any = None
    """The expected value specified in the test (for diagnostics)."""


# ---------------------------------------------------------------------------
# Suite / TestCase
# ---------------------------------------------------------------------------


class Message(BaseModel):
    """A chat message (system / user / assistant)."""

    role: str
    content: str


class ToolDefinition(BaseModel):
    """A tool available to the model during this test."""

    type: str = "function"
    function: dict[str, Any]


class AssertionSpec(BaseModel):
    """Declarative assertion specification from the suite YAML/JSON."""

    id: str
    type: str
    """Assertion type key, e.g. 'finish_reason', 'json_schema', 'contains'."""

    params: dict[str, Any] = Field(default_factory=dict)
    """Type-specific parameters."""


class TestCase(BaseModel):
    """A single test within a suite."""

    id: str
    description: str = ""
    messages: list[Message]
    temperature: float | None = None
    max_tokens: int | None = None
    seed: int | None = None
    response_format: dict[str, Any] | None = None
    tools: list[ToolDefinition] | None = None
    assertions: list[AssertionSpec] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    skip: bool = False


class Suite(BaseModel):
    """A collection of test cases that form a parity test run."""

    name: str
    description: str = ""
    version: str = "1.0"
    tests: list[TestCase] = Field(default_factory=list)
