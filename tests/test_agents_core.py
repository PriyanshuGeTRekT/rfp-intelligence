"""Deterministic agent components: fields, confidence, reconciliation, validation, LLM seam."""

from collections.abc import Iterator
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from rfp_intel.agents import llm as llm_mod
from rfp_intel.agents.confidence import Evidence, score, tier
from rfp_intel.agents.evidence import EvidenceItem, EvidenceStore, FieldEvidence, gather
from rfp_intel.agents.fields import FieldCatalog, load_fields
from rfp_intel.agents.llm import AnthropicLLM, LLMError, ScriptedLLM, Usage, cost
from rfp_intel.agents.reconcile import (
    ChangeEvent,
    apply_text_events,
    display_datetime,
    events_from_facts,
    format_datetime,
    resolve_datetime,
)
from rfp_intel.agents.schema import FieldResult
from rfp_intel.agents.validate import FieldDraft, Quote, validate
from rfp_intel.config import Settings
from rfp_intel.facts.datetimes import find_datetimes
from rfp_intel.facts.extract import extract_facts
from rfp_intel.facts.labels import load_fact_types
from rfp_intel.facts.models import Fact, FactKind
from rfp_intel.facts.store import FactStore
from rfp_intel.ingestion.models import BidFolder
from rfp_intel.search.runtime import Runtime

from .conftest import REPO_ROOT, build_sample_pdf, fake_runtime


@pytest.fixture(scope="module")
def catalog() -> FieldCatalog:
    return load_fields(REPO_ROOT / "config" / "fields.yaml")


# ---------------------------------------------------------------------------------------------
# Fields


def test_twenty_fields_in_four_groups_plus_summary(catalog: FieldCatalog) -> None:
    assert len(catalog.fields) == 20
    assert catalog.extraction_groups == [
        "identity_dates",
        "commercial_legal",
        "product_specs",
        "parties_logistics",
    ]
    assert [f.key for f in catalog.group("report")] == ["bid_summary"]
    assert all(catalog.group(g) for g in catalog.extraction_groups)


def test_field_labels_exist_in_fact_config(catalog: FieldCatalog) -> None:
    labels = set(load_fact_types(REPO_ROOT / "config" / "fact_types.yaml").types)
    assert {t for f in catalog.fields for t in f.fact_types} <= labels


# ---------------------------------------------------------------------------------------------
# Confidence


@pytest.mark.parametrize(
    ("evidence", "expected"),
    [
        (Evidence(found=True, distinct_documents=2), "A"),
        (Evidence(found=True, set_by_addendum=True), "A"),
        (Evidence(found=True), "B"),
        (Evidence(found=True, assembled=True, distinct_documents=2), "C"),
        (Evidence(found=True, ocr=True, distinct_documents=3), "C"),
        (Evidence(found=True, grounded=False), "C"),
        (Evidence(found=True, explained_difference=True), "D"),
        (Evidence(found=True, unexplained_conflict=True), "E"),
        (Evidence(found=True, confirmed_by_addendum=True), "A"),  # B moved up one
        (Evidence(found=False, coverage_met=True), "NF-1"),
        (Evidence(found=False), "NF-2"),
        (Evidence(found=True, rejected=True), "X"),
    ],
)
def test_confidence_tiers(evidence: Evidence, expected: str) -> None:
    assert tier(evidence) == expected


def test_tier_numbers_are_ordered() -> None:
    values = [
        score(Evidence(found=True, **kw))[1]
        for kw in (
            {"distinct_documents": 2},
            {},
            {"assembled": True},
            {"explained_difference": True},
            {"unexplained_conflict": True},
        )
    ]
    assert values == sorted(values, reverse=True)


# ---------------------------------------------------------------------------------------------
# Reconciliation


def dt_fact(
    context: str,
    *,
    doc_type: str,
    file: str,
    label: str = "deadline",
    addendum: int | None = None,
    doc_date: str | None = None,
    block: int = 0,
) -> Fact:
    (m,) = find_datetimes(context)
    return Fact(
        fact_id=f"{file}:{block}", bid_id="B", doc_id=file, file_name=file, doc_type=doc_type,
        addendum_number=addendum, doc_date=doc_date, page=1, block_index=block,
        kind=FactKind.DATETIME, fact_types=[label], raw=context[m.start : m.end], start=m.start,
        end=m.end, value=m.value(), context=context,
    )  # fmt: skip


