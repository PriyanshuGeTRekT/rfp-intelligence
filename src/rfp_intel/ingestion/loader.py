"""Load a bid folder: parse every supported file, enrich it, and report what failed."""

from collections.abc import Callable
from pathlib import Path

from opentelemetry import trace

from rfp_intel.ingestion.html import parse_html, parse_text
from rfp_intel.ingestion.meta import CueConfig, enrich, load_cues
from rfp_intel.ingestion.models import BidFolder, Issue, PageStatus, ParsedDocument
from rfp_intel.ingestion.office import parse_docx, parse_xlsx
from rfp_intel.ingestion.pdf import parse_pdf
from rfp_intel.logs import get_logger

log = get_logger(__name__)
tracer = trace.get_tracer(__name__)

Parser = Callable[[Path, str, str], ParsedDocument]
PARSERS: dict[str, Parser] = {
    ".pdf": parse_pdf,
    ".html": parse_html,
    ".htm": parse_html,
    ".txt": parse_text,
    ".md": parse_text,
    ".docx": parse_docx,
    ".xlsx": parse_xlsx,
}


def _page_issues(doc: ParsedDocument) -> list[Issue]:
    issues: list[Issue] = []
    ocr = [p.number for p in doc.pages if p.status is PageStatus.OCR]
    if ocr:
        issues.append(
            Issue(
                file_name=doc.file_name,
                severity="info",
                message=f"{len(ocr)} scanned pages read by OCR; check citations against the file",
            )
        )
    for page in doc.pages:
        if page.status in (PageStatus.OK, PageStatus.OCR):
            continue
        issues.append(
            Issue(
                file_name=doc.file_name,
                page=page.number,
                severity="warning",
                message=page.note or f"page is {page.status.value}",
            )
        )
    if doc.pages and all(p.status not in (PageStatus.OK, PageStatus.OCR) for p in doc.pages):
        issues.append(
            Issue(
                file_name=doc.file_name, severity="error", message="no extractable text on any page"
            )
        )
    return issues


def list_files(folder: Path) -> tuple[list[tuple[Path, str]], list[str]]:
    """Supported files as (path, path relative to the folder), and unsupported ones."""
    supported: list[tuple[Path, str]] = []
    unsupported: list[str] = []
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        if path.name.startswith((".", "~$")):
            continue
        rel = path.relative_to(folder).as_posix()
        if path.suffix.lower() in PARSERS:
            supported.append((path, rel))
        else:
            unsupported.append(rel)
    return supported, unsupported


def unsupported_issue(rel: str) -> Issue:
    suffix = Path(rel).suffix or "none"
    return Issue(
        file_name=rel, severity="warning", message=f"unsupported file type '{suffix}'; skipped"
    )


def parse_file(path: Path, bid_id: str, rel: str, cues: CueConfig) -> ParsedDocument:
    """Parse and enrich one file. Raises on unreadable input; callers decide what to do."""
    with tracer.start_as_current_span("ingest.file") as span:
        span.set_attribute("rfp.file", rel)
        doc = enrich(PARSERS[path.suffix.lower()](path, bid_id, rel), cues)
        span.set_attribute("rfp.doc_type", doc.doc_type.value)
        span.set_attribute("rfp.pages", doc.page_count)
        span.set_attribute("rfp.blocks", len(doc.blocks))
        span.set_attribute("rfp.tables", len(doc.tables))
        return doc


def page_issues(doc: ParsedDocument) -> list[Issue]:
    return _page_issues(doc)


def load_bid_folder(folder: Path, cues: CueConfig | Path) -> BidFolder:
    """Parse every file under `folder`. One bad file never stops the others."""
    cue_config = load_cues(cues) if isinstance(cues, Path) else cues
    bid_id = folder.name
    documents: list[ParsedDocument] = []
    issues: list[Issue] = []

    with tracer.start_as_current_span("ingest.folder") as span:
        span.set_attribute("rfp.bid_id", bid_id)
        files, skipped = list_files(folder)
        issues.extend(unsupported_issue(rel) for rel in skipped)
        for path, rel in files:
            try:
                doc = parse_file(path, bid_id, rel, cue_config)
            except Exception as exc:  # one unreadable file must not stop the bid
                log.warning("ingest_file_failed", file=rel, error=str(exc))
                issues.append(
                    Issue(file_name=rel, severity="error", message=f"could not parse: {exc}")
                )
                continue
            documents.append(doc)
            issues.extend(_page_issues(doc))
        span.set_attribute("rfp.documents", len(documents))
        span.set_attribute("rfp.issues", len(issues))

    log.info("ingest_folder_done", bid_id=bid_id, documents=len(documents), issues=len(issues))
    return BidFolder(
        bid_id=bid_id, path=str(folder), documents=documents, issues=issues, skipped_files=skipped
    )
