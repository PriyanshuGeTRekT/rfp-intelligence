"""Data model produced by ingestion and consumed by the fact layer and the chunker."""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field

BBox = tuple[float, float, float, float]


class DocType(StrEnum):
    BID_PAGE = "bid_page"
    RFP = "rfp"
    ADDENDUM = "addendum"
    SPECS = "specs"
    AFFIDAVIT = "affidavit"
    FORM = "form"
    OTHER = "other"


class BlockKind(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    KV = "kv"
    TABLE = "table"


class PageStatus(StrEnum):
    OK = "ok"
    NO_TEXT_LAYER = "no_text_layer"  # images but no extractable text: scanned, needs OCR
    EMPTY = "empty"
    ERROR = "error"


class Block(BaseModel):
    """One unit of reading order: a heading, a paragraph, a label-value pair or a table.

    Paragraph text keeps one visual row per line where a row has side-by-side segments,
    joined with " | ", so a label stays next to its value ("Solicitation Due | 27-JUN-2024").
    """

    kind: BlockKind
    text: str
    page: int
    section_path: list[str] = Field(default_factory=list)
    heading_level: int | None = None
    label: str | None = None
    value: str | None = None
    table_id: int | None = None
    bbox: BBox | None = None


class Table(BaseModel):
    table_id: int
    page: int
    rows: list[list[str]]
    bbox: BBox | None = None
    method: str

    def to_text(self) -> str:
        return "\n".join(" | ".join(c for c in row if c) for row in self.rows if any(row))


class PageInfo(BaseModel):
    number: int
    status: PageStatus
    char_count: int
    image_count: int = 0
    note: str | None = None


class Section(BaseModel):
    path: list[str]
    page_start: int
    page_end: int
    block_indices: list[int]


class Issue(BaseModel):
    file_name: str
    page: int | None = None
    severity: str  # "warning" | "error"
    message: str


class ParsedDocument(BaseModel):
    doc_id: str
    bid_id: str
    file_name: str
    source_path: str
    file_sha256: str
    media_type: str  # "pdf" | "html" | "text"
    title: str
    doc_type: DocType = DocType.OTHER
    doc_type_reason: str = ""
    addendum_number: int | None = None
    doc_date: date | None = None
    doc_date_source: str | None = None  # "text" | "pdf_metadata" | None
    page_count: int
    pages: list[PageInfo]
    blocks: list[Block]
    tables: list[Table] = Field(default_factory=list)
    sections: list[Section] = Field(default_factory=list)
    running_text: list[str] = Field(
        default_factory=list,
        description="Repeated page headers and footers removed from the body, kept once here",
    )
    metadata: dict[str, str] = Field(default_factory=dict)

    def text(self) -> str:
        return "\n\n".join(b.text for b in self.blocks)

    def page_text(self, page: int) -> str:
        return "\n\n".join(b.text for b in self.blocks if b.page == page)


class BidFolder(BaseModel):
    bid_id: str
    path: str
    documents: list[ParsedDocument]
    issues: list[Issue] = Field(default_factory=list)
    skipped_files: list[str] = Field(default_factory=list)
