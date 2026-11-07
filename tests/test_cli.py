from pathlib import Path

import pytest
from typer.testing import CliRunner

from rfp_intel.cli import app

runner = CliRunner()


def test_help_lists_every_command() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in (
        "doctor",
        "index",
        "search",
        "extract",
        "ask",
        "eval",
        "serve",
        "compare",
        "go-no-go",
    ):
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


@pytest.mark.parametrize("command", [["extract", "BidA"], ["ask", "When is it due?"]])
def test_llm_commands_explain_the_missing_key(
    monkeypatch: pytest.MonkeyPatch, data_dir: Path, command: list[str]
) -> None:
    monkeypatch.setenv("RFP_DATA_DIR", str(data_dir))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("RFP_ANTHROPIC_API_KEY", "")
    result = runner.invoke(app, command)
    assert result.exit_code == 1
    assert "ANTHROPIC_API_KEY" in result.output


def test_qa_report_renders_the_log(tmp_path: Path) -> None:
    from rfp_intel.agents.qa import Citation, QAResult

    log = tmp_path / "qa.jsonl"
    result = QAResult(
        question="When is it due?", bid_id="B", found=True, answer="July 9.",
        citations=[Citation(bid_id="B", file="a.pdf", page="1", quote="Due  July 9.", evidence_id="e")],
        passages_reviewed=3, config="hybrid_facts", model="m", scope=["B"],
    )  # fmt: skip
    log.write_text(result.model_dump_json() + "\n", encoding="utf-8")
    out = tmp_path / "qa.md"
    assert runner.invoke(app, ["qa-report", "--log", str(log), "--out", str(out)]).exit_code == 0
    text = out.read_text(encoding="utf-8")
    assert "## 1. When is it due?" in text and "1. [B] a.pdf, p. 1: “Due July 9.”" in text


def test_deliverables_runs_every_step_in_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import json

    from rfp_intel import cli
    from rfp_intel.agents.schema import BidResult, ValidationTally

    data, outputs, traces = tmp_path / "bids", tmp_path / "outputs", tmp_path / "traces"
    for d in (data / "BidA", data / "BidB", outputs, traces):
        d.mkdir(parents=True)
    for name, value in (("RFP_DATA_DIR", data), ("RFP_OUTPUTS_DIR", outputs),
                        ("RFP_TRACES_DIR", traces)):  # fmt: skip
        monkeypatch.setenv(name, str(value))
    monkeypatch.chdir(tmp_path)
    steps: list[str] = []

    def fake_extract(bid: str, out: object, resume: object) -> None:
        steps.append(f"extract {bid}")
        record = BidResult(bid_id=bid, run_id=f"run-{bid}", generated_at="t", documents=[],
                           fields={}, validation=ValidationTally())  # fmt: skip
        (outputs / f"{bid}.json").write_text(record.model_dump_json(), encoding="utf-8")
        span = {"span_id": "1", "parent_span_id": None, "name": "agent.run", "start": "0",
                "duration_ms": 1.0, "status": "UNSET", "events": [], "resource": {},
                "attributes": {"rfp.run_id": f"run-{bid}"}}  # fmt: skip
        (traces / f"run-{bid}.jsonl").write_text(json.dumps(span) + "\n", encoding="utf-8")

    def fake_ask_batch(questions: Path, log_path: Path) -> None:
        steps.append("questions")
        log_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(cli, "extract", fake_extract)
    monkeypatch.setattr(cli, "ask_batch", fake_ask_batch)
    (tmp_path / "eval").mkdir()
    (tmp_path / "eval" / "gold.yaml").write_text("bids: {}\n", encoding="utf-8")
    result = runner.invoke(app, ["deliverables", "--gold", "eval/gold.yaml"])
    assert result.exit_code == 0, result.output
    assert steps == ["extract BidA", "extract BidB", "questions"]
    assert "run-BidB" in (tmp_path / "docs" / "trace_example.md").read_text(encoding="utf-8")
    assert (tmp_path / "docs" / "qa_log.md").exists()
    assert (tmp_path / "docs" / "eval" / "extraction.md").exists()


def test_go_no_go_and_compare_commands(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from .test_decisions import GOOD, record

    out = tmp_path / "outputs"
    out.mkdir()
    for bid, values in (("A", GOOD), ("B", {"bid_bond_requirement": "10% bid bond"})):
        (out / f"{bid}.json").write_text(record(bid, **values).model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("RFP_OUTPUTS_DIR", str(out))
    monkeypatch.setenv("RFP_TRACES_DIR", str(tmp_path / "traces"))
    result = runner.invoke(app, ["go-no-go", "B", "--as-of", "2024-06-01"])
    assert result.exit_code == 2 and "**NO-GO**" in result.output  # no-go exits 2
    report = tmp_path / "cmp.md"
    result = runner.invoke(app, ["compare", "A", "B", "--no-summary", "--out", str(report)])
    assert result.exit_code == 0, result.output
    assert "| Bid | Decision |" in report.read_text(encoding="utf-8")
    assert runner.invoke(app, ["compare", "A", "missing", "--no-summary"]).exit_code == 1
