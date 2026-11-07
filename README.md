# RFP Intelligence Platform

Hybrid search and multi-agent field extraction over public bid documents. Given a bid folder
(portal HTML page, RFP PDF, addenda, spec sheets, affidavits), it produces one cited JSON with
20 fields and answers free-form questions with citations, or says the answer is not in the
documents.

> Status: phases 1 to 5 done: ingestion, the fact layer, hybrid search with incremental
> indexing, the retrieval evaluation, and the multi-agent extraction graph with question
> answering, all tested end to end with a scripted model. Not yet done: a run against the
> live Claude API (no key during development), the per-bid JSON outputs, the Q&A log and the
> example trace that come from such a run, the architecture diagram and the demo.

## Quick start

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12 or newer. Run every command from the
repo root.

```bash
uv sync
cp .env.example .env        # then set ANTHROPIC_API_KEY
uv run rfp doctor           # shows config and the bid folders it can see
uv run pytest               # unit tests: no API key, no model downloads
uv run rfp index            # index every bid folder (first run downloads ~100 MB of models)
uv run rfp search "When is the proposal due after the addendums?" --bid Bid1
uv run pytest -m slow       # end-to-end retrieval tests with the real models
```

| Command | What it does | Status |
|---|---|---|
| `rfp doctor` | Show configuration, check data directory and keys | done |
| `rfp parse <bid> [--out f.json]` | Parse a bid folder; print type, title, date and issues per file | done |
| `rfp facts <bid> [--type deadline] [--kind datetime]` | Extract and store typed facts; print the matching ones | done |
| `rfp index [bid ...] [--force]` | Index bid folders incrementally; unchanged files are skipped | done |
| `rfp search "<query>" [--bid] [--doc-type] [--addendum] [--config] [--json]` | Hybrid search; file, pages, chunk text and per-list ranks per hit | done |
| `rfp extract <bid> [--out f.json] [--resume RUN_ID]` | Multi-agent extraction to `outputs/<bid>.json`; needs `ANTHROPIC_API_KEY` | done, untested live |
| `rfp ask "<question>" [--bid] [--k] [--config]` | Cited answer or "Not found in documents."; appends to `outputs/qa_log.jsonl` | done, untested live |
| `rfp eval retrieval [--config] [--check] [--update-baseline]` | Recall@k, MRR and latency per configuration; writes docs/eval/retrieval.md | done |
| `rfp serve` | REST API: `POST /index`, `GET /search`, `POST /ask` | done |

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

### Ingestion

One parser per format (PyMuPDF for PDF, BeautifulSoup for HTML, a plain reader for `.txt`
and `.md`) produces the same model: blocks (heading, paragraph, label-value, table) in reading
order, each with its page and section path, plus tables, page status and document metadata.

- **Visual rows.** Lines that overlap vertically are one row; segments far apart are joined
  with ` | `. This keeps form labels next to their values ("Solicitation Due | 27-JUN-2024
  14:00:00") and keeps borderless tables such as price schedules readable row by row.
- **Ruled tables.** PyMuPDF finds the grid; each cell is then read from word positions,
  because PyMuPDF's own cell text drops spaces and moves hyphens in some PDFs ("210-BLYZ"
  came out as "210BLYZ -"). Wrapped form cells that spill onto a new row are merged back.
- **Headers and footers.** Margin lines repeating on at least half the pages (digits masked,
  so "Page 3 of 40" matches "Page 4 of 40") are removed from the body and kept once in
  `running_text`, so an identifier printed only in a running header is not lost.
- **Headings and sections.** Bold, larger or all-caps short lines are headings; numbering sets
  the level ("2.1" is level 2). A heading repeated at the top of the next page is dropped.
- **Cleaning.** NFKC, zero-width and replacement characters removed, dot leaders and character
  rules dropped, hyphenated line breaks joined only where a lowercase word continues, wrapped
  email addresses and URLs rejoined.
