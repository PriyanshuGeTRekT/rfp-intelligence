from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from rfp_intel.api.app import create_app
from rfp_intel.config import Settings

from .conftest import build_sample_pdf, fake_runtime


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings, runtime_factory=fake_runtime))


@pytest.fixture
def secured(settings: Settings) -> TestClient:
    app = create_app(
        settings.model_copy(update={"api_key": SecretStr("k3y")}), runtime_factory=fake_runtime
    )
    return TestClient(app)


def test_health_is_open(secured: TestClient) -> None:
    r = secured.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}])
def test_missing_or_wrong_key_is_401(secured: TestClient, headers: dict[str, str]) -> None:
    assert secured.get("/search", params={"q": "due date"}, headers=headers).status_code == 401


def test_correct_key_reaches_the_route(secured: TestClient) -> None:
    r = secured.get("/search", params={"q": "due date"}, headers={"X-API-Key": "k3y"})
    assert r.status_code == 200
    assert r.json()["hits"] == []


@pytest.mark.parametrize("path", ["../", "../../etc", "BidA/../../x"])
def test_index_rejects_paths_outside_data_dir(client: TestClient, path: str) -> None:
    r = client.post("/index", json={"path": path})
    assert r.status_code == 400
    assert "outside the data directory" in r.json()["detail"]


def test_index_missing_folder_is_404(client: TestClient) -> None:
    assert client.post("/index", json={"path": "NoSuchBid"}).status_code == 404


def test_index_then_search(client: TestClient, data_dir: Path) -> None:
    build_sample_pdf(data_dir / "BidA" / "RFQ_2024-117.pdf")
    first = client.post("/index", json={"path": "BidA"})
    assert first.status_code == 200, first.text
    assert first.json()["added"] == ["RFQ_2024-117.pdf"]
    again = client.post("/index", json={"path": "BidA"}).json()
    assert again["unchanged"] == ["RFQ_2024-117.pdf"] and again["added"] == []

    r = client.get("/search", params={"q": "379-BFNZ", "bid_id": "BidA", "k": 3})
    assert r.status_code == 200
    body = r.json()
    hit = body["hits"][0]
    assert {"file_name", "page_start", "page_end", "text", "signals"} <= set(hit)
    assert "379-BFNZ" in hit["text"]
    assert hit["file_name"] == "RFQ_2024-117.pdf" and hit["page_start"] == 2
    assert body["query"]["identifiers"] == ["379-BFNZ", "379BFNZ"]


def test_search_rejects_unknown_config(client: TestClient) -> None:
    assert client.get("/search", params={"q": "x", "config": "magic"}).status_code == 422


def test_oversized_body_is_413(settings: Settings) -> None:
    small = TestClient(
        create_app(
            settings.model_copy(update={"max_request_bytes": 64}), runtime_factory=fake_runtime
        )
    )
    r = small.post("/ask", json={"question": "x" * 200})
    assert r.status_code == 413


def test_search_validates_k(client: TestClient) -> None:
    assert client.get("/search", params={"q": "x", "k": 500}).status_code == 422


def test_search_accepts_top_k_as_in_the_brief(client: TestClient, data_dir: Path) -> None:
    build_sample_pdf(data_dir / "BidA" / "RFQ_2024-117.pdf")
    client.post("/index", json={"path": "BidA"})
    r = client.get("/search", params={"q": "laptop", "bid_id": "BidA", "top_k": 1})
    assert r.status_code == 200 and len(r.json()["hits"]) == 1
    assert client.get("/api/search", params={"q": "laptop", "top_k": 2}).status_code == 200


def _full_bid(data_dir: Path) -> Path:
    from .agents_fakes import ADDENDUM
    from .test_html import PORTAL

    folder = data_dir / "BidA"
    build_sample_pdf(folder / "RFQ_2024-117.pdf")
    (folder / "portal.html").write_text(PORTAL, encoding="utf-8")
    (folder / "addendum_2.md").write_text(ADDENDUM, encoding="utf-8")
    return folder