RFP = dt_fact("Solicitation Due | 27-JUN-2024 14:00:00", doc_type="rfp", file="rfp.pdf")
PORTAL_NEW = dt_fact(
    "Closing Date: 07/09/2024 03:00 PM EDT", doc_type="bid_page", file="portal.html"
)
ADD2 = dt_fact(
    "The new due date for this RFP will be July 9, 2024 at 2:00 PM CST.",
    doc_type="addendum",
    file="add2.pdf",
    addendum=2,
    doc_date="2024-06-27",
)


def test_addendum_replaces_and_portal_corroborates() -> None:
    facts = [RFP, PORTAL_NEW, ADD2]
    r = resolve_datetime("due_date", facts, events_from_facts(facts))
    assert r.value == "2024-07-09 14:00 CDT"
    assert r.normalized and r.normalized["utc"] == "2024-07-09T19:00:00Z"
    (change,) = r.changes
    assert (change.operation, change.old_value, change.new_value, change.addendum_number) == (
        "replace",
        "27-JUN-2024 14:00:00",
        "July 9, 2024 at 2:00 PM CST",
        2,
    )
    assert {s.file for s in r.sources} == {"add2.pdf", "portal.html"}
    assert any("Matches the portal" in n for n in r.notes)
    assert any("CDT applies" in n for n in r.notes)
    assert tier(r.evidence) == "A" and not r.conflict


def test_later_addendum_wins_regardless_of_input_order() -> None:
    add1 = dt_fact(
        "Proposals are now due July 2, 2024 at 2:00 PM CT.",
        doc_type="addendum",
        file="add1.pdf",
        addendum=1,
        doc_date="2024-06-13",
    )
    facts = [ADD2, add1, RFP]
    r = resolve_datetime("due_date", facts, events_from_facts(facts))
    assert r.value == "2024-07-09 14:00 CDT"
    assert [c.addendum_number for c in r.changes] == [1, 2]
    assert r.changes[1].old_value == "July 2, 2024 at 2:00 PM CT"


def test_addendum_repeating_the_date_confirms_it() -> None:
    same = dt_fact(
        "Reminder: proposals remain due 27-JUN-2024 14:00:00.",
        doc_type="addendum",
        file="add1.pdf",
        addendum=1,
    )
    facts = [RFP, same]
    r = resolve_datetime("due_date", facts, events_from_facts(facts))
    assert [c.operation for c in r.changes] == ["confirm"]
    assert r.value == "2024-06-27 14:00" and r.evidence.confirmed_by_addendum


def test_unexplained_portal_difference_is_a_conflict() -> None:
    portal_old = dt_fact(
        "Closing Date: 06/28/2024 03:00 PM EDT", doc_type="bid_page", file="portal.html"
    )
    r = resolve_datetime("due_date", [RFP, portal_old], [])
    assert r.conflict and tier(r.evidence) == "E"
    assert any("no document or addendum explains" in n for n in r.notes)


def test_stale_portal_is_explained_by_the_addendum() -> None:
    portal_old = dt_fact(
        "Closing Date: 06/27/2024 03:00 PM EDT", doc_type="bid_page", file="portal.html"
    )
    facts = [RFP, portal_old, ADD2]
    r = resolve_datetime("due_date", facts, events_from_facts(facts))
    assert not r.conflict and tier(r.evidence) == "D"
    assert any("supersedes" in n for n in r.notes)


def test_date_from_document_time_from_portal() -> None:
    doc = dt_fact("PROPOSAL DUE | 06/10/2024", doc_type="rfp", file="porfp.pdf")
    portal = dt_fact(
        "Closing Date: 06/10/2024 02:00 PM EDT", doc_type="bid_page", file="portal.html"
    )
    r = resolve_datetime("due_date", [doc, portal], [])
    assert r.value == "2024-06-10 14:00 EDT"
    assert r.evidence.assembled and tier(r.evidence) == "C"
    assert {s.file for s in r.sources} == {"porfp.pdf", "portal.html"}


