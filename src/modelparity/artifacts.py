"""Artifact writer for ModelParity run outputs.

Every test run produces a self-contained artifact directory::

    <out_dir>/
        run.json          — run metadata and endpoint manifests
        suite.json        — sanitized copy of the test suite
        results.jsonl     — one JSON object per test result (newline-delimited)
        summary.json      — aggregate counts and final status
        report.md         — human-readable Markdown report

All writes are **atomic** where the OS allows it: content is written to a
temporary file in the same directory, then renamed over the target.  This
prevents partially-written files from being read by concurrent processes or
a viewer that opens files while the run is still progressing.

Secrets must never appear in artifact files.  Callers are responsible for
scrubbing data through :class:`~modelparity.redaction.RedactionPolicy`
before passing it here.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    """Return current UTC time as an ISO 8601 string with ``Z`` suffix."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write_text(path: Path, content: str) -> None:
    """Write *content* to *path* atomically using a temp-then-rename strategy.

    The temporary file is created in the same directory as *path* so that the
    rename is guaranteed to be on the same filesystem (required for atomicity
    on POSIX; best-effort on Windows where rename may overwrite).

    Args:
        path: Destination file path.
        content: Text content to write (UTF-8).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path_str = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        # On Windows, os.replace atomically replaces the destination.
        os.replace(tmp_path_str, path)
    except Exception:
        # Clean up the temp file on error
        try:
            os.unlink(tmp_path_str)
        except OSError:
            pass
        raise


def _atomic_write_json(path: Path, data: Any, *, indent: int = 2) -> None:
    """Serialize *data* to JSON and write to *path* atomically.

    Args:
        path: Destination file path.
        data: JSON-serializable Python object.
        indent: JSON indentation level.
    """
    content = json.dumps(data, indent=indent, ensure_ascii=False, default=str)
    _atomic_write_text(path, content + "\n")


class ArtifactWriter:
    """Manages all file output for a single ModelParity test run.

    The writer is created once per run, assigned a stable
    :attr:`run_id` (UUID4), and used throughout the run to accumulate
    result records before finalizing.

    Args:
        out_dir: Directory where artifact files will be written.  Created
            automatically if it does not exist.

    Attributes:
        run_id: Unique identifier for this run (UUID4 string).
        started_at: ISO 8601 UTC timestamp captured at construction time.
        out_dir: Resolved :class:`~pathlib.Path` for the output directory.
    """

    def __init__(self, out_dir: Path) -> None:
        self.out_dir: Path = Path(out_dir).resolve()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.run_id: str = str(uuid.uuid4())
        self.started_at: str = _utc_now()
        self._result_count: int = 0

    # ------------------------------------------------------------------
    # run.json
    # ------------------------------------------------------------------

    def write_run_manifest(
        self,
        suite: dict[str, Any],
        endpoint_manifests: dict[str, Any],
    ) -> None:
        """Write ``run.json`` with run metadata and endpoint summaries.

        This file is written at the *start* of a run (before any results
        are available) so that the directory can be identified even if the
        process crashes mid-run.

        Args:
            suite: Sanitized (secret-free) representation of the test suite
                being executed.  Only non-sensitive metadata is written
                (e.g. suite name, test count) — callers should strip
                provider credentials before passing this dict.
            endpoint_manifests: Mapping of endpoint key → endpoint metadata
                dict (provider, model, base_url — never API keys).
        """
        manifest: dict[str, Any] = {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "suite_name": suite.get("name", "<unnamed>"),
            "suite_version": suite.get("version"),
            "test_count": len(suite.get("tests", [])),
            "endpoints": endpoint_manifests,
            "modelparity_version": _get_version(),
        }
        _atomic_write_json(self.out_dir / "run.json", manifest)

    # ------------------------------------------------------------------
    # results.jsonl
    # ------------------------------------------------------------------

    def write_result(
        self,
        test_id: str,
        reference_result: dict[str, Any],
        candidate_result: dict[str, Any],
        comparison: dict[str, Any],
    ) -> None:
        """Append one result record to ``results.jsonl``.

        Each line is a self-contained JSON object so the file can be
        streamed / processed line-by-line without loading the entire file.

        Args:
            test_id: Stable identifier for the test case.
            reference_result: Assertion results for the reference endpoint.
            candidate_result: Assertion results for the candidate endpoint.
            comparison: Parity comparison metadata (pass counts, verdict, …).
        """
        record: dict[str, Any] = {
            "run_id": self.run_id,
            "recorded_at": _utc_now(),
            "seq": self._result_count,
            "test_id": test_id,
            "reference": reference_result,
            "candidate": candidate_result,
            "comparison": comparison,
        }
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        results_path = self.out_dir / "results.jsonl"
        results_path.parent.mkdir(parents=True, exist_ok=True)
        # Append — not atomic per-line, but JSONL is inherently append-safe.
        with results_path.open("a", encoding="utf-8") as fh:
            fh.write(line)
        self._result_count += 1

    # ------------------------------------------------------------------
    # suite.json
    # ------------------------------------------------------------------

    def write_suite_snapshot(self, suite_dict: dict[str, Any]) -> str:
        """Write a sanitized snapshot of the test suite and return its SHA-256.

        The snapshot is useful for reproducibility: it records exactly which
        tests were run.  Callers must strip credentials before passing
        *suite_dict*.

        Args:
            suite_dict: Sanitized test-suite dict.

        Returns:
            Hex-encoded SHA-256 digest of the canonical JSON representation.
        """
        canonical = json.dumps(
            suite_dict, sort_keys=True, ensure_ascii=False, default=str
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        suite_data: dict[str, Any] = {
            "sha256": digest,
            "captured_at": _utc_now(),
            "suite": suite_dict,
        }
        _atomic_write_json(self.out_dir / "suite.json", suite_data)
        return digest

    # ------------------------------------------------------------------
    # summary.json
    # ------------------------------------------------------------------

    def finalize(self, summary: dict[str, Any]) -> None:
        """Write ``summary.json`` and mark the run as complete.

        Should be called exactly once, after all results have been written.

        Args:
            summary: Aggregate statistics dict (pass/fail counts, overall
                verdict, duration, …).  Will be augmented with run metadata
                before writing.
        """
        final: dict[str, Any] = {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finalized_at": _utc_now(),
            "result_count": self._result_count,
            **summary,
            "complete": True,
        }
        _atomic_write_json(self.out_dir / "summary.json", final)

    # ------------------------------------------------------------------
    # report.md
    # ------------------------------------------------------------------

    def write_markdown_report(self, report_content: str) -> None:
        """Write a human-readable Markdown report to ``report.md``.

        Args:
            report_content: Full Markdown string to write.
        """
        _atomic_write_text(self.out_dir / "report.md", report_content)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_version() -> str:
    """Return the installed modelparity version or a fallback string."""
    try:
        from importlib.metadata import version

        return version("modelparity")
    except Exception:  # noqa: BLE001
        return "unknown"
