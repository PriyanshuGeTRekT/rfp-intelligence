from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rfp_intel.agents.qa import NOT_FOUND, answer
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
        llm,
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
        llm,
        "claude-opus-5-5",
        "How soon must equipment be delivered?",
        bid_id="BidA",
    )
    assert not r.found and r.answer == NOT_FOUND
    assert r.citations == [] and r.dropped_citations == 2  # first try and the retry
    assert r.usage["calls"] == 2


def test_no_passages_means_not_found_without_calling_the_model(runtime: Runtime) -> None:
    llm = answering(verbatim=True)
    r = answer(runtime.engine(), llm, "claude-opus-5-5", "Anything?", bid_id="NoSuchBid")
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
    assert client.post("/ask", json={"question": "x?", "config": "magic"}).status_code == 422


def test_ask_without_a_key_is_503(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = TestClient(
        create_app(
            settings.model_copy(update={"anthropic_api_key": None}), runtime_factory=fake_runtime
        )
    )
    r = client.post("/ask", json={"question": "When is it due?"})
    assert r.status_code == 503 and "ANTHROPIC_API_KEY" in r.json()["detail"]
