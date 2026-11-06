"""HTML parsing for bid portal pages (BidNet, state eProcurement sites, agency pages).

Portal pages are mostly label-value fields. Labels are found generically, not per portal:
elements whose class marks them as a label (`mets-field-label`, `field-label`, ...),
`<label>`, `<dt>`/`<dd>` pairs and two-cell `<th>`/`<td>` table rows. Everything else becomes
headings and paragraphs in document order.
"""

import hashlib
import re
from pathlib import Path

from bs4 import BeautifulSoup
from bs4.element import Comment, NavigableString, Tag

from rfp_intel.ingestion.clean import normalize_text
from rfp_intel.ingestion.models import (
    Block,
    BlockKind,
    PageInfo,
    PageStatus,
    ParsedDocument,
    Table,
)
from rfp_intel.ingestion.structure import assign_sections

_DROP_TAGS = [
    "script",
    "style",
    "noscript",
    "svg",
    "template",
    "iframe",
    "nav",
    "footer",
    "header",
    "aside",
    "button",
    "select",
    "input",
]
_HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_BLOCK_TAGS = {
    "address", "article", "blockquote", "body", "dd", "div", "dl", "dt", "fieldset", "figure",
    "form", "html", "li", "main", "ol", "p", "pre", "section", "table", "tbody", "td", "th",
    "thead", "tr", "ul",
}  # fmt: skip
_LABEL_CLASS_RE = re.compile(r"(?:^|[-_])label(?:$|[-_])", re.I)
# Page chrome, recognised by words in class names and ids rather than by any one portal's
# markup. "tab" and "header" are deliberately absent: portals put real content inside both.
_CHROME_TOKENS = {
    "hidden", "dialog", "modal", "popup", "cookie", "cookies", "share", "social", "ajax",
    "loading", "spinner", "skip", "toolbar", "menu", "breadcrumb", "breadcrumbs", "navbar",
    "footer", "print", "banner",
}  # fmt: skip
_CHROME_ROLES = {
    "dialog",
    "alertdialog",
    "navigation",
    "banner",
    "menu",
    "menubar",
    "contentinfo",
    "search",
}
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _tokens(value: str) -> set[str]:
    """ "accessibilitySkipToContent mets-ajax_indicator" -> {accessibility, skip, ..., ajax}."""
    return {t for t in re.split(r"[^a-z0-9]+", _CAMEL_RE.sub(" ", value).lower()) if t}


def _is_chrome(el: Tag) -> bool:
    if el.name in ("html", "body", "main") or el.find("h1") is not None:
        return False
    if str(el.get("role") or "").lower() in _CHROME_ROLES:
        return True
    style = str(el.get("style") or "").replace(" ", "").lower()
    if "display:none" in style or "visibility:hidden" in style:
        return True
    words: set[str] = set()
    for cls in el.get("class") or []:
        words |= _tokens(cls)
    words |= _tokens(str(el.get("id") or ""))
    return bool(words & _CHROME_TOKENS)


def _squash(text: str) -> str:
    return normalize_text(" ".join(text.split()))


def _text(el: Tag | NavigableString) -> str:
    return _squash(el.get_text(" ", strip=True) if isinstance(el, Tag) else str(el))


def _is_label(el: Tag) -> bool:
    if el.name in ("label", "dt"):
        return True
    return any(
        _LABEL_CLASS_RE.search(c) and not c.lower().startswith("no") for c in el.get("class") or []
    )


