"""Pydantic v2 models for the ModelParity suite YAML format.

Provides the full data-model hierarchy, a discriminated-union for assertion
types, and a :class:`SuiteValidator` helper that converts raw dicts (loaded
from YAML/JSON) into validated :class:`Suite` objects with semantic checks.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

# ---------------------------------------------------------------------------
# Shared configuration
# ---------------------------------------------------------------------------

_STRICT_MODEL_CFG = ConfigDict(extra="forbid", populate_by_name=True)


# ---------------------------------------------------------------------------
# Assertion models (discriminated union on `type`)
# ---------------------------------------------------------------------------


class ResponseReceivedAssertion(BaseModel):
    """Assert that the endpoint returned *any* HTTP response (no network error)."""

    model_config = _STRICT_MODEL_CFG

    type: Literal["response_received"]


class NonEmptyResponseAssertion(BaseModel):
    """Assert that the response message content is non-empty after stripping."""

    model_config = _STRICT_MODEL_CFG

    type: Literal["non_empty_response"]


class ValidJsonAssertion(BaseModel):
    """Assert that the response content is valid JSON."""

    model_config = _STRICT_MODEL_CFG

    type: Literal["valid_json"]


class JsonSchemaAssertion(BaseModel):
    """Assert that the response JSON validates against the given JSON Schema."""

    model_config = _STRICT_MODEL_CFG

    type: Literal["json_schema"]
    schema_: dict[str, Any] = Field(..., alias="schema")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class JsonValueAssertion(BaseModel):
    """Assert that the value at a JSONPath expression equals the expected value.

    ``path`` uses JSONPath syntax (e.g. ``$.choices[0].message.content``).
    ``equals`` is compared with standard Python equality after JSON parsing.
    """

    model_config = _STRICT_MODEL_CFG

    type: Literal["json_value"]
    path: str = Field(..., description="JSONPath expression, e.g. '$.key'")
    equals: Any = Field(..., description="Expected value at the given path")


class ExactMatchAssertion(BaseModel):
    """Assert that the response content matches ``expected`` exactly (case-sensitive)."""

    model_config = _STRICT_MODEL_CFG

    type: Literal["exact_match"]
    expected: str


class NormalizeStep(str):
    """Valid normalization step identifier."""


_NORMALIZE_STEPS = Literal["lowercase", "strip", "collapse_whitespace"]


class NormalizedMatchAssertion(BaseModel):
    """Assert that the response content matches ``expected`` after normalization.

    Normalization steps are applied in order.  The default pipeline strips
    surrounding whitespace and lowercases the text.
    """

    model_config = _STRICT_MODEL_CFG

    type: Literal["normalized_match"]
    expected: str
    normalize: list[_NORMALIZE_STEPS] = Field(
        default=["lowercase", "strip"],
        description="Ordered list of normalization operations to apply.",
    )


class ToolCallNameAssertion(BaseModel):
    """Assert that the first tool call in the response has the expected name."""

    model_config = _STRICT_MODEL_CFG

    type: Literal["tool_call_name"]
    expected_name: str


class ToolCallArgsSchemaAssertion(BaseModel):
    """Assert that the tool-call arguments object validates against ``schema``."""

    model_config = _STRICT_MODEL_CFG

    type: Literal["tool_call_args_schema"]
    schema_: dict[str, Any] = Field(..., alias="schema")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class FinishReasonAssertion(BaseModel):
    """Assert that the response ``finish_reason`` matches ``expected``."""

    model_config = _STRICT_MODEL_CFG

    type: Literal["finish_reason"]
    expected: str


# Discriminated union – Pydantic resolves the correct subtype via `type`.
Assertion = (
    ResponseReceivedAssertion
    | NonEmptyResponseAssertion
    | ValidJsonAssertion
    | JsonSchemaAssertion
    | JsonValueAssertion
    | ExactMatchAssertion
    | NormalizedMatchAssertion
    | ToolCallNameAssertion
    | ToolCallArgsSchemaAssertion
    | FinishReasonAssertion
)

# ---------------------------------------------------------------------------
# Conversation message
# ---------------------------------------------------------------------------


class Message(BaseModel):
    """A single chat message in a test's conversation history."""

    model_config = _STRICT_MODEL_CFG

    role: Literal["system", "user", "assistant"]
    content: str


