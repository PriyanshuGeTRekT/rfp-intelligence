from pathlib import Path

import pytest
from typer.testing import CliRunner

from rfp_intel.cli import app
from rfp_intel.config import Settings
from rfp_intel.telemetry import build_tracer_provider
from rfp_intel.trace_render import load_spans, render_trace


@pytest.fixture
def trace_file(settings: Settings) -> Path:
    provider = build_tracer_provider(settings, "run-x")
    tracer = provider.get_tracer("t")
    with tracer.start_as_current_span("agent.run") as run:
        run.set_attribute("rfp.bid_id", "Bid1")
        with tracer.start_as_current_span("agent.extract.identity_dates") as ex:
            ex.set_attribute("agent.fields", ["bid_number", "title"])
            ex.set_attribute("llm.cost_usd", 0.0123)
            ex.set_attribute("search.filters", "hidden")
            with tracer.start_as_current_span("search") as s:
                s.set_attribute("search.query", "solicitation number")
                s.set_attribute("search.top_chunk_ids", ["a", "b"])
        with tracer.start_as_current_span("agent.validate") as v:
            v.set_attribute("agent.failed", ["delivery_date"])
            v.add_event("retry", {"field": "delivery_date", "reason": "quote not verbatim"})
    provider.shutdown()
    return settings.traces_dir / "run-x.jsonl"


def test_render_tree_order_attributes_and_summary(trace_file: Path) -> None:
    text = render_trace(load_spans(trace_file))
    lines = text.splitlines()
    assert lines[0] == "# Trace run-x"
    assert "4 spans, 1 with model usage, estimated cost $0.0123" in lines[2]
    tree = [ln for ln in lines if ln and not ln.startswith(("#", "```")) and "spans" not in ln]
    assert tree[0].startswith("agent.run (")
    assert tree[1] == "  rfp.bid_id=Bid1"
    extract = next(
        i for i, ln in enumerate(tree) if ln.startswith("  agent.extract.identity_dates")
    )
    validate = next(i for i, ln in enumerate(tree) if ln.startswith("  agent.validate"))
    assert extract < validate  # children in start order
    assert any(ln.startswith("    search (") for ln in tree)  # grandchild indented twice
    assert '    agent.fields=["bid_number", "title"]' in tree
    assert "search.filters" not in text and "top_chunk_ids" not in text  # hidden attributes
    assert "    * retry: field=delivery_date, reason=quote not verbatim" in tree


def test_trace_command(
    trace_file: Path, settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RFP_TRACES_DIR", str(settings.traces_dir))
    out = tmp_path / "docs" / "trace.md"
    result = CliRunner().invoke(app, ["trace", "run-x", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert out.read_text(encoding="utf-8").startswith("# Trace run-x")
    assert CliRunner().invoke(app, ["trace", "nope"]).exit_code == 1


def test_full_model_calls_are_appended_once_per_kind() -> None:
    from rfp_intel.trace_render import render_trace

    def span(i: int, name: str, start: str) -> dict:  # type: ignore[type-arg]
        return {
            "span_id": str(i), "parent_span_id": "0", "name": name, "start": start,
            "duration_ms": 5.0, "status": "UNSET", "events": [], "resource": {},
            "attributes": {"llm.model": "m", "llm.input": f"prompt {i}", "llm.output": '{"a": 1}',
                           "llm.input_tokens": 10, "llm.output_tokens": 2},
        }  # fmt: skip

    root = {"span_id": "0", "parent_span_id": None, "name": "agent.run", "start": "0",
            "duration_ms": 50.0, "status": "UNSET", "events": [], "resource": {},
            "attributes": {"rfp.run_id": "run-x"}}  # fmt: skip
    text = render_trace(
        [root, span(1, "agent.extract.a", "1"), span(2, "agent.extract.b", "2"),
         span(3, "agent.summary", "3")]
    )  # fmt: skip
    assert "# Trace run-x" in text and "## Model calls in full" in text
    assert "### agent.extract.a" in text and "### agent.extract.b" not in text
    assert "prompt 1" in text and '"a": 1' in text and "### agent.summary" in text


def test_paths_under_the_working_directory_are_shown_relative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from rfp_intel.trace_render import scrub_paths

    monkeypatch.chdir(tmp_path)
    folder = str(tmp_path / "data" / "bids" / "Bid2")
    once = json.dumps({"folder": folder})
    twice = json.dumps({"agent.input": once})
    for text in (folder, once, twice):
        assert str(tmp_path) not in scrub_paths(text)
        assert json.dumps(str(tmp_path))[1:-1] not in scrub_paths(text)
    assert (
        json.loads(json.loads(scrub_paths(twice))["agent.input"])["folder"].replace("\\", "/")
        == "data/bids/Bid2"
    )
