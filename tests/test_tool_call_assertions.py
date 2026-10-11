"""Tests for modelparity.assertions.tool_call_assertions."""

from __future__ import annotations

import json

import pytest

from modelparity.assertions.base import NormalizedResponse
from modelparity.assertions.tool_call_assertions import (
    ToolCallArgsSchemaAssertion,
    ToolCallNameAssertion,
)


def _resp(**kwargs) -> NormalizedResponse:
    defaults = dict(
        http_status=200,
        content=None,
        tool_calls=None,
        finish_reason="tool_calls",
        error=None,
        raw_response=None,
        latency_ms=None,
    )
    defaults.update(kwargs)
    return NormalizedResponse(**defaults)  # type: ignore[arg-type]


def _tc(name: str, args: dict) -> dict:
    """Build a mock tool_call dict."""
    return {"function": {"name": name, "arguments": json.dumps(args)}}


# ---------------------------------------------------------------------------
# ToolCallNameAssertion
# ---------------------------------------------------------------------------


def test_tool_call_name_pass() -> None:
    r = ToolCallNameAssertion("get_weather").run(
        _resp(tool_calls=[_tc("get_weather", {"city": "London"})])
    )
    assert r.passed


def test_tool_call_name_pass_multiple_calls() -> None:
    r = ToolCallNameAssertion("search").run(
        _resp(tool_calls=[_tc("get_weather", {}), _tc("search", {"q": "test"})])
    )
    assert r.passed


def test_tool_call_name_fail_wrong_name() -> None:
    r = ToolCallNameAssertion("get_weather").run(
        _resp(tool_calls=[_tc("search", {})])
    )
    assert r.failed
    assert "get_weather" in r.message


def test_tool_call_name_fail_no_calls() -> None:
    r = ToolCallNameAssertion("get_weather").run(_resp(tool_calls=None))
    assert r.failed


def test_tool_call_name_fail_empty_calls() -> None:
    r = ToolCallNameAssertion("get_weather").run(_resp(tool_calls=[]))
    assert r.failed


def test_tool_call_name_malformed_call() -> None:
    """Malformed entries should not crash; they appear as <malformed>."""
    r = ToolCallNameAssertion("get_weather").run(
        _resp(tool_calls=[{"no_function_key": True}])
    )
    assert r.failed
    assert "<malformed>" in str(r.observed)


# ---------------------------------------------------------------------------
# ToolCallArgsSchemaAssertion
# ---------------------------------------------------------------------------


ARGS_SCHEMA = {
    "type": "object",
    "properties": {
        "city": {"type": "string"},
        "units": {"type": "string", "enum": ["celsius", "fahrenheit"]},
    },
    "required": ["city"],
}


def test_tool_call_args_schema_pass() -> None:
    r = ToolCallArgsSchemaAssertion(ARGS_SCHEMA).run(
        _resp(tool_calls=[_tc("get_weather", {"city": "Paris", "units": "celsius"})])
    )
    assert r.passed


def test_tool_call_args_schema_pass_optional_absent() -> None:
    r = ToolCallArgsSchemaAssertion(ARGS_SCHEMA).run(
        _resp(tool_calls=[_tc("get_weather", {"city": "Tokyo"})])
    )
    assert r.passed


def test_tool_call_args_schema_fail_missing_required() -> None:
    r = ToolCallArgsSchemaAssertion(ARGS_SCHEMA).run(
        _resp(tool_calls=[_tc("get_weather", {"units": "celsius"})])
    )
    assert r.failed
    assert "city" in r.message


def test_tool_call_args_schema_fail_wrong_enum() -> None:
    r = ToolCallArgsSchemaAssertion(ARGS_SCHEMA).run(
        _resp(tool_calls=[_tc("get_weather", {"city": "NYC", "units": "kelvin"})])
    )
    assert r.failed


def test_tool_call_args_schema_fail_no_calls() -> None:
    r = ToolCallArgsSchemaAssertion(ARGS_SCHEMA).run(_resp(tool_calls=None))
    assert r.failed


def test_tool_call_args_schema_args_as_dict() -> None:
    """When arguments is already a dict (not a JSON string), it should still work."""
    tc = {"function": {"name": "fn", "arguments": {"city": "Berlin"}}}
    r = ToolCallArgsSchemaAssertion(ARGS_SCHEMA).run(_resp(tool_calls=[tc]))
    assert r.passed


def test_tool_call_args_schema_invalid_json_args() -> None:
    tc = {"function": {"name": "fn", "arguments": "not json"}}
    r = ToolCallArgsSchemaAssertion(ARGS_SCHEMA).run(_resp(tool_calls=[tc]))
    assert r.failed
    assert "not valid JSON" in r.message