- **Classification is by content.** `config/doc_types.yaml` holds weighted cues per type
  (addendum, rfp, specs, affidavit, form); head text counts double and the file name is a weak
  extra signal. Each document records the reason for its type.
- **Document date.** A date next to a cue such as "Issue Date" or "Publication" on the first
  pages, else the PDF creation date. "Due date" is not a cue: an addendum that moves the
  deadline must not take the new deadline as its own date.
- **Failures are reported, not fatal.** Unsupported files are skipped and listed, unreadable
  files are logged as errors, and pages without a text layer (scans, or text drawn as vector
  outlines like the W-9 in Bid1) are flagged as needing OCR.

### Fact layer

Dates, durations, money, percentages, identifiers, emails, phones, URLs and quantities are
parsed once per document, with no LLM, into typed facts with exact provenance. The extraction
agents will then choose among normalized candidates instead of reading raw text, and a field
with no candidate facts can be reported as not found with evidence.

- **Every fact is verbatim.** `raw` is the exact substring of its block at `[start, end)`, so
  any value shown can be checked against the source text.
- **Context decides meaning.** A value's context is the label to its left in a row ("PROPOSAL
  DUE | 06/10/2024"), its column header in a table, or its sentence. A row holding both an
  issue date and a due date gives each its own label.
- **Topic labels come from `config/fact_types.yaml`.** Each label has cues and exclusions:
  "deadline" excludes questions, pre-bid meetings, awards and line-item tables, so "Questions
  Deadline" and a product table's "Due Date" column are not deadline candidates. Generic
  portal labels ("Event date") borrow the field above; the section heading is the last resort.
- **Time zones are read as local time in the named zone.** "2:00 PM CST" on July 9 is Central
  Daylight Time, so it equals the portal's "3:00 PM EDT" (both 19:00 UTC) instead of looking
  an hour apart. The fact keeps a `tz_note` and the literal reading (`utc_literal`) so the
  interpretation is visible. Zone data comes from the `tzdata` package, which Windows needs.
- **Times pair with dates** right after them ("27-JUN-2024 14:00:00") or, failing that, with
  the nearest date in the same sentence ("at 2:00 PM CST via TEAMS ... on June 10, 2024").
  Dates without a year take the document's year and are flagged `year_inferred`.
- **Durations keep their anchor and count**: "within 45 days of Award", "two (2) successive one
  (1) year extensions" (one year, count two), "3 years following the date of delivery".
- **Identifiers** are uppercase letter-digit tokens of five or more characters, SKU-shaped
  tokens such as "379-BFNZ", and bare numbers only after a cue word ("Proposal 168884").
  Spans already taken by dates, phones, amounts and addresses are skipped.
- **Storage** is one SQLite table, replaced per document in a single transaction, so
  re-indexing a changed file never leaves stale facts behind.

### Chunking

Chunks follow the document's structure rather than a fixed window (targets: about 380
tokens, at most 480, about 60 tokens of overlap; bge-small reads 512 word pieces).

| Chunk type | What it holds | Why |
|---|---|---|
| `section` | Prose of one section, its heading first; small sibling sections are merged under their shared parent | A chunk never mixes unrelated sections, and short bold-headed sections are not slivers |
| `table` / `table_rows` | A whole table, or slices of rows with the header repeated | A SKU stays next to the column that names it |
| `qa_pair` | One addendum question with its answer | The unit an addendum question needs |
| `kv` | Consecutive portal fields under their heading | Portal pages are field lists |

Each chunk carries the exact block spans it covers, so the facts inside it become metadata:
`identifiers` (each id in written and compact form) and `fact_types` (deadline,
bond_insurance, ...). The embedded text starts with a short header (document title, type,
addendum number and date, section path), a cheap form of contextual retrieval. Form
scaffolding ("Type / Provide your answer below", signature blanks) is flagged
`is_boilerplate` and down-weighted, except in affidavits and forms, where the form is the
requirement.

### Retrieval

