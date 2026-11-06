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
