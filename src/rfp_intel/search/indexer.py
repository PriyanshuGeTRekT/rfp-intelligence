"""Incremental indexing of bid folders.

For each file: hash it; skip it when the manifest already holds that hash for the current
pipeline and embedding model; otherwise parse, extract facts, chunk, embed and replace the
file's old facts and chunks. Files that disappeared from the folder are removed from the
index. A file that fails to parse keeps its previous index entry and is reported.
"""

import hashlib
import threading
from pathlib import Path

from opentelemetry import trace
from pydantic import BaseModel, Field

from rfp_intel.facts.extract import extract_facts
from rfp_intel.facts.labels import FactTypeConfig
from rfp_intel.facts.store import FactStore
from rfp_intel.ingestion.loader import list_files, page_issues, parse_file, unsupported_issue
from rfp_intel.ingestion.meta import CueConfig
from rfp_intel.ingestion.models import Issue
from rfp_intel.logs import get_logger
from rfp_intel.search.backend import SearchBackend
from rfp_intel.search.chunking import ChunkConfig, chunk_document
from rfp_intel.search.embed import DenseEmbedder, SparseEmbedder
from rfp_intel.search.manifest import PIPELINE_VERSION, Manifest, ManifestEntry, now

log = get_logger(__name__)
tracer = trace.get_tracer(__name__)


class IndexReport(BaseModel):
    bid_id: str
    added: list[str] = Field(default_factory=list)
    changed: list[str] = Field(default_factory=list)
    unchanged: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)
    chunks_written: int = 0
    facts_written: int = 0
    issues: list[Issue] = Field(default_factory=list)


class Indexer:
    def __init__(
        self,
        backend: SearchBackend,
        dense: DenseEmbedder,
        sparse: SparseEmbedder,
        db_path: Path,
        cues: CueConfig,
        fact_config: FactTypeConfig,
        chunk_config: ChunkConfig | None = None,
        docs_dir: Path | None = None,
    ) -> None:
        self.backend = backend
        self.dense = dense
        self.sparse = sparse
        self.db_path = db_path
        self.cues = cues
        self.fact_config = fact_config
        self.chunk_config = chunk_config or ChunkConfig()
        self.docs_dir = docs_dir  # parsed documents are kept here as JSON for later steps

    def index_folder(self, folder: Path, *, force: bool = False) -> IndexReport:
        bid_id = folder.name
        report = IndexReport(bid_id=bid_id)
        with (
            tracer.start_as_current_span("index.folder") as span,
            FactStore(self.db_path) as facts,
            Manifest(self.db_path) as manifest,
        ):
            span.set_attribute("rfp.bid_id", bid_id)
            known = manifest.entries(bid_id)
            files, unsupported = list_files(folder)
            report.issues.extend(unsupported_issue(rel) for rel in unsupported)
            present = set()
            for path, rel in files:
                present.add(rel)
                sha = hashlib.sha256(path.read_bytes()).hexdigest()
                entry = known.get(rel)
                if entry is not None and not force and entry.is_current(sha, self.dense.name):
                    report.unchanged.append(rel)
                    continue
                try:
                    doc = parse_file(path, bid_id, rel, self.cues)
                except Exception as exc:  # keep the previous index entry, report the failure
                    log.warning("index_file_failed", file=rel, error=str(exc))
                    report.failed.append(rel)
                    report.issues.append(
                        Issue(file_name=rel, severity="error", message=f"could not parse: {exc}")
                    )
                    continue
                report.issues.extend(page_issues(doc))
                with tracer.start_as_current_span("index.file") as fspan:
                    fspan.set_attribute("rfp.file", rel)
                    if entry is not None:
                        self.backend.delete_document(entry.doc_id)
                        facts.delete_document(entry.doc_id)
                    doc_facts = extract_facts(doc, self.fact_config)
                    facts.replace_document(doc.doc_id, doc_facts)
                    chunks = chunk_document(doc, doc_facts, self.chunk_config)
                    texts = [c.embed_text for c in chunks]
                    self.backend.upsert(
                        chunks,
                        self.dense.embed_documents(texts),
                        self.sparse.embed_documents(texts),
                    )
                    fspan.set_attribute("rfp.chunks", len(chunks))
                    fspan.set_attribute("rfp.facts", len(doc_facts))
                if self.docs_dir is not None:
                    self.docs_dir.mkdir(parents=True, exist_ok=True)
                    (self.docs_dir / f"{doc.doc_id}.json").write_text(
                        doc.model_dump_json(), encoding="utf-8"
                    )
                manifest.put(
                    ManifestEntry(
                        bid_id=bid_id,
                        rel_path=rel,
                        file_sha256=sha,
                        doc_id=doc.doc_id,
                        doc_type=doc.doc_type.value,
                        chunks=len(chunks),
                        facts=len(doc_facts),
                        pipeline_version=PIPELINE_VERSION,
                        embed_model=self.dense.name,
                        indexed_at=now(),
                    )
                )
                (report.changed if entry is not None else report.added).append(rel)
                report.chunks_written += len(chunks)
                report.facts_written += len(doc_facts)

            for rel, entry in known.items():
                if rel not in present:
                    self.backend.delete_document(entry.doc_id)
                    facts.delete_document(entry.doc_id)
                    manifest.remove(bid_id, rel)
                    report.removed.append(rel)
                    if self.docs_dir is not None:
                        (self.docs_dir / f"{entry.doc_id}.json").unlink(missing_ok=True)

            for name in ("added", "changed", "unchanged", "removed", "failed"):
                span.set_attribute(f"index.{name}", len(getattr(report, name)))
        log.info(
            "index_folder_done",
            bid_id=bid_id,
            added=len(report.added),
            changed=len(report.changed),
            unchanged=len(report.unchanged),
            removed=len(report.removed),
            failed=len(report.failed),
        )
        return report

    def index_new_bids(self, data_dir: Path, bid_ids: list[str] | None = None) -> list[IndexReport]:
        """Index the bid folders under `data_dir` that are not in the index yet (only those in
        `bid_ids`, when given), so a question or search on a fresh setup does not come back
        empty. Bids already indexed are left as they are: re-indexing changed files is the
        job of `rfp index` and of an extraction run."""
        if not data_dir.is_dir():
            return []
        with _first_index_lock:  # two requests on a fresh server must not index a bid twice
            with Manifest(self.db_path) as manifest:
                known = set(manifest.bids())
            new = [
                p
                for p in sorted(data_dir.iterdir())
                if p.is_dir() and p.name not in known and (bid_ids is None or p.name in bid_ids)
            ]
            return [self.index_folder(p) for p in new]


_first_index_lock = threading.Lock()
