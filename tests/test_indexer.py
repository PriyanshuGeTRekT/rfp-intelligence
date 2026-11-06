from collections.abc import Iterator
from pathlib import Path

import pytest

from rfp_intel.config import Settings
from rfp_intel.facts.store import FactStore
from rfp_intel.search.backend import Filters
from rfp_intel.search.manifest import Manifest
from rfp_intel.search.runtime import Runtime

from .conftest import build_sample_pdf, fake_runtime


@pytest.fixture
def runtime(settings: Settings) -> Iterator[Runtime]:
    with fake_runtime(settings) as rt:
        yield rt


@pytest.fixture
def folder(data_dir: Path) -> Path:
    f = data_dir / "BidA"
    build_sample_pdf(f / "rfq.pdf")
    (f / "notes.md").write_text(
        "# Delivery\n\nDeliver within 45 days of award.\n", encoding="utf-8"
    )
    (f / "pricing.xlsx").write_bytes(b"not supported")
    return f


def _doc_ids(settings: Settings) -> dict[str, str]:
    with Manifest(settings.db_path) as m:
        return {rel: e.doc_id for rel, e in m.entries("BidA").items()}


def test_incremental_add_change_remove(runtime: Runtime, settings: Settings, folder: Path) -> None:
    indexer = runtime.indexer()

    first = indexer.index_folder(folder)
    assert sorted(first.added) == ["notes.md", "rfq.pdf"]
    assert first.chunks_written > 0 and first.facts_written > 0
    assert any(i.file_name == "pricing.xlsx" for i in first.issues)
    total = runtime.backend.count(Filters(bid_id="BidA"))
    old_notes = _doc_ids(settings)["notes.md"]

    second = indexer.index_folder(folder)
    assert sorted(second.unchanged) == ["notes.md", "rfq.pdf"] and second.chunks_written == 0

    (folder / "notes.md").write_text(
        "# Delivery\n\nDeliver within 30 days of award.\n", encoding="utf-8"
    )
    third = indexer.index_folder(folder)
    assert third.changed == ["notes.md"] and third.unchanged == ["rfq.pdf"]
    new_notes = _doc_ids(settings)["notes.md"]
    assert new_notes != old_notes
    assert runtime.backend.count(Filters(doc_id=old_notes)) == 0
    assert runtime.backend.count(Filters(bid_id="BidA")) == total
    with FactStore(settings.db_path) as facts:
        assert facts.query(doc_id=old_notes) == []
        assert [
            f.value["amount"] for f in facts.query(doc_id=new_notes) if f.kind.value == "duration"
        ] == [30]

    (folder / "notes.md").unlink()
    fourth = indexer.index_folder(folder)
    assert fourth.removed == ["notes.md"]
    assert runtime.backend.count(Filters(doc_id=new_notes)) == 0
    assert "notes.md" not in _doc_ids(settings)
    assert not (settings.docs_dir / f"{new_notes}.json").exists()


def test_force_reindexes_everything(runtime: Runtime, folder: Path) -> None:
    indexer = runtime.indexer()
    indexer.index_folder(folder)
    report = indexer.index_folder(folder, force=True)
    assert sorted(report.changed) == ["notes.md", "rfq.pdf"]


def test_a_broken_file_keeps_its_previous_index(
    runtime: Runtime, settings: Settings, folder: Path
) -> None:
    indexer = runtime.indexer()
    indexer.index_folder(folder)
    good = _doc_ids(settings)["rfq.pdf"]
    (folder / "rfq.pdf").write_bytes(b"%PDF-1.7 now corrupt")
    report = indexer.index_folder(folder)
    assert report.failed == ["rfq.pdf"]
    assert _doc_ids(settings)["rfq.pdf"] == good
    assert runtime.backend.count(Filters(doc_id=good)) > 0


def test_parsed_documents_are_saved(runtime: Runtime, settings: Settings, folder: Path) -> None:
    runtime.indexer().index_folder(folder)
    for doc_id in _doc_ids(settings).values():
        assert (settings.docs_dir / f"{doc_id}.json").exists()


def test_adding_a_bid_leaves_other_bids_alone(
    runtime: Runtime, data_dir: Path, folder: Path
) -> None:
    indexer = runtime.indexer()
    indexer.index_folder(folder)
    before = runtime.backend.count(Filters(bid_id="BidA"))
    other = data_dir / "BidB"
    other.mkdir()
    (other / "a.md").write_text("# Scope\n\nMonitors.\n", encoding="utf-8")
    report = indexer.index_folder(other)
    assert report.added == ["a.md"]
    assert runtime.backend.count(Filters(bid_id="BidA")) == before
