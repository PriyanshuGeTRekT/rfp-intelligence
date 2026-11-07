"""Word (.docx) and Excel (.xlsx) attachments.

Bid folders often carry pricing sheets and fill-in forms in Office formats. Both become the same
`ParsedDocument` as a PDF:

- .docx: paragraphs and tables in body order; "Heading N" and "Title" styles become headings,
  so sections work as they do for PDFs. Word files have no fixed pages, so everything is page 1.
- .xlsx: each worksheet is one "page" (numbered in workbook order, the sheet name in the page
  note), with the sheet name as a heading and its used range as a table. Formulas are read as
  their last computed values.
"""

import hashlib
import re
from pathlib import Path

import docx
from docx.table import Table as DocxTable
from docx.text.paragraph import Paragraph
from openpyxl import load_workbook

from rfp_intel.ingestion.clean import normalize_text
from rfp_intel.ingestion.models import Block, BlockKind, PageInfo, PageStatus, ParsedDocument, Table
from rfp_intel.ingestion.structure import assign_sections

MAX_SHEET_ROWS = 2_000  # a sheet longer than this is cut, and the page note says so
_HEADING_RE = re.compile(r"^Heading (\d)$")


def _doc_id(bid_id: str, sha: str) -> str:
    return hashlib.sha256(f"{bid_id}/{sha}".encode()).hexdigest()[:16]


def _heading_level(paragraph: Paragraph) -> int | None:
    style = paragraph.style.name if paragraph.style is not None else ""
    if style == "Title":
        return 1
    m = _HEADING_RE.match(style or "")
    return int(m.group(1)) if m else None


def _rows(cells: list[list[str]]) -> list[list[str]]:
    rows = [[normalize_text(c) for c in row] for row in cells]
    return [row for row in rows if any(row)]


def parse_docx(path: Path, bid_id: str, file_name: str | None = None) -> ParsedDocument:
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    document = docx.Document(str(path))
    blocks: list[Block] = []
    tables: list[Table] = []
    for child in document.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            paragraph = Paragraph(child, document)
            text = normalize_text(paragraph.text)
            if not text:
                continue
            level = _heading_level(paragraph)
            kind = BlockKind.HEADING if level else BlockKind.PARAGRAPH
            blocks.append(Block(kind=kind, text=text, page=1, heading_level=level))
        elif tag == "tbl":
            table = DocxTable(child, document)
            rows = _rows([[cell.text for cell in row.cells] for row in table.rows])
            if not rows:
                continue
            t = Table(table_id=len(tables), page=1, rows=rows, method="docx")
            tables.append(t)
            blocks.append(
                Block(kind=BlockKind.TABLE, text=t.to_text(), page=1, table_id=t.table_id)
            )
    blocks, sections = assign_sections(blocks)
    chars = sum(len(b.text) for b in blocks)
    core_title = normalize_text(document.core_properties.title or "")
    title = core_title or next((b.text for b in blocks if b.kind is BlockKind.HEADING), path.stem)
    return ParsedDocument(
        doc_id=_doc_id(bid_id, sha),
        bid_id=bid_id,
        file_name=file_name or path.name,
        source_path=str(path),
        file_sha256=sha,
        media_type="docx",
        title=title,
        page_count=1,
        pages=[
            PageInfo(
                number=1, status=PageStatus.OK if chars else PageStatus.EMPTY, char_count=chars
            )
        ],
        blocks=blocks,
        tables=tables,
        sections=sections,
    )


def parse_xlsx(path: Path, bid_id: str, file_name: str | None = None) -> ParsedDocument:
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    workbook = load_workbook(path, read_only=True, data_only=True)
    blocks: list[Block] = []
    tables: list[Table] = []
    pages: list[PageInfo] = []
    try:
        for number, sheet in enumerate(workbook.worksheets, start=1):
            cells: list[list[str]] = []
            truncated = False
            for i, row in enumerate(sheet.iter_rows(values_only=True)):
                if i >= MAX_SHEET_ROWS:
                    truncated = True
                    break
                cells.append(["" if v is None else str(v) for v in row])
            rows = _rows(cells)
            note = f"sheet: {sheet.title}" + (
                f" (first {MAX_SHEET_ROWS} rows)" if truncated else ""
            )
            if not rows:
                pages.append(
                    PageInfo(number=number, status=PageStatus.EMPTY, char_count=0, note=note)
                )
                continue
            name = normalize_text(sheet.title)
            blocks.append(Block(kind=BlockKind.HEADING, text=name, page=number, heading_level=1))
            t = Table(table_id=len(tables), page=number, rows=rows, method="xlsx")
            tables.append(t)
            text = t.to_text()
            blocks.append(Block(kind=BlockKind.TABLE, text=text, page=number, table_id=t.table_id))
            pages.append(
                PageInfo(number=number, status=PageStatus.OK, char_count=len(text), note=note)
            )
    finally:
        workbook.close()
    blocks, sections = assign_sections(blocks)
    return ParsedDocument(
        doc_id=_doc_id(bid_id, sha),
        bid_id=bid_id,
        file_name=file_name or path.name,
        source_path=str(path),
        file_sha256=sha,
        media_type="xlsx",
        title=path.stem,
        page_count=len(pages),
        pages=pages,
        blocks=blocks,
        tables=tables,
        sections=sections,
    )
