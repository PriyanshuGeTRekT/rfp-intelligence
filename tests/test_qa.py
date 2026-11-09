from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rfp_intel.agents.guarded import GuardedLLM
from rfp_intel.agents.qa import NOT_FOUND, answer, plan_retrieval
from rfp_intel.api.app import create_app
from rfp_intel.config import Settings
from rfp_intel.search.runtime import Runtime

from .agents_fakes import answering
from .conftest import build_sample_pdf, fake_runtime


@pytest.fixture
def runtime(settings: Settings, data_dir: Path) -> Iterator[Runtime]:
    build_sample_pdf(data_dir / "BidA" / "RFQ_2024-117.pdf")
    with fake_runtime(settings) as rt:
        rt.indexer().index_folder(data_dir / "BidA")
        yield rt


def test_cited_answer(runtime: Runtime) -> None:
    llm = answering(verbatim=True)
    r = answer(
        runtime.engine(),
        GuardedLLM(llm),
        "claude-opus-5-5",
        "How soon must equipment be delivered?",
        bid_id="BidA",
    )
    assert r.found and r.answer.startswith("Delivery is required")
    (c,) = r.citations
    assert c.file == "RFQ_2024-117.pdf" and c.bid_id == "BidA"
    assert c.page.startswith("1")  # the cited chunk spans pages 1-2
    assert c.quote == "within 45 days of award." and r.dropped_citations == 0
    assert r.passages_reviewed > 0 and r.usage["calls"] == 1


def test_paraphrased_citations_make_the_answer_not_found(runtime: Runtime) -> None:
    llm = answering(verbatim=False)
    r = answer(
        runtime.engine(),
        GuardedLLM(llm),
        "claude-opus-5-5",
        "How soon must equipment be delivered?",
        bid_id="BidA",
    )
    assert not r.found and r.answer == NOT_FOUND
    assert r.citations == [] and r.dropped_citations == 2  # first try and the retry
    assert r.usage["calls"] == 2


def test_no_passages_means_not_found_without_calling_the_model(runtime: Runtime) -> None:
    llm = answering(verbatim=True)
    r = answer(
        runtime.engine(), GuardedLLM(llm), "claude-opus-5-5", "Anything?", bid_id="NoSuchBid"
    )
    assert not r.found and r.answer == NOT_FOUND and r.usage == {} | r.usage
    assert llm.calls == []


def test_ask_endpoint(settings: Settings, data_dir: Path) -> None:
    build_sample_pdf(data_dir / "BidA" / "RFQ_2024-117.pdf")
    app = create_app(settings, runtime_factory=fake_runtime, llm=answering(verbatim=True))
    client = TestClient(app)
    assert client.post("/index", json={"path": "BidA"}).status_code == 200
    r = client.post(
        "/ask", json={"question": "How soon must equipment be delivered?", "bid_id": "BidA"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["found"] and body["citations"][0]["file"] == "RFQ_2024-117.pdf"
    assert body["scope"] == ["BidA"]
    assert client.post("/ask", json={"question": "x"}).status_code == 422  # too short


def test_a_fresh_setup_indexes_its_bids_on_the_first_question(
    settings: Settings, data_dir: Path
) -> None:
    """Nothing has been indexed (a new clone, or `docker compose up` on an empty volume): the
    first question and the first search index the bid folders instead of finding nothing."""
    build_sample_pdf(data_dir / "BidA" / "RFQ_2024-117.pdf")
    client = TestClient(
        create_app(settings, runtime_factory=fake_runtime, llm=answering(verbatim=True))
    )
    r = client.post("/ask", json={"question": "How soon must equipment be delivered?"})
    assert r.status_code == 200 and r.json()["found"], r.text
    assert client.get("/search", params={"q": "delivery"}).json()["hits"]


def test_a_failed_model_call_is_an_answer_not_a_crash(runtime: Runtime) -> None:
    from rfp_intel.agents.llm import ScriptedLLM

    r = answer(
        runtime.engine(), GuardedLLM(ScriptedLLM({})), "m", "When is delivery due?", bid_id="BidA"
    )
    assert not r.found and r.error and "no scripted response" in r.error
    assert r.answer.startswith("The question could not be answered")


def test_retrieval_plan_scopes_compares_and_addenda() -> None:
    bids = ["Bid1", "Bid2"]
    one = plan_retrieval("When is Bid1 due after all addendums?", None, bids, 8)
    assert one.bids == ["Bid1"] and one.addenda
    both = plan_retrieval("Compare the warranty requirements of both bids.", None, bids, 8)
    assert both.bids == ["Bid1", "Bid2"] and both.per_bid == 4 and not both.addenda
    anywhere = plan_retrieval("Is a bid bond required?", None, bids, 8)
    assert anywhere.bids == [None] and anywhere.per_bid == 8
    pinned = plan_retrieval("Compare both bids", "Bid2", bids, 8)
    assert pinned.bids == ["Bid2"]


def test_ask_without_a_key_is_503(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = TestClient(
        create_app(
            settings.model_copy(update={"anthropic_api_key": None}), runtime_factory=fake_runtime
        )
    )
    r = client.post("/ask", json={"question": "When is it due?"})
    assert r.status_code == 503 and "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_statements_without_a_valid_citation_are_removed(runtime: Runtime) -> None:
    from rfp_intel.agents.llm import ScriptedLLM
    from rfp_intel.agents.outputs import AnswerOut, CitationOut, StatementOut

    from .agents_fakes import _find, passages

    def respond(system: str, user: str) -> AnswerOut:
        eid = _find("within 45 days of award.", passages(user)) or "missing"
        return AnswerOut(
            found=True,
            statements=[
                StatementOut(
                    text="Delivery is due within 45 days of award.",
                    citations=[CitationOut(evidence_id=eid, quote="within 45 days of award.")],
                ),
                StatementOut(  # an unsupported claim with a paraphrased citation
                    text="Late delivery costs $500 a day.",
                    citations=[CitationOut(evidence_id=eid, quote="late fees of 500 dollars")],
                ),
                StatementOut(text="Installation is included.", citations=[]),  # no citation
            ],
        )

    r = answer(
        runtime.engine(), GuardedLLM(ScriptedLLM({"AnswerOut": respond})), "m",
        "How soon must equipment be delivered?", bid_id="BidA",
    )  # fmt: skip
    assert r.found and r.answer == "Delivery is due within 45 days of award."
    assert r.removed_statements == 2 and r.dropped_citations == 1
    assert [s.citations for s in r.statements] == [[0]] and len(r.citations) == 1
