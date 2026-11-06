from collections.abc import Callable
from pathlib import Path

import pymupdf
import pytest

from rfp_intel.config import Settings, get_settings
from rfp_intel.ingestion.meta import CueConfig, load_cues
from rfp_intel.ingestion.models import Block, BlockKind, PageInfo, PageStatus, ParsedDocument

REPO_ROOT = Path(__file__).resolve().parents[1]
BIDS_DIR = REPO_ROOT / "data" / "bids"
CUES_PATH = REPO_ROOT / "config" / "doc_types.yaml"


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    root = tmp_path / "bids"
    (root / "BidA").mkdir(parents=True)
    return root


@pytest.fixture
def settings(tmp_path: Path, data_dir: Path) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        data_dir=data_dir,
        state_dir=tmp_path / "var",
        traces_dir=tmp_path / "traces",
        config_dir=REPO_ROOT / "config",
        api_key=None,
    )


@pytest.fixture(autouse=True)
def _fresh_settings_cache() -> None:
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def cues() -> CueConfig:
    return load_cues(CUES_PATH)


# ---------------------------------------------------------------------------------------------
# Synthetic documents

HEADER = "Riverside County Purchasing RFQ 2024-117"


def _header_footer(page: pymupdf.Page, number: int, total: int) -> None:
    page.insert_text((150, 30), HEADER, fontsize=9, fontname="helv")
    page.insert_text((72, 770), "Riverside County rev 1.0", fontsize=9, fontname="helv")
    page.insert_text((470, 770), f"Page {number} of {total}", fontsize=9, fontname="helv")


def _table(page: pymupdf.Page, top: float, rows: list[tuple[str, str]]) -> None:
    left, mid, right, height = 72.0, 300.0, 520.0, 22.0
    for i, (a, b) in enumerate(rows):
        y = top + i * height
        page.draw_rect(pymupdf.Rect(left, y, mid, y + height), color=(0, 0, 0), width=0.8)
        page.draw_rect(pymupdf.Rect(mid, y, right, y + height), color=(0, 0, 0), width=0.8)
        page.insert_text((left + 4, y + 15), a, fontsize=10, fontname="helv")
        page.insert_text((mid + 4, y + 15), b, fontsize=10, fontname="helv")


def build_sample_pdf(path: Path) -> Path:
    """Four pages exercising headers, key-value rows, hyphenation, headings, a ruled table,
    an image-only page and an empty page."""
    doc = pymupdf.open()
    total = 4

    p1 = doc.new_page(width=612, height=792)
    _header_footer(p1, 1, total)
    p1.insert_text((72, 120), "Request for Quotation 2024-117", fontsize=18, fontname="helv")
    p1.insert_text((72, 170), "1.1 Key Dates", fontsize=10, fontname="hebo")
    p1.insert_text((72, 200), "Quotes Due", fontsize=10, fontname="helv")
    p1.insert_text((320, 200), "July 9, 2024 2:00 PM CDT", fontsize=10, fontname="helv")
    p1.insert_text((72, 214), "Pre-Bid Meeting", fontsize=10, fontname="helv")
    p1.insert_text((320, 214), "June 10, 2024", fontsize=10, fontname="helv")
    p1.insert_text((72, 250), "All equipment must meet the require-", fontsize=10, fontname="helv")
    p1.insert_text((72, 262), "ments listed below and be delivered", fontsize=10, fontname="helv")
    p1.insert_text((72, 274), "within 45 days of award.", fontsize=10, fontname="helv")
    p1.insert_text((72, 310), "DELIVERY", fontsize=10, fontname="hebo")
    p1.insert_text((72, 324), "Deliver to the central warehouse.", fontsize=10, fontname="helv")

    p2 = doc.new_page(width=612, height=792)
    _header_footer(p2, 2, total)
    p2.insert_text((72, 110), "DELIVERY", fontsize=10, fontname="hebo")  # repeated after break
    p2.insert_text((72, 124), "Continued delivery terms on page two.", fontsize=10, fontname="helv")
    _table(p2, 160, [("Item", "SKU"), ("Laptop 15 inch", "379-BFNZ"), ("Dock", "WD22TB4")])

    p3 = doc.new_page(width=612, height=792)
    _header_footer(p3, 3, total)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 40), False)
    pix.clear_with(180)
    p3.insert_image(pymupdf.Rect(72, 100, 540, 700), pixmap=pix)

    p4 = doc.new_page(width=612, height=792)
    _header_footer(p4, 4, total)

    doc.set_metadata({"creationDate": "D:20240613175856-05'00'", "title": ""})
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    return build_sample_pdf(tmp_path / "RFQ_2024-117.pdf")


@pytest.fixture
def make_doc() -> Callable[..., ParsedDocument]:
    """Build a ParsedDocument from plain paragraphs, for metadata and classifier tests."""

    def _make(
        *paragraphs: str,
        title: str = "Untitled",
        file_name: str = "doc.pdf",
        media_type: str = "pdf",
        running_text: list[str] | None = None,
        metadata: dict[str, str] | None = None,
        kv: list[tuple[str, str]] | None = None,
    ) -> ParsedDocument:
        blocks = [Block(kind=BlockKind.PARAGRAPH, text=p, page=1) for p in paragraphs]
        blocks += [
            Block(kind=BlockKind.KV, text=f"{k}: {v}", page=1, label=k, value=v)
            for k, v in kv or []
        ]
        return ParsedDocument(
            doc_id="x",
            bid_id="B",
            file_name=file_name,
            source_path=file_name,
            file_sha256="0",
            media_type=media_type,
            title=title,
            page_count=1,
            pages=[PageInfo(number=1, status=PageStatus.OK, char_count=100)],
            blocks=blocks,
            running_text=running_text or [],
            metadata=metadata or {},
        )

    return _make
