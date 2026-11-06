"""Walk a parsed document and turn every value in it into a typed, labelled fact.

Context matters more than the value: "06/10/2024" is a deadline next to "PROPOSAL DUE" and a
line-item date under a "Qty | Due Date" header. So each value's context is the nearest thing
that names it: the label to its left in a row, its column header in a table, or its sentence.
"""

import hashlib
import re
from dataclasses import dataclass

from rfp_intel.facts.datetimes import find_datetimes
from rfp_intel.facts.labels import FactTypeConfig, label
from rfp_intel.facts.models import Fact, FactKind
from rfp_intel.facts.patterns import (
    QTY_UNITS,
    Match,
    find_contacts,
    find_durations,
    find_identifiers,
    find_money,
    find_percents,
    find_prose_quantities,
    is_number_cell,
)
from rfp_intel.ingestion.models import Block, BlockKind, ParsedDocument, Table

SEPARATOR = " | "
MAX_LABEL_CHARS = 80
_QTY_HEADER_RE = re.compile(r"\b(?:qty|quantity|quantities)\b", re.I)
_LINE_NO_RE = re.compile(r"^\s*\d{1,3}(?:\.\d{1,3})?\.?\s+")
_ABBREVIATIONS = {
    "no", "nos", "inc", "co", "corp", "ltd", "llc", "st", "dr", "mr", "ms", "mrs", "jr", "sr",
    "a.m", "p.m", "e.g", "i.e", "etc", "vs", "approx", "ext", "dept", "sec", "u.s", "fig",
}  # fmt: skip
_SENTENCE_END_RE = re.compile(r"[.!?]\s+(?=[A-Z0-9(\"“])")


@dataclass(frozen=True)
class _Unit:
    """A span of block text to extract from, with the text that names its values."""

    offset: int  # start of `text` within the block text
    text: str
    label: str  # label to the left or column header; empty when the unit names itself
    scope_extra: str = ""  # extra text for exclusions only (a table's header row)


def split_sentences(text: str) -> list[tuple[int, str]]:
    """Sentence spans with offsets, without splitting "No. 2", "2:00 p.m. CST" or "1. Item"."""
    pieces: list[tuple[int, str]] = []
    start = 0
    for m in _SENTENCE_END_RE.finditer(text):
        before = text[start : m.start()].split()
        token = before[-1].lower().rstrip(".") if before else ""
        list_number = token.isdigit() and len(token) <= 2  # "1. Item", not "2024. Next"
        if token in _ABBREVIATIONS or list_number or (len(token) == 1 and token.isalpha()):
            continue
        pieces.append((start, text[start : m.start() + 1]))
        start = m.end()
    if start < len(text):
        pieces.append((start, text[start:]))
    return [(o, s) for o, s in pieces if s.strip()]


