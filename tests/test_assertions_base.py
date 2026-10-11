"""Tests for modelparity.assertions.base."""

from __future__ import annotations

import pytest

from modelparity.assertions.base import AssertionResult, BaseAssertion, NormalizedResponse


# ---------------------------------------------------------------------------
# NormalizedResponse
# ---------------------------------------------------------------------------


def test_normalized_response_fields() -> None:
    r = NormalizedResponse(
        http_status=200,
        content="hello",
        tool_calls=None,
        finish_reason="stop",
        error=None,
        raw_response={"id": "abc"},
        latency_ms=42.5,
    )
    assert r.http_status == 200
    assert r.content == "hello"
    assert r.finish_reason == "stop"
    assert r.latency_ms == 42.5


# ---------------------------------------------------------------------------
# AssertionResult
# ---------------------------------------------------------------------------


def test_assertion_result_pass() -> None:
    r = AssertionResult(
        assertion_type="Foo",
        status="PASS",
        expected="x",
        observed="x",
        message="ok",
    )
    assert r.passed
    assert not r.failed


def test_assertion_result_fail() -> None:
    r = AssertionResult(
        assertion_type="Foo",
        status="FAIL",
        expected="x",
        observed="y",
        message="bad",
        hint="maybe this",
    )
    assert r.failed
    assert not r.passed
    assert r.hint == "maybe this"


# ---------------------------------------------------------------------------
# BaseAssertion helpers
# ---------------------------------------------------------------------------


class ConcreteAssertion(BaseAssertion):
    assertion_type = "Concrete"

    def run(self, response: NormalizedResponse) -> AssertionResult:
        return self._pass(expected="any", observed="any", message="ok")


def test_base_assertion_pass_helper() -> None:
    a = ConcreteAssertion()
    r = a._pass(expected="a", observed="a", message="msg")
    assert r.status == "PASS"
    assert r.assertion_type == "Concrete"


def test_base_assertion_fail_helper() -> None:
    a = ConcreteAssertion()
    r = a._fail(expected="a", observed="b", message="msg", hint="h")
    assert r.status == "FAIL"
    assert r.hint == "h"
