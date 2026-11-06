"""Document-level metadata: type, addendum number and document date.

Everything here reads content, not file names, so it works on folders it has never seen.
The file name is only a weak extra signal for the type.
"""

import re
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from rfp_intel.ingestion.models import BlockKind, DocType, ParsedDocument
from rfp_intel.ingestion.pdf import pdf_metadata_date

HEAD_CHARS = 800
BODY_CHARS = 8000

# ---------------------------------------------------------------------------------------------
# Classification


class Cue(BaseModel):
    pattern: str
    weight: float


class TypeCues(BaseModel):
    cues: list[Cue]
    filename: list[str] = Field(default_factory=list)


class CueConfig(BaseModel):
    min_score: float = 4
    head_multiplier: float = 2
    filename_weight: float = 2
    min_portal_fields: int = 3
    types: dict[DocType, TypeCues]


@lru_cache(maxsize=8)
def load_cues(path: Path) -> CueConfig:
    with path.open(encoding="utf-8") as fh:
        return CueConfig.model_validate(yaml.safe_load(fh))


def _head_and_body(doc: ParsedDocument) -> tuple[str, str]:
    text = doc.text()
    head = "\n".join([doc.title, *doc.running_text, text[:HEAD_CHARS]])
    return head, text[:BODY_CHARS]


def classify(doc: ParsedDocument, cues: CueConfig) -> tuple[DocType, str]:
    """Return the document type and a short human-readable reason."""
    if doc.media_type == "html":
        fields = sum(1 for b in doc.blocks if b.kind is BlockKind.KV)
        if fields >= cues.min_portal_fields:
            return DocType.BID_PAGE, f"html page with {fields} label-value fields"

    head, body = _head_and_body(doc)
    name = Path(doc.file_name).stem.lower()
    scores: dict[DocType, float] = {}
    hits: dict[DocType, list[str]] = {}
    for doc_type, spec in cues.types.items():
        score = 0.0
        found: list[str] = []
        for cue in spec.cues:
            rx = re.compile(cue.pattern, re.I)
            in_head = len(rx.findall(head))
            in_body = len(rx.findall(body))
            if in_head or in_body:
                score += cue.weight * (cues.head_multiplier * min(in_head, 2) + min(in_body, 3))
                m = rx.search(head) or rx.search(body)
                if m:
                    found.append(m.group(0).strip().lower())
        for keyword in spec.filename:
            if re.search(rf"(?<![a-z]){re.escape(keyword)}", name):
                score += cues.filename_weight
                found.append(f"file name '{keyword}'")
                break
        scores[doc_type] = score
        hits[doc_type] = found

    best = max(scores, key=lambda t: scores[t])
    if scores[best] < cues.min_score:
        return (
            DocType.OTHER,
            f"no type reached the minimum score (best {best.value} {scores[best]:.0f})",
        )
    runner_up = sorted(scores.values(), reverse=True)[1] if len(scores) > 1 else 0
    cue_list = ", ".join(dict.fromkeys(hits[best]))[:160]
    return best, f"{best.value} score {scores[best]:.0f} (next {runner_up:.0f}): {cue_list}"


# ---------------------------------------------------------------------------------------------
# Addendum number

_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
}  # fmt: skip
_ROMAN = {
    "i": 1,
    "ii": 2,
    "iii": 3,
    "iv": 4,
    "v": 5,
    "vi": 6,
    "vii": 7,
    "viii": 8,
    "ix": 9,
    "x": 10,
}
_ADDENDUM_NO_RE = re.compile(
    r"\b(?:addendum|amendment)\s*(?:no\.?|number|#)?\s*[:\-]?\s*"
    r"(\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten|[ivx]{1,4})\b",
    re.I,
)
_ORDINAL_RE = re.compile(r"\b(first|second|third|fourth|fifth)\s+(?:addendum|amendment)\b", re.I)


