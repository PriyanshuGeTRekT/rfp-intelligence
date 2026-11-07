"""PDF parsing with PyMuPDF.

Pipeline per document:
1. Read text lines with font size, boldness and position.
2. Find page headers and footers that repeat across pages and remove them from the body.
3. Find ruled tables and read each cell from word positions (PyMuPDF's own cell text drops
   spaces and moves hyphens in some PDFs, e.g. "210-BLYZ" comes out as "210BLYZ -").
4. Group the remaining lines into visual rows by vertical overlap, so side-by-side text
   stays together: "Solicitation Due | 27-JUN-2024 14:00:00".
5. Group rows into headings and paragraphs, then assign section paths.
"""

import hashlib
import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pymupdf

from rfp_intel.ingestion.clean import (
    is_bullet,
    is_page_number,
    join_lines,
    normalize_text,
    page_marker_key,
)
from rfp_intel.ingestion.models import (
    BBox,
    Block,
    BlockKind,
    PageInfo,
    PageStatus,
    ParsedDocument,
    Table,
)
from rfp_intel.ingestion.structure import assign_sections, numbered_level

MARGIN_FRACTION = 0.12  # top and bottom bands searched for running headers and footers
MIN_PAGE_CHARS = 10  # below this a page counts as having no text
# A textless page with this many vector shapes is almost always text drawn as outlines
# (a flattened form, a printed-to-PDF scan), so it is reported as needing OCR, not empty.
MIN_OUTLINE_DRAWINGS = 20
# Tables on OCR pages, found from layout (see _layout_tables).
MIN_TABLE_ROWS = 3
MIN_LAYOUT_COLUMNS = 3
COLUMN_TOLERANCE = 18.0  # points: segment starts this close are one column
MAX_MEDIAN_CELL_CHARS = 40  # longer cells are prose that happens to be indented
OCR_SIZE_RATIO = 0.75  # an OCR box is about 4/3 of the font size
_LIST_START_RE = re.compile(r"^(?:\(?\d{1,2}[.)]|\(?[a-zA-Z][.)]|[•◦▪■●○·])\s")
_PDF_DATE_RE = re.compile(r"D:(\d{4})(\d{2})(\d{2})")


@dataclass
class _Line:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    size: float
    bold: bool

    @property
    def height(self) -> float:
        return max(self.y1 - self.y0, 1.0)


@dataclass
class _Row:
    lines: list[_Line]

    @property
    def y0(self) -> float:
        return min(ln.y0 for ln in self.lines)

    @property
    def y1(self) -> float:
        return max(ln.y1 for ln in self.lines)

    @property
    def x0(self) -> float:
        return min(ln.x0 for ln in self.lines)

    @property
    def size(self) -> float:
        return max(ln.size for ln in self.lines)

    @property
    def bold(self) -> bool:
        return all(ln.bold for ln in self.lines)

    @property
    def multi(self) -> bool:
        return len(self.lines) > 1

    def text(self) -> str:
        parts = [self.lines[0].text]
        for prev, cur in zip(self.lines, self.lines[1:], strict=False):
            gap = cur.x0 - prev.x1
            parts.append(" | " if gap >= max(12.0, 1.5 * cur.size) else " ")
            parts.append(cur.text)
        return "".join(parts)


@dataclass
class _Item:
    """A row or a table, positioned on the page for reading order."""

    y0: float
    row: _Row | None = None
    table: Table | None = None


# ---------------------------------------------------------------------------------------------
# Lines


def _is_bold(span: dict[str, Any]) -> bool:
    return bool(span["flags"] & 16) or "bold" in span["font"].lower()


def _line_text(spans: list[dict[str, Any]]) -> str:
    """Join spans, inserting a space or a column separator where the PDF left a gap."""
    out = ""
    prev_x1: float | None = None
    for span in spans:
        text = span["text"]
        if prev_x1 is not None and text.strip():
            gap = span["bbox"][0] - prev_x1
            size = span["size"]
            if gap >= max(12.0, 1.5 * size):
                out = out.rstrip() + " | "
            elif gap > 0.15 * size and not out.endswith(" ") and not text.startswith(" "):
                out += " "
        out += text
        if text.strip():
            prev_x1 = span["bbox"][2]
    return normalize_text(out)


