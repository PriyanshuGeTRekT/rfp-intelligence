"""Failure handling, question routing, batching, budgets and cross-field checks."""

from collections.abc import Iterator
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from rfp_intel.agents import consistency
from rfp_intel.agents.evidence import EvidenceItem, FactCandidate
from rfp_intel.agents.fields import load_fields
from rfp_intel.agents.graph import graph_mermaid, run_extraction, run_question
from rfp_intel.agents.guarded import GuardedLLM
from rfp_intel.agents.llm import LLMError, ScriptedLLM, estimate_tokens
from rfp_intel.agents.nodes.extract import (
    MIN_PASSAGE_TOKENS,
    _budget,
    _distinct_first,
    _fit_candidates,
    _fixed_tokens,
    _holding_candidates,
)
from rfp_intel.agents.nodes.orchestrator import extraction_tasks
from rfp_intel.agents.outputs import GroupDraftOut
from rfp_intel.agents.prompts import candidate_sections, fit_passages, passage_tokens
from rfp_intel.agents.schema import DocumentInfo, FieldResult
from rfp_intel.agents.services import Services
from rfp_intel.config import Settings
from rfp_intel.search.runtime import Runtime

from .agents_fakes import ADDENDUM, Extractor, answering, events, rewrite, summary
from .conftest import REPO_ROOT, build_sample_pdf, fake_runtime
from .test_html import PORTAL

CATALOG = load_fields(REPO_ROOT / "config" / "fields.yaml")


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


class Flaky:
    """Fails the first `failures` extraction calls with a timeout, then behaves."""

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.extractor = Extractor()

    def __call__(self, system: str, user: str) -> BaseModel:
        if self.failures > 0:
            self.failures -= 1
            raise TimeoutError("the provider did not answer in 120 s")
        return self.extractor(system, user)


def _llm(extract: object) -> ScriptedLLM:
    return ScriptedLLM(
        {"GroupDraftOut": extract, "EventsOut": events, "SummaryOut": summary,
         "QueriesOut": rewrite}  # type: ignore[dict-item]
    )  # fmt: skip


def test_a_timed_out_batch_is_retried_not_fatal(
    settings: Settings, runtime: Runtime, bid_folder: Path, tmp_path: Path
) -> None:
    services = Services.build(settings, runtime, _llm(Flaky(failures=1)), tmp_path / "out")
    result, _state = run_extraction(services, bid_folder, run_id="flaky")
    assert len(result.fields) == 20 and result.validation.failed == 0
    assert any("TimeoutError" in e for e in result.errors)  # recorded, not raised
    assert result.validation.retries >= 1


def test_a_model_that_always_fails_still_produces_a_record(
    settings: Settings, runtime: Runtime, bid_folder: Path, tmp_path: Path
) -> None:
    broken = ScriptedLLM({})  # every call raises LLMError
    services = Services.build(settings, runtime, broken, tmp_path / "out")
    result, _ = run_extraction(services, bid_folder, run_id="broken")
    assert len(result.fields) == 20
    due = result.by_key("due_date")
    assert due.status == "found" and due.value == "2024-07-16 14:00 CDT"  # no model needed
    failed = result.by_key("bid_number")
    assert failed.status == "failed" and failed.tier == "X"
    assert str(failed.notes).startswith("Extraction failed: the model call failed")
    assert result.by_key("bid_summary").status == "failed"
    assert result.validation.failed >= 15 and (tmp_path / "out" / "BidA.json").exists()
    assert any("addendum addendum_2.md: failed" in e for e in result.errors)


def test_questions_go_through_the_graph(
    settings: Settings, runtime: Runtime, bid_folder: Path, tmp_path: Path
) -> None:
    runtime.indexer().index_folder(bid_folder)
    services = Services.build(settings, runtime, answering(verbatim=True), tmp_path)
    result, state = run_question(services, "How soon must equipment be delivered?", bid_id="BidA")
    assert state["mode"] == "ask" and [s["agent"] for s in state["plan"]] == ["answer"]
    assert result.found and result.citations[0].quote == "within 45 days of award."
    assert state["final_output"]["answer"] == result.answer


