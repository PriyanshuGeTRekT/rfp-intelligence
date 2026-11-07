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
from rfp_intel.search.models import DEFAULT_CONFIG

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
    ] = DEFAULT_CONFIG,
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
    from rfp_intel.agents.evidence import EvidenceStore
    from rfp_intel.agents.fields import load_fields
    from rfp_intel.agents.graph import Services, run_extraction
    from rfp_intel.agents.llm import LLMError, llm_from_settings
    from rfp_intel.search.runtime import open_runtime
    from rfp_intel.telemetry import setup_tracing

    s = get_settings()
    folder = _bid_folder(bid)
    try:
        llm = llm_from_settings(s)
    except LLMError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _, run_id = setup_tracing(s, run_id=resume)
    out_dir = out.parent if out is not None else Path("outputs")
    with open_runtime(s) as rt:
        services = Services(
            settings=s,
            engine=rt.engine(),
            indexer=rt.indexer(),
            llm=llm,
            catalog=load_fields(s.config_dir / "fields.yaml"),
            store=EvidenceStore(loader=rt.backend.fetch),
            out_dir=out_dir,
        )
        result, _state = run_extraction(
            services,
            folder.name,
            run_id=run_id,
            resume=resume is not None,
            checkpoint_path=s.state_dir / "checkpoints.sqlite",
        )
    if out is not None and out.name != f"{folder.name}.json":
        out.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    width = max(len(k) for k in result.fields)
    for key, fr in result.fields.items():
        value = ", ".join(fr.value) if isinstance(fr.value, list) else (fr.value or "null")
        typer.echo(f"{key:<{width}}  [{fr.tier:<4} {fr.confidence:.2f}]  {value[:90]}")
    v = result.validation
    typer.echo(
        f"\n{v.fields} fields: {v.passed_first_time} passed first time, "
        f"{v.passed_after_retry} after retry, {v.failed} failed; {v.retries} retries; "
        f"{len(result.addendum_changes)} addendum changes"
    )
    u = result.usage
    typer.echo(
        f"{int(u.get('calls', 0))} LLM calls, {int(u.get('input_tokens', 0))} in / "
        f"{int(u.get('output_tokens', 0))} out tokens, ${u.get('cost_usd', 0):.4f}"
    )
    typer.echo(
        f"wrote {out_dir / (folder.name + '.json')}; trace {s.traces_dir / (run_id + '.jsonl')}"
    )


@app.command()
def ask(
    question: str,
    bid: Annotated[str | None, typer.Option(help="Restrict to one bid")] = None,
    k: Annotated[int, typer.Option(help="Passages to read")] = 8,
    config: Annotated[str, typer.Option(help="Retrieval configuration")] = DEFAULT_CONFIG,
    log_path: Annotated[Path, typer.Option(help="Append the cited answer here")] = Path(
        "outputs/qa_log.jsonl"
    ),
    no_log: Annotated[bool, typer.Option("--no-log", help="Do not append to the log")] = False,
) -> None:
    """Answer a question with citations, or say it is not in the documents."""
    from rfp_intel.agents.llm import LLMError, llm_from_settings
    from rfp_intel.agents.qa import answer
    from rfp_intel.search.models import NAMED_CONFIGS
    from rfp_intel.search.runtime import open_runtime
    from rfp_intel.telemetry import setup_tracing

    s = get_settings()
    try:
        llm = llm_from_settings(s)
    except LLMError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    setup_tracing(s)
    with open_runtime(s, load_reranker=NAMED_CONFIGS[config].rerank) as rt:
        result = answer(rt.engine(), llm, s.extract_model, question, bid_id=bid, k=k, config=config)
    typer.echo(result.answer)
    for c in result.citations:
        typer.echo(f'  [{c.bid_id}] {c.file} p{c.page}: "{c.quote}"')
    typer.echo(
        f"({result.passages_reviewed} passages, {result.dropped_citations} citations dropped, "
        f"${result.usage.get('cost_usd', 0):.4f})"
    )
    if not no_log:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(result.model_dump_json() + "\n")


CONFIG_DESCRIPTIONS = {
    "dense": "bge-small embeddings only",
    "sparse": "BM25 only (Qdrant sparse vectors with IDF), with synonym expansion",
    "hybrid": "dense + BM25 + exact identifier matches, fused with RRF (k=60)",
    "hybrid_facts": "hybrid plus dense and BM25 lists restricted to chunks with the fact labels "
    "the question routes to (default)",
    "hybrid_facts_rerank": "hybrid_facts, top 30 reranked by the configured cross-encoder "
    "(RFP_RERANK_MODEL, default BAAI/bge-reranker-v2-m3-int8)",
}


