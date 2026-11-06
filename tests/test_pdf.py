from datetime import date
from pathlib import Path

import pytest

from rfp_intel.ingestion.models import BlockKind, PageStatus, ParsedDocument
from rfp_intel.ingestion.pdf import _merge_continuation_rows, parse_pdf, pdf_metadata_date

from .conftest import HEADER


@pytest.fixture
def doc(sample_pdf: Path) -> ParsedDocument:
    return parse_pdf(sample_pdf, bid_id="BidA")


def test_running_headers_and_page_numbers_leave_the_body(doc: ParsedDocument) -> None:
    body = doc.text()
    assert HEADER not in body
    assert "Riverside County rev" not in body
    assert "Page 1 of 4" not in body
    assert HEADER in doc.running_text
    assert not any("Page" in t and "of" in t for t in doc.running_text)


def test_title_is_the_largest_first_page_text(doc: ParsedDocument) -> None:
    assert doc.title == "Request for Quotation 2024-117"


def test_side_by_side_label_and_value_stay_on_one_row(doc: ParsedDocument) -> None:
    rows = doc.text().splitlines()
    assert "Quotes Due | July 9, 2024 2:00 PM CDT" in rows
    assert "Pre-Bid Meeting | June 10, 2024" in rows


def test_wrapped_lines_are_joined_and_dehyphenated(doc: ParsedDocument) -> None:
    text = doc.text()
    assert (
        "All equipment must meet the requirements listed below and be delivered within 45 days of award."
        in text
    )
    assert "require-" not in text


def test_headings_build_section_paths(doc: ParsedDocument) -> None:
    para = next(b for b in doc.blocks if "45 days" in b.text)
    assert para.section_path == ["Request for Quotation 2024-117", "1.1 Key Dates"]
    delivery = next(b for b in doc.blocks if "central warehouse" in b.text)
    assert delivery.section_path[-1] == "DELIVERY"
    levels = {b.text: b.heading_level for b in doc.blocks if b.kind is BlockKind.HEADING}
    assert levels["1.1 Key Dates"] == 2
    assert levels["DELIVERY"] == 3


def test_heading_repeated_after_page_break_is_dropped(doc: ParsedDocument) -> None:
    headings = [b for b in doc.blocks if b.kind is BlockKind.HEADING and b.text == "DELIVERY"]
    assert len(headings) == 1
    continued = next(b for b in doc.blocks if "page two" in b.text)
    assert continued.page == 2
    assert continued.section_path[-1] == "DELIVERY"


def test_ruled_table_cells_are_read_by_position(doc: ParsedDocument) -> None:
    assert len(doc.tables) == 1
    table = doc.tables[0]
    assert table.page == 2
    assert table.rows == [["Item", "SKU"], ["Laptop 15 inch", "379-BFNZ"], ["Dock", "WD22TB4"]]
    block = next(b for b in doc.blocks if b.kind is BlockKind.TABLE)
    assert block.table_id == table.table_id
    assert "Laptop 15 inch | 379-BFNZ" in block.text
    # table text appears once, as the table block, not again as loose rows
    assert doc.text().count("379-BFNZ") == 1


def test_page_status(doc: ParsedDocument) -> None:
    status = {p.number: p.status for p in doc.pages}
    assert status == {
        1: PageStatus.OK,
        2: PageStatus.OK,
        3: PageStatus.NO_TEXT_LAYER,
        4: PageStatus.EMPTY,
    }
    assert doc.pages[2].image_count == 1


def test_ids_are_content_addressed(sample_pdf: Path) -> None:
    a = parse_pdf(sample_pdf, bid_id="BidA")
    b = parse_pdf(sample_pdf, bid_id="BidA")
    c = parse_pdf(sample_pdf, bid_id="BidB")
    assert a.doc_id == b.doc_id != c.doc_id
    assert a.file_sha256 == c.file_sha256


def test_metadata_date() -> None:
    assert pdf_metadata_date({"creationDate": "D:20240613175856-05'00'"}) == date(2024, 6, 13)
    assert pdf_metadata_date({"modDate": "D:20240514181050Z"}) == date(2024, 5, 14)
    assert pdf_metadata_date({"creationDate": "garbage"}) is None


def test_wrapped_form_cells_merge_into_one_row() -> None:
    rows = [
        ["Agency POC Name:", "Tamaira Hawkins", "Agency POC", "410-260-7533"],
        ["", "", "Phone Number:", ""],
        ["Agency POC Email", "thawkins@treasurer.state.md", "Agency POC", "N/A"],
        ["Address:", ".us", "Fax:", ""],
        ["Agency POC Mailing", "MD State Treasurer's Office", "", ""],
        ["Address:", "80 Calvert Street", "", ""],
    ]
    assert _merge_continuation_rows(rows) == [
        ["Agency POC Name:", "Tamaira Hawkins", "Agency POC Phone Number:", "410-260-7533"],
        ["Agency POC Email Address:", "thawkins@treasurer.state.md.us", "Agency POC Fax:", "N/A"],
        ["Agency POC Mailing Address:", "MD State Treasurer's Office 80 Calvert Street", "", ""],
    ]


def test_full_data_rows_are_never_merged() -> None:
    rows = [
        ["Description", "SKU"],
        ["Dell Latitude 5550 XCTO Base", "210-BLYZ"],
        ["Intel Core Ultra 5", "379-BFNZ"],
    ]
    assert _merge_continuation_rows(rows) == rows


def test_corrupt_file_raises(tmp_path: Path) -> None:
    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"%PDF-1.7 this is not really a pdf")
    with pytest.raises(Exception):  # noqa: B017 - any parser error is acceptable here
        parse_pdf(bad, bid_id="BidA")
