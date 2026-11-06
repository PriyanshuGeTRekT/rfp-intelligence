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
