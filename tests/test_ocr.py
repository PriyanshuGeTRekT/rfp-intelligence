"""Scanned pages: a PDF page that is only a picture of text is read by OCR."""

from pathlib import Path

import pymupdf
import pytest

from rfp_intel.ingestion.models import PageStatus
from rfp_intel.ingestion.pdf import parse_pdf

pytest.importorskip("rapidocr_onnxruntime")


def _scanned_pdf(path: Path) -> Path:
    """Render a text page to an image and put only the image in a new PDF, like a scanner."""
    source = pymupdf.open()
    page = source.new_page(width=612, height=792)
    page.insert_text((72, 120), "Request for Proposals 2025-003", fontsize=20, fontname="helv")
    page.insert_text((72, 180), "Proposals are due September 12, 2024 at 2:00 PM.", fontsize=12)
    pixmap = page.get_pixmap(dpi=150)
    scan = pymupdf.open()
    scanned = scan.new_page(width=612, height=792)
    scanned.insert_image(scanned.rect, pixmap=pixmap)
    scan.save(path)
    return path


def test_image_only_pages_are_read_by_ocr(tmp_path: Path) -> None:
    doc = parse_pdf(_scanned_pdf(tmp_path / "scan.pdf"), "BidX")
    assert doc.pages[0].status is PageStatus.OCR
    text = " ".join(b.text for b in doc.blocks)
    assert "Request for Proposals 2025-003" in text
    assert "September 12, 2024" in text


def test_ocr_can_be_turned_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from rfp_intel.config import get_settings
    from rfp_intel.ingestion import ocr

    monkeypatch.setenv("RFP_OCR", "false")
    get_settings.cache_clear()
    ocr._engine.cache_clear()
    try:
        doc = parse_pdf(_scanned_pdf(tmp_path / "scan.pdf"), "BidX")
        assert doc.pages[0].status is PageStatus.NO_TEXT_LAYER and not doc.blocks
    finally:
        ocr._engine.cache_clear()


def test_chunks_from_ocr_pages_are_flagged_and_cap_confidence(tmp_path: Path) -> None:
    from rfp_intel.agents.confidence import Evidence, tier
    from rfp_intel.search.chunking import chunk_document

    doc = parse_pdf(_scanned_pdf(tmp_path / "scan.pdf"), "BidX")
    chunks = chunk_document(doc, [])
    assert chunks and all(c.ocr for c in chunks) and chunks[0].payload()["ocr"] is True
    assert tier(Evidence(found=True, distinct_documents=2, ocr=True)) == "C"  # never A or B


def test_a_fully_scanned_document_is_not_reported_as_unreadable(tmp_path: Path) -> None:
    from rfp_intel.ingestion.loader import page_issues

    issues = page_issues(parse_pdf(_scanned_pdf(tmp_path / "scan.pdf"), "BidX"))
    assert [i.severity for i in issues] == ["info"] and "read by OCR" in issues[0].message


def _scanned_table(path: Path) -> Path:
    """A price table with no ruling lines, scanned: only its layout says it is a table."""
    source = pymupdf.open()
    page = source.new_page(width=612, height=792)
    page.insert_text((72, 90), "Price Schedule", fontsize=16, fontname="helv")
    rows = [
        ("Line", "Description", "Quantity", "Unit"),
        ("1", "Chromebook 11 inch", "500", "Each"),
        ("2", "Charging cart 36 bay", "12", "Each"),
        ("3", "Extended warranty 3 years", "500", "Each"),
    ]
    for i, cells in enumerate(rows):
        for x, text in zip((72, 140, 380, 470), cells, strict=True):
            page.insert_text((x, 140 + 24 * i), text, fontsize=12, fontname="helv")
    page.insert_text((72, 300), "Prices must include delivery to each school.", fontsize=12)
    scan = pymupdf.open()
    scanned = scan.new_page(width=612, height=792)
    scanned.insert_image(scanned.rect, pixmap=page.get_pixmap(dpi=200))
    scan.save(path)
    return path


def test_tables_on_scanned_pages_are_found_from_layout(tmp_path: Path) -> None:
    doc = parse_pdf(_scanned_table(tmp_path / "prices.pdf"), "BidX")
    [table] = doc.tables
    assert table.method == "ocr_layout" and len(table.rows) == 4 and len(table.rows[0]) == 4
    assert table.rows[0] == ["Line", "Description", "Quantity", "Unit"]
    assert table.rows[2][1].startswith("Charging cart") and table.rows[2][2] == "12"
    text = " ".join(b.text for b in doc.blocks)
    assert "Price Schedule" in text and "delivery to each school" in text  # prose stays prose


def test_label_value_rows_are_not_mistaken_for_a_table() -> None:
    from rfp_intel.ingestion.pdf import _layout_tables, _Line

    def line(text: str, x: float, y: float) -> _Line:
        return _Line(text=text, x0=x, y0=y, x1=x + 8 * len(text), y1=y + 12, size=12, bold=False)

    form = [line(t, x, 100 + 20 * i) for i, pair in enumerate(
        [("Bid Number", "2025-003"), ("Due Date", "September 6, 2024"), ("Contact", "S. Rivera")]
    ) for t, x in zip(pair, (72, 300), strict=True)]  # fmt: skip
    assert _layout_tables(form, 1, 0) == []  # two columns: the row path keeps them together


def test_indented_paragraphs_are_not_mistaken_for_a_table() -> None:
    from rfp_intel.ingestion.pdf import _layout_tables, _Line

    def line(text: str, x: float, y: float) -> _Line:
        return _Line(text=text, x0=x, y0=y, x1=x + 6 * len(text), y1=y + 12, size=12, bold=False)

    rows = [
        [("A.", 72), ("Payment of the contract price shall be made when the product", 110)],
        [("has been delivered to District and an invoice for completed work", 72)],
        [("B.", 72), ("From the payments in Paragraph A, District may make deductions", 110)],
        [("(1)", 110), ("Liquidated and other damages described in this contract;", 150)],
        [("(2)", 110), ("Defective equipment, materials, supplies, or work not remedied;", 150)],
    ]
    lines = [line(t, x, 100 + 18 * i) for i, row in enumerate(rows) for t, x in row]
    assert _layout_tables(lines, 1, 0) == []
