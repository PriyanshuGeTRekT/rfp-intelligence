from pathlib import Path

import pytest
from typer.testing import CliRunner

from rfp_intel.cli import app

runner = CliRunner()


def test_help_lists_every_command() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("doctor", "index", "search", "extract", "ask", "eval", "serve"):
        assert command in result.output


def test_doctor_reports_bid_folders(monkeypatch: pytest.MonkeyPatch, data_dir: Path) -> None:
    monkeypatch.setenv("RFP_DATA_DIR", str(data_dir))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-print")
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "BidA" in result.output
    assert "sk-should-not-print" not in result.output


def test_doctor_fails_when_data_dir_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("RFP_DATA_DIR", str(tmp_path / "nope"))
    assert runner.invoke(app, ["doctor"]).exit_code == 1


def test_unbuilt_commands_say_so() -> None:
    result = runner.invoke(app, ["index", "Bid1"])
    assert result.exit_code == 2
