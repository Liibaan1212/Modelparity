"""Assertion runner for ModelParity.

Dispatches assertion configuration dicts (as authored in test-suite YAML /
JSON) to the corresponding :class:`~modelparity.assertions.base.BaseAssertion`
instances, runs each one against a
:class:`~modelparity.assertions.base.NormalizedResponse`, and returns the
aggregated list of :class:`~modelparity.assertions.base.AssertionResult`
objects.
"""

from __future__ import annotations

import traceback
from typing import Any

from modelparity.assertions.base import AssertionResult, BaseAssertion, NormalizedResponse
from modelparity.assertions.json_assertions import (
    ExactMatchAssertion,
    FinishReasonAssertion,
    JsonSchemaAssertion,
    JsonValueAssertion,
    NonEmptyResponseAssertion,
    NormalizedMatchAssertion,
    ResponseReceivedAssertion,
    ValidJsonAssertion,
)
from modelparity.assertions.tool_call_assertions import (
    ToolCallArgsSchemaAssertion,
    ToolCallNameAssertion,
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

#: Maps the ``type`` string used in config files to a factory function that
#: accepts the config dict (minus ``"type"``) and returns an assertion instance.
_ASSERTION_REGISTRY: dict[str, type[BaseAssertion]] = {
    "ResponseReceived": ResponseReceivedAssertion,
    "NonEmptyResponse": NonEmptyResponseAssertion,
    "ValidJson": ValidJsonAssertion,
    "JsonSchema": JsonSchemaAssertion,
    "JsonValue": JsonValueAssertion,
    "ExactMatch": ExactMatchAssertion,
    "NormalizedMatch": NormalizedMatchAssertion,
    "FinishReason": FinishReasonAssertion,
    "ToolCallName": ToolCallNameAssertion,
    "ToolCallArgsSchema": ToolCallArgsSchemaAssertion,
}


def _build_assertion(config: dict[str, Any]) -> BaseAssertion:
    """Instantiate an assertion from a configuration dict.

    The dict must contain a ``"type"`` key whose value matches a registered
    assertion name.  All other keys are forwarded as keyword arguments to
    the assertion's ``__init__``.

    Args:
        config: Assertion configuration dict.

    Returns:
        A ready-to-use :class:`BaseAssertion` instance.

    Raises:
        KeyError: If ``"type"`` is absent from *config*.
        ValueError: If the ``"type"`` value is not registered.
        TypeError: If the remaining keys don't match the assertion's
            constructor signature.
    """
    config = dict(config)  # shallow copy — don't mutate caller's dict
    assertion_type = config.pop("type")
    if assertion_type not in _ASSERTION_REGISTRY:
        registered = sorted(_ASSERTION_REGISTRY)
        raise ValueError(
            f"Unknown assertion type {assertion_type!r}. "
            f"Registered types: {registered}"
        )
    cls = _ASSERTION_REGISTRY[assertion_type]
    return cls(**config)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_assertions(
    assertions_config: list[dict[str, Any]],
    response: NormalizedResponse,
) -> list[AssertionResult]:
    """Dispatch and run a list of assertion configs against *response*.

    Each element of *assertions_config* must be a dict with at least a
    ``"type"`` key matching a registered assertion name.  Remaining keys
    are forwarded to the assertion's constructor.

    If an individual assertion raises an unexpected exception (e.g. a bug
    in a custom assertion or an unexpected data shape), the error is caught
    and surfaced as a ``FAIL`` result rather than propagating and aborting
    the entire run.

    Args:
        assertions_config: Ordered list of assertion configuration dicts.
        response: The normalized API response to evaluate.

    Returns:
        Ordered list of :class:`AssertionResult` objects, one per config
        entry.  The length always equals ``len(assertions_config)``.

    Example::

        results = run_assertions(
            [
                {"type": "ResponseReceived"},
                {"type": "ValidJson"},
                {"type": "JsonSchema", "schema": {"type": "object"}},
            ],
            response,
        )
    """
    results: list[AssertionResult] = []

    for idx, config in enumerate(assertions_config):
        assertion_type_name: str = config.get("type", f"<unknown#{idx}>")
        try:
            assertion = _build_assertion(config)
            result = assertion.run(response)
        except Exception:  # noqa: BLE001
            tb = traceback.format_exc()
            result = AssertionResult(
                assertion_type=assertion_type_name,
                status="FAIL",
                expected="<assertion to execute without error>",
                observed="<unexpected exception>",
                message=(
                    f"Assertion {assertion_type_name!r} raised an unexpected "
                    f"exception:\n{tb}"
                ),
                hint="This may indicate a misconfigured assertion or a bug in the assertion implementation.",
            )
        results.append(result)

    return results


def registered_assertion_types() -> list[str]:
    """Return a sorted list of all registered assertion type names.

    Useful for validation, help text, and documentation generation.
    """
    return sorted(_ASSERTION_REGISTRY)
