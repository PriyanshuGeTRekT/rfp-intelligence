"""Load a bid folder: parse every supported file, enrich it, and report what failed."""

from collections.abc import Callable
from pathlib import Path

from opentelemetry import trace

from rfp_intel.ingestion.html import parse_html, parse_text
from rfp_intel.ingestion.meta import CueConfig, enrich, load_cues
from rfp_intel.ingestion.models import BidFolder, Issue, PageStatus, ParsedDocument
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
}


def _page_issues(doc: ParsedDocument) -> list[Issue]:
    issues: list[Issue] = []
    for page in doc.pages:
        if page.status is PageStatus.OK:
            continue
        issues.append(
            Issue(
                file_name=doc.file_name,
                page=page.number,
                severity="warning",
                message=page.note or f"page is {page.status.value}",
            )
        )
    if doc.pages and all(p.status is not PageStatus.OK for p in doc.pages):
        issues.append(
            Issue(
                file_name=doc.file_name, severity="error", message="no extractable text on any page"
            )
        )
    return issues


def load_bid_folder(folder: Path, cues: CueConfig | Path) -> BidFolder:
    """Parse every file under `folder`. One bad file never stops the others."""
    cue_config = load_cues(cues) if isinstance(cues, Path) else cues
    bid_id = folder.name
    documents: list[ParsedDocument] = []
    issues: list[Issue] = []
    skipped: list[str] = []

    with tracer.start_as_current_span("ingest.folder") as span:
        span.set_attribute("rfp.bid_id", bid_id)
        for path in sorted(p for p in folder.rglob("*") if p.is_file()):
            rel = path.relative_to(folder).as_posix()
            if path.name.startswith((".", "~$")):
                continue
            parser = PARSERS.get(path.suffix.lower())
            if parser is None:
                skipped.append(rel)
                issues.append(
                    Issue(
                        file_name=rel,
                        severity="warning",
                        message=f"unsupported file type '{path.suffix or 'none'}'; skipped",
                    )
                )
                continue
            with tracer.start_as_current_span("ingest.file") as file_span:
                file_span.set_attribute("rfp.file", rel)
                try:
                    doc = enrich(parser(path, bid_id, rel), cue_config)
                except Exception as exc:  # one unreadable file must not stop the bid
                    log.warning("ingest_file_failed", file=rel, error=str(exc))
                    file_span.record_exception(exc)
                    issues.append(
                        Issue(file_name=rel, severity="error", message=f"could not parse: {exc}")
                    )
                    continue
                file_span.set_attribute("rfp.doc_type", doc.doc_type.value)
                file_span.set_attribute("rfp.pages", doc.page_count)
                file_span.set_attribute("rfp.blocks", len(doc.blocks))
                file_span.set_attribute("rfp.tables", len(doc.tables))
                documents.append(doc)
                issues.extend(_page_issues(doc))
        span.set_attribute("rfp.documents", len(documents))
        span.set_attribute("rfp.issues", len(issues))

    log.info("ingest_folder_done", bid_id=bid_id, documents=len(documents), issues=len(issues))
    return BidFolder(
        bid_id=bid_id, path=str(folder), documents=documents, issues=issues, skipped_files=skipped
    )
