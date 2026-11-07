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