def test_bids_extraction_job_result_and_trace(settings: Settings, data_dir: Path) -> None:
    import time

    from .agents_fakes import make_llm

    _full_bid(data_dir)
    client = TestClient(create_app(settings, runtime_factory=fake_runtime, llm=make_llm()))
    bids = client.get("/api/bids").json()
    assert [(b["bid_id"], b["indexed"]) for b in bids] == [("BidA", False)]
    assert client.get("/api/bids/BidA/result").status_code == 404

    job = client.post("/api/bids/BidA/extract")
    assert job.status_code == 202
    job_id, run_id = job.json()["job_id"], job.json()["run_id"]
    for _ in range(100):
        status = client.get(f"/api/jobs/{job_id}").json()
        if status["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.1)
    assert status["status"] == "succeeded", status
    assert status["validation"]["failed"] == 0

    result = client.get("/api/bids/BidA/result").json()
    assert result["run_id"] == run_id and "Due Date" in result["fields"]
    detail = client.get("/api/bids/BidA").json()
    assert detail["indexed"] and detail["documents"] == 3
    assert detail["result"]["due_date"] == "2024-07-16 14:00 CDT"
    assert {f["doc_type"] for f in detail["files"]} >= {"addendum", "bid_page"}
    assert client.get("/api/bids/Nope").status_code == 404


def test_source_files_are_served_inside_the_bid_only(client: TestClient, data_dir: Path) -> None:
    _full_bid(data_dir)
    pdf = client.get("/api/bids/BidA/files/RFQ_2024-117.pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    html = client.get("/api/bids/BidA/files/portal.html")
    assert html.headers["content-type"].startswith("text/plain")  # never rendered as HTML
    assert client.get("/api/bids/BidA/files/..%2F..%2Fsecret.txt").status_code in (400, 404)
    assert client.get("/api/bids/BidA/files/missing.pdf").status_code == 404


def test_trace_endpoint_reads_a_run_file(client: TestClient, settings: Settings) -> None:
    settings.traces_dir.mkdir(parents=True, exist_ok=True)
    span = {"span_id": "1", "parent_span_id": None, "name": "agent.run", "start": "t",
            "duration_ms": 5.0, "status": "OK", "attributes": {"rfp.run_id": "run-123"}}  # fmt: skip
    import json

    (settings.traces_dir / "run-123.jsonl").write_text(json.dumps(span) + "\n", encoding="utf-8")
    spans = client.get("/api/runs/run-123/trace").json()
    assert spans[0]["name"] == "agent.run"
    assert client.get("/api/runs/nope-404/trace").status_code == 404
    assert client.get("/api/runs/..%2Fx/trace").status_code in (400, 404)


def test_health_reports_the_model_without_loading_anything(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["extract_model"] and body["reranker"] is None


def test_jobs_survive_a_restart_and_interrupted_ones_are_marked(settings: Settings) -> None:
    from datetime import UTC, datetime

    from rfp_intel.api.jobs import INTERRUPTED, Jobs, JobStore
    from rfp_intel.api.schemas import Job

    store = JobStore(settings.db_path)
    now = datetime.now(UTC)
    store.save(
        Job(job_id="done1", bid_id="BidA", run_id="r1", status="succeeded", submitted_at=now)
    )
    store.save(Job(job_id="live1", bid_id="BidA", run_id="r2", status="running", submitted_at=now))
    store.close()

    jobs = Jobs(JobStore(settings.db_path))  # a new server process
    assert jobs.get("done1") is not None and jobs.get("done1").status == "succeeded"  # type: ignore[union-attr]
    interrupted = jobs.get("live1")
    assert interrupted is not None and interrupted.status == "failed"
    assert interrupted.error == INTERRUPTED and jobs.active_for("BidA") is None
    jobs.shutdown()


def test_the_web_app_is_served_and_index_html_is_revalidated(
    settings: Settings, tmp_path: Path
) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>", encoding="utf-8")
    (dist / "assets" / "index-abc.js").write_text("console.log(1)", encoding="utf-8")
    client = TestClient(create_app(settings, runtime_factory=fake_runtime, web_dist=dist))
    page = client.get("/bids/Bid1")  # a client-side route falls back to the app
    assert page.status_code == 200 and page.text == "<html>app</html>"
    assert page.headers["cache-control"] == "no-cache"
    assert client.get("/assets/index-abc.js").status_code == 200
    assert client.get("/api/nope").status_code == 404
