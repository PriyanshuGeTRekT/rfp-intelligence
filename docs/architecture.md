# Architecture

Two deterministic layers (ingestion with the fact layer, then the hybrid index) do as much of
the work as possible without a model. The agents on top use the search engine as their tool,
choose among typed candidates and cited passages, and everything they produce is checked by
code before it is written out.

## System

```mermaid
flowchart LR
    subgraph Clients
        WEB[Web app<br/>React]
        CLI[CLI / main.py]
        MCP[MCP server]
    end

    API[FastAPI<br/>/index /search /ask<br/>/api/bids /api/jobs /api/runs]

    subgraph Ingestion["Ingestion (no model)"]
        P[Parsers<br/>PyMuPDF, BeautifulSoup]
        C[Cleaning, headers,<br/>tables, sections]
        T[Doc type, addendum no.,<br/>document date]
        X[Typed facts<br/>dates+zones, durations,<br/>money, ids, contacts]
        K[Structure-aware<br/>chunking]
        P --> C --> T --> X --> K
    end

    subgraph Stores
        Q[(Qdrant<br/>dense + BM25 + payload)]
        S[(SQLite<br/>facts, manifest,<br/>checkpoints)]
        E[(addendum<br/>events cache)]
    end

    subgraph Search["Search engine (no model)"]
        R[Query analysis:<br/>identifiers, fact routing,<br/>synonym expansion]
        L[dense, bm25, identifiers,<br/>facts_dense, facts_bm25]
        U[RRF fusion,<br/>cross-encoder rerank]
        R --> L --> U
    end

    subgraph Agents["Agent graph (LangGraph)"]
        PL[Orchestrator]
        IN[Ingestion agent]
        RC[Reconciliation agent]
        RT[Retrieval agent]
        EX[Extraction agents]
        VA[Validator]
        RP[Report agent]
        QA[Q&A agent]
    end

    LLM{{Any LLM provider<br/>paced, guarded}}

    subgraph Output
        J[outputs/bid.json]
        QL[outputs/qa_log.jsonl]
        TR[traces/run.jsonl]
    end

    WEB --> API
    API --> Agents
    API --> Search
    CLI --> Agents
    MCP --> Agents
    MCP --> Search
    IN --> P
    K --> Q
    X --> S
    Q --> L
    S --> RC
    E <--> RC
    RT --> R
    RC --> R
    QA --> R
    RC --> LLM
    RT --> LLM
    EX --> LLM
    RP --> LLM
    QA --> LLM
    RP --> J
    QA --> QL
    Agents --> TR
```

## Agent graph

Generated from the compiled graph with `uv run rfp diagram` (source in
[agent_graph.mmd](agent_graph.mmd)). Dotted edges are decisions: `plan` routes a question to
`answer` and a bid to `ingest`; `reconcile` fans out one `retrieve` branch per batch of fields
(with `Send`, so batches run in parallel); each `retrieve` hands its task and evidence to its
own `extract` (with `Command(goto=Send(...))`); `validate` sends each rejected field back to
`retrieve` with the reason (at most `RFP_MAX_RETRIES` times), or moves on to `report`.

```mermaid
graph TD;
	__start__([<p>__start__</p>]):::first
	plan(plan)
	ingest(ingest)
	reconcile(reconcile)
	extract(extract)
	validate(validate)
	report(report)
	answer(answer)
	retrieve(retrieve)
	__end__([<p>__end__</p>]):::last
	__start__ --> plan;
	extract --> validate;
	ingest --> reconcile;
	plan -.-> answer;
	plan -.-> ingest;
	reconcile -.-> retrieve;
	reconcile -.-> validate;
	retrieve -.-> extract;
	validate -.-> report;
	validate -.-> retrieve;
	answer --> __end__;
	report --> __end__;
	classDef default fill:#e6f2f0,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#9fd3cb
```

## One extraction run, step by step

1. **plan** (orchestrator) reads the goal. For a bid it writes the plan: ingest, reconcile,
   one retrieve-and-extract step per batch of fields, validate, report. For a question, one
   step: answer.
2. **ingest** indexes the folder incrementally (files whose hash and embedding model match
   the manifest are skipped; new or changed files are parsed, chunked, embedded and their
   facts stored) and lists the documents with type, addendum number, date and pages.
3. **reconcile** loads the bid's facts. Deadline and pre-bid facts inside addenda become
   `replace` events with no model. For each addendum, the search engine is queried inside
   that document for change language and for each field an addendum can change; one
   structured call over those passages lists the other changes (new requirements,
   amendments, clarifications); events whose quote is not verbatim addendum text are
   dropped; the result is cached per document. The date fields are resolved by folding the
   events over the base documents, with the portal page used to fill a missing time and to
   corroborate.