@app.command(name="eval")
def eval_(
    suite: Annotated[
        str, typer.Argument(help="retrieval (extraction comes with the agents)")
    ] = "retrieval",
    gold: Annotated[Path, typer.Option(help="Gold questions")] = Path("eval/retrieval_gold.yaml"),
    configs: Annotated[
        list[str] | None, typer.Option("--config", help="Configs to run; all by default")
    ] = None,
    extra_reranker: Annotated[
        str | None,
        typer.Option(
            help="Also run hybrid_facts with this reranker, e.g. BAAI/bge-reranker-v2-m3-int8"
        ),
    ] = None,
    out_dir: Annotated[Path, typer.Option(help="Where the report goes")] = Path("docs/eval"),
    baseline: Annotated[Path, typer.Option(help="Committed baseline")] = Path("eval/baseline.json"),
    check: Annotated[
        bool, typer.Option(help="Fail if the default config fell below the baseline")
    ] = False,
    update_baseline: Annotated[
        bool, typer.Option(help="Write this run as the new baseline")
    ] = False,
) -> None:
    """Run the retrieval evaluation and write docs/eval/retrieval.md and .json."""
    from rfp_intel.eval.retrieval import (
        baseline_from,
        check_regression,
        evaluate,
        load_baseline,
        load_gold,
        save_run,
    )
    from rfp_intel.search.embed import FastEmbedReranker
    from rfp_intel.search.engine import SearchEngine
    from rfp_intel.search.models import NAMED_CONFIGS, SearchConfig
    from rfp_intel.search.runtime import open_runtime

    if suite != "retrieval":
        _todo(f"eval {suite}")
    names = configs or list(NAMED_CONFIGS)
    unknown = [n for n in names if n not in NAMED_CONFIGS]
    if unknown:
        typer.echo(f"unknown config {unknown}; choose from {', '.join(NAMED_CONFIGS)}", err=True)
        raise typer.Exit(code=1)
    s = get_settings()
    gold_set = load_gold(gold)
    descriptions = {n: CONFIG_DESCRIPTIONS[n] for n in names}
    with open_runtime(s) as rt:
        if rt.backend.count() == 0:
            typer.echo("the index is empty; run `rfp index` first", err=True)
            raise typer.Exit(code=1)
        run = evaluate(rt.engine(), gold_set, names, gold_file=gold.as_posix())
        if extra_reranker:
            label = f"hybrid_facts_rerank[{extra_reranker.split('/')[-1]}]"
            engine = SearchEngine(
                rt.backend, rt.dense, rt.sparse, rt.fact_config, synonyms=rt.synonyms,
                reranker=FastEmbedReranker(extra_reranker, cache_dir=s.models_dir),
            )  # fmt: skip
            extra = evaluate(
                engine, gold_set, [SearchConfig(name=label)], gold_file=gold.as_posix()
            )
            run.configs.extend(extra.configs)
            descriptions[label] = f"hybrid_facts reranked by {extra_reranker}"
    save_run(run, out_dir / "retrieval.json", out_dir / "retrieval.md", descriptions)

    for c in run.configs:
        typer.echo(
            f"{c.config:<44} R@1 {c.metric('recall@1'):.3f}  R@5 {c.metric('recall@5'):.3f}  "
            f"R@10 {c.metric('recall@10'):.3f}  MRR {c.metric('mrr'):.3f}  "
            f"{c.metric('latency_ms'):.0f} ms"
        )
    typer.echo(f"report: {out_dir / 'retrieval.md'}")

    default = DEFAULT_CONFIG if DEFAULT_CONFIG in names else names[0]
    if update_baseline:
        baseline.parent.mkdir(parents=True, exist_ok=True)
        baseline.write_text(baseline_from(run, default).model_dump_json(indent=2), encoding="utf-8")
        typer.echo(f"baseline written: {baseline}")
    if check:
        problems = check_regression(run, load_baseline(baseline))
        for p in problems:
            typer.echo(f"REGRESSION: {p}", err=True)
        if problems:
            raise typer.Exit(code=1)
        typer.echo("no regression against the baseline")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the REST API."""
    import uvicorn

    uvicorn.run("rfp_intel.api.app:create_app", factory=True, host=host, port=port)
