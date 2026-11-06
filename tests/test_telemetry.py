import json
import re
from pathlib import Path
from typing import Any

import pytest

from rfp_intel.config import Settings
from rfp_intel.telemetry import build_tracer_provider, new_run_id, redact_text


def _run_two_spans(settings: Settings, run_id: str) -> list[dict[str, Any]]:
    provider = build_tracer_provider(settings, run_id)
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("extract") as parent:
        parent.set_attribute("rfp.bid_id", "Bid1")
        with tracer.start_as_current_span("search") as child:
            child.set_attribute("contact", "Write to buyer@dallasisd.org or call (972) 925-3700")
            child.set_attribute("query.ids", ["JA-207652", "060B5400007"])
            child.add_event("hit", {"text": "fax 214.932.5000"})
    provider.shutdown()
    path = settings.traces_dir / f"{run_id}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_jsonl_trace_has_parent_child_tree(settings: Settings) -> None:
    spans = _run_two_spans(settings, "run-1")
    by_name = {s["name"]: s for s in spans}
    assert set(by_name) == {"extract", "search"}
    assert by_name["search"]["parent_span_id"] == by_name["extract"]["span_id"]
    assert by_name["search"]["trace_id"] == by_name["extract"]["trace_id"]
    assert by_name["extract"]["parent_span_id"] is None
    assert by_name["extract"]["resource"]["rfp.run_id"] == "run-1"
    assert by_name["search"]["duration_ms"] >= 0


def test_redaction_masks_pii_in_attributes_and_events(settings: Settings) -> None:
    spans = _run_two_spans(settings, "run-2")
    search = next(s for s in spans if s["name"] == "search")
    assert search["attributes"]["contact"] == "Write to [EMAIL] or call [PHONE]"
    assert search["attributes"]["query.ids"] == ["JA-207652", "060B5400007"]
    assert search["events"][0]["attributes"]["text"] == "fax [PHONE]"


def test_redaction_can_be_turned_off(tmp_path: Path) -> None:
    raw = Settings(_env_file=None, traces_dir=tmp_path, trace_redact_pii=False)  # type: ignore[call-arg]
    spans = _run_two_spans(raw, "run-3")
    search = next(s for s in spans if s["name"] == "search")
    assert "buyer@dallasisd.org" in search["attributes"]["contact"]


@pytest.mark.parametrize(
    "text",
    [
        "JA-207652",
        "Sourcing 168884",
        "060B5400007",
        "E20P4600040",
        "379-BFNZ",
        "07/09/2024 03:00 PM EDT",
        "2024-07-09T14:00:00-05:00",
        "27-JUN-2024 14:00:00",
        "$250,000",
    ],
)
def test_redaction_leaves_identifiers_dates_and_money_alone(text: str) -> None:
    assert redact_text(text) == text


def test_run_id_is_sortable_and_unique() -> None:
    a, b = new_run_id(), new_run_id()
    assert re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{6}", a)
    assert a != b