def test_portal_only_and_nothing() -> None:
    r = resolve_datetime("due_date", [PORTAL_NEW], [])
    assert r.value == "2024-07-09 15:00 EDT" and any("Only the portal" in n for n in r.notes)
    none = resolve_datetime("pre_bid_meeting", [RFP], [])
    assert none.value is None and not none.evidence.found


def test_format_datetime() -> None:
    assert format_datetime({"date": "2024-07-09"}) == "2024-07-09"
    value = {"date": "2024-07-09", "time": "09:05", "tz_text": "ET"}
    assert format_datetime(value) == "2024-07-09 09:05 ET"
    assert display_datetime(value) == "July 9, 2024, 9:05 AM ET"
    assert display_datetime({"date": "2024-07-09", "time": "00:00"}) == "July 9, 2024, 12:00 AM"


def _event(
    op: str, text: str | None, n: int, seq: int = 0, field: str = "additional_documentation"
) -> ChangeEvent:
    return ChangeEvent(
        bid_id="B", file_name=f"add{n}.pdf", page=1, addendum_number=n, doc_date=date(2024, 6, n),
        seq=seq, field=field, operation=op, new_text=text, quote=text or "q", origin="llm",  # type: ignore[arg-type]
    )  # fmt: skip


def test_text_events_fold_in_order() -> None:
    events = [
        _event("add_requirement", "Signed Addendum 2 acknowledgement", 2),
        _event("add_requirement", "Form 1295", 1),
        _event("clarify", "Etching is required on laptops only", 1, seq=1),
        _event("add_requirement", "Form 1295", 2, seq=1),  # duplicate: no change
    ]
    value, changes, notes = apply_text_events("additional_documentation", ["W-9"], events)
    assert value == ["W-9", "Form 1295", "Signed Addendum 2 acknowledgement"]
    assert [c.operation for c in changes] == [
        "add_requirement",
        "clarify",
        "add_requirement",
        "add_requirement",
    ]
    assert notes == ["Addendum 1: Etching is required on laptops only"]
    replaced, _, _ = apply_text_events(
        "installation",
        "None",
        [_event("replace", "White glove deployment", 1, field="installation")],
    )
    assert replaced == "White glove deployment"


def test_real_bids_due_dates(bid1_folder: BidFolder, bid2_folder: BidFolder) -> None:
    config = load_fact_types(REPO_ROOT / "config" / "fact_types.yaml")
    f1 = [f for d in bid1_folder.documents for f in extract_facts(d, config)]
    r1 = resolve_datetime("due_date", f1, events_from_facts(f1))
    assert r1.value == "2024-07-09 14:00 CDT" and tier(r1.evidence) == "A"
    assert r1.changes[0].old_value == "27-JUN-2024 14:00:00"
    pre = resolve_datetime("pre_bid_meeting", f1, events_from_facts(f1))
    assert pre.value == "2024-06-10 14:00 CDT"
    assert any(n.startswith("Extended by Addendum 2 (original date: 2024-06-27") for n in r1.notes)
    f2 = [f for d in bid2_folder.documents for f in extract_facts(d, config)]
    r2 = resolve_datetime("due_date", f2, events_from_facts(f2))
    assert r2.value == "2024-06-10 14:00 EDT" and r2.evidence.assembled
    assert resolve_datetime("pre_bid_meeting", f2, []).value is None


# ---------------------------------------------------------------------------------------------
# Validation


@pytest.fixture
def store() -> EvidenceStore:
    s = EvidenceStore()
    s.add(EvidenceItem(evidence_id="e1", file="porfp.pdf", page_start=2, page_end=2, doc_type="rfp",
                       text="9. Delivery within 45 days of Award.\nPORFP Number: #E20P4600040 eMMA Project Number: BPM044557"))  # fmt: skip
    s.add(EvidenceItem(evidence_id="e2", file="add2.pdf", page_start=1, page_end=1, doc_type="addendum",
                       text="The new due date for this RFP will be July 9, 2024 at 2:00 PM CST."))  # fmt: skip
    return s


