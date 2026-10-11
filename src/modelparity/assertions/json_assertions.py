"""JSON and text-based assertions for ModelParity.

Each assertion class is instantiated with its configuration and exposes
a single :meth:`~BaseAssertion.run` method that accepts a
:class:`~modelparity.assertions.base.NormalizedResponse` and returns an
:class:`~modelparity.assertions.base.AssertionResult`.
"""

from __future__ import annotations

import json
import re
from typing import Any

import jsonschema

from modelparity.assertions.base import AssertionResult, BaseAssertion, NormalizedResponse


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_path(data: Any, path: str) -> tuple[bool, Any]:
    """Extract a value from *data* using a simple dotted-path expression.

    Supports paths of the form ``$.key``, ``$.key.nested``,
    ``$.key[0].field``, etc.  Only dict and list containers are traversed.

    Args:
        data: The root object to traverse (typically a parsed JSON dict).
        path: A dotted path string.  The leading ``$`` segment is the root.

    Returns:
        A ``(found, value)`` tuple.  *found* is ``False`` when any
        intermediate key / index is missing.
    """
    # Strip leading "$." or "$"
    if path.startswith("$."):
        path = path[2:]
    elif path.startswith("$"):
        path = path[1:]

    if not path:
        return True, data

    # Split on "." but keep bracket notation together
    segments: list[str] = re.split(r"\.", path)

    current = data
    for segment in segments:
        # Handle array index notation: key[0]
        match = re.fullmatch(r"([^\[]+)\[(\d+)\]", segment)
        if match:
            key, idx = match.group(1), int(match.group(2))
            if not isinstance(current, dict) or key not in current:
                return False, None
            current = current[key]
            if not isinstance(current, list) or idx >= len(current):
                return False, None
            current = current[idx]
        else:
            if isinstance(current, dict):
                if segment not in current:
                    return False, None
                current = current[segment]
            elif isinstance(current, list):
                try:
                    current = current[int(segment)]
                except (ValueError, IndexError):
                    return False, None
            else:
                return False, None

    return True, current


# ---------------------------------------------------------------------------
# Core connectivity / content assertions
# ---------------------------------------------------------------------------


class ResponseReceivedAssertion(BaseAssertion):
    """Assert that the API responded with a 2xx HTTP status and no error.

    This is typically the first assertion in every test — if it fails,
    downstream assertions will also fail but their results should be
    interpreted cautiously.
    """

    assertion_type = "ResponseReceived"

    def run(self, response: NormalizedResponse) -> AssertionResult:  # noqa: D102
        if response.error is not None:
            return self._fail(
                expected="No error",
                observed=response.error,
                message=f"Request failed with error: {response.error}",
                hint="Check that the endpoint URL and API key are correct.",
            )
        if response.http_status is None:
            return self._fail(
                expected="2xx HTTP status",
                observed=None,
                message="No HTTP status recorded (request may not have been sent).",
            )
        if not (200 <= response.http_status < 300):
            return self._fail(
                expected="2xx HTTP status",
                observed=response.http_status,
                message=f"Non-2xx HTTP status: {response.http_status}",
                hint="The provider may have rejected the request due to auth, rate-limiting, or an invalid model name.",
            )
        return self._pass(
            expected="2xx HTTP status",
            observed=response.http_status,
            message=f"Response received successfully (HTTP {response.http_status}).",
        )


class NonEmptyResponseAssertion(BaseAssertion):
    """Assert that the response contains non-empty assistant text content."""

    assertion_type = "NonEmptyResponse"

    def run(self, response: NormalizedResponse) -> AssertionResult:  # noqa: D102
        content = response.content
        if content is None:
            return self._fail(
                expected="Non-empty content",
                observed=None,
                message="Response content is None.",
                hint="The model may have returned a tool call or an empty message.",
            )
        if not content.strip():
            return self._fail(
                expected="Non-empty content",
                observed=repr(content),
                message="Response content is empty or whitespace-only.",
            )
        return self._pass(
            expected="Non-empty content",
            observed=f"<{len(content)} chars>",
            message="Response contains non-empty content.",
        )