def _extract_lines(page: pymupdf.Page) -> list[_Line]:
    lines: list[_Line] = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            if abs(line["dir"][1]) > 0.1:  # rotated or vertical text
                continue
            spans = [s for s in line["spans"] if s["text"].strip()]
            if not spans:
                continue
            text = _line_text(spans)
            if not text:
                continue
            main = max(spans, key=lambda s: len(s["text"].strip()))
            x0, y0, x1, y1 = line["bbox"]
            lines.append(
                _Line(
                    text=text,
                    x0=x0,
                    y0=y0,
                    x1=x1,
                    y1=y1,
                    size=round(float(main["size"]), 1),
                    bold=all(_is_bold(s) for s in spans),
                )
            )
    return lines


def _in_margin(line: _Line, page_height: float) -> bool:
    return (
        line.y1 <= MARGIN_FRACTION * page_height or line.y0 >= (1 - MARGIN_FRACTION) * page_height
    )


def _running_keys(pages: list[list[_Line]], heights: list[float]) -> set[str]:
    """Margin lines that repeat on at least half of the pages that have text."""
    counts: Counter[str] = Counter()
    pages_with_text = 0
    for lines, height in zip(pages, heights, strict=True):
        if lines:
            pages_with_text += 1
        counts.update({page_marker_key(ln.text) for ln in lines if _in_margin(ln, height)})
    if pages_with_text < 2:
        return set()
    threshold = max(2, math.ceil(0.5 * pages_with_text))
    return {key for key, n in counts.items() if n >= threshold}


# ---------------------------------------------------------------------------------------------
# Tables


def _cell_text(words: list[tuple[Any, ...]], rect: pymupdf.Rect) -> str:
    inside = [
        w for w in words if rect.contains(pymupdf.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2))
    ]
    if not inside:
        return ""
    inside.sort(key=lambda w: (w[3], w[0]))
    lines: list[list[tuple[Any, ...]]] = []
    for w in inside:
        if lines and abs(lines[-1][-1][3] - w[3]) <= 3:
            lines[-1].append(w)
        else:
            lines.append([w])
    text = ""
    for line in lines:
        text = join_lines(text, " ".join(str(w[4]) for w in sorted(line, key=lambda w: w[0])))
    return normalize_text(text)


def _is_continuation(prev: list[str], row: list[str]) -> bool:
    """Is `row` only the wrapped second line of cells in `prev`?

    Form tables wrap long labels and values onto a new table row, e.g.
    ["Agency POC Email", "thawkins@treasurer.state.md"] then ["Address:", ".us"]. The row is a
    continuation when its first filled cell continues a label that is not finished yet (no
    trailing colon) and either it fills fewer cells, or it is the line that finishes the label.
    """
    filled = {i for i, c in enumerate(row) if c}
    prev_filled = {i for i, c in enumerate(prev) if c}
    if not filled or not filled <= prev_filled:
        return False
    first = min(filled)
    if prev[first].rstrip().endswith((":", ".")):
        return False
    if filled < prev_filled:
        return True
    return row[first].rstrip().endswith(":")


def _merge_continuation_rows(rows: list[list[str]]) -> list[list[str]]:
    merged: list[list[str]] = []
    for row in rows:
        if merged and _is_continuation(merged[-1], row):
            merged[-1] = [
                join_lines(p, c) if c else p for p, c in zip(merged[-1], row, strict=True)
            ]
            continue
        merged.append(list(row))
    return merged


def _clean_table(rows: list[list[str]]) -> list[list[str]]:
    rows = [r for r in rows if any(r)]
    if not rows:
        return []
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    keep = [i for i in range(width) if any(r[i] for r in rows)]
    return [[r[i] for i in keep] for r in rows]


