"""Tests for modelparity.assertions.json_assertions."""

from __future__ import annotations

import json

import pytest

from modelparity.assertions.base import NormalizedResponse
from modelparity.assertions.json_assertions import (
    ExactMatchAssertion,
    FinishReasonAssertion,
    JsonSchemaAssertion,
    JsonValueAssertion,
    NonEmptyResponseAssertion,
    NormalizedMatchAssertion,
    ResponseReceivedAssertion,
    ValidJsonAssertion,
    _extract_path,
    _normalize,
)


def _resp(**kwargs) -> NormalizedResponse:
    """Build a NormalizedResponse with sensible defaults."""
    defaults = dict(
        http_status=200,
        content=None,
        tool_calls=None,
        finish_reason="stop",
        error=None,
        raw_response=None,
        latency_ms=None,
    )
    defaults.update(kwargs)
    return NormalizedResponse(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _extract_path
# ---------------------------------------------------------------------------


def test_extract_path_simple() -> None:
    data = {"a": {"b": 1}}
    found, val = _extract_path(data, "$.a.b")
    assert found
    assert val == 1


def test_extract_path_array_index() -> None:
    data = {"items": [10, 20, 30]}
    found, val = _extract_path(data, "$.items[1]")
    assert found
    assert val == 20


def test_extract_path_missing_key() -> None:
    found, val = _extract_path({"x": 1}, "$.y")
    assert not found
    assert val is None


def test_extract_path_root() -> None:
    found, val = _extract_path(42, "$")
    assert found
    assert val == 42


# ---------------------------------------------------------------------------
# _normalize
# ---------------------------------------------------------------------------


def test_normalize_lowercase() -> None:
    assert _normalize("HELLO", ["lowercase"]) == "hello"


def test_normalize_strip() -> None:
    assert _normalize("  hi  ", ["strip"]) == "hi"


def test_normalize_collapse_whitespace() -> None:
    assert _normalize("a  b\t\nc", ["collapse_whitespace"]) == "a b c"


def test_normalize_combined() -> None:
    result = _normalize("  HELLO   WORLD  ", ["strip", "lowercase", "collapse_whitespace"])
    assert result == "hello world"


def test_normalize_unknown_step() -> None:
    with pytest.raises(ValueError, match="Unknown normalization step"):
        _normalize("x", ["unknown_step"])


# ---------------------------------------------------------------------------
# ResponseReceivedAssertion
# ---------------------------------------------------------------------------


def test_response_received_pass() -> None:
    r = ResponseReceivedAssertion().run(_resp(http_status=200))
    assert r.passed


def test_response_received_fail_on_error() -> None:
    r = ResponseReceivedAssertion().run(_resp(error="connection refused"))
    assert r.failed
    assert "connection refused" in r.message


def test_response_received_fail_on_4xx() -> None:
    r = ResponseReceivedAssertion().run(_resp(http_status=401))
    assert r.failed
    assert "401" in r.message


def test_response_received_fail_on_no_status() -> None:
    r = ResponseReceivedAssertion().run(_resp(http_status=None))
    assert r.failed


# ---------------------------------------------------------------------------
# NonEmptyResponseAssertion
# ---------------------------------------------------------------------------


def test_non_empty_pass() -> None:
    r = NonEmptyResponseAssertion().run(_resp(content="hello"))
    assert r.passed


def test_non_empty_fail_none() -> None:
    r = NonEmptyResponseAssertion().run(_resp(content=None))
    assert r.failed


def test_non_empty_fail_whitespace() -> None:
    r = NonEmptyResponseAssertion().run(_resp(content="   \n"))
    assert r.failed


# ---------------------------------------------------------------------------
# ValidJsonAssertion
# ---------------------------------------------------------------------------


def test_valid_json_pass() -> None:
    r = ValidJsonAssertion().run(_resp(content='{"key": "value"}'))
    assert r.passed


def test_valid_json_fail_on_invalid() -> None:
    r = ValidJsonAssertion().run(_resp(content="not json"))
    assert r.failed
    assert "not valid JSON" in r.message


def test_valid_json_fail_on_empty() -> None:
    r = ValidJsonAssertion().run(_resp(content=None))
    assert r.failed


# ---------------------------------------------------------------------------
# JsonSchemaAssertion
# ---------------------------------------------------------------------------


SCHEMA = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}


