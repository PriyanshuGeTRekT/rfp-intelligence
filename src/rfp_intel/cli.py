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
    from rfp_intel.security import PathNotAllowedError, resolve_within

    s = get_settings()
    try:
        folder = resolve_within(s.data_dir, bid)
    except PathNotAllowedError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    if not folder.is_dir():
        typer.echo(f"bid folder not found: {folder}", err=True)
        raise typer.Exit(code=1)

    result = load_bid_folder(folder, s.config_dir / "doc_types.yaml")
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
def index(
    bid: BidArg,
    force: Annotated[bool, typer.Option(help="Re-index even unchanged files")] = False,
) -> None:
    """Parse a bid folder and add its chunks and facts to the index (incremental)."""
    _todo("index")


@app.command()
def search(
    query: str,
    bid: Annotated[str | None, typer.Option(help="Restrict to one bid")] = None,
    doc_type: Annotated[str | None, typer.Option(help="rfp, addendum, specs, ...")] = None,
    k: int = 5,
) -> None:
    """Hybrid search; prints file, page, score and chunk text for each hit."""
    _todo("search")


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