def _find_tables(page: pymupdf.Page, page_no: int, first_id: int) -> list[Table]:
    try:
        found = page.find_tables().tables
    except Exception:  # table detection is best effort; the rows path still covers the text
        return []
    words = page.get_text("words")
    tables: list[Table] = []
    for t in found:
        raw = [
            ["" if cell is None else _cell_text(words, pymupdf.Rect(cell)) for cell in row.cells]
            for row in t.rows
        ]
        rows = _clean_table(_merge_continuation_rows(_clean_table(raw)))
        if len(rows) < 2 or len(rows[0]) < 2:
            continue
        cells = [c for r in rows for c in r]
        if sum(1 for c in cells if c) / len(cells) < 0.25:
            continue
        tables.append(
            Table(
                table_id=first_id + len(tables),
                page=page_no,
                rows=rows,
                bbox=_bbox(t.bbox),
                method="pymupdf_lines+word_cells",
            )
        )
    return tables


@dataclass
class _Segment:
    text: str
    x0: float
    x1: float


def _segments(row: _Row) -> list[_Segment]:
    """A row's text split where a column gap separates it (the same gap `_Row.text` marks)."""
    segs: list[_Segment] = []
    for ln in row.lines:
        if segs and ln.x0 - segs[-1].x1 < max(12.0, 1.5 * ln.size):
            segs[-1] = _Segment(f"{segs[-1].text} {ln.text}", segs[-1].x0, ln.x1)
        else:
            segs.append(_Segment(ln.text, ln.x0, ln.x1))
    return segs