# ---------------------------------------------------------------------------
# JSON parsing / schema assertions
# ---------------------------------------------------------------------------


class ValidJsonAssertion(BaseAssertion):
    """Assert that the response content is valid JSON."""

    assertion_type = "ValidJson"

    def run(self, response: NormalizedResponse) -> AssertionResult:  # noqa: D102
        content = response.content
        if not content:
            return self._fail(
                expected="Valid JSON string",
                observed=None,
                message="No content to parse as JSON.",
            )
        try:
            json.loads(content)
        except json.JSONDecodeError as exc:
            return self._fail(
                expected="Valid JSON string",
                observed=content[:120] + ("…" if len(content) > 120 else ""),
                message=f"Content is not valid JSON: {exc}",
                hint="The model may have wrapped the JSON in markdown code fences or added trailing text.",
            )
        return self._pass(
            expected="Valid JSON string",
            observed="<valid JSON>",
            message="Content parsed successfully as JSON.",
        )


class JsonSchemaAssertion(BaseAssertion):
    """Assert that the parsed JSON content validates against a JSON Schema.

    Args:
        schema: A JSON Schema dict (Draft 7 / Draft 2020-12 are both
            supported via the ``jsonschema`` library).
    """

    assertion_type = "JsonSchema"

    def __init__(self, schema: dict) -> None:
        self._schema = schema

    def run(self, response: NormalizedResponse) -> AssertionResult:  # noqa: D102
        content = response.content
        if not content:
            return self._fail(
                expected="JSON matching schema",
                observed=None,
                message="No content to validate against schema.",
            )
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            return self._fail(
                expected="JSON matching schema",
                observed=content[:120],
                message=f"Content is not valid JSON — cannot validate schema: {exc}",
            )
        try:
            jsonschema.validate(instance=parsed, schema=self._schema)
        except jsonschema.ValidationError as exc:
            path_str = " -> ".join(str(p) for p in exc.absolute_path) or "<root>"
            return self._fail(
                expected="JSON conforming to provided schema",
                observed=f"Validation error at {path_str!r}: {exc.message}",
                message=f"JSON Schema validation failed: {exc.message} (path: {path_str})",
                hint="The schema mismatch may reflect a provider-specific difference in output structure.",
            )
        except jsonschema.SchemaError as exc:
            return self._fail(
                expected="JSON conforming to provided schema",
                observed="<schema error>",
                message=f"The provided JSON Schema is itself invalid: {exc.message}",
            )
        return self._pass(
            expected="JSON conforming to provided schema",
            observed="<schema valid>",
            message="Parsed JSON validates successfully against the provided schema.",
        )


class JsonValueAssertion(BaseAssertion):
    """Assert that a value at a dotted path equals an expected value.

    Args:
        path: A dotted path expression starting with ``$``
            (e.g. ``$.choices[0].message.role``).
        equals: The expected value.  Comparison is strict (``==``).
    """

    assertion_type = "JsonValue"

    def __init__(self, path: str, equals: Any) -> None:
        self._path = path
        self._equals = equals

    def run(self, response: NormalizedResponse) -> AssertionResult:  # noqa: D102
        content = response.content
        if not content:
            return self._fail(
                expected=self._equals,
                observed=None,
                message="No content — cannot extract JSON path.",
            )
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            return self._fail(
                expected=self._equals,
                observed=None,
                message=f"Content is not valid JSON: {exc}",
            )
        found, value = _extract_path(parsed, self._path)
        if not found:
            return self._fail(
                expected=self._equals,
                observed="<path not found>",
                message=f"Path {self._path!r} not found in parsed JSON.",
                hint="The key may be absent or the path expression may be incorrect.",
            )
        if value != self._equals:
            return self._fail(
                expected=self._equals,
                observed=value,
                message=f"Value at {self._path!r} does not match expected.",
            )
        return self._pass(
            expected=self._equals,
            observed=value,
            message=f"Value at {self._path!r} matches expected.",
        )