def test_a_repeated_question_is_answered_from_the_semantic_cache(
    settings: Settings, runtime: Runtime, bid_folder: Path, tmp_path: Path
) -> None:
    runtime.indexer().index_folder(bid_folder)
    asker = answering(verbatim=True)
    services = Services.build(settings, runtime, asker, tmp_path)
    first, _ = run_question(services, "How soon must equipment be delivered?", bid_id="BidA")
    again, _ = run_question(services, "How soon must equipment be delivered ?", bid_id="BidA")
    assert len(asker.calls) == 1  # the second answer made no model call
    assert again.cached_from == first.question and again.cache_similarity is not None
    assert again.answer == first.answer and again.citations == first.citations
    assert again.usage == {}
    other_bid, _ = run_question(services, "How soon must equipment be delivered?", bid_id=None)
    assert other_bid.cached_from is None and len(asker.calls) == 2  # another scope misses


def test_the_cache_misses_when_numbers_or_documents_differ(tmp_path: Path) -> None:
    from rfp_intel.agents.qa import QAResult
    from rfp_intel.agents.qa_cache import SemanticCache, anchors
    from rfp_intel.search.embed import HashingDense

    dense = HashingDense()
    cache = SemanticCache(tmp_path / "c.sqlite", dense.embed_query, threshold=0.9)
    answer = QAResult(question="q", bid_id=None, found=True, answer="10%", passages_reviewed=1,
                      config="hybrid")  # fmt: skip
    cache.store("Is a bid bond required for Bid1?", "*", "fp1", answer)
    assert cache.lookup("Is a bid bond required for Bid1?", "*", "fp1") is not None
    assert cache.lookup("Is a bid bond required for Bid2?", "*", "fp1") is None  # anchors differ
    assert cache.lookup("Is a bid bond required for Bid1?", "*", "fp2") is None  # re-indexed
    assert cache.lookup("Who is the contact for Bid1?", "*", "fp1") is None  # too different
    assert anchors("What changed in Addendum 2 for Bid1?") == "2 bid1"
    cache.close()


def test_batches_respect_the_batch_size() -> None:
    tasks = extraction_tasks(CATALOG, {}, batch_size=2)
    assert all(len(t.fields) <= 2 for t in tasks)
    assert sorted(k for t in tasks for k in t.fields) == sorted(
        f.key for f in CATALOG.fields if f.type != "summary"
    )
    assert {t.batch for t in tasks} >= {"identity_dates", "identity_dates/2"}
    resolved = {
        "due_date": {"value": "2024-07-16 14:00 CDT"},
        "pre_bid_meeting": {"value": "2024-06-10"},
    }
    keys = [k for t in extraction_tasks(CATALOG, resolved, 5) for k in t.fields]
    assert "due_date" not in keys and "pre_bid_meeting" in keys  # enriched, with a hint
    hinted = next(
        t for t in extraction_tasks(CATALOG, resolved, 5) if "pre_bid_meeting" in t.fields
    )
    assert hinted.hints == {"pre_bid_meeting": "2024-06-10"}


def _item(i: int, chars: int = 400) -> EvidenceItem:
    return EvidenceItem(evidence_id=f"e{i}", file="f.pdf", page_start=1, page_end=1,
                        doc_type="rfp", text="x" * chars)  # fmt: skip


def test_passages_fit_the_budget_without_starving_a_field() -> None:
    shared = _item(0)
    passages = {"a": [shared, _item(1), _item(2)], "b": [shared, _item(3), _item(4)]}
    kept = fit_passages(passages, budget_tokens=450)  # room for three 127-token passages
    assert [i.evidence_id for i in kept["a"]] == ["e0", "e1"]
    assert [i.evidence_id for i in kept["b"]] == ["e0", "e3"]  # the shared one is paid once
    assert fit_passages(passages, budget_tokens=10) == {"a": [], "b": []}


def test_every_field_gets_its_best_passage_even_when_passages_are_long() -> None:
    # Three fields whose best passages (about 600 tokens each) cannot all fit whole: each is
    # cut to an equal share instead of the last field getting nothing.
    passages = {k: [_item(i, chars=2_100)] for i, k in enumerate("abc")}
    kept = fit_passages(passages, budget_tokens=1_000)
    assert all(len(kept[k]) == 1 for k in "abc")
    for k, (item,) in kept.items():
        head = item.text.removesuffix(" […]")
        assert item.text.endswith(" […]") and passages[k][0].text.startswith(head)
    assert sum(passage_tokens(i) for (i,) in kept.values()) <= 1_000


def _fr(key: str, value: str, d: str | None = None) -> FieldResult:
    return FieldResult(key=key, value=value, status="found", confidence=0.95, tier="A",
                       normalized={"date": d} if d else None)  # fmt: skip


