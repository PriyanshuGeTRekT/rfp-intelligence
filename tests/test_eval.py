from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import pytest

from rfp_intel.config import Settings
from rfp_intel.eval.retrieval import (
    Baseline,
    ConfigResult,
    EvalRun,
    GoldQuestion,
    GoldSet,
    Locator,
    QuestionResult,
    check_regression,
    evaluate,
    load_gold,
    matches,
    render_markdown,
    score_question,
)
from rfp_intel.facts.extract import extract_facts
from rfp_intel.facts.labels import load_fact_types
from rfp_intel.ingestion.models import BidFolder
from rfp_intel.search.chunking import chunk_document
from rfp_intel.search.models import Chunk, Hit

from .conftest import BIDS_DIR, REPO_ROOT, build_sample_pdf, fake_runtime

GOLD = REPO_ROOT / "eval" / "retrieval_gold.yaml"


def _hit(rank: int, file_name: str, text: str, page: int = 1) -> Hit:
    return Hit(
        rank=rank, score=1.0, chunk_id=f"c{rank}", bid_id="B", file_name=file_name, page_start=page,
        page_end=page, doc_type="rfp", section_path=[], chunk_type="section", text=text,
    )  # fmt: skip


def test_locator_matching() -> None:
    loc = Locator(file="addendum 2", must_contain="July 9,  2024", pages=[1, 2])
    assert matches(loc, "Addendum 2 RFP.pdf", "new due date July 9, 2024 at 2:00", 1, 1)
    assert matches(loc, "Addendum 2 RFP.pdf", "new due date\nJULY 9, 2024", 2, 3)
    assert not matches(loc, "Addendum 1 RFP.pdf", "July 9, 2024", 1, 1)
    assert not matches(loc, "Addendum 2 RFP.pdf", "July 9, 2024", 3, 4)
    assert not matches(loc, "Addendum 2 RFP.pdf", "June 27, 2024", 1, 1)


def test_scoring_any_and_all() -> None:
    hits = [
        _hit(1, "rfp.pdf", "noise"),
        _hit(2, "porfp.pdf", "Mercury Affidavit required"),
        _hit(6, "mercury.pdf", "MERCURY AFFIDAVIT"),
    ]
    locs = [
        Locator(file="porfp", must_contain="mercury affidavit"),
        Locator(file="mercury", must_contain="affidavit"),
        Locator(file="contract", must_contain="affidavit"),
    ]
    any_q = GoldQuestion(id="a", bid="B", question="q", relevant=locs)
    all_q = GoldQuestion(id="b", bid="B", question="q", relevant=locs, match="all")
    a = score_question(any_q, hits, 5.0)
    assert a.first_relevant_rank == 2 and a.recall == {1: 0.0, 3: 1.0, 5: 1.0, 10: 1.0}
    b = score_question(all_q, hits, 5.0)
    assert b.recall[5] == pytest.approx(1 / 3) and b.recall[10] == pytest.approx(2 / 3)
    none = score_question(any_q, [_hit(1, "x.pdf", "nothing")], 1.0)
    assert none.first_relevant_rank is None and none.recall[10] == 0.0


def _result(qid: str, rank: int | None, split: str = "dev", ms: float = 10.0) -> QuestionResult:
    recall = {k: 1.0 if rank is not None and rank <= k else 0.0 for k in (1, 3, 5, 10)}
    return QuestionResult(
        id=qid,
        split=split,
        question=qid,
        first_relevant_rank=rank,
        recall=recall,
        latency_ms=ms,
        top=["f.pdf p1"],
    )


def _run(ranks: list[int | None], config: str = "hybrid_facts") -> EvalRun:
    questions = [
        _result(f"q{i}", r, "heldout" if i == 0 else "dev", 10.0 * (i + 1))
        for i, r in enumerate(ranks)
    ]
    return EvalRun(
        created_at="t",
        git_commit="abc",
        gold_file="g",
        question_count=len(ranks),
        configs=[ConfigResult(config=config, questions=questions)],
    )


def test_metrics() -> None:
    c = _run([1, 2, None, 6]).configs[0]
    assert c.metric("recall@1") == pytest.approx(0.25)
    assert c.metric("recall@5") == pytest.approx(0.5)
    assert c.metric("recall@10") == pytest.approx(0.75)
    assert c.metric("mrr") == pytest.approx((1 + 0.5 + 0 + 1 / 6) / 4)
    assert c.metric("latency_ms") == pytest.approx(25.0)
    assert c.metric("recall@1", "heldout") == 1.0


