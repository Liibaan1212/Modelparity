"""Assertion evaluators for ModelParity.

Each public ``evaluate_*`` function accepts a :class:`~modelparity.models.NormalizedResponse`
and returns an :class:`~modelparity.models.AssertionResult`.

The top-level :func:`evaluate_assertion` dispatcher routes to the correct
evaluator based on the ``type`` field of an :class:`~modelparity.schema.Assertion`
discriminated-union object.
"""

from __future__ import annotations

import json
import re
from typing import Any

import jsonschema

from modelparity.models import AssertionResult, NormalizedResponse
from modelparity.schema import (
    Assertion,
    ExactMatchAssertion,
    FinishReasonAssertion,
    JsonSchemaAssertion,
    JsonValueAssertion,
    NonEmptyResponseAssertion,
    NormalizedMatchAssertion,
    ResponseReceivedAssertion,
    ToolCallArgsSchemaAssertion,
    ToolCallNameAssertion,
    ValidJsonAssertion,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ok(assertion_id: str, message: str, actual: Any = None, expected: Any = None) -> AssertionResult:
    return AssertionResult(
        assertion_id=assertion_id,
        passed=True,
        message=message,
        actual=actual,
        expected=expected,
    )


def _fail(assertion_id: str, message: str, actual: Any = None, expected: Any = None) -> AssertionResult:
    return AssertionResult(
        assertion_id=assertion_id,
        passed=False,
        message=message,
        actual=actual,
        expected=expected,
    )


def _parse_json(content: str | None) -> tuple[bool, Any, str]:
    """Attempt to parse *content* as JSON.

    Returns
    -------
    (success, parsed_value, error_message)
    """
    if content is None:
        return False, None, "Response content is None"
    try:
        return True, json.loads(content), ""
    except json.JSONDecodeError as exc:
        return False, None, str(exc)


def _jsonpath_get(data: Any, path: str) -> tuple[bool, Any, str]:
    """Evaluate a simple JSONPath expression against *data*.

    Supports dot-notation paths like ``$.key``, ``$.a.b``, and
    array indexing like ``$.items[0].name``.

    Returns
    -------
    (success, value, error_message)
    """
    if not path.startswith("$"):
        return False, None, f"JSONPath must start with '$', got: {path!r}"

    # Tokenise the path
    segments = re.split(r"\.(?![^\[]*\])", path[1:])  # split on dots outside brackets
    current = data
    for segment in segments:
        if not segment:
            continue
        # Handle array index: key[0]
        m = re.match(r"^([^\[]*)\[(\d+)\]$", segment)
        if m:
            key, idx = m.group(1), int(m.group(2))
            if key:
                if not isinstance(current, dict) or key not in current:
                    return False, None, f"Key '{key}' not found"
                current = current[key]
            if not isinstance(current, list) or idx >= len(current):
                return False, None, f"Index [{idx}] out of range"
            current = current[idx]
        else:
            if not isinstance(current, dict) or segment not in current:
                return False, None, f"Key '{segment}' not found"
            current = current[segment]
    return True, current, ""


# ---------------------------------------------------------------------------
# Individual evaluators
# ---------------------------------------------------------------------------


def evaluate_response_received(
    spec: ResponseReceivedAssertion,
    response: NormalizedResponse,
    assertion_id: str = "response_received",
) -> AssertionResult:
    """Assert that the endpoint returned any response (no network error)."""
    if response.is_error:
        return _fail(assertion_id, f"Request failed: {response.error}", actual=response.error)
    return _ok(assertion_id, "Response received successfully.")


def evaluate_non_empty_response(
    spec: NonEmptyResponseAssertion,
    response: NormalizedResponse,
    assertion_id: str = "non_empty_response",
) -> AssertionResult:
    """Assert that the response content is non-empty after stripping."""
    if response.is_error:
        return _fail(assertion_id, f"Request failed: {response.error}", actual=None)
    content = (response.content or "").strip()
    if not content:
        return _fail(assertion_id, "Response content is empty or whitespace-only.", actual=repr(response.content))
    return _ok(assertion_id, f"Response content is non-empty ({len(content)} chars).", actual=content[:80])


def evaluate_valid_json(
    spec: ValidJsonAssertion,
    response: NormalizedResponse,
    assertion_id: str = "valid_json",
) -> AssertionResult:
    """Assert that the response content is valid JSON."""
    if response.is_error:
        return _fail(assertion_id, f"Request failed: {response.error}")
    success, _, error_msg = _parse_json(response.content)
    if not success:
        return _fail(
            assertion_id,
            f"Content is not valid JSON: {error_msg}",
            actual=repr((response.content or "")[:120]),
        )
    return _ok(assertion_id, "Content is valid JSON.")


def evaluate_json_schema(
    spec: JsonSchemaAssertion,
    response: NormalizedResponse,
    assertion_id: str = "json_schema",
) -> AssertionResult:
    """Assert that the response JSON validates against the given schema."""
    if response.is_error:
        return _fail(assertion_id, f"Request failed: {response.error}")
    success, parsed, error_msg = _parse_json(response.content)
    if not success:
        return _fail(assertion_id, f"Content is not valid JSON: {error_msg}")
    try:
        jsonschema.validate(instance=parsed, schema=spec.schema_)
    except jsonschema.ValidationError as exc:
        return _fail(
            assertion_id,
            f"JSON Schema validation failed: {exc.message}",
            actual=parsed,
            expected=spec.schema_,
        )
    return _ok(assertion_id, "JSON Schema validation passed.", actual=parsed, expected=spec.schema_)


def evaluate_json_value(
    spec: JsonValueAssertion,
    response: NormalizedResponse,
    assertion_id: str = "json_value",
) -> AssertionResult:
    """Assert that the value at a JSONPath equals the expected value."""
    if response.is_error:
        return _fail(assertion_id, f"Request failed: {response.error}")
    success, parsed, error_msg = _parse_json(response.content)
    if not success:
        return _fail(assertion_id, f"Content is not valid JSON: {error_msg}")
    found, actual, path_err = _jsonpath_get(parsed, spec.path)
    if not found:
        return _fail(assertion_id, f"JSONPath '{spec.path}' not found: {path_err}", expected=spec.equals)
    if actual != spec.equals:
        return _fail(
            assertion_id,
            f"JSONPath '{spec.path}' is {actual!r}, expected {spec.equals!r}.",
            actual=actual,
            expected=spec.equals,
        )
    return _ok(assertion_id, f"JSONPath '{spec.path}' == {spec.equals!r}.", actual=actual, expected=spec.equals)


def evaluate_exact_match(
    spec: ExactMatchAssertion,
    response: NormalizedResponse,
    assertion_id: str = "exact_match",
) -> AssertionResult:
    """Assert exact content match."""
    if response.is_error:
        return _fail(assertion_id, f"Request failed: {response.error}")
    actual = response.content or ""
    if actual != spec.expected:
        return _fail(
            assertion_id,
            f"Exact match failed. Got {actual!r}, expected {spec.expected!r}.",
            actual=actual,
            expected=spec.expected,
        )
    return _ok(assertion_id, "Exact match passed.", actual=actual, expected=spec.expected)


def evaluate_normalized_match(
    spec: NormalizedMatchAssertion,
    response: NormalizedResponse,
    assertion_id: str = "normalized_match",
) -> AssertionResult:
    """Assert content match after normalization steps."""
    if response.is_error:
        return _fail(assertion_id, f"Request failed: {response.error}")
    text = response.content or ""
    normalized_expected = spec.expected

    for step in spec.normalize:
        if step == "lowercase":
            text = text.lower()
            normalized_expected = normalized_expected.lower()
        elif step == "strip":
            text = text.strip()
            normalized_expected = normalized_expected.strip()
        elif step == "collapse_whitespace":
            text = re.sub(r"\s+", " ", text)
            normalized_expected = re.sub(r"\s+", " ", normalized_expected)

    if text != normalized_expected:
        return _fail(
            assertion_id,
            f"Normalized match failed. Got {text!r}, expected {normalized_expected!r}.",
            actual=text,
            expected=normalized_expected,
        )
    return _ok(assertion_id, "Normalized match passed.", actual=text, expected=normalized_expected)


def evaluate_tool_call_name(
    spec: ToolCallNameAssertion,
    response: NormalizedResponse,
    assertion_id: str = "tool_call_name",
) -> AssertionResult:
    """Assert that the first tool call has the expected name."""
    if response.is_error:
        return _fail(assertion_id, f"Request failed: {response.error}")
    if not response.tool_calls:
        return _fail(
            assertion_id,
            "No tool calls in response.",
            expected=spec.expected_name,
        )
    actual_name = response.tool_calls[0].name
    if actual_name != spec.expected_name:
        return _fail(
            assertion_id,
            f"Tool call name is {actual_name!r}, expected {spec.expected_name!r}.",
            actual=actual_name,
            expected=spec.expected_name,
        )
    return _ok(assertion_id, f"Tool call name is {actual_name!r}.", actual=actual_name, expected=spec.expected_name)


def evaluate_tool_call_args_schema(
    spec: ToolCallArgsSchemaAssertion,
    response: NormalizedResponse,
    assertion_id: str = "tool_call_args_schema",
) -> AssertionResult:
    """Assert tool-call arguments validate against the given schema."""
    if response.is_error:
        return _fail(assertion_id, f"Request failed: {response.error}")
    if not response.tool_calls:
        return _fail(assertion_id, "No tool calls in response.", expected=spec.schema_)
    raw_args = response.tool_calls[0].arguments
    success, parsed, error_msg = _parse_json(raw_args)
    if not success:
        return _fail(assertion_id, f"Tool call arguments are not valid JSON: {error_msg}")
    try:
        jsonschema.validate(instance=parsed, schema=spec.schema_)
    except jsonschema.ValidationError as exc:
        return _fail(assertion_id, f"Tool call args schema validation failed: {exc.message}", actual=parsed)
    return _ok(assertion_id, "Tool call args schema validation passed.", actual=parsed)


def evaluate_finish_reason(
    spec: FinishReasonAssertion,
    response: NormalizedResponse,
    assertion_id: str = "finish_reason",
) -> AssertionResult:
    """Assert the response finish_reason matches the expected value."""
    if response.is_error:
        return _fail(assertion_id, f"Request failed: {response.error}")
    actual = response.finish_reason
    if actual != spec.expected:
        return _fail(
            assertion_id,
            f"finish_reason is {actual!r}, expected {spec.expected!r}.",
            actual=actual,
            expected=spec.expected,
        )
    return _ok(assertion_id, f"finish_reason is {actual!r}.", actual=actual, expected=spec.expected)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_EVALUATORS = {
    "response_received": evaluate_response_received,
    "non_empty_response": evaluate_non_empty_response,
    "valid_json": evaluate_valid_json,
    "json_schema": evaluate_json_schema,
    "json_value": evaluate_json_value,
    "exact_match": evaluate_exact_match,
    "normalized_match": evaluate_normalized_match,
    "tool_call_name": evaluate_tool_call_name,
    "tool_call_args_schema": evaluate_tool_call_args_schema,
    "finish_reason": evaluate_finish_reason,
}


def evaluate_assertion(
    assertion: Assertion,  # type: ignore[valid-type]
    response: NormalizedResponse,
    assertion_index: int = 0,
) -> AssertionResult:
    """Dispatch to the correct evaluator for *assertion*.

    Parameters
    ----------
    assertion:
        A validated assertion spec from the suite schema.
    response:
        The normalized response to evaluate against.
    assertion_index:
        Zero-based index used to generate a stable assertion ID.

    Returns
    -------
    AssertionResult
        The outcome of evaluating the assertion.

    Raises
    ------
    ValueError
        If the assertion type is not registered (should not happen after validation).
    """
    a_type: str = assertion.type  # type: ignore[union-attr]
    assertion_id = f"{a_type}[{assertion_index}]"
    evaluator = _EVALUATORS.get(a_type)
    if evaluator is None:
        raise ValueError(f"No evaluator registered for assertion type '{a_type}'")
    return evaluator(assertion, response, assertion_id)  # type: ignore[call-arg]
