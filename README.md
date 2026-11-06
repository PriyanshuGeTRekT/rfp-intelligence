# RFP Intelligence Platform

Hybrid search and multi-agent field extraction over public bid documents. Given a bid folder
(portal HTML page, RFP PDF, addenda, spec sheets, affidavits), it produces one cited JSON with
20 fields and answers free-form questions with citations, or says the answer is not in the
documents.

> Status: phases 1 and 2 done. Ingestion (PDF, HTML and text parsing, tables, sections,
> content-based classification, failure report) and the fact layer (typed, labelled values
> with exact provenance, stored in SQLite). Search and agents are next.

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
| `rfp parse <bid> [--out f.json]` | Parse a bid folder; print type, title, date and issues per file | done |
| `rfp facts <bid> [--type deadline] [--kind datetime]` | Extract and store typed facts; print the matching ones | done |
| `rfp index <bid>` | Parse a bid folder and index it incrementally | phase 3 |
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

## Assumptions and limitations

- US month-first numeric dates are assumed ("06/10/2024" is June 10). Time-zone handling
  covers US zones and UTC.

- Two-column prose layouts are not detected; side-by-side columns would be merged into rows.
  None of the bids seen so far use them.
- OCR is not run yet; pages that need it are reported.
- `.docx` and `.xlsx` attachments are skipped and reported.
- PDF table detection costs about 0.15 s per page, so a 62-page RFP parses in about 10 s.
  Indexing is incremental, so this cost is paid once per file.