One Qdrant collection holds a dense vector (`BAAI/bge-small-en-v1.5`), a BM25 sparse vector
(`Qdrant/bm25`, with Qdrant's IDF modifier) and the chunk payload per point. It runs embedded
(a folder under `var/`, no server) or against a server via `RFP_QDRANT_URL`. Keeping dense,
sparse and metadata on one point makes adding, changing and deleting a document one
operation on one store.

A query builds up to five ranked lists, all under the same metadata filters (bid, document
type, addendum number):

1. `dense`: embedding similarity;
2. `bm25`: keywords, with procurement synonyms from `config/synonyms.yaml` added
   ("bid bond" also searches "bid security", "surety");
3. `identifiers`: chunks whose identifier list contains an id from the query, matched
   exactly (so "wd22tb4" finds "WD22TB4" without relying on how BM25 splits hyphens);
4. and 5. `facts_dense` and `facts_bm25`: the same searches restricted to chunks holding
   facts with the labels the question routes to, using the same cues as the facts ("When is
   it due?" routes to deadline, "When are questions due?" to questions only).

The lists are fused with reciprocal rank fusion (k = 60; identifier matches weigh double).
Fusion runs in Python so k, weights and each hit's rank in every list are visible; each hit
reports them in `signals`. Named configurations (`dense`, `sparse`, `hybrid`, `hybrid_facts`,
`hybrid_facts_rerank`) switch parts on and off. The default is `hybrid_facts`; reranking the
top 30 with `BAAI/bge-reranker-v2-m3-int8` is opt-in (`--config hybrid_facts_rerank`), for
the reasons measured below.

### Retrieval evaluation

`eval/retrieval_gold.yaml` holds 32 questions over both bids, 26 dev and 6 held out (written
after the system and never used for tuning). Each expected passage is a locator (file,
phrase it must contain, optional pages) rather than a chunk id, so labels survive
re-chunking, and a unit test fails if any locator matches no chunk. Each question is searched
within its own bid. `uv run rfp eval retrieval` writes [docs/eval/retrieval.md](docs/eval/retrieval.md)
with per-question ranks and misses.

| Config | Recall@1 | Recall@5 | Recall@10 | MRR@10 | Median latency |
|---|---|---|---|---|---|
| `dense` | 0.438 | 0.760 | 0.854 | 0.578 | 8 ms |
| `sparse` (BM25) | 0.438 | 0.729 | 0.875 | 0.563 | 7 ms |
| `hybrid` (dense + BM25 + identifiers, RRF) | 0.469 | 0.792 | 0.906 | 0.638 | 17 ms |
| `hybrid_facts` (default) | 0.635 | 0.854 | 0.896 | 0.755 | 26 ms |
| `hybrid_facts_rerank`, bge-reranker-v2-m3-int8 | 0.698 | 0.927 | 0.958 | 0.823 | 6.3 s |
| `hybrid_facts_rerank`, ms-marco-MiniLM-L-12-v2 | 0.542 | 0.802 | 0.906 | 0.690 | 1.4 s |

What the rows show:

- **Fusion beats either retriever alone**, and dense and BM25 fail on different questions:
  BM25 misses paraphrases ("more time to respond"), dense misses exact strings (the
  solicitation number).
- **Fact routing is the largest single gain**: MRR 0.638 to 0.755. Restricting extra lists to
  chunks holding deadline, bond or warranty facts lifts the right chunk above the boilerplate
  that mentions the same words. Bid2's warranty table goes from rank 8 to 1.
- **The small reranker hurts.** MiniLM, trained on short web passages, drops below no reranking
  on every metric; it buried the Bid2 warranty table again (rank 9). It was the planned
  default and was replaced because of this table.
- **The large reranker is the best on quality and on the held-out questions** (MRR 0.750 vs
  0.617), but costs about 6 s per query on CPU. Interactive search uses `hybrid_facts`; the
  extraction agents can pay for the reranker where a field's evidence matters most.
- **Known misses.** "Minority and women-owned business participation goal" is missed by every
  configuration: the goal sentence sits in a long chunk among a dozen other M/WBE form
  chunks. An M/WBE synonym group added after this analysis did not fix it and is kept as
  correct vocabulary. "Did the district agree to give vendors more time?" is found by dense
  alone (rank 2) but outvoted in fusion by chunks that appear lower in several lists.
- **Caveats.** 32 questions over two bids is small; one question moves Recall@5 by about
  0.03. The dev questions were written by the system's author, so they favour the
  vocabulary the system knows; the held-out rows are the more honest numbers.

`eval/baseline.json` stores the default configuration's Recall@5 and MRR. Before merging a
retrieval change, `uv run rfp eval retrieval --config hybrid_facts --check` fails if either
fell by more than 0.05. CI does not run it, because it needs the models and an index.

### Incremental indexing

A manifest table (in the same SQLite file as the facts) records each file's content hash,
document id, pipeline version and embedding model. `rfp index` re-processes a file only when
one of those changes, deletes the index entries of files that disappeared, and leaves other
bids untouched. A file that fails to parse keeps its previous entry and is reported.

### Agent building blocks (deterministic)

The parts of the agent system that need no LLM are built and tested first; the LangGraph
graph and prompts sit on top of them.

- **Fields** (`config/fields.yaml`): the 20 fields with their type, group (four extraction
  groups run in parallel, plus the generated summary), description for the prompt, fact
  labels and search queries. It is the one file to tune for a new kind of bid.
- **Evidence per field** (`agents/evidence.py`): hybrid search for the field's queries plus
  every chunk that holds a fact with the field's labels, so a typed candidate is never lost
  to ranking. Evidence text stays in a store keyed by chunk id; graph state carries ids only.
  The searches run are recorded: they are the proof behind "not found".
- **Addendum reconciliation** (`agents/reconcile.py`): addenda become ordered change events
  (replace, amend, confirm, clarify, add_requirement), applied in addendum order by a pure
  function. Date fields need no LLM: deadline and pre-bid facts inside an addendum become
  replace events. The portal page never overrides a document; it fills a missing time and
  corroborates. A difference nothing explains is a conflict, not a silent choice. On the real
  bids this yields Bid1's due date as July 9, 2024, 2:00 PM CDT (Addendum 2 replacing June 27,
  matching the portal's 3:00 PM EDT) and Bid2's as June 10, 2024, 2:00 PM EDT (date from the
  purchase-order RFP, time from the portal).
- **Validator** (`agents/validate.py`): every quote must be verbatim text from the passage it
  cites; the value must follow from the quotes by field type (identifiers as tokens, dates
  that parse to a quoted date, no number that the quotes do not contain, list items covered
  by quoted words); "not found" is accepted only after at least three searches and no
  labelled facts. A failure returns a reason for the retry.
- **Confidence** (`agents/confidence.py`): a decision table, not a formula. A: grounded and
  two documents agree or an addendum set it (0.95). B: grounded, one source (0.85). C:
  loosely grounded, OCR, or assembled from two sources (0.70). D: sources differ but an
  addendum explains it (0.60). E: unexplained conflict (0.40). NF-1: not found after a
  thorough search (0.80). NF-2: not found, search incomplete (0.50). The numbers label tiers;
  they are not probabilities, and the tiers will be checked against the gold fields.
- **LLM seam** (`agents/llm.py`): one `structured()` call returning a validated Pydantic
  object and usage (tokens, cache reads, latency, cost). `AnthropicLLM` uses `messages.parse`
  with the output schema, `output_config.effort`, a cached system prompt, retries on
  transient errors and explicit errors for refusal, truncation and schema mismatch.
  `ScriptedLLM` answers deterministically for tests.

### Agent graph

`agents/graph.py` is a LangGraph `StateGraph`. The brief's roles map onto it like this:

| Role | Where |
|---|---|
| Orchestrator / Planner | `plan` node (checks the index, lists documents, sets the group plan) and the two conditional edges that fan out and route retries |
| Ingestion | `plan` indexes the folder when the manifest has nothing for the bid |
| Retrieval / Search | the search engine, called as a tool by every extraction node |
| Extraction | four `extract_group` nodes run in parallel, one `Send` and one structured LLM call per field group; `extract_field` retries one field with the validator's reason and the slower reranked retrieval |
| Addendum Reconciliation | `reconcile`: date events from facts (no model), other events by one cached LLM call per addendum; the date fields are resolved here and never sent to the model |
| Validator / Critic | `validate`: deterministic checks; a failed field loops back, at most `max_retries` (2) times |
| Q&A / Report | `finalize` writes the JSON and the generated summary; `agents/qa.py` answers questions |

Design choices worth knowing:

- **Shared state is small.** State holds the plan, document list, events, drafts, validations,
  attempts, usage and a log; evidence text lives in a store keyed by chunk id, fetched on
  demand. Keys written by parallel branches have merge reducers, so no branch overwrites
  another.
- **Structured everywhere.** Every model response is a Pydantic schema (`agents/outputs.py`)
  requested through the API's structured outputs; every node update is a typed dict.
- **Resumable.** The graph compiles with a SQLite checkpointer keyed by run id;
  `rfp extract --resume RUN_ID` continues or returns a finished run.
- **Guardrails.** A found value with no verbatim quote never reaches the output; "not found"
  is accepted only after a thorough search with no labelled facts; a field the validator
  rejects on every attempt is reported as null with the reasons (tier X), never guessed.
- **Q&A.** Retrieve, answer with quoted citations, check every quote against its passage.
  Citations that are not verbatim are dropped, and an answer left without one becomes
  "Not found in documents." rather than an unsupported claim.
- **Cost.** Extraction is 4 group calls plus one per addendum (cached), one per retry and one
  summary; the system prompt is cached by the API. Usage, latency and an estimated cost are
  recorded per call, on the spans and in the result's `usage`.
- **Errors.** Timeouts and rate limits retry with backoff; refusals, truncated output and
  schema mismatches raise a clear error; one unreadable file never stops a run.

## Assumptions and limitations

- **No live run yet.** The agent graph and Q&A are tested end to end with a scripted model
  and the real search stack, but have not been run against the Claude API. The first live
  run will produce `outputs/<bid>.json`, `outputs/qa_log.jsonl` and `traces/<run_id>.jsonl`.
- **Windows path length.** This repo's current location is deep enough that the Anthropic
  SDK cannot be imported from `.venv`: one of its module files ends up past the 260-character
  path limit. Clone or move the repo to a short path (for example `C:\dev\rfp-intelligence`)
  or enable Windows long paths. Nothing outside the live Claude client imports the SDK, and
  Linux and CI are unaffected.
- `AnthropicLLM` has not yet been run against the live API (no key during development); its
  request shape is covered by tests with a fake client.

- The embedded Qdrant store allows one process at a time; run the API or the CLI against
  it, not both, or point both at a Qdrant server with `RFP_QDRANT_URL`.
- Token counts are estimated at four characters per token, not with the model's tokenizer.
- Models are cached in `~/.cache/rfp-intel/models` (override with `RFP_MODEL_CACHE_DIR`). A
  cache inside a deeply nested repo on Windows breaks the 260-character path limit for the
  reranker's files, which is why the cache is not under `var/`.

- US month-first numeric dates are assumed ("06/10/2024" is June 10). Time-zone handling
  covers US zones and UTC.

- Two-column prose layouts are not detected; side-by-side columns would be merged into rows.
  None of the bids seen so far use them.
- OCR is not run yet; pages that need it are reported.
- `.docx` and `.xlsx` attachments are skipped and reported.
- PDF table detection costs about 0.15 s per page, so a 62-page RFP parses in about 10 s.
  Indexing is incremental, so this cost is paid once per file.
