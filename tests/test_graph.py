"""The extraction graph end to end, with the scripted model and the fake search stack."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from rfp_intel.agents.graph import run_extraction
from rfp_intel.agents.llm import ScriptedLLM
from rfp_intel.agents.schema import BidResult
from rfp_intel.agents.services import Services
from rfp_intel.config import Settings
from rfp_intel.search.runtime import Runtime

from .agents_fakes import ADDENDUM, make_llm
from .conftest import build_sample_pdf, fake_runtime
from .test_html import PORTAL


@pytest.fixture
def bid_folder(data_dir: Path) -> Path:
    folder = data_dir / "BidA"
    build_sample_pdf(folder / "RFQ_2024-117.pdf")
    (folder / "portal.html").write_text(PORTAL, encoding="utf-8")
    (folder / "addendum_2.md").write_text(ADDENDUM, encoding="utf-8")
    return folder


@pytest.fixture
def runtime(settings: Settings) -> Iterator[Runtime]:
    with fake_runtime(settings) as rt:
        yield rt


def _services(settings: Settings, rt: Runtime, tmp_path: Path) -> Services:
    return Services.build(settings, rt, make_llm(), tmp_path / "out")


def calls(services: Services) -> list:  # type: ignore[type-arg]
    llm = services.llm.llm
    assert isinstance(llm, ScriptedLLM)
    return llm.calls


@pytest.fixture
def run(
    settings: Settings, runtime: Runtime, tmp_path: Path, bid_folder: Path
) -> tuple[BidResult, dict, Services]:  # type: ignore[type-arg]
    services = _services(settings, runtime, tmp_path)
    result, state = run_extraction(services, "BidA", run_id="run-1")
    return result, state, services


def test_plan_indexes_an_unindexed_bid_and_lists_documents(
    run: tuple[BidResult, dict, Services],
) -> None:  # type: ignore[type-arg]
    result, state, _ = run
    assert "ingest: 3 added" in " ".join(state["log"])
    assert {d.file for d in result.documents} == {
        "RFQ_2024-117.pdf",
        "portal.html",
        "addendum_2.md",
    }
    addendum = next(d for d in result.documents if d.file == "addendum_2.md")
    assert addendum.doc_type == "addendum" and addendum.addendum_number == 2
    agents = [step["agent"] for step in state["plan"]]
    assert agents[:2] == ["ingest", "reconcile"] and agents[-2:] == ["validate", "report"]
    assert agents.count("retrieve+extract") == 4  # one parallel branch per field group
    assert state["mode"] == "extract"


def test_all_twenty_fields_with_status_sources_confidence_notes(
    run: tuple[BidResult, dict, Services],
) -> None:  # type: ignore[type-arg]
    result, _, _ = run
    assert len(result.fields) == 20
    assert "Due Date" in result.fields and "Bid Bond Requirement" in result.fields
    for name, fr in result.fields.items():
        assert fr.status in ("found", "not_found", "conflict"), name
        assert 0 < fr.confidence <= 1 and fr.tier
        if fr.status == "found" and fr.key != "bid_summary":
            assert fr.sources, name
            for src in fr.sources:
                assert src.file and src.page >= 1 and src.quote
        if fr.status == "not_found":
            assert fr.value is None and str(fr.notes).startswith("Not found in documents."), name


def test_due_date_is_reconciled_without_the_model(run: tuple[BidResult, dict, Services]) -> None:  # type: ignore[type-arg]
    result, state, services = run
    due = result.by_key("due_date")
    assert due.value == "2024-07-16 14:00 CDT"
    assert due.normalized and due.normalized["display"] == "July 16, 2024, 2:00 PM CDT"
    assert due.tier == "D"  # the portal still shows July 9; the addendum explains the difference
    assert due.notes and "supersedes" in due.notes
    assert "Extended by Addendum 2 (original date: 2024-07-09 14:00 CDT)" in due.notes
    assert {s.file for s in due.sources} == {"addendum_2.md"}
    change = next(c for c in result.addendum_changes if c.field == "due_date")
    assert (change.operation, change.old_value, change.new_value, change.addendum_number) == (
        "replace", "July 9, 2024 2:00 PM CDT", "July 16, 2024 at 2:00 PM CST", 2,
    )  # fmt: skip
    assert "due_date" in state["resolved"] and "due_date" not in state["drafts"]
    assert result.by_key("pre_bid_meeting").value == "2024-06-10"
    # the model is never asked for the due date; the pre-bid meeting is asked with the
    # resolved date as a hint, for its place and attendance
    extraction = [c.user for c in calls(services) if c.schema == "GroupDraftOut"]
    assert not any("- due_date (" in u for u in extraction)
    assert any(
        "Already resolved from the documents and addenda: 2024-06-10" in u for u in extraction
    )


def test_validator_retry_loop(run: tuple[BidResult, dict, Services]) -> None:  # type: ignore[type-arg]
    result, state, services = run
    delivery = result.by_key("delivery_date")
    assert delivery.status == "found" and delivery.value == "Within 45 days of award"
    assert state["attempts"]["delivery_date"] == 2
    assert result.validation.retries == 1 and result.validation.passed_after_retry == 1
    retry_call = next(c for c in calls(services) if "was rejected by the validator" in c.user)
    assert "verbatim" in retry_call.user
    assert any("retry:delivery_date" in line and "attempt 2" in line for line in state["log"])
    # the retry searched with queries the cheap model rewrote from the validator's reason
    assert any(c.schema == "QueriesOut" and "delivery_date" not in c.user for c in calls(services))
    assert "delivery days after award" in state["evidence"]["delivery_date"]["queries"]


def test_addendum_events_are_applied_and_bad_quotes_dropped(
    run: tuple[BidResult, dict, Services],
) -> None:  # type: ignore[type-arg]
    result, state, _ = run
    kinds = {(e["field"], e["operation"]) for e in state["events"]}
    assert ("additional_documentation", "add_requirement") in kinds
    assert ("installation", "clarify") not in kinds  # its quote was not verbatim
    docs = result.by_key("additional_documentation")
    assert isinstance(docs.value, list) and "A signed copy of Addendum 2" in docs.value
    assert docs.tier == "A" and docs.status == "found"
    change = next(c for c in result.addendum_changes if c.field == "additional_documentation")
    assert change.source.file == "addendum_2.md" and change.source.quote.startswith(
        "Bidders must submit"
    )


def test_found_not_found_and_summary(run: tuple[BidResult, dict, Services]) -> None:  # type: ignore[type-arg]
    result, _, _ = run
    assert result.by_key("bid_number").value == "RFQ-117"
    assert result.by_key("bid_bond_requirement").value == "Not required"
    assert result.by_key("part_no").value == ["379-BFNZ", "WD22TB4"]
    payment = result.by_key("payment_terms")
    assert (
        payment.status == "not_found"
        and payment.tier == "NF-1"
        and "Searched" in str(payment.notes)
    )
    summary = result.by_key("bid_summary")
    assert (
        summary.status == "found"
        and summary.tier == "B"
        and summary.value
        and "July 16, 2024" in summary.value
    )
    v = result.validation
    assert v.fields == 20 and v.failed == 0
    assert v.passed + v.not_found + v.conflicts == 20


def test_result_file_usage_and_json_shape(
    run: tuple[BidResult, dict, Services], tmp_path: Path
) -> None:  # type: ignore[type-arg]
    result, state, _ = run
    path = tmp_path / "out" / "BidA.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data) >= {
        "bid_id",
        "run_id",
        "documents",
        "fields",
        "addendum_changes",
        "validation",
        "usage",
    }
    assert data["fields"]["Due Date"]["sources"][0]["quote"]
    assert data["fields"]["Due Date"]["key"] == "due_date"
    assert set(data["validation"]) >= {"passed", "failed", "not_found"}
    assert data == state["final_output"]
    assert result.usage["calls"] >= 6  # 1 addendum + 4 groups + 1 retry + 1 summary
    assert state["usage"]["input_tokens"] > 0


def test_resume_returns_the_finished_run_without_new_calls(
    settings: Settings, runtime: Runtime, tmp_path: Path, bid_folder: Path
) -> None:
    services = _services(settings, runtime, tmp_path)
    ckpt = tmp_path / "ckpt.sqlite"
    first, _ = run_extraction(services, "BidA", run_id="run-2", checkpoint_path=ckpt)
    n_calls = len(calls(services))
    again, _ = run_extraction(services, "BidA", run_id="run-2", resume=True, checkpoint_path=ckpt)
    assert again.by_key("due_date").value == first.by_key("due_date").value
    assert len(calls(services)) == n_calls


def test_addendum_events_are_cached_per_document(
    settings: Settings, runtime: Runtime, tmp_path: Path, bid_folder: Path
) -> None:
    services = _services(settings, runtime, tmp_path)
    run_extraction(services, "BidA", run_id="run-3")
    first_events = sum(1 for c in calls(services) if c.schema == "EventsOut")
    run_extraction(services, "BidA", run_id="run-4")
    second_events = sum(1 for c in calls(services) if c.schema == "EventsOut")
    assert first_events == 1 and second_events == 1
    assert list((settings.state_dir / "events").glob("*.json"))
