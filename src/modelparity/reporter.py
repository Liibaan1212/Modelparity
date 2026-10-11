"""Markdown report generator for ModelParity run artifacts.

Reads ``results.jsonl`` and ``manifest.json`` from a run directory and
produces a structured Markdown report suitable for CI logs, GitHub PRs,
or standalone files.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modelparity.compare import TestStatus


# ---------------------------------------------------------------------------
# Status icon helpers
# ---------------------------------------------------------------------------

_STATUS_ICONS: dict[str, str] = {
    TestStatus.PASS: "[PASS]",
    TestStatus.REGRESSION: "[REGRESSION]",
    TestStatus.CONTRACT_FAIL: "[CONTRACT_FAIL]",
    TestStatus.BASELINE_FAIL: "[BASELINE_FAIL]",
    TestStatus.ERROR: "[ERROR]",
    TestStatus.INCONCLUSIVE: "[INCONCLUSIVE]",
    TestStatus.SKIPPED: "[SKIPPED]",
}


def _icon(status: str) -> str:
    return _STATUS_ICONS.get(status, f"[{status}]")



# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


def generate_report(
    run_dir: Path,
    regenerated: bool = False,
) -> str:
    """Generate a Markdown report from a run directory.

    Parameters
    ----------
    run_dir:
        Path to a completed run directory containing ``results.jsonl``
        and optionally ``manifest.json`` and ``summary.json``.
    regenerated:
        If True, prepend a ``REGENERATED`` header warning.

    Returns
    -------
    str
        Complete Markdown report string.

    Raises
    ------
    FileNotFoundError
        If ``results.jsonl`` is not found in *run_dir*.
    """
    results_path = run_dir / "results.jsonl"
    if not results_path.exists():
        raise FileNotFoundError(f"results.jsonl not found in {run_dir}")

    manifest: dict[str, Any] = {}
    for candidate_name in ["manifest.json", "run.json"]:
        manifest_path = run_dir / candidate_name
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            break

    summary_data: dict[str, Any] = {}
    summary_path = run_dir / "summary.json"
    if summary_path.exists():
        summary_data = json.loads(summary_path.read_text(encoding="utf-8"))

    results: list[dict[str, Any]] = []
    for line in results_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        raw_rec = json.loads(line)
        # Normalize between flat and nested record format
        comp = raw_rec.get("comparison", {})
        ref = raw_rec.get("reference", {})
        cand = raw_rec.get("candidate", {})
        norm_rec = {
            "test_id": raw_rec.get("test_id", "?"),
            "status": raw_rec.get("status") or comp.get("classification") or "INCONCLUSIVE",
            "reference_passed": raw_rec.get("reference_passed", comp.get("ref_passed", False)),
            "candidate_passed": raw_rec.get("candidate_passed", comp.get("cand_passed", False)),
            "reference_error": raw_rec.get("reference_error") or ref.get("error"),
            "candidate_error": raw_rec.get("candidate_error") or cand.get("error"),
            "reference_assertions": raw_rec.get("reference_assertions") or ref.get("assertions", []),
            "candidate_assertions": raw_rec.get("candidate_assertions") or cand.get("assertions", []),
        }
        results.append(norm_rec)

    lines: list[str] = []

    # Header
    if regenerated:
        lines += [
            "> [!NOTE]",
            "> **REPLAY/REGENERATED**: This report was regenerated from saved run artifacts.",
            "> No new network requests were made.",
            "",
        ]

    suite_name = manifest.get("suite_name", "Parity Suite")
    started_at = manifest.get("started_at", "")
    lines += [
        f"# ModelParity Report - {suite_name}",
        "",
    ]
    if started_at:
        lines += [f"**Run started:** `{started_at}`", ""]

    # Summary table
    total = summary_data.get("total", len(results))
    passed = summary_data.get("passed", sum(1 for r in results if r.get("status") == "PASS"))
    regressions = summary_data.get("regressions", sum(1 for r in results if r.get("status") == "REGRESSION"))
    contract_fails = summary_data.get("contract_fails", sum(1 for r in results if r.get("status") == "CONTRACT_FAIL"))
    baseline_fails = summary_data.get("baseline_fails", sum(1 for r in results if r.get("status") == "BASELINE_FAIL"))
    errors = summary_data.get("errors", sum(1 for r in results if r.get("status") == "ERROR"))

    lines += [
        "## Summary",
        "",
        "| Metric | Count |",
        "|--------|-------|",
        f"| Total tests | {total} |",
        f"| PASS | {passed} |",
        f"| REGRESSION | {regressions} |",
        f"| CONTRACT_FAIL | {contract_fails} |",
        f"| BASELINE_FAIL | {baseline_fails} |",
        f"| ERROR | {errors} |",
        "",
    ]

    if regressions > 0:
        lines += [
            "> [!CAUTION]",
            f"> **{regressions} regression(s) detected.** The candidate endpoint failed tests that the reference passed.",
            "",
        ]

    # Adapter info
    endpoints = manifest.get("endpoints", {})
    ref_manifest = endpoints.get("reference") or manifest.get("reference_adapter", {})
    cand_manifest = endpoints.get("candidate") or manifest.get("candidate_adapter", {})
    if ref_manifest or cand_manifest:
        lines += ["## Endpoints", ""]
        if ref_manifest:
            lines += [
                "**Reference Endpoint:**",
                "```yaml",
                *[f"  {k}: {v}" for k, v in ref_manifest.items()],
                "```",
                "",
            ]
        if cand_manifest:
            lines += [
                "**Candidate Endpoint:**",
                "```yaml",
                *[f"  {k}: {v}" for k, v in cand_manifest.items()],
                "```",
                "",
            ]

    # Per-test results
    lines += ["## Test Results", ""]
    lines += [
        "| Test ID | Status | Reference | Candidate |",
        "|---------|--------|-----------|-----------|",
    ]
    for result in results:
        status = result.get("status", "INCONCLUSIVE")
        ref_ok = "[OK]" if result.get("reference_passed") else "[FAIL]"
        cand_ok = "[OK]" if result.get("candidate_passed") else "[FAIL]"
        lines.append(f"| `{result.get('test_id', '?')}` | {_icon(status)} | {ref_ok} | {cand_ok} |")


    lines.append("")

    # Detailed failures
    failing = [r for r in results if r.get("status") not in ("PASS", "SKIPPED")]
    if failing:
        lines += ["## Failure Details", ""]
        for result in failing:
            test_id = result.get("test_id", "unknown")
            status = result.get("status", "?")
            lines += [
                f"### `{test_id}` - {_icon(status)}",
                "",
            ]

            if result.get("reference_error"):
                lines += [f"**Reference error:** `{result['reference_error']}`", ""]
            if result.get("candidate_error"):
                lines += [f"**Candidate error:** `{result['candidate_error']}`", ""]

            # Failed assertions
            for side, key in [("Reference", "reference_assertions"), ("Candidate", "candidate_assertions")]:
                assertions = result.get(key, [])
                failed_assertions = [a for a in assertions if not a.get("passed")]
                if failed_assertions:
                    lines += [f"**{side} failed assertions:**", ""]
                    for a in failed_assertions:
                        a_id = a.get("id") or a.get("assertion_id", "?")
                        lines += [
                            f"- `{a_id}`: {a.get('message', '')}",
                        ]
                        if a.get("actual") is not None:
                            lines.append(f"  - Actual: `{a['actual']}`")
                        if a.get("expected") is not None:
                            lines.append(f"  - Expected: `{a['expected']}`")
                    lines.append("")

    # Limitations notice & footer
    lines += [
        "> [!IMPORTANT]",
        "> **Notice:** ModelParity verifies user-defined behavior contracts, not bit-for-bit or logit-level parity.",
        "> Valid JSON structure or tool-call envelope does not guarantee semantic correctness.",
        "",
        "---",
        "",
        f"*Generated by ModelParity at {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}*",
    ]

    return "\n".join(lines)

