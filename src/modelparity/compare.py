"""Parity comparison engine for ModelParity.

Compares reference and candidate test outcomes to classify each test as
PASS, REGRESSION, CONTRACT_FAIL, BASELINE_FAIL, ERROR, or INCONCLUSIVE,
and aggregates results into a :class:`RunSummary`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Status codes
# ---------------------------------------------------------------------------


class TestStatus(str, Enum):
    """Final status code for a single parity test.
    """
    __test__ = False

    PASS = "PASS"
    REGRESSION = "REGRESSION"
    CONTRACT_FAIL = "CONTRACT_FAIL"
    BASELINE_FAIL = "BASELINE_FAIL"
    ERROR = "ERROR"
    INCONCLUSIVE = "INCONCLUSIVE"
    SKIPPED = "SKIPPED"


# ---------------------------------------------------------------------------
# Per-test result
# ---------------------------------------------------------------------------


@dataclass
class AssertionOutcome:
    """Slim serialisable summary of a single assertion result."""

    assertion_id: str
    passed: bool
    message: str
    actual: Any = None
    expected: Any = None


@dataclass
class TestResult:
    """Parity result for a single test case.

    Holds the raw assertion outcomes for both sides plus the computed
    :class:`TestStatus`.
    """
    __test__ = False


    test_id: str
    status: TestStatus
    reference_assertions: list[AssertionOutcome] = field(default_factory=list)
    candidate_assertions: list[AssertionOutcome] = field(default_factory=list)
    reference_error: str | None = None
    candidate_error: str | None = None
    notes: str = ""

    @property
    def reference_passed(self) -> bool:
        """True if all reference assertions passed (and no error)."""
        if self.reference_error:
            return False
        return all(a.passed for a in self.reference_assertions)

    @property
    def candidate_passed(self) -> bool:
        """True if all candidate assertions passed (and no error)."""
        if self.candidate_error:
            return False
        return all(a.passed for a in self.candidate_assertions)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-safe dictionary for JSONL output."""
        return {
            "test_id": self.test_id,
            "status": self.status.value,
            "reference_passed": self.reference_passed,
            "candidate_passed": self.candidate_passed,
            "reference_error": self.reference_error,
            "candidate_error": self.candidate_error,
            "reference_assertions": [
                {
                    "assertion_id": a.assertion_id,
                    "passed": a.passed,
                    "message": a.message,
                    "actual": a.actual,
                    "expected": a.expected,
                }
                for a in self.reference_assertions
            ],
            "candidate_assertions": [
                {
                    "assertion_id": a.assertion_id,
                    "passed": a.passed,
                    "message": a.message,
                    "actual": a.actual,
                    "expected": a.expected,
                }
                for a in self.candidate_assertions
            ],
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Classification logic
# ---------------------------------------------------------------------------


def classify(
    test_id: str,
    ref_passed: bool,
    cand_passed: bool,
    ref_error: str | None = None,
    cand_error: str | None = None,
) -> TestStatus:
    """Determine the :class:`TestStatus` from pass/fail flags.

    Parameters
    ----------
    test_id:
        Identifier for the test (used only for error messages).
    ref_passed:
        Whether all reference assertions passed.
    cand_passed:
        Whether all candidate assertions passed.
    ref_error:
        Non-None string if the reference side had a hard error.
    cand_error:
        Non-None string if the candidate side had a hard error.

    Returns
    -------
    TestStatus
        Classified status.
    """
    if ref_error or cand_error:
        return TestStatus.ERROR

    if ref_passed and cand_passed:
        return TestStatus.PASS
    if ref_passed and not cand_passed:
        return TestStatus.REGRESSION
    if not ref_passed and cand_passed:
        return TestStatus.CONTRACT_FAIL
    # not ref_passed and not cand_passed
    return TestStatus.BASELINE_FAIL


# ---------------------------------------------------------------------------
# Run summary
# ---------------------------------------------------------------------------


@dataclass
class RunSummary:
    """Aggregated statistics for a complete parity run."""

    total: int = 0
    passed: int = 0
    regressions: int = 0
    contract_fails: int = 0
    baseline_fails: int = 0
    errors: int = 0
    inconclusive: int = 0
    skipped: int = 0

    def add(self, status: TestStatus) -> None:
        """Increment the appropriate counter for *status*."""
        self.total += 1
        match status:
            case TestStatus.PASS:
                self.passed += 1
            case TestStatus.REGRESSION:
                self.regressions += 1
            case TestStatus.CONTRACT_FAIL:
                self.contract_fails += 1
            case TestStatus.BASELINE_FAIL:
                self.baseline_fails += 1
            case TestStatus.ERROR:
                self.errors += 1
            case TestStatus.INCONCLUSIVE:
                self.inconclusive += 1
            case TestStatus.SKIPPED:
                self.skipped += 1

    @property
    def has_regressions(self) -> bool:
        """True if any test regressed (candidate broke what reference passed)."""
        return self.regressions > 0

    @property
    def exit_code(self) -> int:
        """Recommended process exit code for the run.

        Returns
        -------
        int
            0 = all pass, 1 = assertion failures, 3 = runner error, 4 = inconclusive.
        """
        if self.errors > 0:
            return 3
        if self.inconclusive > 0:
            return 4
        if self.regressions > 0 or self.contract_fails > 0 or self.baseline_fails > 0:
            return 1
        return 0

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-safe dictionary."""
        return {
            "total": self.total,
            "passed": self.passed,
            "regressions": self.regressions,
            "contract_fails": self.contract_fails,
            "baseline_fails": self.baseline_fails,
            "errors": self.errors,
            "inconclusive": self.inconclusive,
            "skipped": self.skipped,
        }