def _ev(field: str, queries: int = 3, typed: int = 0) -> FieldEvidence:
    return FieldEvidence(
        field=field,
        queries=[f"q{i}" for i in range(queries)],
        typed_fact_count=typed,
        evidence_ids=["e1", "e2"],
    )


def _check(
    catalog: FieldCatalog,
    store: EvidenceStore,
    field: str,
    value: Any,
    quotes: list[tuple[str, str]],
    **ev: int,
) -> tuple[bool, str | None]:
    draft = FieldDraft(
        field=field,
        status="found",
        value=value,
        quotes=[Quote(evidence_id=e, text=t) for e, t in quotes],
    )
    r = validate(draft, catalog.by_key(field), store, _ev(field, **ev))
    return r.passed, r.retry_reason


def test_verbatim_quotes_pass_and_paraphrases_fail(
    catalog: FieldCatalog, store: EvidenceStore
) -> None:
    assert _check(
        catalog,
        store,
        "delivery_date",
        "Within 45 days of award",
        [("e1", "Delivery within  45 days of award")],
    )[0]
    ok, reason = _check(
        catalog,
        store,
        "delivery_date",
        "Within 45 days of award",
        [("e1", "Delivery must happen within 45 days after award")],
    )
    assert not ok and "verbatim" in str(reason)
    ok, reason = _check(
        catalog, store, "delivery_date", "Within 45 days", [("missing", "Delivery within 45 days")]
    )
    assert not ok


def test_invented_numbers_fail(catalog: FieldCatalog, store: EvidenceStore) -> None:
    ok, reason = _check(
        catalog,
        store,
        "delivery_date",
        "Within 30 days of award",
        [("e1", "Delivery within 45 days of Award")],
    )
    assert not ok and "30" in str(reason)


def test_identifiers_and_dates(catalog: FieldCatalog, store: EvidenceStore) -> None:
    assert _check(
        catalog, store, "bid_number", "BPM044557", [("e1", "eMMA Project Number: BPM044557")]
    )[0]
    ok, reason = _check(
        catalog, store, "bid_number", "BPM044558", [("e1", "eMMA Project Number: BPM044557")]
    )
    assert not ok and "bpm044558" in str(reason)
    assert _check(
        catalog,
        store,
        "due_date",
        "2024-07-09 14:00 CDT",
        [("e2", "July 9, 2024 at 2:00 PM CST")],
    )[0]
    ok, reason = _check(
        catalog, store, "due_date", "July 10, 2024", [("e2", "July 9, 2024 at 2:00 PM CST")]
    )
    assert not ok and "date" in str(reason)


def test_list_items_need_support(catalog: FieldCatalog, store: EvidenceStore) -> None:
    good = ["PORFP Number E20P4600040"]
    assert _check(
        catalog, store, "additional_documentation", good, [("e1", "PORFP Number: #E20P4600040")]
    )[0]
    ok, reason = _check(
        catalog,
        store,
        "additional_documentation",
        ["Notarized performance bond"],
        [("e1", "PORFP Number: #E20P4600040")],
    )
    assert not ok and "not supported" in str(reason)


def test_words_run_together_by_ocr_still_support_a_value(catalog: FieldCatalog) -> None:
    # Bid3's scanned RFP: OCR dropped the spaces in "PROJECT TITLE: ... Computer Equipment".
    ocr = EvidenceStore()
    ocr.add(EvidenceItem(evidence_id="o1", file="rfp.pdf", page_start=1, page_end=1,
                         doc_type="rfp", text="PROJECT TITLE:BID#:RFP2025-003ComputerEquipment"))  # fmt: skip
    quote = [("o1", "PROJECT TITLE:BID#:RFP2025-003ComputerEquipment")]
    assert _check(catalog, ocr, "title", "Computer Equipment", quote)[0]
    ok, reason = _check(catalog, ocr, "title", "Network Switches", quote)
    assert not ok and "not supported" in str(reason)


def test_uncited_found_value_fails(catalog: FieldCatalog, store: EvidenceStore) -> None:
    ok, reason = _check(catalog, store, "title", "Dell laptops", [])
    assert not ok and "no quotes" in str(reason)


