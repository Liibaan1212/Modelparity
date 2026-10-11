"""Integration tests for ModelParity CLI."""

from pathlib import Path
from typer.testing import CliRunner

from modelparity.cli import app

runner = CliRunner()


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "ModelParity" in result.output
    assert "init" in result.output
    assert "validate" in result.output
    assert "run" in result.output
    assert "report" in result.output
    assert "replay" in result.output
    assert "doctor" in result.output


def test_cli_init_and_validate(tmp_path: Path):
    suite_file = tmp_path / "parity.yaml"
    init_res = runner.invoke(app, ["init", "--out", str(suite_file)])
    assert init_res.exit_code == 0
    assert suite_file.exists()

    val_res = runner.invoke(app, ["validate", str(suite_file)])
    assert val_res.exit_code == 0
    assert "valid" in val_res.output.lower()


def test_cli_offline_demo_run():
    suite_path = Path("examples/offline-demo/parity.yaml")
    assert suite_path.exists()

    val_res = runner.invoke(app, ["validate", str(suite_path)])
    assert val_res.exit_code == 0

    doc_res = runner.invoke(app, ["doctor", str(suite_path)])
    assert doc_res.exit_code == 0

    # The offline demo has one intentional regression in json-contract-failure-demo
    run_res = runner.invoke(app, ["run", str(suite_path), "--out", "test-tmp-run"])
    assert run_res.exit_code == 1
    assert "json-product-extraction" in run_res.output
    assert "REGRESSION" in run_res.output
