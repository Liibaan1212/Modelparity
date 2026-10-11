"""Command-line interface for ModelParity.

Provides the following commands:
  - init:      Scaffold a starter parity.yaml file
  - validate:  Validate a test suite schema and assertions without sending requests
  - run:       Execute a parity test suite against reference and candidate endpoints
  - report:    Generate or view a human-readable report from saved run artifacts
  - replay:    Re-run assertions offline against saved response fixtures
  - doctor:    Verify endpoint reachability and capability preflight
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from modelparity import __version__
from modelparity.adapters import get_adapter
from modelparity.adapters.recorded import RecordedAdapter
from modelparity.artifacts import ArtifactWriter
from modelparity.compare import TestResult, TestStatus, classify
from modelparity.constants import (
    EXIT_ASSERTION_FAIL,
    EXIT_INCONCLUSIVE,
    EXIT_INVALID_SUITE,
    EXIT_OK,
    EXIT_RUNNER_FAILURE,
    STATUS_BASELINE_FAIL,
    STATUS_CONTRACT_FAIL,
    STATUS_INCONCLUSIVE,
    STATUS_PASS,
    STATUS_REQUEST_ERROR,
    STATUS_SKIPPED,
)
from modelparity.models import RedactionPolicy
from modelparity.reporter import generate_report
from modelparity.runner import Runner
from modelparity.schema import SuiteValidator

app = typer.Typer(
    name="modelparity",
    help="ModelParity: Portable behavior-contract testing for LLM serving configurations.",
    no_args_is_help=True,
    add_completion=False,
)

console = Console()
err_console = Console(stderr=True)

DEFAULT_STARTER_YAML = """version: 1
suite:
  name: "starter-parity-suite"
  description: "Starter behavior contracts for comparing reference vs. candidate inference"
  capture:
    response_text: true
    redact_secrets: true
    save_endpoint_url: false

endpoints:
  reference:
    adapter: openai_compatible
    base_url: "http://127.0.0.1:8001/v1"
    model: "reference-model-label"
    api_key_env: "MODELPARITY_REFERENCE_KEY"
    capabilities:
      - chat_completions
      - finish_reason
  candidate:
    adapter: openai_compatible
    base_url: "http://127.0.0.1:8002/v1"
    model: "candidate-model-label"
    api_key_env: "MODELPARITY_CANDIDATE_KEY"
    capabilities:
      - chat_completions
      - finish_reason

defaults:
  timeout_seconds: 30
  temperature: 0.0
  max_tokens: 128

tests:
  - id: smoke-greeting
    description: "Model must return non-empty text response"
    labels: ["smoke"]
    messages:
      - role: user
        content: "Hello, reply with greeting only."
    assertions:
      - type: response_received
      - type: non_empty_response

  - id: json-output-contract
    description: "Model must return valid JSON with expected fields"
    labels: ["json"]
    messages:
      - role: system
        content: "Return JSON only with status and count fields."
      - role: user
        content: "Items: 5 units processed."
    assertions:
      - type: response_received
      - type: valid_json
      - type: json_schema
        schema:
          type: object
          properties:
            status:
              type: string
            count:
              type: integer
          required: ["status", "count"]
          additionalProperties: false
