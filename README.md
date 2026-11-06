# RFP Intelligence Platform

Hybrid search and multi-agent field extraction over public bid documents. Given a bid folder
(portal HTML page, RFP PDF, addenda, spec sheets, affidavits), it produces one cited JSON with
20 fields and answers free-form questions with citations, or says the answer is not in the
documents.

> Status: phase 0 (scaffold). Configuration, logging, tracing, API security basics, CLI
> surface, tests and CI are in place. Ingestion, search and agents are next.

## Quick start

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12 or newer. Run every command from the
repo root.

```bash
uv sync
cp .env.example .env        # then set ANTHROPIC_API_KEY
uv run rfp doctor           # shows config and the bid folders it can see
uv run pytest               # unit tests: no API key, no model downloads
```

| Command | What it does | Status |
|---|---|---|
| `rfp doctor` | Show configuration, check data directory and keys | done |
| `rfp index <bid>` | Parse a bid folder and index it incrementally | phase 1 to 3 |
| `rfp search "<query>"` | Hybrid search with file, page and chunk text per hit | phase 3 |
| `rfp extract <bid>` | Multi-agent extraction to one cited JSON | phase 5 |
| `rfp ask "<question>"` | Cited answer or "not found in documents" | phase 6 |
| `rfp eval retrieval` | Recall@k and MRR per retrieval configuration | phase 4 |
| `rfp serve` | REST API: `POST /index`, `GET /search`, `POST /ask` | routes stubbed |

## Layout

```
src/rfp_intel/
  config.py       settings from env/.env only (models, paths, keys)
  logs.py         structlog JSON logs carrying trace and span ids
  telemetry.py    OpenTelemetry: JSONL span file per run, optional OTLP, PII redaction
  security.py     path allow-list for anything a user can point at
  cli.py          Typer CLI (`rfp ...`)
  api/            FastAPI app, X-API-Key auth, request size cap
  ingestion/      PDF/HTML parsing, cleaning, doc-type classification, tables
  facts/          typed facts at ingest: dates with IANA zones, money, ids, contacts
  search/         Qdrant dense + BM25 hybrid, identifier field, rerank, manifest
  agents/         LangGraph orchestration, extraction groups, reconciliation, validator
  eval/           retrieval and extraction evaluation
config/           field definitions and fact-type cues (YAML)
data/bids/        the two provided bids
docs/             architecture, design decisions, example trace, eval reports
tests/            unit tests (CI runs them without keys or model downloads)
```

## Observability

Every run writes its spans to `traces/<run_id>.jsonl`. To browse traces in Arize Phoenix
locally, install the `obs` extra, start Phoenix and point the exporter at it:

```bash
uv sync --extra obs
uv run --with arize-phoenix python -m phoenix.server.main serve
```

Then set `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:6006/v1/traces` in `.env`. Emails and
phone numbers in span attributes are masked before export unless `RFP_TRACE_REDACT_PII=false`.

## Design decisions

To be written as each phase lands: chunking, embedding model, retrieval and fusion, the fact
layer, addendum reconciliation, agent framework, prompts, confidence tiers.

## Assumptions and limitations

To be written.
