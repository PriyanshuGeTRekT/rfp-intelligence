"""Command-line interface: `rfp <command>`.

The command signatures are final; bodies arrive phase by phase. Unbuilt commands exit with
code 2 and say so, rather than pretending to work.
"""

import platform
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from rfp_intel import __version__
from rfp_intel.config import get_settings
from rfp_intel.logs import configure_logging
from rfp_intel.search.models import CONFIG_DESCRIPTIONS, DEFAULT_CONFIG

if TYPE_CHECKING:
    from datetime import date

    from rfp_intel.agents.llm import LLM
    from rfp_intel.agents.schema import BidResult
    from rfp_intel.agents.services import Services
    from rfp_intel.search.runtime import Runtime

app = typer.Typer(help="RFP Intelligence Platform", no_args_is_help=True)

BidArg = Annotated[
    str, typer.Argument(help="Bid folder: a name under the data directory, or any folder path")
]


@app.callback()
def main(
    json_logs: Annotated[bool, typer.Option("--json-logs/--pretty-logs")] = False,
) -> None:
    # Windows consoles and redirected output default to a legacy code page; model answers
    # contain characters it lacks (non-breaking hyphens, curly quotes).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    configure_logging(get_settings().log_level, json=json_logs)


def _todo(what: str) -> None:
    typer.echo(f"{what} is not implemented yet.", err=True)
    raise typer.Exit(code=2)


def _provider_summary() -> str:
    from rfp_intel.agents.llm import LLMError
    from rfp_intel.agents.providers import resolve_provider

    try:
        r = resolve_provider(get_settings())
    except LLMError as exc:
        return f"NOT READY: {exc}"
    where = f" at {r.base_url}" if r.base_url else ""
    return f"{r.name}{where} (key from {r.key_source})"


@app.command(name="llm-check")
def llm_check() -> None:
    """Make one tiny model call to confirm the configured provider, key and model work."""
    from rfp_intel.agents.llm import LLMError, llm_from_settings
    from rfp_intel.agents.providers import check_llm, resolve_provider

    s = get_settings()
    try:
        resolved = resolve_provider(s)
        llm = llm_from_settings(s)
        for model in dict.fromkeys([s.cheap_model, s.extract_model]):
            r = check_llm(llm, model)
            verdict = "ok" if r["ok"] else f"unexpected reply {r['reply']}"
            typer.echo(
                f"{resolved.name} {model}: {verdict}"
                f" in {r['latency_ms']} ms, {r['input_tokens']} in / {r['output_tokens']} out "
                f"tokens, ${r['cost_usd']:.5f}, structured output via {r['structured_output_mode']}"
            )
    except LLMError as exc:
        typer.echo(f"FAILED: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:  # the provider's own errors: show them, do not hide them
        typer.echo(f"FAILED: {type(exc).__name__}: {exc}", err=True)
        raise typer.Exit(code=1) from exc


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
        "LLM provider": _provider_summary(),
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
    from rfp_intel.ingestion.loader import PARSERS
    from rfp_intel.security import PathNotAllowedError, resolve_within

    path = Path(bid)
    if path.is_dir() and any(p.suffix.lower() in PARSERS for p in path.iterdir() if p.is_file()):
        return path.resolve()  # a bid folder anywhere on this machine: it holds documents
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
    out: Annotated[Path | None, typer.Option(help="Also write the JSON here")] = None,
    resume: Annotated[str | None, typer.Option(help="Resume a previous run id")] = None,
) -> None:
    """Run the multi-agent extraction and write one cited JSON for the bid."""
    from rfp_intel.agents.graph import run_extraction
    from rfp_intel.search.runtime import open_runtime
    from rfp_intel.telemetry import setup_tracing

    s = get_settings()
    folder = _bid_folder(bid)
    llm = _llm_or_exit()
    _, run_id = setup_tracing(s, run_id=resume)
    with open_runtime(s, load_reranker=s.extract_rerank) as rt:
        result, _state = run_extraction(
            _services(rt, llm),
            folder,
            run_id=run_id,
            resume=resume is not None,
            checkpoint_path=s.state_dir / "checkpoints.sqlite",
        )
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    _print_result(result)
    typer.echo(
        f"wrote {s.outputs_dir / (folder.name + '.json')}; "
        f"trace {s.traces_dir / (run_id + '.jsonl')}"
    )


def _llm_or_exit() -> "LLM":
    from rfp_intel.agents.llm import LLMError, llm_from_settings

    try:
        return llm_from_settings(get_settings())
    except LLMError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


