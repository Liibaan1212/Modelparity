"""Base types for ModelParity assertions.

Defines the :class:`NormalizedResponse` container that all normalizers
produce, the :class:`AssertionResult` value object that every assertion
returns, and the :class:`BaseAssertion` abstract base that every
concrete assertion must implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Normalized response container
# ---------------------------------------------------------------------------


@dataclass
class NormalizedResponse:
    """Provider-agnostic representation of a single model API response.

    All adapter normalizers (OpenAI, Anthropic, Gemini, …) convert their
    provider-specific payloads into this common shape so that assertions
    can be written once and applied to any provider.

    Attributes:
        http_status: HTTP status code returned by the provider, or ``None``
            when the request could not be sent at all (e.g. DNS failure).
        content: The assistant's text reply extracted from the first
            ``assistant`` message, or ``None`` if absent / not applicable.
        tool_calls: Raw tool-call objects from the API response (list of
            dicts).  ``None`` means the provider returned no tool calls.
        finish_reason: Provider-supplied stop reason string
            (e.g. ``"stop"``, ``"tool_calls"``, ``"length"``).
        error: Human-readable error description when the request failed,
            ``None`` on success.
        raw_response: Full deserialized API response body.  May be ``None``
            when raw-response capture is disabled to conserve memory /
            storage.
        latency_ms: End-to-end request latency in milliseconds, or ``None``
            when timing was not captured.
    """

    http_status: int | None
    content: str | None
    tool_calls: list[dict] | None
    finish_reason: str | None
    error: str | None
    raw_response: dict | None
    latency_ms: float | None


# ---------------------------------------------------------------------------
# Assertion result value object
# ---------------------------------------------------------------------------


@dataclass
class AssertionResult:
    """Immutable result produced by a single assertion run.

    Attributes:
        assertion_type: Short identifier for the assertion class,
            e.g. ``"ValidJson"``.
        status: ``"PASS"`` or ``"FAIL"``.
        expected: The value or condition the assertion expected to find.
        observed: The value or condition actually observed in the response.
        message: Human-readable summary of the outcome.
        hint: An optional hypothesis to help diagnose a failure.  Hints
            are *hypotheses only* — they are never definitive conclusions.
    """

    assertion_type: str
    status: str  # 'PASS' or 'FAIL'
    expected: Any
    observed: Any
    message: str
    hint: str | None = field(default=None)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    @property
    def passed(self) -> bool:
        """Return ``True`` when the assertion passed."""
        return self.status == "PASS"

    @property
    def failed(self) -> bool:
        """Return ``True`` when the assertion failed."""
        return self.status == "FAIL"


# ---------------------------------------------------------------------------
# Abstract base assertion
# ---------------------------------------------------------------------------


class BaseAssertion(ABC):
    """Abstract base for all ModelParity assertion types.

    Subclasses must implement :meth:`run` and should set the class-level
    :attr:`assertion_type` string to a short, stable identifier used in
    reports and configuration files.

    Example::

        class MyAssertion(BaseAssertion):
            assertion_type = "MyAssertion"

            def run(self, response: NormalizedResponse) -> AssertionResult:
                ...
    """

    #: Short stable name used in config files and report output.
    assertion_type: str = "BaseAssertion"

    @abstractmethod
    def run(self, response: NormalizedResponse) -> AssertionResult:
        """Evaluate the assertion against *response* and return a result.

        Args:
            response: The normalized provider response to evaluate.

        Returns:
            An :class:`AssertionResult` with ``status`` of either
            ``"PASS"`` or ``"FAIL"``.
        """

    # ------------------------------------------------------------------
    # Protected helpers available to all subclasses
    # ------------------------------------------------------------------

    def _pass(
        self,
        *,
        expected: Any,
        observed: Any,
        message: str,
        hint: str | None = None,
    ) -> AssertionResult:
        """Build a PASS result."""
        return AssertionResult(
            assertion_type=self.assertion_type,
            status="PASS",
            expected=expected,
            observed=observed,
            message=message,
            hint=hint,
        )

    def _fail(
        self,
        *,
        expected: Any,
        observed: Any,
        message: str,
        hint: str | None = None,
    ) -> AssertionResult:
        """Build a FAIL result."""
        return AssertionResult(
            assertion_type=self.assertion_type,
            status="FAIL",
            expected=expected,
            observed=observed,
            message=message,
            hint=hint,
        )
