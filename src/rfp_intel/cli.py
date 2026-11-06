"""Command-line interface: `rfp <command>`.

The command signatures are final; bodies arrive phase by phase. Unbuilt commands exit with
code 2 and say so, rather than pretending to work.
"""

import platform
from pathlib import Path
from typing import Annotated

import typer

from rfp_intel import __version__
from rfp_intel.config import get_settings
from rfp_intel.logs import configure_logging

app = typer.Typer(help="RFP Intelligence Platform", no_args_is_help=True)

BidArg = Annotated[str, typer.Argument(help="Bid folder name under the data directory")]


@app.callback()
def main(
    json_logs: Annotated[bool, typer.Option("--json-logs/--pretty-logs")] = False,
) -> None:
    configure_logging(get_settings().log_level, json=json_logs)


def _todo(what: str) -> None:
    typer.echo(f"{what} is not implemented yet.", err=True)
    raise typer.Exit(code=2)


@app.command()
def doctor() -> None:
    """Show configuration and check that the data directory and keys are in place."""
    s = get_settings()
    bids = sorted(p.name for p in s.data_dir.iterdir() if p.is_dir()) if s.data_dir.is_dir() else []
    rows = {
        "version": __version__,
        "python": platform.python_version(),
        "data_dir": f"{s.data_dir} ({'found' if s.data_dir.is_dir() else 'MISSING'})",
        "bid folders": ", ".join(bids) or "none",
        "state_dir": str(s.state_dir),
        "traces_dir": str(s.traces_dir),
        "ANTHROPIC_API_KEY": "set" if s.anthropic_api_key else "not set",
        "extract / cheap model": f"{s.extract_model} / {s.cheap_model}",
        "embed / sparse / rerank": f"{s.embed_model} / {s.sparse_model} / {s.rerank_model}",
        "API key auth": "on" if s.api_key else "off",
        "OTLP endpoint": s.otlp_endpoint or "off (JSONL only)",
    }
    width = max(len(k) for k in rows)
    for key, value in rows.items():
        typer.echo(f"{key:<{width}}  {value}")
    if not s.data_dir.is_dir():
        raise typer.Exit(code=1)


@app.command()
def parse(
    bid: BidArg,
    out: Annotated[Path | None, typer.Option(help="Write the parsed bid as JSON here")] = None,
) -> None:
    """Parse a bid folder and print what was found in each file (no indexing)."""
    from rfp_intel.ingestion.loader import load_bid_folder

    s = get_settings()
    result = load_bid_folder(_bid_folder(bid), s.config_dir / "doc_types.yaml")
    for doc in result.documents:
        extra = f" addendum {doc.addendum_number}" if doc.addendum_number else ""
        when = f"{doc.doc_date} ({doc.doc_date_source})" if doc.doc_date else "no date"
        typer.echo(
            f"{doc.file_name}\n"
            f"  type   {doc.doc_type.value}{extra}  [{doc.doc_type_reason}]\n"
            f"  title  {doc.title}\n"
            f"  date   {when}\n"
            f"  size   {doc.page_count} pages, {len(doc.blocks)} blocks, "
            f"{len(doc.tables)} tables, {len(doc.sections)} sections"
        )
    if result.issues:
        typer.echo("issues:")
        for issue in result.issues:
            where = f" p{issue.page}" if issue.page else ""
            typer.echo(f"  {issue.severity:<7} {issue.file_name}{where}: {issue.message}")
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        typer.echo(f"wrote {out}")