def _segments(line: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    pos = 0
    for part in line.split(SEPARATOR):
        out.append((pos, part))
        pos += len(part) + len(SEPARATOR)
    return out


def _text_units(block: Block) -> list[_Unit]:
    if block.kind is BlockKind.KV:
        return [_Unit(0, block.text, "")]
    units: list[_Unit] = []
    line_start = 0
    for line in block.text.split("\n"):
        segments = _segments(line)
        for k, (seg_off, seg) in enumerate(segments):
            left = segments[k - 1][1].strip() if k > 0 else ""
            left = left if len(left) <= MAX_LABEL_CHARS else ""
            for sent_off, sentence in split_sentences(seg):
                units.append(_Unit(line_start + seg_off + sent_off, sentence, left))
        line_start += len(line) + 1
    return units


def _looks_like_header(row: list[str], min_cells: int) -> bool:
    filled = [c for c in row if c]
    return (
        len(filled) >= min_cells
        and not any(ch.isdigit() for c in filled for ch in c)
        and all(len(c) <= 40 and not c.rstrip().endswith(":") for c in filled)
    )


def _header_row(rows: list[list[str]], before: int) -> list[str] | None:
    """Column headers for row `before`: the first row if it looks like headers, else the
    nearest row above with three or more short, digit-free cells. Two-cell rows such as
    "Manufacturer Name | Dell" are label-value pairs in a form layout, not headers."""
    for r in range(before - 1, -1, -1):
        if _looks_like_header(rows[r], 2 if r == 0 else 3):
            return rows[r]
    return None


def _table_units(block: Block, table: Table) -> tuple[list[_Unit], list[Match]]:
    """Units per cell, and quantities read from a "Qty" column."""
    units: list[_Unit] = []
    quantities: list[Match] = []
    line_start = 0
    for r, row in enumerate(table.rows):
        if not any(row):
            continue
        header = _header_row(table.rows, r)
        header_text = SEPARATOR.join(c for c in header if c) if header else ""
        line = SEPARATOR.join(c for c in row if c)
        pos = 0
        filled_before: list[str] = []
        for c, cell in enumerate(row):
            if not cell:
                continue
            cell_off = line_start + line.index(cell, pos)
            pos = line.index(cell, pos) + len(cell)
            if header is not None and row is not header and c < len(header) and header[c]:
                name = header[c]
            else:
                name = (
                    filled_before[-1]
                    if filled_before and len(filled_before[-1]) <= MAX_LABEL_CHARS
                    else ""
                )
            if row is not header:
                for sent_off, sentence in split_sentences(cell):
                    units.append(_Unit(cell_off + sent_off, sentence, name, header_text))
                qty_column = (
                    header is not None
                    and c < len(header)
                    and _QTY_HEADER_RE.search(header[c] or "") is not None
                )
                if qty_column and is_number_cell(cell):
                    item = next((x for i, x in enumerate(row) if x and i != c), "")
                    quantities.append(
                        Match(
                            FactKind.QUANTITY,
                            cell_off,
                            cell_off + len(cell),
                            {"qty": int(cell.replace(",", "")), "item": _LINE_NO_RE.sub("", item)},
                        )
                    )
            filled_before.append(cell)
        line_start += len(line) + 1
    return units, quantities


def _row_quantities(block: Block) -> list[Match]:
    """ "15.01 Tier 1 Small | 50,000 | Each" plus its wrapped continuation lines."""
    out: list[Match] = []
    lines = block.text.split("\n")
    line_start = 0
    for i, line in enumerate(lines):
        segments = _segments(line)
        for k in range(1, len(segments) - 1):
            off, cell = segments[k]
            unit = segments[k + 1][1].strip().lower()
            if is_number_cell(cell) and unit in QTY_UNITS:
                item = segments[0][1]
                for nxt in lines[i + 1 :]:
                    if SEPARATOR in nxt:
                        break
                    item = f"{item} {nxt}"
                out.append(
                    Match(
                        FactKind.QUANTITY,
                        line_start + off,
                        line_start + off + len(cell),
                        {
                            "qty": int(cell.replace(",", "")),
                            "unit": unit,
                            "item": _LINE_NO_RE.sub("", item).strip(),
                        },
                    )
                )
        line_start += len(line) + 1
    return out


def _extract(text: str, default_year: int | None) -> list[Match]:
    matches: list[Match] = [
        Match(FactKind.DATETIME, m.start, m.end, m.value())
        for m in find_datetimes(text, default_year)
    ]
    matches += find_durations(text)
    matches += find_money(text)
    matches += find_percents(text)
    matches += find_contacts(text)
    matches += find_prose_quantities(text)
    taken = [(m.start, m.end) for m in matches]
    matches += find_identifiers(text, taken)
    return matches


def extract_facts(doc: ParsedDocument, config: FactTypeConfig) -> list[Fact]:
    default_year = doc.doc_date.year if doc.doc_date else None
    tables = {t.table_id: t for t in doc.tables}
    facts: list[Fact] = []
    seen: set[tuple[int, int, int, FactKind]] = set()

    def neighbours(block_index: int, block: Block) -> str:
        """The label-value fields just above a field, within the same section."""
        if block.kind is not BlockKind.KV:
            return ""
        texts: list[str] = []
        for prev in reversed(doc.blocks[max(0, block_index - 2) : block_index]):
            if prev.kind is not BlockKind.KV or prev.section_path != block.section_path:
                break
            texts.insert(0, prev.text)
        return SEPARATOR.join(texts)

    def add(block_index: int, block: Block, match: Match, context: str, scope_extra: str) -> None:
        key = (block_index, match.start, match.end, match.kind)
        if key in seen:
            return
        seen.add(key)
        section = block.section_path[-1] if block.section_path else None
        fact_id = hashlib.sha1(
            f"{doc.doc_id}:{block_index}:{match.start}:{match.kind}".encode(), usedforsecurity=False
        ).hexdigest()[:16]
        facts.append(
            Fact(
                fact_id=fact_id,
                bid_id=doc.bid_id,
                doc_id=doc.doc_id,
                file_name=doc.file_name,
                doc_type=doc.doc_type.value,
                addendum_number=doc.addendum_number,
                doc_date=doc.doc_date.isoformat() if doc.doc_date else None,
                page=block.page,
                block_index=block_index,
                section=section,
                kind=match.kind,
                fact_types=label(
                    config,
                    match.kind,
                    context,
                    section=section,
                    scope_extra=scope_extra,
                    neighbours=neighbours(block_index, block),
                ),
                raw=block.text[match.start : match.end],
                start=match.start,
                end=match.end,
                value=match.value,
                context=context,
            )
        )

    for bi, block in enumerate(doc.blocks):
        if block.kind is BlockKind.HEADING:
            continue
        table = tables.get(block.table_id) if block.table_id is not None else None
        if table is not None:
            units, quantities = _table_units(block, table)
        else:
            units, quantities = _text_units(block), _row_quantities(block)
        for unit in units:
            context = f"{unit.label}{SEPARATOR}{unit.text}" if unit.label else unit.text
            for m in _extract(unit.text, default_year):
                shifted = Match(m.kind, m.start + unit.offset, m.end + unit.offset, m.value)
                add(bi, block, shifted, context, unit.scope_extra)
        for q in quantities:
            add(bi, block, q, block.text[q.start : q.end] + f" ({q.value.get('item', '')})", "")
    return facts