def test_regression_gate() -> None:
    base = Baseline(config="hybrid_facts", recall_at_5=0.80, mrr=0.70, git_commit="abc")
    assert check_regression(_run([1, 1, 1, 2]), base) == []
    problems = check_regression(_run([1, None, None, 9]), base)
    assert any("recall@5" in p for p in problems) and any("mrr" in p for p in problems)


def test_markdown_report() -> None:
    md = render_markdown(_run([1, None, 3, 2]), {"hybrid_facts": "the default"})
    assert "| Config | Recall@1 |" in md
    assert "## Held-out questions only" in md
    assert "`hybrid_facts`: q1 (>10)" in md
    assert "- `hybrid_facts`: the default" in md


def test_evaluate_end_to_end_with_fakes(settings: Settings, data_dir: Path) -> None:
    build_sample_pdf(data_dir / "BidA" / "rfq.pdf")
    gold = GoldSet(
        questions=[
            GoldQuestion(
                id="sku",
                bid="BidA",
                question="379-BFNZ",
                relevant=[Locator(file="rfq", must_contain="379-BFNZ", pages=[2])],
            )
        ]
    )
    with fake_runtime(settings) as rt:
        rt.indexer().index_folder(data_dir / "BidA")
        run = evaluate(rt.engine(), gold, ["dense", "hybrid_facts"], gold_file="g.yaml")
    assert [c.config for c in run.configs] == ["dense", "hybrid_facts"]
    assert run.config("hybrid_facts").questions[0].first_relevant_rank == 1


# ---------------------------------------------------------------------------------------------
# The gold set itself


def test_gold_set_shape() -> None:
    gold = load_gold(GOLD)
    ids = [q.id for q in gold.questions]
    assert len(ids) == len(set(ids)) and len(ids) >= 15
    assert Counter(q.bid for q in gold.questions).keys() == {"Bid1", "Bid2", "Bid3"}
    assert all(q.split == "unseen" for q in gold.questions if q.bid == "Bid3")
    assert sum(q.split == "heldout" for q in gold.questions) >= 5


@pytest.fixture(scope="module")
def real_chunks(bid1_folder: BidFolder, bid2_folder: BidFolder) -> Iterator[list[Chunk]]:
    config = load_fact_types(REPO_ROOT / "config" / "fact_types.yaml")
    yield [
        c
        for f in (bid1_folder, bid2_folder)
        for d in f.documents
        for c in chunk_document(d, extract_facts(d, config))
    ]


def test_every_gold_passage_exists_in_the_chunks(real_chunks: list[Chunk]) -> None:
    """A label that matches no chunk would silently cap recall; catch it here instead."""
    gold = load_gold(GOLD)
    missing = [
        (q.id, loc.must_contain)
        for q in gold.questions
        if q.bid in ("Bid1", "Bid2")  # Bid3 needs OCR: see the slow test below
        for loc in q.relevant
        if not any(
            c.bid_id == q.bid and matches(loc, c.file_name, c.text, c.page_start, c.page_end)
            for c in real_chunks
        )
    ]
    assert missing == []


@pytest.mark.slow
def test_every_unseen_bid_passage_exists_in_its_chunks() -> None:
    """Bid3's RFP is a 70-page scan: parsing it runs OCR (about 2.5 minutes on a laptop)."""
    from rfp_intel.ingestion.loader import load_bid_folder

    config = load_fact_types(REPO_ROOT / "config" / "fact_types.yaml")
    folder = load_bid_folder(BIDS_DIR / "Bid3", REPO_ROOT / "config" / "doc_types.yaml")
    chunks = [c for d in folder.documents for c in chunk_document(d, extract_facts(d, config))]
    gold = load_gold(GOLD)
    missing = [
        (q.id, loc.must_contain)
        for q in gold.questions
        if q.bid == "Bid3"
        for loc in q.relevant
        if not any(matches(loc, c.file_name, c.text, c.page_start, c.page_end) for c in chunks)
    ]
    assert missing == []


def test_the_regression_gate_ignores_the_unseen_bid() -> None:
    from rfp_intel.eval.retrieval import KNOWN

    run = _run([1, 1, 1, 1])
    unseen = [_result(f"u{i}", None, "unseen", 10.0) for i in range(4)]  # all missed
    run.configs[0].questions.extend(unseen)
    c = run.configs[0]
    assert c.metric("recall@5") == pytest.approx(0.5) and c.metric("recall@5", KNOWN) == 1.0
    base = Baseline(config="hybrid_facts", recall_at_5=0.95, mrr=0.95, git_commit="abc")
    assert check_regression(run, base) == []
