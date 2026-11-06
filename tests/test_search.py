from collections.abc import Iterator
from pathlib import Path

import pytest

from rfp_intel.config import Settings
from rfp_intel.facts.labels import load_fact_types, route
from rfp_intel.search.backend import QdrantBackend
from rfp_intel.search.fusion import RankedList, rrf
from rfp_intel.search.models import NAMED_CONFIGS
from rfp_intel.search.query import analyze, load_synonyms, query_identifiers
from rfp_intel.search.runtime import Runtime

from .conftest import REPO_ROOT, build_sample_pdf, fake_runtime
from .test_html import PORTAL

ADDENDUM = """# ADDENDUM No. 2

The purpose of this addendum is to extend the due date of this RFQ.

The new due date for this RFQ will be July 16, 2024 at 2:00 PM CST.
"""


@pytest.fixture
def runtime(settings: Settings, data_dir: Path) -> Iterator[Runtime]:
    folder = data_dir / "BidA"
    build_sample_pdf(folder / "RFQ_2024-117.pdf")
    (folder / "portal.html").write_text(PORTAL, encoding="utf-8")
    (folder / "addendum_2.md").write_text(ADDENDUM, encoding="utf-8")
    other = data_dir / "BidB"
    other.mkdir()
    (other / "notes.md").write_text(
        "# Scope\n\nBidB buys 40 monitors, SKU 555-ZZZZ, due July 1, 2024.\n", encoding="utf-8"
    )
    with fake_runtime(settings) as rt:
        indexer = rt.indexer()
        indexer.index_folder(folder)
        indexer.index_folder(other)
        yield rt


def test_rrf_math_weights_and_duplicates() -> None:
    fused = rrf([RankedList("a", ["x", "y", "x"]), RankedList("b", ["y"], weight=2.0)], k=60)
    assert [f.chunk_id for f in fused] == ["y", "x"]
    y, x = fused
    assert y.score == pytest.approx(1 / 62 + 2 / 61)
    assert x.score == pytest.approx(1 / 61)  # the repeated "x" in list a counts once
    assert y.ranks == {"a": 2, "b": 1}


def test_query_analysis() -> None:
    config = load_fact_types(REPO_ROOT / "config" / "fact_types.yaml")
    synonyms = load_synonyms(REPO_ROOT / "config" / "synonyms.yaml")
    assert query_identifiers("dock wd22tb4 and 379-bfnz?") == ["WD22TB4", "379-BFNZ", "379BFNZ"]
    assert route(config, "When are proposals due?") == ["deadline"]
    assert route(config, "When are questions due?") == ["questions"]
    assert "bond_insurance" in route(config, "Is a bid bond required?")
    a = analyze("Is a bid bond required?", config, synonyms)
    assert "bid security" in a.expansions and "bid security" in a.sparse_query
    assert analyze("Is a bid bond required?", config, synonyms, expand=False).expansions == []


def test_identifier_query_finds_the_exact_row(runtime: Runtime) -> None:
    result = runtime.engine().search("wd22tb4", bid_id="BidA", k=3)
    top = result.hits[0]
    assert "WD22TB4" in top.text
    assert "identifiers" in top.signals["ranks"]


def test_deadline_question_routes_to_deadline_chunks(runtime: Runtime) -> None:
    result = runtime.engine().search("When are quotes due?", bid_id="BidA", k=5)
    assert result.query.fact_types == ["deadline"]
    texts = " ".join(h.text for h in result.hits[:3])
    assert "Quotes Due | July 9, 2024 2:00 PM CDT" in texts
    assert any(
        "facts_bm25" in h.signals["ranks"] or "facts_dense" in h.signals["ranks"]
        for h in result.hits
    )


def test_filters_restrict_every_list(runtime: Runtime) -> None:
    engine = runtime.engine()
    assert {h.bid_id for h in engine.search("monitors due", k=10).hits} == {"BidA", "BidB"}
    assert {h.bid_id for h in engine.search("monitors due", bid_id="BidB", k=10).hits} == {"BidB"}
    portal_only = engine.search("closing date", bid_id="BidA", doc_types=["bid_page"], k=10).hits
    assert portal_only and {h.doc_type for h in portal_only} == {"bid_page"}
    addendum = engine.search("due date", bid_id="BidA", addendum_number=2, k=10).hits
    assert addendum and {h.addendum_number for h in addendum} == {2}
    assert "July 16, 2024" in addendum[0].text


def test_named_configs_use_only_their_lists(runtime: Runtime) -> None:
    engine = runtime.engine()
    dense = engine.search("delivery terms", bid_id="BidA", config="dense").hits
    assert dense and all(set(h.signals["ranks"]) == {"dense"} for h in dense)
    sparse = engine.search("delivery terms", bid_id="BidA", config="sparse").hits
    assert sparse and all(set(h.signals["ranks"]) == {"bm25"} for h in sparse)
    assert "rerank" not in sparse[0].signals
    # the default (hybrid_facts) does not rerank; reranking is opt-in
    assert "rerank" not in engine.search("delivery terms", bid_id="BidA").hits[0].signals
    reranked = engine.search("delivery terms", bid_id="BidA", config="hybrid_facts_rerank")
    assert "rerank" in reranked.hits[0].signals
    assert set(NAMED_CONFIGS) == {
        "dense",
        "sparse",
        "hybrid",
        "hybrid_facts",
        "hybrid_facts_rerank",
    }


def test_every_hit_has_file_page_and_text(runtime: Runtime) -> None:
    for h in runtime.engine().search("delivery", k=10).hits:
        assert h.file_name and h.page_start >= 1 and h.page_end >= h.page_start and h.text


def test_dimension_change_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "q"
    QdrantBackend(8, path=path).close()
    with pytest.raises(ValueError, match="embedding model changed"):
        QdrantBackend(16, path=path)