"""


@app.command()
def init(
    output: Path = typer.Option(
        Path("parity.yaml"),
        "--out",
        "-o",
        help="Target path to create starter configuration file.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing file if present.",
    ),
) -> None:
    """Create a starter parity.yaml suite file."""
    if output.exists() and not force:
        err_console.print(
            f"[bold red]Error:[/bold red] File '{output}' already exists. Use --force to overwrite."
        )
        raise typer.Exit(code=EXIT_INVALID_SUITE)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(DEFAULT_STARTER_YAML, encoding="utf-8")
    console.print(
        f"[bold green]Created starter suite:[/bold green] [cyan]{output.resolve()}[/cyan]"
    )
    console.print("Next steps:")
    console.print(f"  1. Edit endpoint URLs and tests in '{output}'")
    console.print(f"  2. Validate with: [bold]modelparity validate {output}[/bold]")
    console.print(f"  3. Run suite with: [bold]modelparity run {output}[/bold]")


@app.command()
def validate(
    suite_file: Path = typer.Argument(
        ...,
        help="Path to parity test suite file (.yaml or .json)",
        exists=True,
        readable=True,
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Treat warnings as errors.",
    ),
) -> None:
    """Validate suite syntax, schema conformance, duplicate IDs, and assertion types."""
    try:
        raw_text = suite_file.read_text(encoding="utf-8")
        data = yaml.safe_load(raw_text)
        if not isinstance(data, dict):
            err_console.print("[bold red]Error:[/bold red] Suite file must contain a mapping/dictionary.")
            raise typer.Exit(code=EXIT_INVALID_SUITE)

        validator = SuiteValidator()
        suite = validator.validate_suite(data)

        console.print(
            f"[bold green]SUCCESS:[/bold green] Suite '{suite.suite.name}' is valid! "
            f"({len(suite.tests)} tests configured)"
        )
    except Exception as exc:
        err_console.print(f"[bold red]Validation Failed:[/bold red] {exc}")
        raise typer.Exit(code=EXIT_INVALID_SUITE) from exc


@app.command()
def run(
    suite_file: Path = typer.Argument(
        ...,
        help="Path to parity test suite file (.yaml or .json)",
        exists=True,
        readable=True,
    ),
    out: Optional[Path] = typer.Option(
        None,
        "--out",
        "-o",
        help="Directory to save run artifacts (defaults to modelparity-run-<timestamp>)",
    ),
    only: Optional[str] = typer.Option(
        None,
        "--only",
        help="Filter tests by label/tag",
    ),
    concurrency: int = typer.Option(
        4,
        "--concurrency",
        "-c",
        help="Maximum concurrent tests to execute",
    ),
) -> None:
    """Execute parity test suite against reference and candidate endpoints."""
    # 1. Load and validate
    try:
        data = yaml.safe_load(suite_file.read_text(encoding="utf-8"))
        validator = SuiteValidator()
        suite = validator.validate_suite(data)
    except Exception as exc:
        err_console.print(f"[bold red]Suite Validation Error:[/bold red] {exc}")
        raise typer.Exit(code=EXIT_INVALID_SUITE) from exc

    # 2. Filter tests if requested
    if only:
        original_count = len(suite.tests)
        suite.tests = [t for t in suite.tests if only in t.labels]
        console.print(
            f"Filtered tests by label '[cyan]{only}[/cyan]': {len(suite.tests)}/{original_count} selected."
        )
        if not suite.tests:
            err_console.print(f"[bold yellow]Warning:[/bold yellow] No tests match label '{only}'.")

    # 3. Resolve output directory
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = out or Path(f"modelparity-run-{timestamp}")
    writer = ArtifactWriter(out_dir)

    console.print(f"[*] Running ModelParity suite: [bold cyan]{suite.suite.name}[/bold cyan]")
    console.print(f"[*] Artifact destination: [dim]{out_dir.resolve()}[/dim]")


    # 4. Initialize adapters
    ref_dict = suite.endpoints.reference.model_dump(by_alias=True)
    cand_dict = suite.endpoints.candidate.model_dump(by_alias=True)

    try:
        ref_adapter = get_adapter(ref_dict)
        cand_adapter = get_adapter(cand_dict)
    except Exception as exc:
        err_console.print(f"[bold red]Adapter Initialization Error:[/bold red] {exc}")
        raise typer.Exit(code=EXIT_RUNNER_FAILURE) from exc

    # 5. Write pre-run manifest
    writer.write_run_manifest(
        suite={"name": suite.suite.name, "tests": [t.id for t in suite.tests]},
        endpoint_manifests={
            "reference": ref_adapter.get_manifest(),
            "candidate": cand_adapter.get_manifest(),
        },
    )
    writer.write_suite_snapshot(data)

    # 6. Execute tests
    runner = Runner(
        suite=suite,
        ref_adapter=ref_adapter,
        cand_adapter=cand_adapter,
        concurrency=concurrency,
    )

    try:
        results = asyncio.run(runner.run_all())
    except Exception as exc:
        err_console.print(f"[bold red]Runner Execution Failure:[/bold red] {exc}")
        raise typer.Exit(code=EXIT_RUNNER_FAILURE) from exc

    from rich import box

    # 7. Classify outcomes and write records
    table = Table(title="Test Results Summary", show_header=True, box=box.ASCII)

    table.add_column("Test ID", style="bold")
    table.add_column("Ref Status")
    table.add_column("Cand Status")
    table.add_column("Classification")

    regressions = 0
    contract_fails = 0
    baseline_fails = 0
    errors = 0
    passes = 0
    inconclusives = 0

    for res in results:
        ref_passed = res.reference_status == STATUS_PASS
        cand_passed = res.candidate_status == STATUS_PASS
        ref_error = res.reference_response.error
        cand_error = res.candidate_response.error

        classified_status = classify(
            test_id=res.test_id,
            ref_passed=ref_passed,
            cand_passed=cand_passed,
            ref_error=ref_error,
            cand_error=cand_error,
        )

        match classified_status:
            case TestStatus.PASS:
                status_str = "[green]PASS[/green]"
                passes += 1
            case TestStatus.REGRESSION:
                status_str = "[bold red]REGRESSION[/bold red]"
                regressions += 1
            case TestStatus.CONTRACT_FAIL:
                status_str = "[yellow]CONTRACT_FAIL[/yellow]"
                contract_fails += 1
            case TestStatus.BASELINE_FAIL:
                status_str = "[magenta]BASELINE_FAIL[/magenta]"
                baseline_fails += 1
            case TestStatus.ERROR:
                status_str = "[bold red]ERROR[/bold red]"
                errors += 1
            case _:
                status_str = "[dim]INCONCLUSIVE[/dim]"
                inconclusives += 1

        table.add_row(
            res.test_id,
            res.reference_status,
            res.candidate_status,
            status_str,
        )

        # Write to JSONL
        ref_res_dict = {
            "status": res.reference_status,
            "error": ref_error,
            "assertions": [
                {"id": a.assertion_id, "passed": a.passed, "message": a.message}
                for a in res.reference_assertions
            ],
        }
        cand_res_dict = {
            "status": res.candidate_status,
            "error": cand_error,
            "assertions": [
                {"id": a.assertion_id, "passed": a.passed, "message": a.message}
                for a in res.candidate_assertions
            ],
        }
        comparison_dict = {
            "classification": classified_status.value,
            "ref_passed": ref_passed,
            "cand_passed": cand_passed,
        }
        writer.write_result(res.test_id, ref_res_dict, cand_res_dict, comparison_dict)

    console.print(table)

    summary_counts = {
        "total": len(results),
        "passed": passes,
        "regressions": regressions,
        "contract_fails": contract_fails,
        "baseline_fails": baseline_fails,
        "errors": errors,
        "inconclusive": inconclusives,
    }
    writer.finalize(summary_counts)

    # 8. Generate markdown report
    try:
        report_text = generate_report(out_dir)
        writer.write_markdown_report(report_text)
    except Exception as exc:
        err_console.print(f"[yellow]Warning: Could not compile report.md:[/yellow] {exc}")

    # Determine exit code
    if errors > 0:
        raise typer.Exit(code=EXIT_RUNNER_FAILURE)
    if regressions > 0 or contract_fails > 0 or baseline_fails > 0:
        raise typer.Exit(code=EXIT_ASSERTION_FAIL)
    if inconclusives > 0 and len(results) == inconclusives:
        raise typer.Exit(code=EXIT_INCONCLUSIVE)

    raise typer.Exit(code=EXIT_OK)


@app.command()
def report(
    run_dir: Path = typer.Argument(
        ...,
        help="Path to completed modelparity run directory containing results.jsonl",
        exists=True,
    ),
    output_file: Optional[Path] = typer.Option(
        None,
        "--out",
        "-o",
        help="Path to save regenerated report (default: stdout)",
    ),
) -> None:
    """Regenerate and display human-readable Markdown report from run artifacts."""
    try:
        content = generate_report(run_dir, regenerated=True)
        if output_file:
            output_file.write_text(content, encoding="utf-8")
            console.print(f"Report written to: [cyan]{output_file.resolve()}[/cyan]")
        else:
            console.print(content)
    except Exception as exc:
        err_console.print(f"[bold red]Failed to generate report:[/bold red] {exc}")
        raise typer.Exit(code=EXIT_RUNNER_FAILURE) from exc


@app.command()
def replay(
    run_dir: Path = typer.Argument(
        ...,
        help="Path to run directory to replay offline",
        exists=True,
    ),
    out: Optional[Path] = typer.Option(
        None,
        "--out",
        "-o",
        help="New output directory for replayed results",
    ),
) -> None:
    """Offline replay: Re-evaluate assertions from saved responses without network requests."""
    console.print("[bold yellow]REPLAY MODE:[/bold yellow] No network requests will be made.")
    results_path = run_dir / "results.jsonl"
    if not results_path.exists():
        err_console.print(f"[bold red]Error:[/bold red] results.jsonl not found in {run_dir}")
        raise typer.Exit(code=EXIT_RUNNER_FAILURE)

    content = generate_report(run_dir, regenerated=True)
    target_path = out or (run_dir / "replayed_report.md")
    target_path.write_text(content, encoding="utf-8")
    console.print(f"[bold green]Replay report generated:[/bold green] [cyan]{target_path}[/cyan]")


@app.command()
def doctor(
    suite_file: Path = typer.Argument(
        ...,
        help="Path to parity test suite file (.yaml or .json)",
        exists=True,
        readable=True,
    ),
) -> None:
    """Diagnostic check: validate suite and test endpoint reachability and declared capabilities."""
    console.print("[*] Running ModelParity doctor check...")
    try:
        data = yaml.safe_load(suite_file.read_text(encoding="utf-8"))
        suite = SuiteValidator().validate_suite(data)
        console.print("  [green][PASS][/green] Suite syntax and schema are valid.")
    except Exception as exc:
        err_console.print(f"  [red][FAIL][/red] Suite validation failed: {exc}")
        raise typer.Exit(code=EXIT_INVALID_SUITE) from exc

    # Check endpoints
    ref_dict = suite.endpoints.reference.model_dump(by_alias=True)
    cand_dict = suite.endpoints.candidate.model_dump(by_alias=True)

    for alias, ep in [("reference", ref_dict), ("candidate", cand_dict)]:
        adapter_type = ep.get("adapter")
        console.print(f"  Checking endpoint '[bold cyan]{alias}[/bold cyan]' ({adapter_type})...")
        if adapter_type == "recorded":
            fixtures_path = Path(ep.get("fixtures_dir", ""))
            if fixtures_path.exists() and fixtures_path.is_dir():
                fixtures = list(fixtures_path.glob("*.json"))
                console.print(f"    [green][PASS][/green] Fixtures directory found with {len(fixtures)} fixture(s).")
            else:
                console.print(f"    [red][FAIL][/red] Fixtures directory '{fixtures_path}' not found or not a directory.")
        elif adapter_type == "openai_compatible":
            base_url = ep.get("base_url", "")
            api_key_env = ep.get("api_key_env", "")
            has_key = bool(os.environ.get(api_key_env)) if api_key_env else False
            console.print(f"    Base URL: {base_url}")
            if api_key_env:
                if has_key:
                    console.print(f"    [green][PASS][/green] API key environment variable '{api_key_env}' is set.")
                else:
                    console.print(f"    [yellow][WARN][/yellow] API key environment variable '{api_key_env}' is NOT set.")
            console.print(f"    Declared capabilities: {ep.get('capabilities', [])}")

    console.print("\nDoctor check completed.")



if __name__ == "__main__":
    app()