# ---------------------------------------------------------------------------
# String / text match assertions
# ---------------------------------------------------------------------------


class ExactMatchAssertion(BaseAssertion):
    """Assert that the content exactly equals an expected string.

    Args:
        expected: The exact string the response content must equal.
    """

    assertion_type = "ExactMatch"

    def __init__(self, expected: str) -> None:
        self._expected = expected

    def run(self, response: NormalizedResponse) -> AssertionResult:  # noqa: D102
        observed = response.content
        if observed == self._expected:
            return self._pass(
                expected=self._expected,
                observed=observed,
                message="Content exactly matches the expected string.",
            )
        return self._fail(
            expected=self._expected,
            observed=observed,
            message="Content does not exactly match the expected string.",
            hint="Consider using NormalizedMatch if minor whitespace or casing differences are acceptable.",
        )


def _normalize(text: str, steps: list[str]) -> str:
    """Apply a sequence of named normalization steps to *text*.

    Supported steps (applied in order):

    - ``"lowercase"``      — convert to lower-case
    - ``"strip"``          — strip leading/trailing whitespace
    - ``"collapse_whitespace"`` — replace runs of whitespace with a single space

    Args:
        text: Input text.
        steps: Ordered list of normalization step names.

    Returns:
        Normalized text.

    Raises:
        ValueError: If an unrecognized step name is supplied.
    """
    for step in steps:
        if step == "lowercase":
            text = text.lower()
        elif step == "strip":
            text = text.strip()
        elif step == "collapse_whitespace":
            text = re.sub(r"\s+", " ", text)
        else:
            raise ValueError(f"Unknown normalization step: {step!r}")
    return text


class NormalizedMatchAssertion(BaseAssertion):
    """Assert that content matches *expected* after normalization.

    Args:
        expected: The expected string (normalization is also applied to it).
        normalize: Ordered list of normalization step names to apply to
            both sides before comparison.  Supported values:
            ``"lowercase"``, ``"strip"``, ``"collapse_whitespace"``.
    """

    assertion_type = "NormalizedMatch"

    def __init__(self, expected: str, normalize: list[str]) -> None:
        self._expected = expected
        self._normalize_steps = normalize

    def run(self, response: NormalizedResponse) -> AssertionResult:  # noqa: D102
        observed = response.content
        if observed is None:
            return self._fail(
                expected=self._expected,
                observed=None,
                message="Content is None — cannot perform normalized comparison.",
            )
        try:
            norm_observed = _normalize(observed, self._normalize_steps)
            norm_expected = _normalize(self._expected, self._normalize_steps)
        except ValueError as exc:
            return self._fail(
                expected=self._expected,
                observed=observed,
                message=f"Normalization error: {exc}",
            )
        if norm_observed == norm_expected:
            return self._pass(
                expected=self._expected,
                observed=observed,
                message=f"Content matches after normalization ({self._normalize_steps}).",
            )
        return self._fail(
            expected=self._expected,
            observed=observed,
            message=f"Normalized content does not match. Expected {norm_expected!r}, got {norm_observed!r}.",
        )


# ---------------------------------------------------------------------------
# Finish reason assertion
# ---------------------------------------------------------------------------


class FinishReasonAssertion(BaseAssertion):
    """Assert that the response finish_reason equals an expected value.

    Args:
        expected: The expected finish reason string
            (e.g. ``"stop"``, ``"tool_calls"``).
    """

    assertion_type = "FinishReason"

    def __init__(self, expected: str) -> None:
        self._expected = expected

    def run(self, response: NormalizedResponse) -> AssertionResult:  # noqa: D102
        observed = response.finish_reason
        if observed == self._expected:
            return self._pass(
                expected=self._expected,
                observed=observed,
                message=f"finish_reason is {observed!r} as expected.",
            )
        return self._fail(
            expected=self._expected,
            observed=observed,
            message=f"finish_reason {observed!r} does not match expected {self._expected!r}.",
            hint="Different providers may use different finish-reason strings for the same semantic outcome.",
        )