# ---------------------------------------------------------------------------
# Response format
# ---------------------------------------------------------------------------


class ResponseFormat(BaseModel):
    """Optional structured-output format hint for the generation request."""

    model_config = _STRICT_MODEL_CFG

    type: Literal["text", "json_object"]


# ---------------------------------------------------------------------------
# Generation overrides per endpoint
# ---------------------------------------------------------------------------


class GenerationOverrides(BaseModel):
    """Per-endpoint overrides applied on top of the suite ``defaults``."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    reference: dict[str, Any] = Field(
        default_factory=dict,
        description="Overrides applied only to the reference endpoint request.",
    )
    candidate: dict[str, Any] = Field(
        default_factory=dict,
        description="Overrides applied only to the candidate endpoint request.",
    )


# ---------------------------------------------------------------------------
# Test case
# ---------------------------------------------------------------------------


class TestCase(BaseModel):
    """A single test case within a suite."""

    model_config = _STRICT_MODEL_CFG

    id: str = Field(..., description="Unique slug-safe identifier for this test.")
    description: str | None = None
    labels: list[str] = Field(default_factory=list)
    messages: list[Message] = Field(..., min_length=1)
    response_format: ResponseFormat | None = None
    generation_overrides: GenerationOverrides = Field(default_factory=GenerationOverrides)
    assertions: list[
        Assertion  # type: ignore[valid-type]  # union resolved at runtime
    ] = Field(
        default_factory=list,
        description="Ordered list of assertions to evaluate on the response.",
    )

    @field_validator("id")
    @classmethod
    def _validate_id_slug(cls, v: str) -> str:
        """Ensure the test ID is slug-safe (alphanumeric, hyphens, underscores)."""
        import re

        if not re.fullmatch(r"[a-zA-Z0-9_\-]+", v):
            raise ValueError(
                f"Test ID '{v}' is not slug-safe. "
                "Use only letters, digits, hyphens, and underscores."
            )
        return v


# ---------------------------------------------------------------------------
# Endpoint configuration
# ---------------------------------------------------------------------------

AdapterType = Literal["openai_compatible", "recorded"]


class EndpointConfig(BaseModel):
    """Configuration for a single endpoint (reference or candidate)."""

    model_config = _STRICT_MODEL_CFG

    adapter: AdapterType = Field(
        ...,
        description="Adapter type: 'openai_compatible' or 'recorded'.",
    )
    base_url: str | None = Field(
        None,
        description="Base URL for the API (required for openai_compatible adapter).",
    )
    model: str | None = Field(None, description="Model identifier to use.")
    api_key_env: str | None = Field(
        None,
        description="Name of the environment variable holding the API key.",
    )
    capabilities: list[str] = Field(
        default_factory=list,
        description="List of capability identifiers declared by this endpoint.",
    )
    fixtures_dir: str | None = Field(
        None,
        description="Path to fixture directory when adapter is 'recorded'.",
    )

    @model_validator(mode="after")
    def _check_openai_base_url(self) -> "EndpointConfig":
        if self.adapter == "openai_compatible" and not self.base_url:
            raise ValueError(
                "base_url is required when adapter is 'openai_compatible'."
            )
        return self



class Endpoints(BaseModel):
    """Pair of reference and candidate endpoint configurations."""

    model_config = _STRICT_MODEL_CFG

    reference: EndpointConfig
    candidate: EndpointConfig


# ---------------------------------------------------------------------------
# Suite-level capture settings
# ---------------------------------------------------------------------------


class CaptureConfig(BaseModel):
    """Controls what information is captured during a run."""

    model_config = _STRICT_MODEL_CFG

    response_text: bool = True
    redact_secrets: bool = True
    save_endpoint_url: bool = False


# ---------------------------------------------------------------------------
# Suite metadata
# ---------------------------------------------------------------------------


class SuiteMeta(BaseModel):
    """Top-level suite metadata block."""

    model_config = _STRICT_MODEL_CFG

    name: str = Field(..., description="Human-readable name for the suite.")
    description: str | None = None
    capture: CaptureConfig = Field(default_factory=CaptureConfig)


# ---------------------------------------------------------------------------
# Generation defaults
# ---------------------------------------------------------------------------


class GenerationDefaults(BaseModel):
    """Default generation parameters applied to every test unless overridden."""

    model_config = _STRICT_MODEL_CFG

    timeout_seconds: int = Field(
        60, ge=1, description="Request timeout in seconds."
    )
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(None, ge=1)
    seed: int | None = None


# ---------------------------------------------------------------------------
# Top-level Suite model
# ---------------------------------------------------------------------------


class Suite(BaseModel):
    """Root model representing a complete ModelParity test suite."""

    model_config = _STRICT_MODEL_CFG

    version: Literal[1] = Field(..., description="Suite schema version. Must be 1.")
    suite: SuiteMeta
    endpoints: Endpoints
    defaults: GenerationDefaults = Field(default_factory=GenerationDefaults)
    tests: list[TestCase] = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Suite validator
# ---------------------------------------------------------------------------


class SuiteValidator:
    """Validates raw suite dictionaries and performs semantic checks.

    Usage::

        from modelparity.schema import SuiteValidator

        with open("suite.yaml") as fh:
            raw = yaml.safe_load(fh)

        suite = SuiteValidator().validate_suite(raw)
    """

    # Assertion types supported for *reference* endpoint evaluation.
    SUPPORTED_ASSERTION_TYPES: frozenset[str] = frozenset(
        {
            "response_received",
            "non_empty_response",
            "valid_json",
            "json_schema",
            "json_value",
            "exact_match",
            "normalized_match",
            "tool_call_name",
            "tool_call_args_schema",
            "finish_reason",
        }
    )

    def validate_suite(self, data: dict[str, Any]) -> Suite:
        """Parse and validate a raw suite dictionary.

        Parameters
        ----------
        data:
            Dictionary loaded from the suite YAML/JSON file.

        Returns
        -------
        Suite
            Fully-validated :class:`Suite` instance.

        Raises
        ------
        pydantic.ValidationError
            If the data does not conform to the schema.
        ValueError
            If semantic constraints (duplicate IDs, unsupported assertions) fail.
        """
        try:
            suite = Suite.model_validate(data)
        except ValidationError:
            raise

        self.check_duplicate_ids(suite)
        self.check_supported_assertions(suite)
        return suite

    def check_duplicate_ids(self, suite: Suite) -> None:
        """Raise :class:`ValueError` if any test IDs are duplicated.

        Parameters
        ----------
        suite:
            Already-validated :class:`Suite` object.

        Raises
        ------
        ValueError
            With a message listing every duplicated ID.
        """
        seen: set[str] = set()
        duplicates: list[str] = []
        for test in suite.tests:
            if test.id in seen:
                duplicates.append(test.id)
            seen.add(test.id)

        if duplicates:
            dup_list = ", ".join(f"'{d}'" for d in duplicates)
            raise ValueError(
                f"Duplicate test IDs found in suite '{suite.suite.name}': {dup_list}. "
                "Each test ID must be unique within a suite."
            )

    def check_supported_assertions(self, suite: Suite) -> None:
        """Raise :class:`ValueError` if any assertion type is unrecognised.

        Parameters
        ----------
        suite:
            Already-validated :class:`Suite` object.

        Raises
        ------
        ValueError
            With details of which test and assertion type is unsupported.
        """
        errors: list[str] = []
        for test in suite.tests:
            for assertion in test.assertions:
                a_type: str = assertion.type  # type: ignore[union-attr]
                if a_type not in self.SUPPORTED_ASSERTION_TYPES:
                    errors.append(
                        f"Test '{test.id}': unsupported assertion type '{a_type}'."
                    )
        if errors:
            detail = "\n  ".join(errors)
            raise ValueError(
                f"Unsupported assertion types detected:\n  {detail}\n"
                f"Supported types: {sorted(self.SUPPORTED_ASSERTION_TYPES)}"
            )
