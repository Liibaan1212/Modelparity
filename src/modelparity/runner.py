"""Test runner for ModelParity.

Executes a :class:`~modelparity.schema.Suite` against a reference and
candidate :class:`~modelparity.adapters.base.BaseAdapter`, evaluating
assertions on both sides and collecting structured results.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from modelparity.adapters.base import BaseAdapter
from modelparity.assertions import evaluate_assertion
from modelparity.models import AssertionResult, NormalizedResponse, RedactionPolicy
from modelparity.schema import Suite, TestCase

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------

STATUS_PASS = "PASS"
STATUS_CONTRACT_FAIL = "CONTRACT_FAIL"
STATUS_REQUEST_ERROR = "REQUEST_ERROR"
STATUS_BASELINE_FAIL = "BASELINE_FAIL"
STATUS_INCONCLUSIVE = "INCONCLUSIVE"
STATUS_SKIPPED = "SKIPPED"

_DEFAULT_CONCURRENCY = 4


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class TestRunResult:
    """Outcome of running a single test case against both endpoints.

    Attributes
    ----------
    test_id:
        The test case identifier.
    reference_response:
        The normalized response from the reference endpoint.
    candidate_response:
        The normalized response from the candidate endpoint.
    reference_assertions:
        Assertion results evaluated on the reference response.
    candidate_assertions:
        Assertion results evaluated on the candidate response.
    reference_status:
        One of: PASS, CONTRACT_FAIL, REQUEST_ERROR, BASELINE_FAIL,
        INCONCLUSIVE, SKIPPED.
    candidate_status:
        Same vocabulary as ``reference_status``.
    """

    test_id: str
    reference_response: NormalizedResponse
    candidate_response: NormalizedResponse
    reference_assertions: list[AssertionResult] = field(default_factory=list)
    candidate_assertions: list[AssertionResult] = field(default_factory=list)
    reference_status: str = STATUS_INCONCLUSIVE
    candidate_status: str = STATUS_INCONCLUSIVE


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class Runner:
    """Executes a ModelParity suite against two endpoints.

    Parameters
    ----------
    suite:
        The validated :class:`~modelparity.schema.Suite` to run.
    ref_adapter:
        Adapter for the reference (baseline) endpoint.
    cand_adapter:
        Adapter for the candidate endpoint under test.
    redaction:
        Controls how secrets are handled in manifests included in results.
        Does not affect request execution.
    concurrency:
        Maximum number of test cases executed concurrently.
        Defaults to :data:`_DEFAULT_CONCURRENCY` (4).
    """

    def __init__(
        self,
        suite: Suite,
        ref_adapter: BaseAdapter,
        cand_adapter: BaseAdapter,
        redaction: RedactionPolicy = RedactionPolicy.REDACT_ALL,
        concurrency: int = _DEFAULT_CONCURRENCY,
    ) -> None:
        self._suite = suite
        self._ref_adapter = ref_adapter
        self._cand_adapter = cand_adapter
        self._redaction = redaction
        self._concurrency = max(1, concurrency)

    async def run_all(self) -> list[TestRunResult]:
        """Run all tests in the suite with bounded concurrency.

        Returns
        -------
        list[TestRunResult]
            One result per test, in suite-declaration order.
        """
        semaphore = asyncio.Semaphore(self._concurrency)
        tests = self._suite.tests

        async def _bounded(test: TestCase) -> TestRunResult:
            async with semaphore:
                return await self.run_one(test)

        tasks = [asyncio.create_task(_bounded(t)) for t in tests]
        results: list[TestRunResult] = []

        for coro in asyncio.as_completed(tasks):
            try:
                results.append(await coro)
            except Exception as exc:  # noqa: BLE001
                logger.error("Unexpected error during test run: %s", exc, exc_info=True)

        # Re-sort into declaration order
        order = {t.id: i for i, t in enumerate(tests)}
        results.sort(key=lambda r: order.get(r.test_id, 999))
        return results

    async def run_one(self, test: TestCase) -> TestRunResult:
        """Run a single test case against both endpoints.

        Both endpoints are contacted concurrently. Assertions are evaluated
        only after both responses are received.

        Parameters
        ----------
        test:
            The test case to run.

        Returns
        -------
        TestRunResult
            Populated result including assertion outcomes and statuses.
        """
        logger.debug("Running test: %s", test.id)
        defaults = self._suite.defaults

        ref_spec = self._build_request_spec(test, side="reference")
        cand_spec = self._build_request_spec(test, side="candidate")

        timeout = float(defaults.timeout_seconds)

        # Fire both requests concurrently
        ref_response, cand_response = await asyncio.gather(
            self._safe_send(self._ref_adapter, ref_spec, timeout, test.id),
            self._safe_send(self._cand_adapter, cand_spec, timeout, test.id),
        )

        # Evaluate assertions on each side
        ref_assertions = self._evaluate_assertions(test, ref_response, side="reference")
        cand_assertions = self._evaluate_assertions(test, cand_response, side="candidate")

        ref_status = self._determine_status(
            response=ref_response,
            assertion_results=ref_assertions,
            ref_adapter=self._ref_adapter,
            other_response=None,  # reference has no baseline
        )
        cand_status = self._determine_status(
            response=cand_response,
            assertion_results=cand_assertions,
            ref_adapter=self._cand_adapter,
            other_response=ref_response,
            ref_status=ref_status,
        )

        return TestRunResult(
            test_id=test.id,
            reference_response=ref_response,
            candidate_response=cand_response,
            reference_assertions=ref_assertions,
            candidate_assertions=cand_assertions,
            reference_status=ref_status,
            candidate_status=cand_status,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_request_spec(self, test: TestCase, side: str) -> dict:
        """Build the provider-agnostic request spec for a test case.

        Merges suite defaults with test-level and per-side overrides.

        Parameters
        ----------
        test:
            The test case.
        side:
            Either ``"reference"`` or ``"candidate"``.

        Returns
        -------
        dict
            Request spec ready to pass to an adapter's ``send()`` method.
        """
        defaults = self._suite.defaults
        overrides: dict = {}
        if side == "reference":
            overrides = test.generation_overrides.reference
        elif side == "candidate":
            overrides = test.generation_overrides.candidate

        # Serialise messages to plain dicts for the adapter
        messages = [m.model_dump() for m in test.messages]

        spec: dict = {
            "test_id": test.id,
            "messages": messages,
            "temperature": overrides.get("temperature", defaults.temperature),
            "max_tokens": overrides.get("max_tokens", defaults.max_tokens),
            "seed": overrides.get("seed", defaults.seed),
        }

        if test.response_format is not None:
            spec["response_format"] = test.response_format.model_dump()

        return spec

    @staticmethod
    async def _safe_send(
        adapter: BaseAdapter,
        request_spec: dict,
        timeout: float,
        test_id: str,
    ) -> NormalizedResponse:
        """Call adapter.send() and absorb any unexpected exceptions.

        Parameters
        ----------
        adapter:
            The adapter to call.
        request_spec:
            The request specification dict.
        timeout:
            Maximum wait time in seconds.
        test_id:
            Test ID for error response attribution.

        Returns
        -------
        NormalizedResponse
            Always returns a response; unexpected exceptions produce an
            error response.
        """
        try:
            response = await adapter.send(request_spec, timeout)
            response.test_id = test_id
            return response
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Unhandled exception in adapter.send() for test %r: %s",
                test_id,
                exc,
                exc_info=True,
            )
            return NormalizedResponse(
                test_id=test_id,
                error=f"Adapter raised an unexpected exception: {type(exc).__name__}",
                error_code="REQUEST_ERROR",
            )

    def _evaluate_assertions(
        self,
        test: TestCase,
        response: NormalizedResponse,
        side: str,
    ) -> list[AssertionResult]:
        """Evaluate all assertions for *test* against *response*.

        Parameters
        ----------
        test:
            The test case containing assertion specs.
        response:
            The normalized response to evaluate.
        side:
            ``"reference"`` or ``"candidate"`` (used for logging only).

        Returns
        -------
        list[AssertionResult]
            One result per assertion spec, in declaration order.
        """
        results: list[AssertionResult] = []
        for idx, assertion in enumerate(test.assertions):
            try:
                result = evaluate_assertion(assertion, response, assertion_index=idx)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Error evaluating assertion[%d] type=%r on test=%r side=%s: %s",
                    idx,
                    assertion.type,
                    test.id,
                    side,
                    exc,
                    exc_info=True,
                )
                result = AssertionResult(
                    assertion_id=f"{assertion.type}[{idx}]",
                    passed=False,
                    message=f"Internal error evaluating assertion: {exc}",
                )
            results.append(result)
        return results

    @staticmethod
    def _determine_status(
        response: NormalizedResponse,
        assertion_results: list[AssertionResult],
        ref_adapter: BaseAdapter,
        other_response: NormalizedResponse | None,
        ref_status: str | None = None,
    ) -> str:
        """Compute the final status string for one side of a test run.

        Status determination logic (in priority order):

        1. ``REQUEST_ERROR`` — the request itself failed.
        2. ``SKIPPED`` — a required capability is missing.
        3. ``PASS`` — all assertions passed.
        4. ``CONTRACT_FAIL`` — at least one assertion failed.
        5. ``BASELINE_FAIL`` — this is the candidate side and the reference
           did not pass (so a failure here is inconclusive).
        6. ``INCONCLUSIVE`` — fallback.

        Parameters
        ----------
        response:
            The normalized response for this side.
        assertion_results:
            Evaluated assertion results.
        ref_adapter:
            The adapter that produced this response (used for capability checks).
        other_response:
            The reference response (only relevant for candidate side).
        ref_status:
            The resolved status of the reference side; used to detect
            BASELINE_FAIL on the candidate.

        Returns
        -------
        str
            One of the STATUS_* constants.
        """
        # 1. Network / HTTP failure
        if response.is_error:
            return STATUS_REQUEST_ERROR

        # 2. No assertions → INCONCLUSIVE (can't determine correctness)
        if not assertion_results:
            return STATUS_INCONCLUSIVE

        # 3. All pass
        all_pass = all(r.passed for r in assertion_results)
        if all_pass:
            return STATUS_PASS

        # 4. At least one failed — but check if baseline itself failed
        if ref_status is not None and ref_status != STATUS_PASS:
            return STATUS_BASELINE_FAIL

        return STATUS_CONTRACT_FAIL