def _to_int(token: str) -> int | None:
    token = token.lower()
    if token.isdigit():
        return int(token)
    return _WORD_NUMBERS.get(token) or _ROMAN.get(token)


def find_addendum_number(doc: ParsedDocument) -> int | None:
    head, _ = _head_and_body(doc)
    for rx in (_ADDENDUM_NO_RE, _ORDINAL_RE):
        m = rx.search(head)
        if m:
            return _to_int(m.group(1))
    m = _ADDENDUM_NO_RE.search(Path(doc.file_name).stem.replace("_", " "))
    return _to_int(m.group(1)) if m else None


# ---------------------------------------------------------------------------------------------
# Dates

_MONTHS = {
    m: i + 1
    for i, names in enumerate(
        [
            ("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"),
            ("may",), ("jun", "june"), ("jul", "july"), ("aug", "august"),
            ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"),
            ("dec", "december"),
        ]
    )
    for m in names
}  # fmt: skip
_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))
_DATE_PATTERNS = [
    # July 9, 2024 / Jul. 9 2024 / June 13th, 2024
    re.compile(
        rf"\b(?P<mon>{_MONTH_ALT})\.?\s+(?P<d>\d{{1,2}})(?:st|nd|rd|th)?,?\s+(?P<y>\d{{4}})\b", re.I
    ),
    # 9 July 2024 / 27-JUN-2024
    re.compile(rf"\b(?P<d>\d{{1,2}})[\s-](?P<mon>{_MONTH_ALT})\.?[\s,-]+(?P<y>\d{{4}})\b", re.I),
    # 06/13/2024 (US order)
    re.compile(r"\b(?P<m>\d{1,2})/(?P<d>\d{1,2})/(?P<y>\d{4})\b"),
    # 2024-06-13
    re.compile(r"\b(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})\b"),
]
# Words that say a date is the document's own date. "Due date" is deliberately absent:
# an addendum that moves the deadline must not take the new deadline as its own date.
_DOC_DATE_CUE_RE = re.compile(
    r"\b(?:issue|issued|publication|posted|release|addendum|amendment|effective)\s+date\b"
    r"|\bdate\s+(?:issued|of\s+issue|posted|of\s+(?:addendum|amendment))\b"
    r"|\bdated\b|\bissued(?:\s+on)?\b|\bpublication\b|^\s*date\s*[:|]",
    re.I | re.M,
)


def find_dates(text: str) -> list[tuple[date, int, int]]:
    """Every calendar date in `text` as (date, start, end), in order of appearance."""
    found: list[tuple[date, int, int]] = []
    for rx in _DATE_PATTERNS:
        for m in rx.finditer(text):
            parts = m.groupdict()
            month = _MONTHS[parts["mon"].lower()] if parts.get("mon") else int(parts["m"])
            try:
                found.append((date(int(parts["y"]), month, int(parts["d"])), m.start(), m.end()))
            except ValueError:
                continue
    found.sort(key=lambda t: t[1])
    return found


def find_doc_date(doc: ParsedDocument) -> tuple[date | None, str | None]:
    """The document's own date: a cue-labelled date near the top, else PDF metadata."""
    first_pages = "\n".join(b.text for b in doc.blocks if b.page <= 2)
    for cue in _DOC_DATE_CUE_RE.finditer(first_pages):
        window = first_pages[cue.end() : cue.end() + 80]
        dates = find_dates(window)
        if dates:
            return dates[0][0], "text"
    meta_date = pdf_metadata_date(doc.metadata)
    if meta_date is not None:
        return meta_date, "pdf_metadata"
    return None, None


def enrich(doc: ParsedDocument, cues: CueConfig) -> ParsedDocument:
    doc.doc_type, doc.doc_type_reason = classify(doc, cues)
    doc.addendum_number = find_addendum_number(doc) if doc.doc_type is DocType.ADDENDUM else None
    doc.doc_date, doc.doc_date_source = find_doc_date(doc)
    return doc
