"""Structure-aware chunking.

Chunks follow the document's own structure instead of a fixed character window:

- prose is packed within one section up to a token target, with a small overlap, so a chunk
  never mixes two sections and its heading path is always correct;
- a table is one chunk when it fits, otherwise slices of rows with the header repeated, so a
  SKU is never separated from the column that names it;
- an addendum question and its answer are one small chunk, because that is the unit a
  question about the addendum needs;
- consecutive portal fields form one chunk.

Every chunk records the exact block spans it covers, so facts found in those spans (their
identifiers and topic labels) become filterable chunk metadata.
"""

import hashlib
import re
from dataclasses import dataclass, field

from pydantic import BaseModel

from rfp_intel.facts.extract import split_sentences
from rfp_intel.facts.models import Fact, FactKind
from rfp_intel.ingestion.models import Block, BlockKind, PageStatus, ParsedDocument
from rfp_intel.search.models import Chunk, ChunkType, Span


class ChunkConfig(BaseModel):
    target_tokens: int = 380
    max_tokens: int = 480  # bge-small reads 512 word pieces; keep headroom for the header
    overlap_tokens: int = 60
    min_tokens: int = 40  # a smaller tail chunk is merged into the one before it


def approx_tokens(text: str) -> int:
    """About four characters per token for English prose; close enough for packing."""
    return max(1, len(text) // 4)


_QA_RE = re.compile(
    r"^\s*(?:Q(?:uestion)?\s*#?\s*)?\d{1,3}[.)]\s+\S.*?(?:\n|\?\s)\s*(?:Answer|Response|A)\s*[:.\-]",
    re.I | re.S,
)
_BOILERPLATE_RE = re.compile(
    r"provide your answer below|^\s*type\s*$|\bsignature\b|print(?:ed)? name"
    r"|\bcheck (?:one|all|applicable)|_{3,}|\(name of [a-z ]+\)|\(title\)"
    r"|^\s*date\s*:?\s*$|attach(?:ed)? (?:hereto|this form)",
    re.I | re.M,
)


_CONTENT_FORMS = {"affidavit", "form"}


@dataclass
class _Piece:
    block_index: int
    start: int
    end: int
    text: str
    page: int

    @property
    def tokens(self) -> int:
        return approx_tokens(self.text)


@dataclass
class _Draft:
    chunk_type: ChunkType
    section_path: list[str]
    pieces: list[_Piece] = field(default_factory=list)

    @property
    def tokens(self) -> int:
        return sum(p.tokens for p in self.pieces)


def _pieces_for_block(index: int, block: Block, cfg: ChunkConfig) -> list[_Piece]:
    """A block as one piece, or sentence by sentence when it is longer than a chunk.

    Sentence-sized pieces let the packer fill chunks evenly and carry the last sentence or two
    into the next chunk as overlap. A sentence longer than a chunk is cut at the budget.
    """
    if approx_tokens(block.text) <= cfg.target_tokens:
        return [_Piece(index, 0, len(block.text), block.text, block.page)]
    pieces: list[_Piece] = []
    budget = cfg.target_tokens * 4  # characters
    for offset, sentence in split_sentences(block.text):
        start, end = offset, offset + len(sentence)
        while end - start > budget:
            pieces.append(
                _Piece(index, start, start + budget, block.text[start : start + budget], block.page)
            )
            start += budget
        pieces.append(_Piece(index, start, end, block.text[start:end], block.page))
    return pieces


def _table_drafts(index: int, block: Block, path: list[str], cfg: ChunkConfig) -> list[_Draft]:
    if approx_tokens(block.text) <= cfg.max_tokens:
        return [
            _Draft(
                ChunkType.TABLE, path, [_Piece(index, 0, len(block.text), block.text, block.page)]
            )
        ]
    lines = block.text.split("\n")
    header = lines[0]
    offsets = []
    pos = 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1
    drafts: list[_Draft] = []
    current: _Draft | None = None
    for i, line in enumerate(lines[1:], start=1):
        piece = _Piece(index, offsets[i], offsets[i] + len(line), line, block.page)
        if (
            current is None
            or current.tokens + piece.tokens + approx_tokens(header) > cfg.target_tokens
        ):
            current = _Draft(
                ChunkType.TABLE_ROWS, path, [_Piece(index, 0, len(header), header, block.page)]
            )
            drafts.append(current)
        current.pieces.append(piece)
    return drafts


def _pack(pieces: list[_Piece], path: list[str], cfg: ChunkConfig) -> list[_Draft]:
    drafts: list[_Draft] = []
    current = _Draft(ChunkType.SECTION, path)
    for piece in pieces:
        if current.pieces and current.tokens + piece.tokens > cfg.target_tokens:
            drafts.append(current)
            overlap: list[_Piece] = []
            for prev in reversed(current.pieces[1:]):  # never carry the whole chunk over
                if sum(p.tokens for p in overlap) + prev.tokens > cfg.overlap_tokens:
                    break
                overlap.insert(0, prev)
            current = _Draft(ChunkType.SECTION, path, list(overlap))
        current.pieces.append(piece)
    if current.pieces:
        if (
            drafts
            and current.tokens < cfg.min_tokens
            and drafts[-1].tokens + current.tokens <= cfg.max_tokens
        ):
            drafts[-1].pieces.extend(p for p in current.pieces if p not in drafts[-1].pieces)
        else:
            drafts.append(current)
    return drafts


def _drafts(doc: ParsedDocument, cfg: ChunkConfig) -> list[_Draft]:
    drafts: list[_Draft] = []
    prose: list[_Piece] = []
    fields: list[_Piece] = []
    carry: list[_Piece] = []  # headings waiting for the content that follows them
    path: list[str] = []
    heading_blocks = {i for i, b in enumerate(doc.blocks) if b.kind is BlockKind.HEADING}

    def emit(new: list[_Draft]) -> None:
        nonlocal carry
        if new and carry:
            new[0].pieces[:0] = carry
            carry = []
        drafts.extend(new)

    def flush_prose() -> None:
        nonlocal prose, carry
        if prose and all(p.block_index in heading_blocks for p in prose):
            carry.extend(prose)  # a heading with nothing under it yet: attach it to what follows
        elif prose:
            emit(_pack(prose, path, cfg))
        prose = []

    def flush() -> None:
        nonlocal fields
        flush_prose()
        if fields:
            groups = _pack(fields, path, cfg)
            for group in groups:
                group.chunk_type = ChunkType.KV
            emit(groups)
        fields = []

    for i, block in enumerate(doc.blocks):
        if block.section_path != path:
            flush()
            path = list(block.section_path)
        if block.kind is BlockKind.HEADING:
            # Headings lead their section's text, so a merged chunk keeps its sub-headings and
            # keyword search sees "Deployment Services" next to what it says.
            prose.append(_Piece(i, 0, len(block.text), block.text, block.page))
            continue
        if block.kind is BlockKind.TABLE:
            flush()
            emit(_table_drafts(i, block, path, cfg))
        elif block.kind is BlockKind.KV:
            flush_prose()
            fields.append(_Piece(i, 0, len(block.text), block.text, block.page))
        elif _QA_RE.match(block.text):
            flush()
            groups = _pack(_pieces_for_block(i, block, cfg), path, cfg)
            for group in groups:
                group.chunk_type = ChunkType.QA_PAIR
            emit(groups)
        else:
            if fields:
                flush()
            prose.extend(_pieces_for_block(i, block, cfg))
    flush()
    if carry:  # trailing headings with no content after them
        drafts.append(_Draft(ChunkType.SECTION, path, carry))
    return _merge_small_sections(drafts, cfg)


def _common_prefix(a: list[str], b: list[str]) -> list[str]:
    out: list[str] = []
    for x, y in zip(a, b, strict=False):
        if x != y:
            break
        out.append(x)
    return out


def _merge_small_sections(drafts: list[_Draft], cfg: ChunkConfig) -> list[_Draft]:
    """Join neighbouring small prose chunks from sibling or nested sections.

    RFPs are full of two-line sections under bold headings; one chunk per heading would give
    slivers too small to retrieve well. Their headings are already in the text, so the merged
    chunk's path is the shared parent.
    """
    merged: list[_Draft] = []
    for draft in drafts:
        prev = merged[-1] if merged else None
        if (
            prev is not None
            and prev.chunk_type is ChunkType.SECTION
            and draft.chunk_type is ChunkType.SECTION
            and prev.tokens + draft.tokens <= cfg.target_tokens
        ):
            shared = _common_prefix(prev.section_path, draft.section_path)
            deepest = max(len(prev.section_path), len(draft.section_path))
            if (
                shared and len(shared) >= deepest - 1
            ):  # siblings or parent and child, never strangers
                prev.pieces.extend(p for p in draft.pieces if p not in prev.pieces)
                prev.section_path = shared
                continue
        merged.append(draft)
    return merged


def _join(pieces: list[_Piece]) -> str:
    out = ""
    prev: _Piece | None = None
    for p in pieces:
        if prev is None:
            out = p.text
        elif prev.block_index == p.block_index:
            out += " " + p.text if prev.end <= p.start else ""
        else:
            out += "\n\n" + p.text
        prev = p
    return out


def is_boilerplate(text: str) -> bool:
    """Form scaffolding: answer boxes, signature lines, "(name of affiant)" blanks."""
    hits = len(_BOILERPLATE_RE.findall(text))
    return hits >= 2 and hits * 100 / max(approx_tokens(text), 1) >= 1.5


def _doc_label(doc: ParsedDocument) -> str:
    label = doc.doc_type.value
    if doc.addendum_number is not None:
        label += f" {doc.addendum_number}"
    if doc.doc_date:
        label += f", {doc.doc_date.isoformat()}"
    return label


def chunk_document(
    doc: ParsedDocument, facts: list[Fact], cfg: ChunkConfig | None = None
) -> list[Chunk]:
    cfg = cfg or ChunkConfig()
    by_block: dict[int, list[Fact]] = {}
    for f in facts:
        by_block.setdefault(f.block_index, []).append(f)

    ocr_pages = {p.number for p in doc.pages if p.status is PageStatus.OCR}
    chunks: list[Chunk] = []
    for n, draft in enumerate(_drafts(doc, cfg)):
        spans = [Span(block_index=p.block_index, start=p.start, end=p.end) for p in draft.pieces]
        inside = [
            f
            for s in spans
            for f in by_block.get(s.block_index, [])
            if f.start >= s.start and f.end <= s.end
        ]
        identifiers: list[str] = []
        for f in inside:
            if f.kind is FactKind.IDENTIFIER:
                identifiers.extend([f.value["id"], f.value["compact"]])
        fact_types = sorted(
            {t for f in inside for t in f.fact_types if t not in ("identifier", "quantity")}
        )
        text = _join(draft.pieces)
        header = f"{doc.title} ({_doc_label(doc)})"
        if draft.section_path:
            header += "\n" + " > ".join(draft.section_path)
        chunk_id = hashlib.sha256(f"{doc.doc_id}:{n}".encode()).hexdigest()[:24]
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                bid_id=doc.bid_id,
                doc_id=doc.doc_id,
                file_name=doc.file_name,
                doc_type=doc.doc_type.value,
                addendum_number=doc.addendum_number,
                doc_date=doc.doc_date.isoformat() if doc.doc_date else None,
                title=doc.title,
                page_start=min(p.page for p in draft.pieces),
                page_end=max(p.page for p in draft.pieces),
                section_path=draft.section_path,
                chunk_type=draft.chunk_type,
                text=text,
                embed_text=f"{header}\n\n{text}",
                spans=spans,
                identifiers=sorted(set(identifiers)),
                fact_types=fact_types,
                fact_ids=sorted({f.fact_id for f in inside}),
                # An affidavit or form *is* the requirement, blanks and all; only scaffolding
                # inside other documents (answer boxes in an RFP) is down-weighted.
                is_boilerplate=(
                    draft.chunk_type is not ChunkType.QA_PAIR
                    and doc.doc_type.value not in _CONTENT_FORMS
                    and is_boilerplate(text)
                ),
                token_estimate=approx_tokens(text),
                ocr=any(
                    page in ocr_pages
                    for page in range(
                        min(p.page for p in draft.pieces), max(p.page for p in draft.pieces) + 1
                    )
                ),
            )
        )
    return chunks