def _services(rt: "Runtime", llm: "LLM") -> "Services":
    from rfp_intel.agents.services import Services

    s = get_settings()
    return Services.build(s, rt, llm, s.outputs_dir)


def _print_result(result: "BidResult") -> None:
    width = max(len(name) for name in result.fields)
    for name, fr in result.fields.items():
        value = ", ".join(fr.value) if isinstance(fr.value, list) else (fr.value or "null")
        typer.echo(f"{name:<{width}}  [{fr.tier:<4} {fr.confidence:.2f}]  {value[:90]}")
    v = result.validation
    typer.echo(
        f"\nvalidation: {v.passed} passed, {v.failed} failed, {v.not_found} not found, "
        f"{v.conflicts} conflicts; {v.retries} retries; "
        f"{len(result.addendum_changes)} addendum changes"
    )
    for issue in v.consistency_issues:
        typer.echo(f"consistency: {issue}")
    for error in result.errors:
        typer.echo(f"error: {error}", err=True)
    u = result.usage
    typer.echo(
        f"{int(u.get('calls', 0))} LLM calls, {int(u.get('input_tokens', 0))} in / "
        f"{int(u.get('output_tokens', 0))} out tokens, ${u.get('cost_usd', 0):.4f}"
    )


@app.command()
def ask(
    question: str,
    bid: Annotated[str | None, typer.Option(help="Restrict to one bid")] = None,
    log_path: Annotated[Path | None, typer.Option(help="Append the cited answer here")] = None,
    no_log: Annotated[bool, typer.Option("--no-log", help="Do not append to the log")] = False,
) -> None:
    """Answer a question with citations, or say it is not in the documents."""
    _ask_all([(question, bid)], log_path=None if no_log else log_path or _qa_log())


@app.command(name="ask-batch")
def ask_batch(
    questions: Annotated[Path, typer.Argument(help="Text file: one question per line")],
    log_path: Annotated[Path | None, typer.Option(help="Append the cited answers here")] = None,
) -> None:
    """Answer every question in a file (blank lines and # comments skipped). A line
    `Bid1 | question` restricts that question to one bid."""
    items: list[tuple[str, str | None]] = []
    for line in questions.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        bid, sep, text = line.partition("|")
        items.append((text.strip(), bid.strip()) if sep else (line, None))
    _ask_all(items, log_path=log_path or _qa_log())


def _qa_log() -> Path:
    return get_settings().outputs_dir / "qa_log.jsonl"


def _ask_all(items: list[tuple[str, str | None]], *, log_path: Path | None) -> None:
    """Answer questions through the agent graph, print them, and append them to the log."""
    from rfp_intel.agents.graph import run_question
    from rfp_intel.search.models import NAMED_CONFIGS
    from rfp_intel.search.runtime import open_runtime
    from rfp_intel.telemetry import setup_tracing

    s = get_settings()
    llm = _llm_or_exit()
    _, run_id = setup_tracing(s)
    with open_runtime(s, load_reranker=NAMED_CONFIGS[s.qa_search_config].rerank) as rt:
        for i, (question, bid) in enumerate(items, start=1):
            result, _ = run_question(
                _services(rt, llm), question, bid_id=bid, run_id=f"{run_id}-q{i}"
            )
            if len(items) > 1:
                typer.echo(f"\n[{i}/{len(items)}] {question}")
            typer.echo(result.answer)
            for c in result.citations:
                typer.echo(f'  [{c.bid_id}] {c.file} p{c.page}: "{c.quote}"')
            typer.echo(
                f"({result.passages_reviewed} passages from {', '.join(result.scope)}, "
                f"{result.dropped_citations} citations dropped, "
                f"${result.usage.get('cost_usd', 0):.4f})"
            )
            if result.error:
                typer.echo(f"error: {result.error}", err=True)
            if log_path is not None:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with log_path.open("a", encoding="utf-8") as fh:
                    fh.write(result.model_dump_json() + "\n")


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

    if suite == "extraction":
        _eval_extraction(
            gold if gold != Path("eval/retrieval_gold.yaml") else Path("eval/extraction_gold.yaml"),
            out_dir,
        )
        return
    if suite != "retrieval":
        typer.echo("suite must be retrieval or extraction", err=True)
        raise typer.Exit(code=1)
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


