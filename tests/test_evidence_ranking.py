"""How a field's evidence is ordered before the prompt budget cuts it, and the evidence-reach
evaluation that measures whether expected values reach the prompt."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from rfp_intel.agents.evidence import diversify
from rfp_intel.config import Settings
from rfp_intel.eval.evidence import evidence_reach, evidence_text, missing_patterns
from rfp_intel.eval.extraction import ExtractionGold, Rule
from rfp_intel.search.runtime import Runtime

from .agents_fakes import ADDENDUM
from .conftest import build_sample_pdf, fake_runtime
from .test_html import PORTAL


@pytest.fixture
def runtime(settings: Settings, data_dir: Path) -> Iterator[Runtime]:
    folder = data_dir / "BidA"
    build_sample_pdf(folder / "RFQ_2024-117.pdf")
    (folder / "portal.html").write_text(PORTAL, encoding="utf-8")
    (folder / "addendum_2.md").write_text(ADDENDUM, encoding="utf-8")
    with fake_runtime(settings) as rt:
        rt.indexer().index_folder(folder)
        yield rt


def test_diversify_moves_a_documents_extra_chunks_after_the_others() -> None:
    files = {"a1": "affidavit.pdf", "a2": "affidavit.pdf", "a3": "affidavit.pdf",
             "m1": "mercury.pdf", "r1": "rfp.pdf"}  # fmt: skip
    ranked = ["a1", "a2", "a3", "m1", "r1"]
    assert diversify(ranked, files) == ["a1", "a2", "m1", "r1", "a3"]
    one_doc = ["a1", "a2", "a3"]
    assert diversify(one_doc, files) == one_doc  # nothing else to make room for


def test_rerank_demotes_the_given_document_types(runtime: Runtime) -> None:
    engine = runtime.engine()
    hits = engine.search("delivery due date quotes", bid_id="BidA", k=10).hits
    ids = [h.chunk_id for h in hits]
    types = {h.chunk_id: h.doc_type for h in hits}
    assert "rfp" in types.values() and len(set(types.values())) > 1
    demoted = [c for c, _ in engine.rerank("delivery due date", ids, demote_doc_types=("rfp",))]
    first_rfp = next(i for i, c in enumerate(demoted) if types[c] == "rfp")
    # Overlap scores are below the 2.0 margin, so every other type now leads.
    assert all(types[c] != "rfp" for c in demoted[:first_rfp])
    assert all(types[c] == "rfp" for c in demoted[first_rfp:])


def test_missing_patterns_follow_the_gold_rule_semantics() -> None:
    prompt = "Proposals must remain valid for 90 days. PORFP Type: Fixed Price"
    assert missing_patterns(Rule(patterns=["fixed price", "90 days"]), prompt) == []
    assert missing_patterns(Rule(patterns=["fixed price", "30 days"]), prompt) == ["30 days"]
    assert missing_patterns(Rule(any_patterns=["Net 30", "90 days"]), prompt) == []
    assert missing_patterns(Rule(any_patterns=["Net 30"]), prompt) == ["Net 30"]
    assert missing_patterns(Rule(absent=True), prompt) == []


def test_evidence_reach_reports_what_the_prompts_contain(
    settings: Settings, runtime: Runtime
) -> None:
    gold = ExtractionGold(
        bids={
            "BidA": {
                "bid_number": Rule(any_patterns=["2024-117"]),
                "part_no": Rule(items=["379-BFNZ", "NOT-IN-ANY-DOCUMENT"]),
                "bid_summary": Rule(patterns=["anything"]),
            }
        }
    )
    reach = {r.field: r for r in evidence_reach(settings, runtime, gold, ["BidA"])}
    assert reach["bid_number"].reached and reach["bid_number"].passages > 0
    assert reach["part_no"].asked and reach["part_no"].missing == ["NOT-IN-ANY-DOCUMENT"]
    assert not reach["bid_summary"].asked  # written from the record, never asked of the model


def test_rerank_with_several_queries_keeps_each_chunks_best_score(runtime: Runtime) -> None:
    engine = runtime.engine()
    ids = [h.chunk_id for h in engine.search("delivery warehouse", bid_id="BidA", k=10).hits]
    one = dict(engine.rerank("delivery warehouse", ids))
    other = dict(engine.rerank("quotes due", ids))
    both = dict(engine.rerank(["delivery warehouse", "quotes due"], ids))
    assert both == {c: max(one[c], other[c]) for c in ids}


def test_evidence_text_ignores_definitions_and_headers() -> None:
    prompt = (
        "Fields to extract:\n- additional_documentation (...): forms, warranty certificates\n\n"
        'Passages:\n\n[e1] portal.html p1 (bid_page; document title "Laptops w/Extended Warranty")\n'
        "Submit the Mercury Affidavit."
    )
    text = evidence_text(prompt)
    assert "Mercury Affidavit" in text and "arrant" not in text
