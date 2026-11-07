import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from rfp_intel.cli import app
from rfp_intel.ingestion.loader import load_bid_folder
from rfp_intel.ingestion.meta import CueConfig
from rfp_intel.ingestion.models import DocType

from .conftest import CUES_PATH, REPO_ROOT, build_sample_pdf
from .test_html import PORTAL


@pytest.fixture
def bid_folder(data_dir: Path) -> Path:
    folder = data_dir / "BidA"
    build_sample_pdf(folder / "RFQ_2024-117.pdf")
    (folder / "portal.html").write_text(PORTAL, encoding="utf-8")
    (folder / "pricing.pptx").write_bytes(b"PK\x03\x04 not supported yet")
    (folder / "broken.pdf").write_bytes(b"%PDF-1.7 truncated")
    (folder / "attachments").mkdir()
    (folder / "attachments" / "notes.txt").write_text("Scope of work: laptops.", encoding="utf-8")
    (folder / "~$lockfile.pdf").write_bytes(b"office lock file")
    return folder


def test_loader_parses_what_it_can_and_reports_the_rest(bid_folder: Path, cues: CueConfig) -> None:
    result = load_bid_folder(bid_folder, cues)
    names = sorted(d.file_name for d in result.documents)
    assert names == ["RFQ_2024-117.pdf", "attachments/notes.txt", "portal.html"]
    assert result.skipped_files == ["pricing.pptx"]
    by_file = {(i.file_name, i.page): i for i in result.issues}
    assert by_file[("broken.pdf", None)].severity == "error"
    assert by_file[("pricing.pptx", None)].severity == "warning"
    assert by_file[("RFQ_2024-117.pdf", 3)].message.endswith("needs OCR")
    assert ("RFQ_2024-117.pdf", 4) in by_file


def test_loader_enriches_documents(bid_folder: Path, cues: CueConfig) -> None:
    docs = {d.file_name: d for d in load_bid_folder(bid_folder, cues).documents}
    assert docs["portal.html"].doc_type is DocType.BID_PAGE
    assert docs["RFQ_2024-117.pdf"].doc_type is DocType.RFP
    assert docs["RFQ_2024-117.pdf"].bid_id == "BidA"


def test_loader_accepts_a_cue_file_path(bid_folder: Path) -> None:
    assert load_bid_folder(bid_folder, CUES_PATH).documents


def test_parse_command(
    bid_folder: Path, data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RFP_DATA_DIR", str(data_dir))
    monkeypatch.setenv("RFP_CONFIG_DIR", str(REPO_ROOT / "config"))
    out = tmp_path / "out" / "BidA.json"
    result = CliRunner().invoke(app, ["parse", "BidA", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "portal.html" in result.output
    assert "type   bid_page" in result.output
    assert "needs OCR" in result.output
    assert out.exists()


def test_facts_command_stores_and_filters(
    bid_folder: Path, data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RFP_DATA_DIR", str(data_dir))
    monkeypatch.setenv("RFP_CONFIG_DIR", str(REPO_ROOT / "config"))
    monkeypatch.setenv("RFP_STATE_DIR", str(tmp_path / "state"))
    result = CliRunner().invoke(app, ["facts", "BidA", "--type", "deadline"])
    assert result.exit_code == 0, result.output
    assert "facts stored for BidA" in result.output
    assert "'July 9, 2024 2:00 PM CDT' -> 2024-07-09T19:00:00Z" in result.output
    assert (tmp_path / "state" / "rfp.sqlite").exists()
    bad = CliRunner().invoke(app, ["facts", "BidA", "--kind", "nonsense"])
    assert bad.exit_code == 1


def test_parse_command_refuses_paths_outside_data_dir(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RFP_DATA_DIR", str(data_dir))
    assert CliRunner().invoke(app, ["parse", "../../no-such-folder"]).exit_code == 1
    empty = data_dir.parent / "not-a-bid"
    (empty / "sub").mkdir(parents=True)
    assert CliRunner().invoke(app, ["parse", str(empty)]).exit_code == 1  # holds no documents


def test_parse_command_accepts_a_bid_folder_anywhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RFP_CONFIG_DIR", str(REPO_ROOT / "config"))
    folder = tmp_path / "elsewhere" / "NewBid"
    folder.mkdir(parents=True)
    build_sample_pdf(folder / "rfq.pdf")
    result = CliRunner().invoke(app, ["parse", str(folder)])
    assert result.exit_code == 0, result.output
    assert "rfq.pdf" in result.output


def test_folder_named_after_bid(tmp_path: Path, cues: CueConfig) -> None:
    folder = tmp_path / "Unseen Bid 42"
    folder.mkdir()
    shutil.copy(build_sample_pdf(tmp_path / "s.pdf"), folder / "s.pdf")
    assert load_bid_folder(folder, cues).bid_id == "Unseen Bid 42"
