"""Word and Excel attachments parse into the same structure as PDFs."""

from pathlib import Path

from docx import Document
from openpyxl import Workbook

from rfp_intel.ingestion.loader import load_bid_folder
from rfp_intel.ingestion.models import BlockKind
from rfp_intel.ingestion.office import parse_docx, parse_xlsx

from .conftest import CUES_PATH


def _docx(path: Path) -> Path:
    doc = Document()
    doc.add_heading("Request for Quotation 2024-117", level=1)
    doc.add_heading("1.1 Submission", level=2)
    doc.add_paragraph("Quotes are due July 9, 2024 at 2:00 PM CDT via the portal.")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "Item", "SKU"
    table.cell(1, 0).text, table.cell(1, 1).text = "Laptop 15 inch", "379-BFNZ"
    doc.save(str(path))
    return path


def _xlsx(path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Price Schedule"
    ws.append(["Line", "Description", "Qty", "Unit price"])
    ws.append([1, "Dell Latitude 5550", 30, None])
    ws.append([2, "Dell Thunderbolt 4 Dock WD22TB4", 30, None])
    wb.create_sheet("Empty")
    wb.save(path)
    return path


def test_docx_keeps_headings_sections_and_tables(tmp_path: Path) -> None:
    doc = parse_docx(_docx(tmp_path / "rfq.docx"), "BidA")
    kinds = [b.kind for b in doc.blocks]
    assert kinds == [BlockKind.HEADING, BlockKind.HEADING, BlockKind.PARAGRAPH, BlockKind.TABLE]
    assert doc.title == "Request for Quotation 2024-117" and doc.media_type == "docx"
    para = doc.blocks[2]
    assert para.section_path[-1] == "1.1 Submission" and "July 9, 2024" in para.text
    assert doc.tables[0].rows[1] == ["Laptop 15 inch", "379-BFNZ"]


def test_xlsx_sheets_become_pages_with_tables(tmp_path: Path) -> None:
    doc = parse_xlsx(_xlsx(tmp_path / "prices.xlsx"), "BidA")
    assert doc.page_count == 2 and doc.pages[0].note == "sheet: Price Schedule"
    assert doc.pages[1].status.value == "empty"
    table = doc.tables[0]
    assert table.page == 1 and table.rows[1] == ["1", "Dell Latitude 5550", "30", ""]
    assert "WD22TB4" in doc.blocks[1].text and doc.blocks[0].text == "Price Schedule"


def test_office_files_are_part_of_a_bid_folder(tmp_path: Path) -> None:
    folder = tmp_path / "BidX"
    folder.mkdir()
    _docx(folder / "rfq.docx")
    _xlsx(folder / "prices.xlsx")
    bid = load_bid_folder(folder, CUES_PATH)
    assert sorted(d.file_name for d in bid.documents) == ["prices.xlsx", "rfq.docx"]
    assert not bid.skipped_files
