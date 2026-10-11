"""Unit tests for parity classification and comparison semantics."""

from modelparity.compare import RunSummary, TestStatus, classify


def test_pass_to_fail_is_regression():
    # reference passed, candidate failed
    status = classify(
        test_id="t1",
        ref_passed=True,
        cand_passed=False,
    )
    assert status == TestStatus.REGRESSION


def test_fail_to_pass_is_not_regression():
    # reference failed, candidate passed (candidate improved or baseline failed)
    status = classify(
        test_id="t2",
        ref_passed=False,
        cand_passed=True,
    )
    assert status == TestStatus.CONTRACT_FAIL


def test_pass_to_pass_no_regression():
    # both passed
    status = classify(
        test_id="t3",
        ref_passed=True,
        cand_passed=True,
    )
    assert status == TestStatus.PASS


def test_fail_to_fail_is_baseline_fail():
    # neither satisfied the contract
    status = classify(
        test_id="t4",
        ref_passed=False,
        cand_passed=False,
    )
    assert status == TestStatus.BASELINE_FAIL


def test_error_classification():
    status = classify(
        test_id="t5",
        ref_passed=False,
        cand_passed=False,
        ref_error="Connection refused",
    )
    assert status == TestStatus.ERROR


def test_summary_counts_and_exit_code():
    summary = RunSummary()
    summary.add(TestStatus.PASS)
    summary.add(TestStatus.PASS)
    assert summary.exit_code == 0
    assert summary.has_regressions is False

    summary.add(TestStatus.REGRESSION)
    assert summary.exit_code == 1
    assert summary.has_regressions is True

    summary_err = RunSummary()
    summary_err.add(TestStatus.ERROR)
    assert summary_err.exit_code == 3