def test_not_found_needs_coverage(catalog: FieldCatalog, store: EvidenceStore) -> None:
    spec = catalog.by_key("bid_bond_requirement")
    draft = FieldDraft(field=spec.key, status="not_found")
    assert validate(draft, spec, store, _ev(spec.key, queries=4)).passed
    few = validate(draft, spec, store, _ev(spec.key, queries=1))
    assert not few.passed and "searches" in str(few.retry_reason)
    typed = validate(draft, spec, store, _ev(spec.key, queries=4, typed=2))
    assert not typed.passed and "2 labelled facts" in str(typed.retry_reason)


# ---------------------------------------------------------------------------------------------
# Evidence gathering


@pytest.fixture
def indexed(settings: Settings, data_dir: Path) -> Iterator[Runtime]:
    build_sample_pdf(data_dir / "BidA" / "rfq.pdf")
    with fake_runtime(settings) as rt:
        rt.indexer().index_folder(data_dir / "BidA")
        yield rt


def test_gather_includes_chunks_holding_typed_facts(
    indexed: Runtime, settings: Settings, catalog: FieldCatalog
) -> None:
    store = EvidenceStore()
    with FactStore(settings.db_path) as facts:
        ev = gather(indexed.engine(), facts, store, "BidA", catalog.by_key("due_date"))
    assert ev.typed_fact_count == 1
    assert ev.candidates[0].raw == "July 9, 2024 2:00 PM CDT"
    texts = [store.get(i).text for i in ev.evidence_ids]  # type: ignore[union-attr]
    assert any("Quotes Due | July 9, 2024 2:00 PM CDT" in t for t in texts)
    assert ev.queries[0] == "Due Date" and len(ev.queries) >= 3
    assert not ev.coverage_met(
        catalog.by_key("due_date")
    )  # typed facts exist, so "not found" is not allowed


def test_gather_for_an_absent_field_meets_coverage(
    indexed: Runtime, settings: Settings, catalog: FieldCatalog
) -> None:
    spec = catalog.by_key("bid_bond_requirement")
    with FactStore(settings.db_path) as facts:
        ev = gather(indexed.engine(), facts, EvidenceStore(), "BidA", spec)
    assert ev.typed_fact_count == 0 and ev.coverage_met(spec)
    assert "queries" in ev.coverage_note()


# ---------------------------------------------------------------------------------------------
# LLM seam


class Answer(BaseModel):
    text: str


def test_scripted_llm_records_calls() -> None:
    llm = ScriptedLLM({"Answer": lambda system, user: Answer(text=user.upper())})
    out, usage = llm.structured(system="sys", user="hello", schema=Answer, model="claude-opus-5-5")
    assert out.text == "HELLO" and usage.calls == 1
    assert llm.calls[0].schema == "Answer" and llm.calls[0].user == "hello"
    with pytest.raises(LLMError):
        llm.structured(system="s", user="u", schema=FieldDraft, model="m")


def test_usage_and_cost() -> None:
    u = Usage(calls=1, input_tokens=1_000_000, output_tokens=100_000, cache_read_tokens=1_000_000)
    assert cost("claude-opus-5-5", u) == pytest.approx(4.0 + 2.0 + 0.4)
    total = Usage()
    total.add(Usage(calls=1, input_tokens=10, cost_usd=0.5))
    total.add(Usage(calls=2, output_tokens=5, cost_usd=0.25))
    assert (total.calls, total.input_tokens, total.output_tokens, total.cost_usd) == (
        3,
        10,
        5,
        0.75,
    )


class _FakeMessages:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes
        self.requests: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class RateLimitError(Exception):  # same name as the SDK's transient error
    pass


def _response(parsed: Any, stop: str = "end_turn") -> SimpleNamespace:
    usage = SimpleNamespace(
        input_tokens=1000,
        output_tokens=200,
        cache_read_input_tokens=5000,
        cache_creation_input_tokens=0,
    )
    return SimpleNamespace(parsed_output=parsed, stop_reason=stop, usage=usage)