def test_json_schema_pass() -> None:
    r = JsonSchemaAssertion(SCHEMA).run(_resp(content='{"name": "Alice"}'))
    assert r.passed


def test_json_schema_fail_missing_required() -> None:
    r = JsonSchemaAssertion(SCHEMA).run(_resp(content='{"age": 30}'))
    assert r.failed
    assert "name" in r.message


def test_json_schema_fail_wrong_type() -> None:
    r = JsonSchemaAssertion(SCHEMA).run(_resp(content='{"name": 123}'))
    assert r.failed


def test_json_schema_fail_invalid_json() -> None:
    r = JsonSchemaAssertion(SCHEMA).run(_resp(content="bad"))
    assert r.failed


# ---------------------------------------------------------------------------
# JsonValueAssertion
# ---------------------------------------------------------------------------


def test_json_value_pass() -> None:
    payload = json.dumps({"status": "ok"})
    r = JsonValueAssertion("$.status", "ok").run(_resp(content=payload))
    assert r.passed


def test_json_value_fail_wrong_value() -> None:
    payload = json.dumps({"status": "error"})
    r = JsonValueAssertion("$.status", "ok").run(_resp(content=payload))
    assert r.failed
    assert r.observed == "error"


def test_json_value_fail_path_not_found() -> None:
    payload = json.dumps({"x": 1})
    r = JsonValueAssertion("$.missing.key", "v").run(_resp(content=payload))
    assert r.failed


def test_json_value_nested_path() -> None:
    payload = json.dumps({"a": {"b": {"c": 42}}})
    r = JsonValueAssertion("$.a.b.c", 42).run(_resp(content=payload))
    assert r.passed


def test_json_value_array_index() -> None:
    payload = json.dumps({"items": ["x", "y", "z"]})
    r = JsonValueAssertion("$.items[2]", "z").run(_resp(content=payload))
    assert r.passed


# ---------------------------------------------------------------------------
# ExactMatchAssertion
# ---------------------------------------------------------------------------


def test_exact_match_pass() -> None:
    r = ExactMatchAssertion("hello").run(_resp(content="hello"))
    assert r.passed


def test_exact_match_fail_case() -> None:
    r = ExactMatchAssertion("Hello").run(_resp(content="hello"))
    assert r.failed


def test_exact_match_fail_whitespace() -> None:
    r = ExactMatchAssertion("hello").run(_resp(content="hello "))
    assert r.failed


# ---------------------------------------------------------------------------
# NormalizedMatchAssertion
# ---------------------------------------------------------------------------


def test_normalized_match_pass() -> None:
    r = NormalizedMatchAssertion("HELLO", ["lowercase", "strip"]).run(
        _resp(content="  hello  ")
    )
    assert r.passed


def test_normalized_match_fail() -> None:
    r = NormalizedMatchAssertion("hello", ["lowercase"]).run(_resp(content="world"))
    assert r.failed


def test_normalized_match_fail_none() -> None:
    r = NormalizedMatchAssertion("hello", ["lowercase"]).run(_resp(content=None))
    assert r.failed


def test_normalized_match_bad_step() -> None:
    r = NormalizedMatchAssertion("hello", ["bad_step"]).run(_resp(content="hello"))
    assert r.failed
    assert "Normalization error" in r.message


# ---------------------------------------------------------------------------
# FinishReasonAssertion
# ---------------------------------------------------------------------------


def test_finish_reason_pass() -> None:
    r = FinishReasonAssertion("stop").run(_resp(finish_reason="stop"))
    assert r.passed


def test_finish_reason_fail() -> None:
    r = FinishReasonAssertion("stop").run(_resp(finish_reason="length"))
    assert r.failed
    assert "length" in r.message
