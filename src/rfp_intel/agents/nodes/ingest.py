"""The ingestion agent: makes sure the bid folder is indexed, then lists its documents.

Indexing is incremental: files whose hash and embedding model match the manifest are skipped,
so calling it on every run costs one hash per file, and a file added to the folder since the
last run is parsed and indexed before extraction starts. Parsing itself (file-type detection,
HTML and PDF parsing with tables, cleaning, metadata) is the `ingestion` package.
"""

from pathlib import Path
from typing import Any

from rfp_intel.agents.guarded import io_attribute
from rfp_intel.agents.schema import DocumentInfo
from rfp_intel.agents.services import Services
from rfp_intel.agents.state import RunState
from rfp_intel.ingestion.models import ParsedDocument
from rfp_intel.search.manifest import Manifest


def _load_doc(docs_dir: Path, doc_id: str) -> ParsedDocument | None:
    path = docs_dir / f"{doc_id}.json"
    if not path.exists():
        return None
    return ParsedDocument.model_validate_json(path.read_text(encoding="utf-8"))


def ingest(s: Services, state: RunState) -> dict[str, Any]:
    folder = Path(state["folder"])
    bid_id = state.get("bid_id") or folder.name
    notes: list[str] = []
    with s.span("agent.ingest") as span:
        if folder.is_dir():
            report = s.indexer.index_folder(folder)
            notes.append(
                f"ingest: {len(report.added)} added, {len(report.unchanged)} unchanged, "
                f"{len(report.failed)} failed"
            )
            notes += [f"ingest issue: {i.file_name}: {i.message}" for i in report.issues]
        with Manifest(s.settings.db_path) as manifest:
            entries = manifest.entries(bid_id)
        documents: list[dict[str, Any]] = []
        for rel, entry in sorted(entries.items()):
            doc = _load_doc(s.settings.docs_dir, entry.doc_id)
            info = DocumentInfo(
                file=rel,
                doc_type=entry.doc_type,
                addendum_number=doc.addendum_number if doc else None,
                doc_date=doc.doc_date if doc else None,
                pages=doc.page_count if doc else 0,
            )
            documents.append(info.model_dump(mode="json") | {"doc_id": entry.doc_id})
        span.set_attribute("rfp.bid_id", bid_id)
        span.set_attribute("agent.input", str(folder))
        span.set_attribute(
            "agent.output", io_attribute([(d["file"], d["doc_type"]) for d in documents])
        )
    return {
        "documents": documents,
        "log": [*notes, f"ingest: {len(documents)} documents"],
    }
