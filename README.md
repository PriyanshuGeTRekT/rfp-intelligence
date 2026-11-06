# RFP Intelligence Platform

Hybrid search and multi-agent field extraction over public bid documents. Given a bid folder
(portal HTML page, RFP PDF, addenda, spec sheets, affidavits), it produces one cited JSON with
20 fields and answers free-form questions with citations, or says the answer is not in the
documents.

> Status: phases 1 to 3 done: ingestion, the fact layer, and hybrid search with incremental
> indexing, CLI and REST API. The retrieval evaluation and the agents are next.

## Quick start

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12 or newer. Run every command from the
repo root.

```bash
uv sync
cp .env.example .env        # then set ANTHROPIC_API_KEY
uv run rfp doctor           # shows config and the bid folders it can see
uv run pytest               # unit tests: no API key, no model downloads
uv run rfp index            # index every bid folder (first run downloads ~200 MB of models)
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
| `rfp extract <bid>` | Multi-agent extraction to one cited JSON | phase 5 |
| `rfp ask "<question>"` | Cited answer or "not found in documents" | phase 6 |
| `rfp eval retrieval` | Recall@k and MRR per retrieval configuration | phase 4 |
| `rfp serve` | REST API: `POST /index`, `GET /search` live; `POST /ask` in phase 6 | done |

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

The lists are fused with reciprocal rank fusion (k = 60; identifier matches weigh double),
then the top 30 are reranked with a cross-encoder (`Xenova/ms-marco-MiniLM-L-12-v2`, about
1.5 s for 30 chunks on CPU; the larger bge-reranker-v2-m3 took 8 s and is an evaluation row,
not the default). Fusion runs in Python so k, weights and each hit's rank in every list are
visible; each hit reports them in `signals`. Named configurations (`dense`, `sparse`,
`hybrid`, `hybrid_facts`, `hybrid_facts_rerank`) switch parts on and off for the evaluation.

### Incremental indexing

A manifest table (in the same SQLite file as the facts) records each file's content hash,
document id, pipeline version and embedding model. `rfp index` re-processes a file only when
one of those changes, deletes the index entries of files that disappeared, and leaves other
bids untouched. A file that fails to parse keeps its previous entry and is reported.

## Assumptions and limitations

- The embedded Qdrant store allows one process at a time; run the API or the CLI against
  it, not both, or point both at a Qdrant server with `RFP_QDRANT_URL`.
- Token counts are estimated at four characters per token, not with the model's tokenizer.

- US month-first numeric dates are assumed ("06/10/2024" is June 10). Time-zone handling
  covers US zones and UTC.

- Two-column prose layouts are not detected; side-by-side columns would be merged into rows.
  None of the bids seen so far use them.
- OCR is not run yet; pages that need it are reported.
- `.docx` and `.xlsx` attachments are skipped and reported.
- PDF table detection costs about 0.15 s per page, so a 62-page RFP parses in about 10 s.
  Indexing is incremental, so this cost is paid once per file.