class _Walker:
    def __init__(self) -> None:
        self.blocks: list[Block] = []
        self.tables: list[Table] = []
        self.kv_containers: dict[int, tuple[str, str]] = {}
        self._inline: list[str] = []

    # Label-value containers are found before walking so they can be emitted in place.
    def index_fields(self, root: Tag) -> None:
        for label in root.find_all(_is_label):
            parent = label.parent
            if not isinstance(parent, Tag) or id(parent) in self.kv_containers:
                continue
            siblings = [s for s in parent.children if isinstance(s, Tag) and s is not label]
            if not siblings:
                continue
            value = normalize_text(" ".join(_text(s) for s in siblings))
            self.kv_containers[id(parent)] = (_text(label).rstrip(":").strip(), value)

    def flush(self) -> None:
        text = _squash(" ".join(self._inline))
        self._inline = []
        if text:
            self.blocks.append(Block(kind=BlockKind.PARAGRAPH, text=text, page=1))

    def emit_kv(self, label: str, value: str) -> None:
        if not value:
            return
        if not label:
            self.blocks.append(Block(kind=BlockKind.PARAGRAPH, text=value, page=1))
            return
        self.blocks.append(
            Block(kind=BlockKind.KV, text=f"{label}: {value}", page=1, label=label, value=value)
        )

    def emit_table(self, table: Tag) -> None:
        rows: list[list[str]] = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"], recursive=False)
            if len(cells) == 2 and cells[0].name == "th" and cells[1].name == "td":
                self.emit_kv(_text(cells[0]).rstrip(":"), _text(cells[1]))
                continue
            row = [_text(c) for c in cells]
            if any(row):
                rows.append(row)
        if len(rows) >= 2 and max(len(r) for r in rows) >= 2:
            t = Table(table_id=len(self.tables), page=1, rows=rows, method="html")
            self.tables.append(t)
            self.blocks.append(
                Block(kind=BlockKind.TABLE, text=t.to_text(), page=1, table_id=t.table_id)
            )
        else:
            for row in rows:
                self._inline.append(" | ".join(c for c in row if c))
                self.flush()

    def walk(self, el: Tag) -> None:
        for child in el.children:
            if isinstance(child, Comment):
                continue
            if isinstance(child, NavigableString):
                self._inline.append(str(child))
                continue
            if not isinstance(child, Tag):
                continue
            if id(child) in self.kv_containers:
                self.flush()
                self.emit_kv(*self.kv_containers[id(child)])
            elif child.name in _HEADINGS:
                self.flush()
                text = _text(child)
                if text:
                    self.blocks.append(
                        Block(
                            kind=BlockKind.HEADING,
                            text=text,
                            page=1,
                            heading_level=_HEADINGS[child.name],
                        )
                    )
            elif child.name == "table":
                self.flush()
                self.emit_table(child)
            elif child.name == "dl":
                self.flush()
                for dt in child.find_all("dt"):
                    dd = dt.find_next_sibling("dd")
                    self.emit_kv(_text(dt).rstrip(":"), _text(dd) if dd else "")
            elif child.name == "br":
                self.flush()
            elif child.name in _BLOCK_TAGS:
                self.flush()
                self.walk(child)
                self.flush()
            else:
                self.walk(child)  # inline element: keep accumulating


def parse_html(path: Path, bid_id: str, file_name: str | None = None) -> ParsedDocument:
    file_name = file_name or path.name
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    soup = BeautifulSoup(raw, "lxml")
    for tag in soup(_DROP_TAGS):
        tag.decompose()
    for tag in soup.find_all(True, attrs={"aria-hidden": "true"}):
        tag.decompose()
    for tag in [t for t in soup.find_all(True) if _is_chrome(t)]:
        if not tag.decomposed:
            tag.decompose()

    root = soup.body or soup
    walker = _Walker()
    walker.index_fields(root)
    walker.walk(root)
    walker.flush()

    h1 = soup.find("h1")
    title = _text(h1) if h1 else ""
    if not title and soup.title:
        title = _text(soup.title)
    title = title or path.stem

    blocks, sections = assign_sections(walker.blocks)
    chars = sum(len(b.text) for b in blocks)
    status = PageStatus.OK if chars else PageStatus.EMPTY
    meta: dict[str, str] = {}
    if soup.title:
        meta["html_title"] = _text(soup.title)
    return ParsedDocument(
        doc_id=hashlib.sha256(f"{bid_id}/{sha}".encode()).hexdigest()[:16],
        bid_id=bid_id,
        file_name=file_name,
        source_path=str(path),
        file_sha256=sha,
        media_type="html",
        title=title,
        page_count=1,
        pages=[PageInfo(number=1, status=status, char_count=chars)],
        blocks=blocks,
        tables=walker.tables,
        sections=sections,
        metadata=meta,
    )


def parse_text(path: Path, bid_id: str, file_name: str | None = None) -> ParsedDocument:
    """Plain text or Markdown: blank-line paragraphs, `#` headings."""
    file_name = file_name or path.name
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    content = raw.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    blocks: list[Block] = []
    for chunk in re.split(r"\n\s*\n", content):
        text = normalize_text(chunk.replace("\n", " "))
        if not text:
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", chunk.strip())
        if m:
            blocks.append(
                Block(
                    kind=BlockKind.HEADING,
                    text=normalize_text(m.group(2)),
                    page=1,
                    heading_level=len(m.group(1)),
                )
            )
        else:
            blocks.append(Block(kind=BlockKind.PARAGRAPH, text=text, page=1))
    blocks, sections = assign_sections(blocks)
    chars = sum(len(b.text) for b in blocks)
    title = next((b.text for b in blocks if b.kind is BlockKind.HEADING), path.stem)
    return ParsedDocument(
        doc_id=hashlib.sha256(f"{bid_id}/{sha}".encode()).hexdigest()[:16],
        bid_id=bid_id,
        file_name=file_name,
        source_path=str(path),
        file_sha256=sha,
        media_type="text",
        title=title,
        page_count=1,
        pages=[
            PageInfo(
                number=1, status=PageStatus.OK if chars else PageStatus.EMPTY, char_count=chars
            )
        ],
        blocks=blocks,
        sections=sections,
    )