def _column_starts(segment_rows: list[list[_Segment]]) -> list[float]:
    """Column positions: segment starts within COLUMN_TOLERANCE of each other form one column,
    and a column counts when segments from at least half the rows start there."""
    starts = sorted(s.x0 for segs in segment_rows for s in segs)
    groups: list[list[float]] = []
    for x in starts:
        if groups and x - groups[-1][-1] <= COLUMN_TOLERANCE:
            groups[-1].append(x)
        else:
            groups.append([x])
    need = max(2, len(segment_rows) // 2)
    return [min(g) for g in groups if len(g) >= need]


def _layout_table(run: list[_Row], page_no: int, table_id: int) -> Table | None:
    segment_rows = [_segments(r) for r in run]
    columns = _column_starts([segs for segs in segment_rows if len(segs) >= 2])
    if len(columns) < MIN_LAYOUT_COLUMNS:
        return None
    grid: list[list[str]] = []
    for segs in segment_rows:
        cells = [""] * len(columns)
        for s in segs:  # a segment belongs to the last column starting at or before it
            col = max([0, *(i for i, x in enumerate(columns) if x <= s.x0 + COLUMN_TOLERANCE / 2)])
            cells[col] = f"{cells[col]} {s.text}".strip()
        grid.append(cells)
    rows = _clean_table(_merge_continuation_rows(_clean_table(grid)))
    if len(rows) < MIN_TABLE_ROWS or len(rows[0]) < MIN_LAYOUT_COLUMNS:
        return None
    cells = [c for r in rows for c in r]
    if sum(1 for c in cells if c) / len(cells) < 0.5:
        return None
    # Indented prose (lettered or numbered paragraphs) also lines up in columns; a table has
    # several filled cells in most rows, and short ones.
    if sum(1 for r in rows if sum(1 for c in r if c) >= 2) < 0.6 * len(rows):
        return None
    lengths = sorted(len(c) for c in cells if c)
    if lengths[len(lengths) // 2] > MAX_MEDIAN_CELL_CHARS:
        return None
    x0 = min(r.x0 for r in run)
    x1 = max(ln.x1 for r in run for ln in r.lines)
    return Table(
        table_id=table_id,
        page=page_no,
        rows=rows,
        bbox=_bbox((x0, run[0].y0, x1, run[-1].y1)),
        method="ocr_layout",
    )


def _layout_tables(lines: list[_Line], page_no: int, first_id: int) -> list[Table]:
    """Tables on a page read by OCR, where there are no ruling lines to find them by.

    A table is a run of consecutive rows split into several segments whose starts line up in
    at least MIN_LAYOUT_COLUMNS shared columns. A one-segment row inside a run that starts right
    of the first column is a wrapped cell and stays in the run, to be merged into the row above.
    Two-column label / value rows are left to the row path, which already keeps them together.
    """
    tables: list[Table] = []
    run: list[_Row] = []

    def close() -> None:
        if len(run) >= MIN_TABLE_ROWS:
            table = _layout_table(run, page_no, first_id + len(tables))
            if table is not None:
                tables.append(table)
        run.clear()

    for row in _build_rows(lines):
        segs = _segments(row)
        near = not run or row.y0 - run[-1].y1 <= 2.5 * row.lines[0].height
        wrapped = bool(run) and len(segs) == 1 and segs[0].x0 > run[0].x0 + COLUMN_TOLERANCE
        if near and (len(segs) >= 2 or wrapped):
            run.append(row)
            continue
        close()
        if len(segs) >= 2:
            run.append(row)
    close()
    return tables


def _bbox(values: Sequence[float]) -> BBox:
    x0, y0, x1, y1 = (round(float(v), 1) for v in values)
    return (x0, y0, x1, y1)


def _inside(line: _Line, bbox: BBox) -> bool:
    cx, cy = (line.x0 + line.x1) / 2, (line.y0 + line.y1) / 2
    return bbox[0] - 1 <= cx <= bbox[2] + 1 and bbox[1] - 1 <= cy <= bbox[3] + 1


# ---------------------------------------------------------------------------------------------
# Rows and blocks


def _build_rows(lines: list[_Line]) -> list[_Row]:
    rows: list[_Row] = []
    for line in sorted(lines, key=lambda ln: (ln.y0, ln.x0)):
        for row in reversed(rows[-3:]):
            overlap = min(row.y1, line.y1) - max(row.y0, line.y0)
            if overlap >= 0.5 * min(line.height, row.y1 - row.y0):
                row.lines.append(line)
                break
        else:
            rows.append(_Row([line]))
    for row in rows:
        row.lines.sort(key=lambda ln: ln.x0)
    return rows


def _is_heading(row: _Row, body_size: float) -> bool:
    text = row.text()
    if not 2 <= len(text) <= 120 or not re.search(r"[A-Za-z]{2}", text):
        return False
    if row.multi and not row.bold:
        return False
    numbered = numbered_level(text) is not None
    if text.endswith((".", ",", ";")) and not numbered:
        return False
    if row.size >= body_size + 1.5:
        return True
    if row.bold and len(text) <= 100:
        return True
    words = text.split()
    return text.isupper() and 2 <= len(words) <= 10 and row.size >= body_size - 0.5


def _heading_level(text: str, size: float, body_size: float) -> int:
    level = numbered_level(text)
    if level is not None:
        return level
    if size >= body_size + 4:
        return 1
    if size >= body_size + 1.5:
        return 2
    return 3


def _blocks_for_page(items: list[_Item], page_no: int, body_size: float) -> list[Block]:
    blocks: list[Block] = []
    para: list[str] = []
    para_bbox: list[float] = []
    prev_row: _Row | None = None
    last_seg_x0: float | None = None  # x of the last segment of a multi-segment row

    def flush() -> None:
        nonlocal para, para_bbox, prev_row
        if para:
            blocks.append(
                Block(
                    kind=BlockKind.PARAGRAPH,
                    text="\n".join(para),
                    page=page_no,
                    bbox=_bbox(para_bbox),
                )
            )
        para, para_bbox, prev_row = [], [], None

    for item in items:
        if item.table is not None:
            flush()
            blocks.append(
                Block(
                    kind=BlockKind.TABLE,
                    text=item.table.to_text(),
                    page=page_no,
                    table_id=item.table.table_id,
                    bbox=item.table.bbox,
                )
            )
            continue
        row = item.row
        assert row is not None
        text = row.text()

        if _is_heading(row, body_size):
            prev_heading = blocks[-1] if blocks and not para else None
            gap_ok = prev_row is None
            if (
                prev_heading is not None
                and prev_heading.kind is BlockKind.HEADING
                and gap_ok
                and prev_heading.bbox is not None
                and row.y0 - prev_heading.bbox[3] <= 0.8 * body_size
                and numbered_level(text) is None
                and prev_heading.text.isupper() == text.isupper()
                and not prev_heading.text.endswith(":")
            ):
                bbox = prev_heading.bbox
                prev_heading.text = f"{prev_heading.text} {text}"
                prev_heading.bbox = (bbox[0], bbox[1], max(bbox[2], row.lines[-1].x1), row.y1)
                continue
            flush()
            blocks.append(
                Block(
                    kind=BlockKind.HEADING,
                    text=text,
                    page=page_no,
                    heading_level=_heading_level(text, row.size, body_size),
                    bbox=(
                        round(row.x0, 1),
                        round(row.y0, 1),
                        round(row.lines[-1].x1, 1),
                        round(row.y1, 1),
                    ),
                )
            )
            continue

        new_block = (
            prev_row is None
            or row.y0 - prev_row.y1 > 0.6 * body_size
            or abs(row.size - prev_row.size) > 1.0
            or (_LIST_START_RE.match(text) is not None and not is_bullet(para[-1]))
        )
        if new_block:
            flush()
            para = [text]
            para_bbox = [row.x0, row.y0, row.lines[-1].x1, row.y1]
            last_seg_x0 = row.lines[-1].x0 if row.multi else None
        else:
            continues_last_segment = (
                not row.multi and last_seg_x0 is not None and abs(row.x0 - last_seg_x0) <= 4
            )
            if row.multi or (
                prev_row is not None and prev_row.multi and not continues_last_segment
            ):
                para.append(text)
            else:
                para[-1] = join_lines(para[-1], text)
            if row.multi:
                last_seg_x0 = row.lines[-1].x0
            elif not continues_last_segment:
                last_seg_x0 = None
            para_bbox = [
                min(para_bbox[0], row.x0),
                para_bbox[1],
                max(para_bbox[2], row.lines[-1].x1),
                row.y1,
            ]
        prev_row = row
    flush()
    return blocks


# ---------------------------------------------------------------------------------------------
# Document


def _body_size(pages: list[list[_Line]]) -> float:
    weights: Counter[float] = Counter()
    for lines in pages:
        for ln in lines:
            weights[ln.size] += len(ln.text)
    return weights.most_common(1)[0][0] if weights else 10.0


def _title(first_page: list[_Row], page_height: float, body_size: float, fallback: str) -> str:
    rows = [
        r for r in first_page if r.y0 < 0.6 * page_height and re.search(r"[A-Za-z]{3}", r.text())
    ]
    if rows:
        top = max(r.size for r in rows)
        if top > body_size:
            picked: list[str] = []
            for r in rows:
                if r.size == top:
                    picked.append(r.text())
                elif picked:
                    break
            return " ".join(picked[:3])
        first_heading = next((r for r in rows if r.bold), None)
        if first_heading is not None:
            return first_heading.text()
    return fallback


def _ocr_scanned_pages(doc: pymupdf.Document, raw_pages: list[list[_Line]]) -> set[int]:
    """OCR every page with almost no text whose content is images (a scan) or vector outlines
    (text flattened into drawings, as some fill-in forms are); return the indexes it read."""
    from rfp_intel.ingestion.ocr import ocr_available, ocr_page

    scanned = [
        i
        for i in range(len(doc))
        if sum(len(ln.text) for ln in raw_pages[i]) < MIN_PAGE_CHARS
        and (doc[i].get_images(full=False) or len(doc[i].get_drawings()) >= MIN_OUTLINE_DRAWINGS)
    ]
    if not scanned or not ocr_available():
        return set()
    read: set[int] = set()
    for i in scanned:
        lines = [
            _Line(
                text=ln.text,
                x0=ln.x0,
                y0=ln.y0,
                x1=ln.x1,
                y1=ln.y1,
                size=round((ln.y1 - ln.y0) * OCR_SIZE_RATIO, 1),
                bold=False,
            )
            for ln in ocr_page(doc[i])
        ]
        if sum(len(ln.text) for ln in lines) >= MIN_PAGE_CHARS:
            raw_pages[i] = lines
            read.add(i)
    return read


def pdf_metadata_date(metadata: dict[str, str]) -> date | None:
    for key in ("creationDate", "modDate"):
        m = _PDF_DATE_RE.match(metadata.get(key, ""))
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
    return None


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_pdf(path: Path, bid_id: str, file_name: str | None = None) -> ParsedDocument:
    file_name = file_name or path.name
    sha = file_sha256(path)
    with pymupdf.open(path) as doc:
        if doc.needs_pass:
            raise ValueError("PDF is encrypted")
        metadata = {k: str(v) for k, v in (doc.metadata or {}).items() if v}
        raw_pages = [_extract_lines(page) for page in doc]
        ocr_pages = _ocr_scanned_pages(doc, raw_pages)
        heights = [page.rect.height for page in doc]
        running = _running_keys(raw_pages, heights)
        body_size = _body_size(raw_pages)

        running_text: list[str] = []
        seen_running: set[str] = set()
        pages: list[PageInfo] = []
        blocks: list[Block] = []
        tables: list[Table] = []
        first_rows: list[_Row] = []

        for index, page in enumerate(doc):
            page_no = index + 1
            height = heights[index]
            body_lines: list[_Line] = []
            for ln in raw_pages[index]:
                key = page_marker_key(ln.text)
                if _in_margin(ln, height) and (key in running or is_page_number(ln.text)):
                    if key not in seen_running and not is_page_number(ln.text):
                        seen_running.add(key)
                        running_text.append(ln.text)
                    continue
                body_lines.append(ln)

            chars = sum(len(ln.text) for ln in body_lines)
            drawings = page.get_drawings() if chars < MIN_PAGE_CHARS else []
            page_tables = (
                _layout_tables(body_lines, page_no, first_id=len(tables))
                if index in ocr_pages
                else _find_tables(page, page_no, first_id=len(tables))
                if chars >= MIN_PAGE_CHARS
                else []
            )
            tables.extend(page_tables)
            free_lines = [
                ln
                for ln in body_lines
                if not any(_inside(ln, t.bbox) for t in page_tables if t.bbox)
            ]
            rows = _build_rows(free_lines)
            if index == 0:
                # The title may sit in a running header, so look at every first-page line.
                first_rows = _build_rows([ln for ln in raw_pages[0] if not is_page_number(ln.text)])
            items = [_Item(y0=r.y0, row=r) for r in rows] + [
                _Item(y0=t.bbox[1] if t.bbox else 0.0, table=t) for t in page_tables
            ]
            items.sort(key=lambda it: it.y0)
            blocks.extend(_blocks_for_page(items, page_no, body_size))

            images = len(page.get_images(full=False))
            if index in ocr_pages:
                pages.append(
                    PageInfo(
                        number=page_no,
                        status=PageStatus.OCR,
                        char_count=chars,
                        image_count=images,
                        note="text read by OCR",
                    )
                )
            elif chars >= MIN_PAGE_CHARS:
                pages.append(
                    PageInfo(
                        number=page_no, status=PageStatus.OK, char_count=chars, image_count=images
                    )
                )
            elif images or len(drawings) >= MIN_OUTLINE_DRAWINGS:
                pages.append(
                    PageInfo(
                        number=page_no,
                        status=PageStatus.NO_TEXT_LAYER,
                        char_count=chars,
                        image_count=images,
                        note=(
                            "page content is images"
                            if images
                            else "page content is vector outlines"
                        )
                        + " with no text layer; needs OCR",
                    )
                )
            else:
                pages.append(PageInfo(number=page_no, status=PageStatus.EMPTY, char_count=chars))

        meta_title = metadata.get("title", "")
        if len(meta_title) < 4 or meta_title.lower().startswith(("microsoft", "untitled")):
            meta_title = Path(file_name).stem.replace("_", " ")
        title = _title(first_rows, heights[0] if heights else 792.0, body_size, meta_title)

        blocks, sections = assign_sections(blocks)
        return ParsedDocument(
            doc_id=hashlib.sha256(f"{bid_id}/{sha}".encode()).hexdigest()[:16],
            bid_id=bid_id,
            file_name=file_name,
            source_path=str(path),
            file_sha256=sha,
            media_type="pdf",
            title=title,
            page_count=len(pages),
            pages=pages,
            blocks=blocks,
            tables=tables,
            sections=sections,
            running_text=running_text,
            metadata=metadata,
        )