def test_anthropic_client_request_shape_retry_and_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: None)
    messages = _FakeMessages([RateLimitError("slow down"), _response(Answer(text="ok"))])
    client = AnthropicLLM("unused", client=SimpleNamespace(messages=messages))
    out, usage = client.structured(
        system="instructions",
        user="question",
        schema=Answer,
        model="claude-opus-5-5",
        effort="high",
    )
    assert out.text == "ok" and len(messages.requests) == 2
    req = messages.requests[-1]
    assert req["output_format"] is Answer and req["output_config"] == {"effort": "high"}
    assert req["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "temperature" not in req and "thinking" not in req
    assert usage.cache_read_tokens == 5000 and usage.cost_usd > 0

    for outcome, message in (
        (_response(None, stop="refusal"), "declined"),
        (_response(None, stop="max_tokens"), "truncated"),
        (_response(None), "did not match"),
    ):
        bad = AnthropicLLM("unused", client=SimpleNamespace(messages=_FakeMessages([outcome])))
        with pytest.raises(LLMError, match=message):
            bad.structured(system="s", user="u", schema=Answer, model="claude-opus-5-5")

    fatal = AnthropicLLM(
        "unused", client=SimpleNamespace(messages=_FakeMessages([ValueError("bad request")]))
    )
    with pytest.raises(ValueError):
        fatal.structured(system="s", user="u", schema=Answer, model="claude-opus-5-5")


def test_model_events_restating_a_date_change_are_dropped() -> None:
    from rfp_intel.agents.reconcile import drop_restated_dates

    date_event = _event("replace", "July 9, 2024 at 2:00 PM CST", 2, field="due_date")
    misfiled = _event("replace", "July 9, 2024 at 2:00 PM CST", 2, field="term_of_bid")
    misfiled = misfiled.model_copy(
        update={"quote": "The new due date for this RFP will be July 9, 2024 at 2:00 PM CST."}
    )
    other = _event("add_requirement", "Signed Addendum 2", 2)
    assert drop_restated_dates([misfiled, other], [date_event]) == [other]


def test_values_use_plain_spaces_and_hyphens() -> None:
    nbsp, nb_hyphen = chr(0x00A0), chr(0x2011)
    fr = FieldResult(key="bid_summary", value=f"due June{nbsp}10, a 3{nb_hyphen}year warranty",
                     status="found", confidence=0.9, tier="B")  # fmt: skip
    assert fr.value == "due June 10, a 3-year warranty"
    items = FieldResult(key="model_no", value=[f"Dock{nbsp}WD22TB4"], status="found",
                        confidence=0.9, tier="B")  # fmt: skip
    assert items.value == ["Dock WD22TB4"]


def test_a_product_label_may_carry_numbers_from_the_passages(catalog: FieldCatalog) -> None:
    # Bid2: the definition asks to prefix each spec with its product when there are several, so
    # the model wrote "Dell Latitude 5550 - ...", and "5550" is in the passage, not the quote.
    specs = EvidenceStore()
    specs.add(EvidenceItem(evidence_id="e1", file="specs.pdf", page_start=1, page_end=1,
                           doc_type="specs", text="Dell Latitude 5550\n16 GB: 2 x 8 GB, DDR5"))  # fmt: skip
    specs.add(EvidenceItem(evidence_id="e2", file="porfp.pdf", page_start=3, page_end=3,
                           doc_type="rfp", text="Dell Limited Hardware Warranty - 3 Years"))  # fmt: skip
    quotes = [("e1", "16 GB: 2 x 8 GB, DDR5"), ("e2", "Dell Limited Hardware Warranty - 3 Years")]
    labelled = ["Dell Latitude 5550 - 16 GB: 2 x 8 GB, DDR5",
                "Dell Latitude 5550 - Dell Limited Hardware Warranty - 3 Years"]  # fmt: skip
    assert _check(catalog, specs, "product_specification", labelled, quotes)[0]
    # A number the spec itself claims must still be quoted, and a label's must be in a passage.
    ok, reason = _check(catalog, specs, "product_specification",
                        ["Dell Latitude 5550 - 32 GB: 2 x 8 GB, DDR5"], quotes)  # fmt: skip
    assert not ok and "32" in str(reason)
    ok, reason = _check(catalog, specs, "product_specification",
                        ["Dell Latitude 7450 - 16 GB: 2 x 8 GB, DDR5"], quotes)  # fmt: skip
    assert not ok and "7450" in str(reason)