def _eval_extraction(gold: Path, out_dir: Path, results: Path | None = None) -> None:
    from rfp_intel.eval.extraction import (
        evaluate_extraction,
        load_extraction_gold,
        save_extraction_report,
    )

    results = results or get_settings().outputs_dir
    report = evaluate_extraction(results, load_extraction_gold(gold), gold_file=gold.as_posix())
    save_extraction_report(report, out_dir / "extraction.json", out_dir / "extraction.md")
    if report.missing_bids:
        typer.echo(f"no results for {report.missing_bids}; run `rfp extract <bid>` first", err=True)
    for bid, acc in report.by_bid().items():
        typer.echo(f"{bid}: {acc:.1%} of fields correct")
    for row in report.calibration():
        typer.echo(f"  tier {row.tier:<4} {row.correct}/{row.count} correct ({row.accuracy:.0%})")
    failed = [s for s in report.scores if not s.passed]
    for s in failed:
        typer.echo(f"  MISS {s.bid_id} {s.field}: {s.reason}")
    typer.echo(f"report: {out_dir / 'extraction.md'}")
    if report.missing_bids and not report.scores:
        raise typer.Exit(code=1)


@app.command(name="qa-report")
def qa_report(
    log_path: Annotated[Path | None, typer.Option("--log", help="Q&A log (JSONL)")] = None,
    out: Annotated[Path, typer.Option(help="Markdown file to write")] = Path("docs/qa_log.md"),
) -> None:
    """Render the Q&A log as Markdown: each question, its answer and its verified citations."""
    from rfp_intel.agents.qa import QAResult

    path = log_path or _qa_log()
    results = [
        QAResult.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    lines = [
        "# Sample Q&A log",
        "",
        f"{len(results)} questions answered by the agent graph (`rfp ask-batch "
        "eval/qa_questions.txt`); raw records in `outputs/qa_log.jsonl`. Every quote below "
        "was checked against the passage it cites.",
        "",
    ]
    for i, r in enumerate(results, start=1):
        meta = f"scope {', '.join(r.scope)} · {r.passages_reviewed} passages · model {r.model}"
        if r.dropped_citations:
            meta += f" · {r.dropped_citations} unverifiable citations removed"
        if r.removed_statements:
            meta += f" · {r.removed_statements} unsupported sentences removed"
        text = (
            " ".join(s.text + "".join(f" [{n + 1}]" for n in s.citations) for s in r.statements)
            or r.answer
        )
        lines += [f"## {i}. {r.question}", "", text, ""]
        for n, c in enumerate(r.citations, start=1):
            quote = " ".join(c.quote.split())
            lines.append(f"{n}. [{c.bid_id}] {c.file}, p. {c.page}: “{quote}”")
        lines += ["", f"<sub>{meta}</sub>", ""]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    typer.echo(f"wrote {out}")


@app.command()
def deliverables(
    bids: Annotated[
        list[str] | None, typer.Argument(help="Bid folders; every folder in the data dir if none")
    ] = None,
    questions: Annotated[Path, typer.Option(help="Q&A questions")] = Path("eval/qa_questions.txt"),
    gold: Annotated[Path, typer.Option(help="Extraction gold")] = Path("eval/extraction_gold.yaml"),
    trace_bid: Annotated[
        str | None, typer.Option(help="Bid whose run becomes docs/trace_example (default: last)")
    ] = None,
) -> None:
    """Regenerate every submitted output in one go: one record per bid, the Q&A log and its
    report, the extraction evaluation, and the example trace. Stops at the first failed step."""
    s = get_settings()
    names = bids or sorted(p.name for p in s.data_dir.iterdir() if p.is_dir())
    for name in names:
        typer.echo(f"\n== extract {name}")
        extract(bid=name, out=None, resume=None)
    log_path = _qa_log()
    log_path.unlink(missing_ok=True)  # the log is rebuilt, not appended to
    typer.echo("\n== questions")
    ask_batch(questions=questions, log_path=log_path)
    qa_report(log_path=log_path, out=Path("docs/qa_log.md"))
    typer.echo("\n== evaluation")
    _eval_extraction(gold, Path("docs/eval"))
    _write_trace_example(s.outputs_dir / f"{trace_bid or names[-1]}.json")


def _write_trace_example(record_path: Path) -> None:
    from rfp_intel.agents.schema import BidResult
    from rfp_intel.trace_render import load_spans, render_trace, scrub_paths

    run_id = BidResult.model_validate_json(record_path.read_text(encoding="utf-8")).run_id
    source = get_settings().traces_dir / f"{run_id}.jsonl"
    Path("docs/trace_example.md").write_text(render_trace(load_spans(source)), encoding="utf-8")
    raw = scrub_paths(source.read_text(encoding="utf-8"))
    Path("docs/trace_example.jsonl").write_text(raw, encoding="utf-8")
    typer.echo(f"wrote docs/trace_example.md and .jsonl from run {run_id}")


def _records_or_exit(bids: list[str]) -> list["BidResult"]:
    from rfp_intel.agents.compare import load_records

    try:
        return load_records(get_settings().outputs_dir, bids)
    except FileNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


def _as_of(value: str | None) -> "date | None":
    from datetime import date

    return date.fromisoformat(value) if value else None


AsOf = Annotated[
    str | None, typer.Option(help="Judge deadlines as of this date (YYYY-MM-DD); default today")
]


@app.command(name="go-no-go")
def go_no_go(
    bid: Annotated[str, typer.Argument(help="Bid id with an extraction record in outputs/")],
    as_of: AsOf = None,
    out: Annotated[Path | None, typer.Option(help="Also write the Markdown report here")] = None,
) -> None:
    """Recommend go, no-go or review for a bid against config/company.yaml (no model call)."""
    from rfp_intel.agents.gonogo import load_company, recommend, render_markdown

    s = get_settings()
    [record] = _records_or_exit([bid])
    rec = recommend(record, load_company(s.config_dir / "company.yaml"), _as_of(as_of))
    text = render_markdown(rec)
    typer.echo(text)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        typer.echo(f"wrote {out}")
    raise typer.Exit(code=0 if rec.decision != "no-go" else 2)


@app.command()
def compare(
    bids: Annotated[list[str], typer.Argument(help="Two or more bid ids with records")],
    out: Annotated[Path, typer.Option(help="Markdown report")] = Path("docs/comparison.md"),
    summary: Annotated[
        bool, typer.Option(help="Write the key differences with the cheap model")
    ] = True,
    as_of: AsOf = None,
) -> None:
    """Side-by-side report of several bids, their key differences and go / no-go."""
    from opentelemetry import trace as otel_trace

    from rfp_intel.agents.compare import compare as compare_bids
    from rfp_intel.agents.compare import render_markdown
    from rfp_intel.agents.fields import load_fields
    from rfp_intel.agents.gonogo import load_company
    from rfp_intel.agents.guarded import GuardedLLM
    from rfp_intel.telemetry import setup_tracing

    if len(bids) < 2:
        typer.echo("name at least two bids", err=True)
        raise typer.Exit(code=1)
    s = get_settings()
    records = _records_or_exit(bids)
    llm = GuardedLLM(_llm_or_exit(), max_output_tokens=s.llm_max_output_tokens) if summary else None
    provider, run_id = setup_tracing(s)
    tracer = otel_trace.get_tracer(__name__)
    with tracer.start_as_current_span(
        "agent.compare", attributes={"rfp.run_id": run_id, "rfp.bids": bids}
    ):
        result = compare_bids(
            records,
            load_fields(s.config_dir / "fields.yaml"),
            llm=llm,
            model=s.cheap_model,
            company=load_company(s.config_dir / "company.yaml"),
            as_of=_as_of(as_of),
        )
    provider.force_flush()
    catalog = load_fields(s.config_dir / "fields.yaml")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(result, catalog), encoding="utf-8")
    out.with_suffix(".json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
    if result.error:
        typer.echo(f"differences not written: {result.error}", err=True)
    typer.echo(f"wrote {out} and {out.with_suffix('.json')}; trace {run_id}")


@app.command()
def trace(
    run_id: Annotated[str, typer.Argument(help="Run id, as printed by `rfp extract`")],
    out: Annotated[
        Path | None, typer.Option(help="Write Markdown here instead of printing")
    ] = None,
) -> None:
    """Render a run's trace (traces/<run_id>.jsonl) as a tree of spans."""
    from rfp_intel.trace_render import load_spans, render_trace

    path = get_settings().traces_dir / f"{run_id}.jsonl"
    if not path.exists():
        typer.echo(f"no trace at {path}", err=True)
        raise typer.Exit(code=1)
    text = render_trace(load_spans(path))
    if out is None:
        typer.echo(text)
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        typer.echo(f"wrote {out}")


@app.command()
def diagram(
    out: Annotated[Path, typer.Option(help="Where to write the Mermaid source")] = Path(
        "docs/agent_graph.mmd"
    ),
) -> None:
    """Write the agent graph's topology as Mermaid (used by docs/architecture.md)."""
    from rfp_intel.agents.graph import graph_mermaid

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(graph_mermaid(), encoding="utf-8")
    typer.echo(f"wrote {out}")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the REST API."""
    import uvicorn

    from rfp_intel.telemetry import setup_server_tracing

    setup_server_tracing(get_settings())
    uvicorn.run("rfp_intel.api.app:create_app", factory=True, host=host, port=port)