@app.command()
def facts(
    bid: BidArg,
    fact_type: Annotated[
        list[str] | None, typer.Option("--type", help="Only these labels, e.g. deadline")
    ] = None,
    kind: Annotated[list[str] | None, typer.Option(help="Only these kinds, e.g. datetime")] = None,
    limit: int = 50,
) -> None:
    """Extract typed facts from a bid, store them, and print the matching ones."""
    from rfp_intel.facts.extract import extract_facts
    from rfp_intel.facts.labels import load_fact_types
    from rfp_intel.facts.models import FactKind
    from rfp_intel.facts.store import FactStore
    from rfp_intel.ingestion.loader import load_bid_folder

    s = get_settings()
    folder = load_bid_folder(_bid_folder(bid), s.config_dir / "doc_types.yaml")
    config = load_fact_types(s.config_dir / "fact_types.yaml")
    try:
        kinds = [FactKind(k) for k in kind or []]
    except ValueError as exc:
        typer.echo(f"unknown kind; choose from {', '.join(k.value for k in FactKind)}", err=True)
        raise typer.Exit(code=1) from exc
    with FactStore(s.db_path) as store:
        total = sum(
            store.replace_document(d.doc_id, extract_facts(d, config)) for d in folder.documents
        )
        found = store.query(folder.bid_id, kinds=kinds or None, fact_types=fact_type or None)
        counts = store.count_by_type(folder.bid_id)
    typer.echo(f"{total} facts stored for {folder.bid_id} in {s.db_path}")
    typer.echo("by label: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    for f in found[:limit]:
        v = f.value
        shown = v.get("utc") or v.get("local") or v.get("date") or v.get("time") or v
        typer.echo(
            f"- {f.file_name} p{f.page} [{', '.join(f.fact_types) or '-'}] {f.kind.value} "
            f"{f.raw!r} -> {shown}\n    {f.context[:160]}"
        )
    if len(found) > limit:
        typer.echo(f"... {len(found) - limit} more (use --limit)")


def _bid_folder(bid: str) -> Path:
    from rfp_intel.security import PathNotAllowedError, resolve_within

    try:
        folder = resolve_within(get_settings().data_dir, bid)
    except PathNotAllowedError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    if not folder.is_dir():
        typer.echo(f"bid folder not found: {folder}", err=True)
        raise typer.Exit(code=1)
    return folder


@app.command()
def index(
    bids: Annotated[
        list[str] | None, typer.Argument(help="Bid folders to index; all folders when omitted")
    ] = None,
    force: Annotated[bool, typer.Option(help="Re-index even unchanged files")] = False,
) -> None:
    """Parse, extract facts, chunk and embed bid folders. Unchanged files are skipped."""
    from rfp_intel.search.runtime import open_runtime
    from rfp_intel.telemetry import setup_tracing

    s = get_settings()
    setup_tracing(s)
    names = bids or sorted(p.name for p in s.data_dir.iterdir() if p.is_dir())
    folders = [_bid_folder(name) for name in names]
    with open_runtime(s, load_reranker=False) as rt:
        indexer = rt.indexer()
        for folder in folders:
            r = indexer.index_folder(folder, force=force)
            typer.echo(
                f"{r.bid_id}: {len(r.added)} added, {len(r.changed)} changed, "
                f"{len(r.unchanged)} unchanged, {len(r.removed)} removed, {len(r.failed)} failed; "
                f"{r.chunks_written} chunks and {r.facts_written} facts written"
            )
            for issue in r.issues:
                where = f" p{issue.page}" if issue.page else ""
                typer.echo(f"  {issue.severity:<7} {issue.file_name}{where}: {issue.message}")


@app.command()
def search(
    query: str,
    bid: Annotated[str | None, typer.Option(help="Restrict to one bid")] = None,
    doc_type: Annotated[
        list[str] | None, typer.Option(help="rfp, addendum, specs, affidavit, bid_page, form")
    ] = None,
    addendum: Annotated[int | None, typer.Option(help="Only this addendum number")] = None,
    k: int = 5,
    config: Annotated[
        str, typer.Option(help="dense, sparse, hybrid, hybrid_facts, hybrid_facts_rerank")
    ] = "hybrid_facts_rerank",
    as_json: Annotated[bool, typer.Option("--json", help="Print the full result as JSON")] = False,
) -> None:
    """Hybrid search; prints file, page, score and chunk text for each hit."""
    from rfp_intel.search.models import NAMED_CONFIGS
    from rfp_intel.search.runtime import open_runtime
    from rfp_intel.telemetry import setup_tracing

    if config not in NAMED_CONFIGS:
        typer.echo(f"unknown config; choose from {', '.join(NAMED_CONFIGS)}", err=True)
        raise typer.Exit(code=1)
    s = get_settings()
    setup_tracing(s)
    with open_runtime(s, load_reranker=NAMED_CONFIGS[config].rerank) as rt:
        if rt.backend.count() == 0:
            typer.echo("the index is empty; run `rfp index` first", err=True)
            raise typer.Exit(code=1)
        result = rt.engine().search(
            query, bid_id=bid, doc_types=doc_type, addendum_number=addendum, k=k, config=config
        )
    if as_json:
        typer.echo(result.model_dump_json(indent=2))
        return
    a = result.query
    typer.echo(
        f"config {result.config} | ids {a.identifiers or '-'} | routed to {a.fact_types or '-'} "
        f"| {result.timings_ms.get('total', 0):.0f} ms"
    )
    for h in result.hits:
        where = f"{h.file_name} p{h.pages}"
        ranks = ", ".join(f"{name} {r}" for name, r in h.signals.get("ranks", {}).items())
        typer.echo(
            f"\n#{h.rank}  {h.score:.3f}  {where}  [{h.doc_type}, {h.chunk_type}]  ({ranks})"
        )
        if h.section_path:
            typer.echo(f"    {' > '.join(h.section_path)}")
        typer.echo("    " + h.text[:400].replace("\n", "\n    "))


@app.command()
def extract(
    bid: BidArg,
    out: Annotated[Path | None, typer.Option(help="Output JSON path")] = None,
    resume: Annotated[str | None, typer.Option(help="Resume a previous run id")] = None,
) -> None:
    """Run the multi-agent extraction and write one cited JSON for the bid."""
    _todo("extract")


@app.command()
def ask(
    question: str,
    bid: Annotated[str | None, typer.Option(help="Restrict to one bid")] = None,
) -> None:
    """Answer a question with citations, or say it is not in the documents."""
    _todo("ask")


@app.command(name="eval")
def eval_(
    suite: Annotated[str, typer.Argument(help="retrieval or extraction")] = "retrieval",
) -> None:
    """Run an evaluation suite and write the report."""
    _todo("eval")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the REST API."""
    import uvicorn

    uvicorn.run("rfp_intel.api.app:create_app", factory=True, host=host, port=port)