def test_consistency_checks_flag_dates_out_of_order() -> None:
    fields = {
        "due_date": _fr("due_date", "2024-07-09 14:00 CDT", "2024-07-09"),
        "pre_bid_meeting": _fr("pre_bid_meeting", "2024-07-20", "2024-07-20"),
        "delivery_date": _fr("delivery_date", "Deliver by June 1, 2024"),
    }
    docs = [
        DocumentInfo(file="rfp.pdf", doc_type="rfp", doc_date=date(2024, 6, 1), pages=10),
        DocumentInfo(file="add9.pdf", doc_type="addendum", doc_date=date(2024, 8, 1), pages=1),
    ]
    issues = consistency.check(fields, docs)
    assert {i.field for i in issues} == {"pre_bid_meeting", "delivery_date", "due_date"}
    consistency.apply(fields, issues)
    assert fields["pre_bid_meeting"].tier == "E"
    assert "Consistency check failed" in str(fields["pre_bid_meeting"].notes)
    ok = {
        "due_date": _fr("due_date", "x", "2024-07-09"),
        "pre_bid_meeting": _fr("p", "x", "2024-06-10"),
    }
    assert consistency.check(ok, docs[:1]) == []


def test_guarded_calls_turn_exceptions_into_outcomes() -> None:
    def boom(system: str, user: str) -> BaseModel:
        raise LLMError("output truncated at 8000 tokens")

    outcome = GuardedLLM(ScriptedLLM({"GroupDraftOut": boom})).call(
        system="s", user="u", schema=GroupDraftOut, model="m"
    )
    assert outcome.output is None and "truncated" in str(outcome.error) and not outcome.ok


def test_mermaid_shows_both_modes_and_the_retry_loop() -> None:
    mermaid = graph_mermaid()
    for edge in (
        "plan",
        "answer",
        "ingest",
        "reconcile",
        "retrieve",
        "extract",
        "validate",
        "report",
    ):
        assert edge in mermaid


def test_an_unseen_folder_anywhere_is_extracted_without_code_changes(
    settings: Settings, runtime: Runtime, bid_folder: Path, tmp_path: Path
) -> None:
    import shutil

    unseen = tmp_path / "elsewhere" / "County RFQ 2024-117"
    shutil.copytree(bid_folder, unseen)
    services = Services.build(settings, runtime, _llm(Extractor()), tmp_path / "out")
    result, _ = run_extraction(services, unseen, run_id="unseen")
    assert result.bid_id == "County RFQ 2024-117" and len(result.fields) == 20
    assert result.by_key("due_date").value == "2024-07-16 14:00 CDT"
    assert (tmp_path / "out" / "County RFQ 2024-117.json").exists()


def test_questions_use_the_reconciled_record_and_fact_chunks(
    settings: Settings, runtime: Runtime, bid_folder: Path, tmp_path: Path
) -> None:
    out = settings.outputs_dir
    run_extraction(Services.build(settings, runtime, _llm(Extractor()), out), bid_folder)
    asker = answering(verbatim=True)
    services = Services.build(settings, runtime, asker, out)
    run_question(services, "When are quotes due after the addendum?", bid_id="BidA")
    prompt = asker.calls[-1].user
    assert "Reconciled values:" in prompt and "BidA · Due Date: 2024-07-16 14:00 CDT" in prompt
    assert "Extended by Addendum 2" in prompt
    assert "addendum_2.md" in prompt  # the chunk holding the new deadline is always included


def test_absent_after_reviewing_the_labelled_facts_is_an_unverified_not_found() -> None:
    from rfp_intel.agents.assemble import from_draft
    from rfp_intel.agents.evidence import EvidenceStore, FieldEvidence
    from rfp_intel.agents.validate import Check, FieldDraft, ValidationResult

    spec = CATALOG.by_key("term_of_bid")
    evidence = FieldEvidence(field=spec.key, queries=["a", "b", "c"], typed_fact_count=4)
    draft = FieldDraft(field=spec.key, status="not_found", notes="Only reporting periods.")
    rejected = ValidationResult(
        field=spec.key, passed=False, checks=[Check(name="not_found_justified", passed=False)]
    )
    fr, _ = from_draft(spec, draft, rejected, evidence, [], EvidenceStore())
    assert (fr.status, fr.tier, fr.value) == ("not_found", "NF-2", None)
    assert str(fr.notes).startswith("Not found in documents.") and "4 labelled facts" in str(
        fr.notes
    )

    errored = draft.model_copy(update={"error": "timeout"})
    fr, _ = from_draft(spec, errored, rejected, evidence, [], EvidenceStore())
    assert fr.status == "failed"  # a model failure is never reported as an absence


