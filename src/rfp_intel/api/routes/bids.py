"""Bids: indexing, the list of bids, their documents, extraction runs and results, and the
source files citations point to."""

from collections import Counter
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from rfp_intel.agents.schema import BidResult, DocumentInfo
from rfp_intel.api.context import AppContext, context
from rfp_intel.api.schemas import BidDetail, BidSummary, IndexRequest, Job, ResultSummary
from rfp_intel.config import Settings
from rfp_intel.ingestion.models import ParsedDocument
from rfp_intel.search.indexer import IndexReport
from rfp_intel.search.manifest import Manifest, ManifestEntry
from rfp_intel.security import PathNotAllowedError, resolve_within

router = APIRouter(tags=["bids"])
OFFICE_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
Ctx = Annotated[AppContext, Depends(context)]


def _folder(settings: Settings, path: str) -> Path:
    try:
        folder = resolve_within(settings.data_dir, path)
    except PathNotAllowedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="bid folder not found")
    return folder


def _result(settings: Settings, bid_id: str) -> BidResult | None:
    path = settings.outputs_dir / f"{bid_id}.json"
    if not path.exists():
        return None
    try:
        return BidResult.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError:
        return None  # an output from an older format; re-run extraction to refresh it


def _result_summary(result: BidResult | None) -> ResultSummary | None:
    if result is None:
        return None
    fields = {f.key: f for f in result.fields.values()}
    due, title = fields.get("due_date"), fields.get("title")
    return ResultSummary(
        run_id=result.run_id,
        generated_at=result.generated_at,
        validation=result.validation,
        due_date=due.value if due and isinstance(due.value, str) else None,
        title=title.value if title and isinstance(title.value, str) else None,
        cost_usd=float(result.usage.get("cost_usd", 0.0)),
    )


def _summary(settings: Settings, bid_id: str, entries: dict[str, ManifestEntry]) -> BidSummary:
    return BidSummary(
        bid_id=bid_id,
        indexed=bool(entries),
        documents=len(entries),
        doc_types=dict(Counter(e.doc_type for e in entries.values())),
        indexed_at=max((e.indexed_at for e in entries.values()), default=None),
        result=_result_summary(_result(settings, bid_id)),
    )


@router.post("/index")
def index(body: IndexRequest, ctx: Ctx, force: bool = False) -> IndexReport:
    """Index one bid folder (incremental: unchanged files are skipped)."""
    folder = _folder(ctx.settings, body.path)
    return ctx.runtime().indexer().index_folder(folder, force=force)


@router.get("/bids")
def list_bids(ctx: Ctx) -> list[BidSummary]:
    """Indexed bids, plus folders in the data directory that are not indexed yet."""
    settings = ctx.settings
    with Manifest(settings.db_path) as manifest:
        indexed = {b: manifest.entries(b) for b in manifest.bids()}
    folders = (
        {p.name for p in settings.data_dir.iterdir() if p.is_dir()}
        if settings.data_dir.is_dir()
        else set()
    )
    return [_summary(settings, b, indexed.get(b, {})) for b in sorted(set(indexed) | folders)]


@router.get("/bids/{bid_id}")
def get_bid(bid_id: str, ctx: Ctx) -> BidDetail:
    settings = ctx.settings
    with Manifest(settings.db_path) as manifest:
        entries = manifest.entries(bid_id)
    if not entries and not (settings.data_dir / bid_id).is_dir():
        raise HTTPException(status_code=404, detail="unknown bid")
    files = []
    for rel, entry in sorted(entries.items()):
        doc_path = settings.docs_dir / f"{entry.doc_id}.json"
        doc = (
            ParsedDocument.model_validate_json(doc_path.read_text(encoding="utf-8"))
            if doc_path.exists()
            else None
        )
        files.append(
            DocumentInfo(
                file=rel,
                doc_type=entry.doc_type,
                addendum_number=doc.addendum_number if doc else None,
                doc_date=doc.doc_date if doc else None,
                pages=doc.page_count if doc else 0,
            )
        )
    summary = _summary(settings, bid_id, entries)
    return BidDetail(**summary.model_dump(), files=files)


@router.get("/bids/{bid_id}/result")
def get_result(bid_id: str, ctx: Ctx) -> BidResult:
    """The latest extraction record for the bid."""
    result = _result(ctx.settings, bid_id)
    if result is None:
        raise HTTPException(status_code=404, detail="no extraction result for this bid yet")
    return result


@router.post("/bids/{bid_id}/extract", status_code=202)
def extract(bid_id: str, ctx: Ctx) -> Job:
    """Start an extraction run in the background; poll the job for its status."""
    _folder(ctx.settings, bid_id)
    if (active := ctx.jobs.active_for(bid_id)) is not None:
        return active
    return ctx.start_extraction(bid_id)


@router.get("/bids/{bid_id}/files/{path:path}")
def source_file(bid_id: str, path: str, ctx: Ctx) -> FileResponse:
    """A source document, so a citation can open the file at its page."""
    folder = _folder(ctx.settings, bid_id)
    try:
        target = resolve_within(folder, path)
    except PathNotAllowedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    suffix = target.suffix.lower()
    if suffix in OFFICE_TYPES:  # browsers cannot show these: download them
        return FileResponse(target, media_type=OFFICE_TYPES[suffix], filename=target.name)
    # PDFs open inline; everything else (portal HTML included) is shown as plain text, so a
    # page from a bid portal cannot run script in this application's origin.
    media_type = "application/pdf" if suffix == ".pdf" else "text/plain; charset=utf-8"
    return FileResponse(target, media_type=media_type, headers={"Content-Disposition": "inline"})