4. **retrieve** (one branch per batch, in parallel): per field, search the field's name and
   queries, search again within the field's preferred document types, add every chunk holding
   a labelled fact, rerank the pool with the cross-encoder. On a retry, a cheap model first
   rewrites the queries from the validator's reason.
5. **extract** (one per batch): fit the passages to the prompt budget, then one structured
   call returns a draft per field (status, value, verbatim quotes with passage ids, notes).
   Fields with no evidence at all skip the model. A failed call marks the batch's drafts with
   the error instead of raising.
6. **validate**: every quote must be a substring of its passage, the value must follow from
   the quotes by field type, "not found" needs at least three searches and no labelled facts,
   and the model call must have succeeded. A failure goes back to step 4 with its reason.
7. **report**: text and list events are applied to the reconcilable fields, each field gets
   its confidence tier, the cross-field checks run (pre-bid before due date, addenda dated
   before the due date, due date after issue, delivery after due date), the summary is written
   and checked for sentence count and invented numbers, and the JSON is written with the
   change log, validation tally, usage and any errors.

Every node is a span under the run's root span, with its input and output; every model call
records its prompt, response, tokens, cost and error. `uv run rfp trace <run_id>` renders the
span file; the web app's Runs page shows it as a waterfall.

## Where the brief's requirements live

| Requirement | Where |
|---|---|
| Parsing, cleaning, metadata, failure log | `ingestion/` |
| Chunking with structure and overlap | `search/chunking.py` |
| Embeddings, vector store with metadata | `search/embed.py`, `search/backend.py` |
| Incremental indexing | `search/manifest.py`, `search/indexer.py` |
| Hybrid retrieval, filters, rerank, query rewriting | `search/engine.py`, `search/query.py`, `config/synonyms.yaml` |
| Retrieval eval, two or more configurations | `eval/retrieval_gold.yaml`, `eval/retrieval.py`, `docs/eval/retrieval.md` |
| REST API, CLI, web UI | `api/`, `cli.py`, `main.py`, `web/` |
| Orchestrator, plan, routing extract vs ask | `agents/nodes/orchestrator.py`, `agents/graph.py` |
| Retrieval agent: rewriting, filters, rerank | `agents/nodes/retrieve.py`, `agents/evidence.py` |
| Extraction specialists, parallel | `agents/nodes/extract.py`, `config/fields.yaml` (groups) |
| Addendum reconciliation | `agents/nodes/reconcile.py`, `agents/addenda.py`, `agents/reconcile.py` |
| Validator, feedback loop with a retry limit | `agents/nodes/validate.py`, `agents/validate.py`, `agents/consistency.py` |
| Q&A and report | `agents/nodes/answer.py`, `agents/qa.py`, `agents/nodes/report.py`, `agents/assemble.py` |
| Shared state | `agents/state.py` |
| Structured agent messages | `agents/state.py`, `agents/outputs.py`, `agents/schema.py` |
| Guardrails: citations, not found | `agents/validate.py`, `agents/qa.py`, `agents/assemble.py` |
| Observability | `telemetry.py`, `agents/guarded.py`, `trace_render.py`, web Runs page |
| Error handling | `agents/guarded.py`, `agents/providers.py` (retry-after), `agents/ratelimit.py`, `ingestion/loader.py` |
| Keys and model names from config | `config.py`, `config/defaults.env`, `.env.example` |
| 20 fields with sources, confidence, notes | `config/fields.yaml`, `agents/confidence.py`, `agents/schema.py` |
| Extraction accuracy and calibration | `eval/extraction_gold.yaml`, `eval/extraction.py`, `docs/eval/extraction.md` |
| Bonus: web UI | `web/` (React): bids, record, search, ask, compare, runs and traces |
| Bonus: OCR for scans and image tables | `ingestion/ocr.py`, `ingestion/pdf.py` (`_ocr_scanned_pages`, `_layout_tables`) |
| Bonus: bid comparison agent | `agents/compare.py`, `rfp compare`, `GET /api/compare`, `docs/comparison.md` |
| Bonus: go / no-go | `agents/gonogo.py`, `config/company.yaml`, `rfp go-no-go`, `GET /api/bids/{id}/go-no-go` |
| Bonus: semantic cache, cost and latency per run | `agents/qa_cache.py`; `usage` on every record, answer and span |
| Bonus: Docker, CI with tests and retrieval eval | `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml` |
