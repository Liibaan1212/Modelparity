"""Tool-call assertions for ModelParity.

These assertions operate on the ``tool_calls`` field of a
:class:`~modelparity.assertions.base.NormalizedResponse` and verify
that the model invoked the expected function with arguments that
conform to a given JSON Schema.
"""

from __future__ import annotations

import json
from typing import Any

import jsonschema

from modelparity.assertions.base import AssertionResult, BaseAssertion, NormalizedResponse


class ToolCallNameAssertion(BaseAssertion):
    """Assert that at least one tool call in the response has the expected name.

    The check is performed against ``tool_call["function"]["name"]`` for
    every element in :attr:`~NormalizedResponse.tool_calls`.

    Args:
        expected_name: The exact function name that must appear in at least
            one tool call.
    """

    assertion_type = "ToolCallName"

    def __init__(self, expected_name: str) -> None:
        self._expected_name = expected_name

    def run(self, response: NormalizedResponse) -> AssertionResult:  # noqa: D102
        tool_calls = response.tool_calls
        if not tool_calls:
            return self._fail(
                expected=self._expected_name,
                observed=None,
                message="Response contains no tool calls.",
                hint="The model may have responded with text instead of invoking a tool.",
            )

        names: list[str] = []
        for tc in tool_calls:
            try:
                name = tc["function"]["name"]
                names.append(name)
            except (KeyError, TypeError):
                names.append("<malformed>")

        if self._expected_name in names:
            return self._pass(
                expected=self._expected_name,
                observed=names,
                message=f"Tool call {self._expected_name!r} found in response.",
            )
        return self._fail(
            expected=self._expected_name,
            observed=names,
            message=(
                f"Expected tool call {self._expected_name!r} not found. "
                f"Observed names: {names}"
            ),
            hint="The model may have chosen a differently named tool or used a free-text response.",
        )


class ToolCallArgsSchemaAssertion(BaseAssertion):
    """Assert that the first tool call's arguments validate against a JSON Schema.

    The ``function.arguments`` field is expected to be a JSON string
    (as returned by OpenAI-compatible APIs).  It is parsed and then
    validated against the provided schema.

    Args:
        schema: A JSON Schema dict describing the expected argument shape.
    """

    assertion_type = "ToolCallArgsSchema"

    def __init__(self, schema: dict) -> None:
        self._schema = schema

    def run(self, response: NormalizedResponse) -> AssertionResult:  # noqa: D102
        tool_calls = response.tool_calls
        if not tool_calls:
            return self._fail(
                expected="Tool call with valid arguments",
                observed=None,
                message="Response contains no tool calls.",
            )

        first_tc = tool_calls[0]
        try:
            raw_args: Any = first_tc["function"]["arguments"]
        except (KeyError, TypeError):
            return self._fail(
                expected="Tool call with valid arguments",
                observed=first_tc,
                message="First tool call is missing 'function.arguments'.",
            )

        # arguments may arrive as a JSON string or as an already-parsed dict
        if isinstance(raw_args, str):
            try:
                parsed_args = json.loads(raw_args)
            except json.JSONDecodeError as exc:
                return self._fail(
                    expected="Valid JSON in function.arguments",
                    observed=raw_args[:120],
                    message=f"function.arguments is not valid JSON: {exc}",
                )
        else:
            parsed_args = raw_args

        try:
            jsonschema.validate(instance=parsed_args, schema=self._schema)
        except jsonschema.ValidationError as exc:
            path_str = " -> ".join(str(p) for p in exc.absolute_path) or "<root>"
            return self._fail(
                expected="Arguments conforming to provided schema",
                observed=f"Validation error at {path_str!r}: {exc.message}",
                message=(
                    f"Tool call arguments failed schema validation: "
                    f"{exc.message} (path: {path_str})"
                ),
                hint="The model may have omitted required fields or used an unexpected type.",
            )
        except jsonschema.SchemaError as exc:
            return self._fail(
                expected="Arguments conforming to provided schema",
                observed="<schema error>",
                message=f"The provided JSON Schema is itself invalid: {exc.message}",
            )

        return self._pass(
            expected="Arguments conforming to provided schema",
            observed="<schema valid>",
            message="First tool call arguments validate successfully against the provided schema.",
        )