def test_questions_use_the_qa_model_when_one_is_set(
    settings: Settings, runtime: Runtime, bid_folder: Path, tmp_path: Path
) -> None:
    runtime.indexer().index_folder(bid_folder)
    asker = answering(verbatim=True)
    qa_settings = settings.model_copy(update={"qa_model": "small-qa-model"})
    result, _ = run_question(Services.build(qa_settings, runtime, asker, tmp_path), "Delivery?")
    assert asker.calls[-1].model == "small-qa-model" and result.model == "small-qa-model"


def _cand(i: int, context: str = "c" * 200) -> FactCandidate:
    return FactCandidate(fact_id=f"f{i}", kind="identifier", raw=f"SKU-{i}", value={"id": f"SKU-{i}"},
                         file="specs.pdf", page=1, doc_type="specs", context=context)  # fmt: skip


def test_fields_sharing_candidates_get_them_listed_once() -> None:
    shared = [_cand(1), _cand(2)]
    model_no, part_no = CATALOG.by_key("model_no"), CATALOG.by_key("part_no")
    text = "\n".join(
        candidate_sections([model_no, part_no], {"model_no": shared, "part_no": shared})
    )
    assert text.count('identifier "SKU-1"') == 1
    assert "Candidate facts for part_no: the same as for model_no." in text


def test_candidates_are_trimmed_to_leave_room_for_passages(settings: Settings) -> None:
    # 60 identifier candidates (about 80 tokens each) would fill the whole prompt cap.
    settings = settings.model_copy(update={"llm_max_prompt_tokens": 3_800})
    services = SimpleNamespace(settings=settings)
    fields = [CATALOG.by_key("model_no"), CATALOG.by_key("part_no"), CATALOG.by_key("product")]
    many = [_cand(i) for i in range(60)]
    kept = _fit_candidates(services, fields, {"model_no": many, "part_no": many, "product": []})  # type: ignore[arg-type]
    assert 0 < len(kept["model_no"]) < 60 and kept["part_no"] == kept["model_no"]
    assert _budget(services, fields, kept) >= MIN_PASSAGE_TOKENS  # type: ignore[arg-type]
    total = (
        _fixed_tokens(fields)
        + estimate_tokens("\n".join(candidate_sections(fields, kept)))
        + MIN_PASSAGE_TOKENS
    )
    assert total <= settings.llm_max_prompt_tokens


def _qty(i: int, raw: str, context: str) -> FactCandidate:
    return FactCandidate(fact_id=f"q{i}", kind="quantity", raw=raw, value={"qty": raw},
                         file="rfp.pdf", page=34, doc_type="rfp", context=context)  # fmt: skip


def test_distinct_values_come_before_repeats() -> None:
    # Bid1's price schedule: "1" on every category line before the estimated quantities.
    cands = [_qty(i, "1", f"{i} Tier {i} line | 1 | Each") for i in range(1, 15)]
    cands += [_qty(20, "50,000", "15.01 Tier 1 Small | 50,000 | Each"),
              _qty(21, "5,000", "16.01 Tier 3 Student | 5,000 | Each")]  # fmt: skip
    assert [c.raw for c in _distinct_first(cands)][:3] == ["1", "50,000", "5,000"]


def test_a_passage_holding_a_kept_candidate_is_citable() -> None:
    shown = EvidenceItem(evidence_id="p34", file="rfp.pdf", page_start=34, page_end=34,
                         doc_type="rfp", text="2.1 Line Information | 1 Tier 1 Small | 1 | Each")  # fmt: skip
    held = EvidenceItem(evidence_id="p35", file="rfp.pdf", page_start=34, page_end=35,
                        doc_type="rfp", text="Line | Item | Target Quantity\n15.01 Tier 1 Small | 50,000 | Each\nStudent Chromebook Laptop (Touch)")  # fmt: skip
    other = EvidenceItem(evidence_id="p9", file="rfp.pdf", page_start=9, page_end=9,
                         doc_type="rfp", text="Proposals must be submitted electronically.")  # fmt: skip
    kept = [
        _qty(20, "50,000", "15.01 Tier 1 Small | 50,000 | Each Student Chromebook Laptop (Touch)")
    ]
    assert _holding_candidates([shown, held, other], kept) == ["p35"]
