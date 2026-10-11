"""Public surface of the modelparity.assertions package.

Import from here to access the assertion runner and all assertion classes
without needing to know the internal module layout.

Example::

    from modelparity.assertions import run_assertions, NormalizedResponse

    results = run_assertions(
        [{"type": "ResponseReceived"}, {"type": "ValidJson"}],
        response,
    )
"""

from modelparity.assertions.base import (
    AssertionResult,
    BaseAssertion,
    NormalizedResponse,
)
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
from modelparity.assertions.evaluator import evaluate_assertion
from modelparity.assertions.runner import (
    registered_assertion_types,
    run_assertions,
)
from modelparity.assertions.tool_call_assertions import (
    ToolCallArgsSchemaAssertion,
    ToolCallNameAssertion,
)

__all__ = [
    # Core types
    "AssertionResult",
    "BaseAssertion",
    "NormalizedResponse",
    # Runner & evaluator
    "evaluate_assertion",
    "run_assertions",
    "registered_assertion_types",
    # JSON / text assertions
    "ResponseReceivedAssertion",
    "NonEmptyResponseAssertion",
    "ValidJsonAssertion",
    "JsonSchemaAssertion",
    "JsonValueAssertion",
    "ExactMatchAssertion",
    "NormalizedMatchAssertion",
    "FinishReasonAssertion",
    # Tool-call assertions
    "ToolCallNameAssertion",
    "ToolCallArgsSchemaAssertion",
]

