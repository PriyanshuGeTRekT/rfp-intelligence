# RFP Intelligence Platform

Hybrid search and multi-agent extraction over public bid documents. Given a bid folder
(portal HTML page, RFP PDF, addenda, spec sheets, affidavits), it produces one JSON record of
20 fields, every value cited to a file, page and verbatim quote, with addendum changes
applied. It also answers free-form questions with checked citations, or says the answer is not
in the documents. It works with any LLM provider and runs on a free tier.

## Quick start

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12 or newer; Node 20+ for the web app.
Run every command from the repo root.

```bash
uv sync
cp .env.example .env                 # pick a provider, set its key (see "LLM providers")
uv run rfp llm-check                 # one tiny call to confirm the model works
uv run python main.py --bid data/bids/Bid1  # extraction: writes outputs/Bid1.json
uv run python main.py --question "What is the submission deadline for Bid1 after all addendums?"
```

The web app and API:

```bash
cd web && npm ci && npm run build && cd ..
uv run python main.py --serve        # http://localhost:8000: web app, API under /api, docs at /docs
```

Or everything in one container: `docker compose up` (builds the web app, serves both on :8000).

`python main.py --bid PATH` accepts any folder of bid documents: a new, unseen bid needs no
code change. The folder name becomes the bid id; it is indexed incrementally on first use.

## What you can run

| Command | What it does |
|---|---|
| `python main.py --bid PATH` / `rfp extract <bid or path> [--resume RUN_ID]` | Multi-agent extraction to `outputs/<bid>.json`; prints the record and validation tally |
| `python main.py --question "..." [--bid-id Bid1]` / `rfp ask "..." [--bid]` | Cited answer or "Not found in documents."; appends to `outputs/qa_log.jsonl` |
| `rfp deliverables` | Regenerate every submitted output: a record per bid, the Q&A log and report, the extraction evaluation, the example trace |
| `rfp ask-batch eval/qa_questions.txt` | Answer a file of questions into the Q&A log (how `outputs/qa_log.jsonl` was made) |
| `python main.py --serve` / `rfp serve` | REST API and web app |
| `rfp index [bid ...] [--force]` | Index bid folders incrementally; unchanged files are skipped |
| `rfp search "<query>" [--bid] [--doc-type] [--addendum] [--config] [--json]` | Hybrid search; file, pages, chunk text and per-list ranks per hit |
| `rfp eval retrieval [--config] [--check]` | Recall@k, MRR and latency per configuration; writes docs/eval/retrieval.md |
| `rfp eval extraction` | Field accuracy and confidence calibration for `outputs/*.json`; writes docs/eval/extraction.md |
| `rfp eval evidence [--bid]` | Whether each expected value reaches the extraction prompt, with a scripted model (no API calls); writes docs/eval/evidence.md |
| `rfp compare Bid1 Bid2 [--no-summary] [--as-of DATE]` | Side-by-side report of several bids with their go / no-go and key differences; writes docs/comparison.md |
| `rfp go-no-go <bid> [--as-of DATE]` | Go, no-go or review against the company profile in `config/company.yaml` (no model call) |
| `rfp trace <run_id> [--out f.md]` | Render a run's spans as a tree, with full prompts and responses |
| `rfp qa-report` | Render `outputs/qa_log.jsonl` as `docs/qa_log.md` |
| `rfp parse <bid>` / `rfp facts <bid>` | Inspect parsing and the typed facts of a bid |
| `rfp doctor` / `rfp llm-check` | Show configuration; test the model connection |
| `rfp diagram` | Write the agent graph as Mermaid |
| `rfp-mcp [--http]` | MCP server with list_bids, search, facts and ask tools (`uv sync --extra mcp`) |

## Web app

A React single-page app (`web/`: React 18, TypeScript, Vite, TanStack Query, Tailwind, Radix
primitives), served by the API at `/` once built.

- **Bids**: every bid folder with its due date, documents by type, validation tally and last
  run; start an extraction (runs in the background, one at a time, with a notification when done).
- **Bid record**: the 20 fields with status, confidence tier (hover for what the tier means),
  and source chips that open the PDF at the cited page; expand a row for the verbatim quotes,
  notes and normalized values. Tabs for addendum changes (a timeline of replaced, added and
  clarified values), documents, and the validation report. Download the JSON.
- **Search**: the retrieval engine on its own, with bid, document-type and configuration
  filters held in the URL (shareable), query analysis (identifiers found, fact labels routed
  to, synonym expansions), highlighted passages and each hit's rank in every retrieval list.
- **Ask**: cited Q&A, scoped to one bid or all; each citation shows the quote and opens its
  source. The five questions from the brief are one click away.
- **Runs**: extraction jobs, and a trace viewer per run: a waterfall of every agent step with
  its prompt, output, tokens, cost and errors.
- **Compare**: pick two or more extracted bids for the side-by-side table, each bid's go / no-go,
  and (one model call, opt-in) the key differences. Each bid also has a **Go / no-go** tab
  listing every check with the value it read and its source.

Light and dark themes, keyboard search (Ctrl/Cmd+K), loading, empty and error states on every
view, responsive down to phone width. An API key, if the server requires one, is entered in
Settings. Development: `uv run rfp serve` in one terminal, `cd web && npm run dev` in another
(Vite proxies `/api` to port 8000). `npm test`, `npm run lint` and `npm run typecheck` run in CI.

## REST API

Interactive docs at `/docs`. The brief's example endpoints are served at the paths it names,
and everything is also under `/api`:

| Endpoint | Purpose |
|---|---|
| `POST /index` `{"path": "Bid1"}` | Index one bid folder (incremental) |
| `GET /search?q=...&bid_id=...&doc_type=...&top_k=5&config=...` | Hybrid search with citations |
| `POST /ask` `{"question": "...", "bid_id": null}` | Cited answer through the agent graph |
| `GET /api/bids`, `GET /api/bids/{id}` | Bids, their documents and latest result summary |
| `POST /api/bids/{id}/extract`, `GET /api/jobs/{job_id}` | Start an extraction run, poll it |
| `GET /api/bids/{id}/result` | The latest extraction record |
| `GET /api/bids/{id}/files/{path}` | A source document (HTML is served as plain text) |
| `GET /api/runs/{run_id}/trace` | Every span of a run |
| `GET /api/bids/{id}/go-no-go?as_of=` | Go / no-go against the company profile |
| `GET /api/compare?bids=Bid1&bids=Bid2&summary=false` | Side-by-side comparison; `summary=true` adds the written differences |
| `GET /health` | Version, provider, model |

`X-API-Key` is required on every route except `/health` when `RFP_API_KEY` is set; request
bodies are size-capped; paths from requests are resolved inside the data directory only.

## Output format

One file per bid, in the brief's shape, keyed by the brief's field names. Abridged from
[outputs/Bid1.json](outputs/Bid1.json) (one source per field shown):

```json
{
  "bid_id": "Bid1",
  "fields": {
    "Due Date": {
      "key": "due_date",
      "value": "2024-07-09 14:00 CDT",
      "status": "found",
      "sources": [{"file": "Addendum 2 RFP JA-207652 Student and Staff Computing Devices.pdf", "page": 1,
                   "quote": "The new due date for this RFP will be July 9, 2024 at 2:00 PM CST."}],
      "confidence": 0.95,
      "tier": "A",
      "normalized": {"date": "2024-07-09", "time": "14:00", "utc": "2024-07-09T19:00:00Z", "display": "July 9, 2024, 2:00 PM CDT"},
      "notes": "Extended by Addendum 2 (original date: 2024-06-27 14:00). 'CST' is written for a date when CDT applies; read as local time in America/Chicago (UTC-05:00). ... Matches the portal's 07/09/2024 03:00 PM EDT."
    },
    "Bid Bond Requirement": {
      "key": "bid_bond_requirement",
      "value": null,
      "status": "not_found",
      "sources": [],
      "confidence": 0.8,
      "tier": "NF-1",
      "notes": "Not found in documents. Bid bond requirement is referenced but not explicitly stated in the provided passages. Searched 4 queries (Bid Bond Requirement; bid bond required amount; bid security guarantee; performance bond insurance); 0 labelled facts; 2 passages reviewed."
    }
  },
  "addendum_changes": [{"field": "due_date", "operation": "replace", "addendum_number": 2, "doc_date": "2024-06-27",
                        "old_value": "27-JUN-2024 14:00:00", "new_value": "July 9, 2024 at 2:00 PM CST", "source": {"...": "..."}}],
  "validation": {"passed": 16, "failed": 0, "not_found": 4, "conflicts": 0, "fields": 20, "retries": 10,
                 "checks_failed": {}, "consistency_issues": []},
  "usage": {"calls": 28, "input_tokens": 55044, "output_tokens": 20436, "cost_usd": 0.019138},
  "errors": ["extract product_specs: LLMError: one call needs about 7757 tokens but the quota is 7500 per minute; ..."]
}
```

- `status` is `found`, `not_found` (null value, after a search the validator accepted as
  thorough), `conflict` (sources disagree and nothing explains it) or `failed` (the validator
  rejected every attempt, or the model could not produce an answer; the notes say which).
- Date fields use `YYYY-MM-DD HH:MM TZ`; the readable form is in `normalized.display`.
- `validation` starts with the brief's `passed` / `failed` / `not_found`; the other counts
  show retries, which checks failed, and cross-field consistency issues.
- `errors` lists anything that went wrong without stopping the run (a timed-out batch, an
  addendum the model could not read).

## Layout

```
main.py           one-command entry: --bid PATH | --question "..." | --serve
src/rfp_intel/
  config.py       settings from env, .env and config/defaults.env (no model names in code)
  ingestion/      PDF/HTML parsing, cleaning, doc-type classification, tables
  facts/          typed facts at ingest: dates with IANA zones, money, ids, contacts
  search/         Qdrant dense + BM25 hybrid, identifier field, rerank, manifest
  agents/         the agent system (below)
    graph.py        LangGraph wiring, run_extraction, run_question
    state.py        shared state and the messages agents exchange (Pydantic)
    services.py     what agents share: settings, search engine, model client, catalog
    nodes/          one module per agent: orchestrator, ingest, reconcile, retrieve,
                    extract, validate, report, answer
    guarded.py      model calls that return errors as data and record the trace
    ratelimit.py    client-side token pacing for per-minute quotas
    providers.py    any OpenAI-compatible API; llm.py: the interface and Claude client
    evidence.py, addenda.py, reconcile.py, validate.py, consistency.py, assemble.py,
    confidence.py, prompts.py, outputs.py, qa.py
  api/            FastAPI app, routes per resource, background extraction jobs
  eval/           retrieval, extraction and evidence-reach evaluation
  telemetry.py    OpenTelemetry: one JSONL span file per run, optional OTLP, PII redaction
web/              React web app
config/           fields, fact types, doc types, synonyms (YAML), model defaults, prices
data/bids/        the two provided bids
docs/             architecture, example trace, eval reports, demo script
outputs/          one JSON record per bid, and the Q&A log
tests/            unit and end-to-end tests (no API key, no model downloads)
```

## LLM providers

The agents call the model through one interface (`structured()`: system prompt, user prompt
and a Pydantic schema in; a validated object and token usage out). `RFP_LLM_PROVIDER` names
the provider; known names fill in the base URL and the key variable.

| `RFP_LLM_PROVIDER` | Key variable | Client |
|---|---|---|
| `anthropic` / `claude` (default) | `ANTHROPIC_API_KEY` | Anthropic SDK: native structured outputs, effort control, prompt caching |
| `openai`, `groq`, `xai` / `grok`, `gemini`, `mistral`, `together`, `openrouter`, `deepseek` | `OPENAI_API_KEY`, `GROQ_API_KEY`, `XAI_API_KEY`, ... | OpenAI-compatible chat API over HTTP, no SDK |
| `azure` | `AZURE_OPENAI_API_KEY`, plus deployment URL and api-version | same, with `api-key` auth |
| `ollama`, `lmstudio`, `vllm` | none | same, against a local server |
| any other name | `RFP_LLM_API_KEY` plus `RFP_LLM_BASE_URL` | same |

Model names live in `config/defaults.env` and are overridden in `.env` (`RFP_EXTRACT_MODEL`
for extraction and Q&A, `RFP_CHEAP_MODEL` for addendum reading, query rewriting and the
summary, `RFP_QA_MODEL` for question answering if it should differ); prices for cost tracking
are in `config/llm_prices.yaml`. The generic client asks
for `json_schema` output and falls back to `json_object` with the schema in the prompt; every
answer is validated with one repair round; 429 and 5xx responses wait as long as the server's
`retry-after` (or Groq's reset headers) says.

**Free tiers.** The submitted outputs were produced with Groq's free tier
(`openai/gpt-oss-120b` for extraction, `openai/gpt-oss-20b` for the cheap calls), which allows
8,000 tokens per minute per model. These settings make that work:

```
RFP_LLM_TOKENS_PER_MINUTE=7500   # the client paces itself instead of hitting 429s
RFP_LLM_MAX_CONCURRENCY=1        # one model call at a time
RFP_LLM_MAX_PROMPT_TOKENS=3800   # evidence is fitted to this budget per call
RFP_LLM_MAX_OUTPUT_TOKENS=3500   # reasoning models spend output tokens thinking
RFP_EXTRACT_BATCH_SIZE=3         # fields per extraction call
RFP_EXTRACT_EFFORT=low
```

A paid tier needs none of them: the defaults run four batches of five fields in parallel.
Free tiers also cap tokens per day (200k per model on Groq for these models); a call the
quota cannot serve fails at once with the provider's message, and the run records it.

## Results of the live runs

All outputs were produced on Groq's free tier on 2026-11-08, after the audit and the evidence
tuning described below. Exact provenance, because it matters for reading the numbers:

| Output | Run | Models |
|---|---|---|
| [outputs/Bid1.json](outputs/Bid1.json) | `20261108T061841Z-b06a6b` | `openai/gpt-oss-120b`, cheap calls `openai/gpt-oss-20b` |
| [outputs/Bid2.json](outputs/Bid2.json) | `20261108T061044Z-144948` | same |
| [outputs/Bid3.json](outputs/Bid3.json) | `20261108T063550Z-932750` | `openai/gpt-oss-20b` throughout (the 120b daily quota went to Bid1 and Bid2) |
| [outputs/qa_log.jsonl](outputs/qa_log.jsonl), [docs/qa_log.md](docs/qa_log.md) | after the extractions above | `openai/gpt-oss-20b` (`RFP_QA_MODEL`) |
| [docs/comparison.md](docs/comparison.md), [docs/trace_example.md](docs/trace_example.md) | the records above; the trace is Bid2's run | as above |

The extraction runs used the code at commit `ad51132`. Three fixes that the runs turned up
(listed under "Found in the re-runs") came after them and are covered by tests.

**Extraction accuracy** against `eval/extraction_gold.yaml` (hand-compiled expected values),
from [docs/eval/extraction.md](docs/eval/extraction.md): **36 of 40 fields (90%)**, Bid1 90%,
Bid2 90%. Under this gold the 2026-11-07 records scored 35 of 40. The first live runs scored
31 of 40, under an earlier and looser gold. Not-found tiers are reliable (NF-1 and NF-2: 7 of 7)
and tier B is 22 of 24, but tier A is 6 of 8: A means every quote verifies, not that a list is
complete. With the unseen Bid3 included, 49 of 60 (82%). Bid1 costs $0.018 (28 model calls,
70k tokens); Bid2 $0.010 (9 calls, 36k tokens). The four misses:

- Bid1 Additional Documentation leaves out the M/WBE forms and the W-9: the attachments table
  that lists them ranks 21st for the field after reranking (see "Tuned with evidence reach").
- Bid1 Payment Terms gives "within 10 days of receiving payment from the district", which is
  what the prime owes its M/WBE subcontractors; the RFP states no payment term for the district.
- Bid2 Additional Documentation now names the Mercury Affidavit and the Contract Affidavit, but
  leaves out the warranty certificate due on award.
- Bid2 Model_no gives the configuration code "CC7802" where the field asks for the marketed
  model (Latitude 5550). The previous run got this right with the same definition, so this is
  run-to-run variance of the model, not a retrieval gap: the evidence-reach check finds the
  model name in the prompt.

Compared with the 2026-11-07 records, the audit and the tuning fixed three fields. Bid1 Product
now names the Chromebook tiers with their quantities. Bid2 Term of Bid gives the solicitation's
90-day quote validity instead of the 30 days in the vendor's quote. Bid2's documents are named by
their titles instead of headings inside them. The audit also found that the gold had accepted
the old values because its rules only checked for words like "10 days" and "Affidavit"; it was
tightened to the hand-compiled values in BASELINE.md.

What the first runs showed, and what was changed because of it. `uv run rfp deliverables`
regenerates every output: about 60-75k tokens per extraction and 80k for the 16 questions.
That is more than one model's 200k daily quota on Groq's free tier, so spread it:
`RFP_QA_MODEL=openai/gpt-oss-20b` draws the questions from that model's quota.

- **Quotes failing on punctuation.** 11 of Bid1's fields were sent back on the first pass, most
  because a quote differed from the source only in separators (`Solicitation Number:` for
  `Solicitation Number |`) or used "..." to skip text. Quotes are now grounded word by word
  and replaced by the exact source text (`validate.ground`); Bid2's run, after the change, sent
  back 3 fields.
- **An addendum date filed under the wrong field.** The addendum reader tagged Addendum 2's
  new due date as a change to the contract term (Bid1's Term of Bid is wrong for this reason).
  Statements that are already date changes are now kept out of other fields.
- **Output truncation.** Reasoning models spend output tokens thinking; two batches hit the
  2,500-token cap. The free-tier settings now allow 3,500.
- **Q&A missing the decisive addendum.** "What is the deadline after all addendums?" first
  came back not found: retrieval returned Addendum 1 ("does not anticipate extending") and not
  Addendum 2. Q&A now always includes the chunks holding facts the question routes to, and the
  extracted record's reconciled value, and answers it correctly with Addendum 2 and the portal.
- **Quota handling.** A daily-quota 429 was retried four times before failing; a quota that
  does not reset within 90 s, or a request larger than the per-minute limit, now fails
  immediately with the provider's reason.
- **Citations attached to the wrong passage.** gpt-oss-20b often copies a quote correctly but
  gives the id of a neighbouring passage. A quote that is verbatim text of another passage the
  model was shown is now pointed at that passage instead of being rejected (extraction and Q&A).
- **Unverified absences reported as failures.** Bid2's contract term: the model said "not
  stated" on every attempt with four labelled facts in view (campaign-finance reporting
  periods), and the field ended as failed. It is now reported as not found at tier NF-2.
- **Uncited sentences in answers.** Q&A answers are now statements with their own citations;
  a sentence without a verified citation is removed.
- **Field definitions.** Model_no now asks for the marketed model, not configuration codes
  (Bid2 returned `CC7802`); Product Specification is a list, one item per specification. The
  bid-bond definition asked for "not specified" as a value while the
  validator (correctly) rejects a value no quote supports; definitions now ask for not_found
  with an explanation. Affidavits and forms included for the bidder to sign now count as
  required documents (Bid2's Additional Documentation was missed).

- **Evidence that never reached the model** (found with an offline check that runs the real
  retrieval and reports whether each expected value is in the extraction prompt). Bid1's W-9 is
  drawn as vector outlines with no text layer; OCR now reads such pages as well as scans. The
  per-field rerank pool grew from 20 to 30 candidates, and the Product, Term of Bid and Product
  Specification definitions now say what to do when the documents give tiers, no term, or long
  specification lists.

**Found in the audit** (2026-11-08), fixed in the code, with tests:

- **A field could reach the model with nothing to read.** The prompt budget took passages field
  by field, so when earlier fields' passages were long a later field got none, and it was
  reported as not found with "No passages were retrieved" although retrieval had found 10
  (Bid3's pre-bid meeting). Every field now gets its best passage first, cut short to an equal
  share of the budget if needed, before any field gets a second (`prompts.fit_passages`).
- **A form's name could not be cited.** The Maryland Contract Affidavit's title exists only in
  the PDF's metadata ("Attachment N – Contract Affidavit"), so the model named the form after a
  phrase inside it. Each passage now shows its document's title, and a quote may come from it.
  A test run of Bid2 showed gpt-oss-120b copying the header's label with the title
  (`document title "MERCURY AFFIDAVIT"`), so such quotes now ground as the title alone.
- **A vendor's terms read as the solicitation's.** Term of Bid now asks for the validity period
  the solicitation requires, not one printed in a vendor quote in the folder, and the extraction
  prompt lists this next to the other look-alike traps.

**Tuned with evidence reach** (2026-11-08). On the free tier an extraction prompt holds about
3,800 tokens for three fields, so each field gets three or four passages; whether the right one
is among them decides more than the model does. `uv run rfp eval evidence` runs the graph with
a scripted model and reports, for every gold rule, whether its expected text reached the prompt
([docs/eval/evidence.md](docs/eval/evidence.md)). It went from 47 to **50 of 54** fields:

- **Fact chunks are reranked with the rest.** Chunks holding a labelled fact used to go ahead
  of the reranked pool unconditionally. For Bid2's Term of Bid that put a "24 months" filing
  period from the Contract Affidavit first, a third of the field's budget. The fact itself still
  reaches the model as a candidate.
- **Signature templates are demoted.** Affidavits and forms are legal boilerplate whose contract
  language scores well with the cross-encoder; fields that do not ask for them subtract a margin
  (they stay in the ranking). Bid2's 90-day validity clause moved from fifth to second.
- **Lists that span documents are spread across them.** For Additional Documentation
  (`diverse: true` in `config/fields.yaml`), no document places a third chunk before every other
  document has placed its best two; seven Contract Affidavit clauses had pushed the Mercury
  Affidavit out. Applied to every field, this cost Bid2's warranty term, so it is per field.

Still missing from the prompt: Bid1's W-9 (its row in the attachments table ranks 21st after
reranking; blending in search rank would undo the reranker's gains elsewhere) and three Bid3
fields, which were left untuned so Bid3 stays an unseen test. Retrieval metrics are unchanged.

**Found in the re-runs** (2026-11-08), fixed after them, with tests:

- **A prompt could exceed the provider's per-minute limit.** The passage budget assumed 60
  tokens per candidate fact, but a candidate line carries up to 200 characters of context. One
  Bid1 product batch, with dozens of part-number candidates, came to 7,711 tokens against a
  7,500 limit and had to be retried in smaller batches. Candidates are now costed by their
  rendered text, and trimmed in turn across fields so that at least 1,000 tokens stay for
  passages. Model and part numbers share their identifier candidates, so the shared list is
  printed once instead of twice. Every extraction prompt now fits the cap, and evidence reach
  stays at 50 of 54.
- **Words run together by OCR failed the support check.** A value's words must appear in its
  quotes, but OCR can drop the spaces ("RFP2025-003ComputerEquipment"). A value word of five or
  more letters now also counts when it occurs inside the quotes' run-together letters. This
  would have kept Bid3's correct title.

**The unseen bid (Bid3).** Downloaded after the code was finished, run through it unchanged
except for one capability the run proved missing (OCR):

- Parsing: the 70-page RFP is a scan; with OCR it is typed `rfp` (it was `other` with no text),
  titled "Request for Proposals (RFP)", dated August 16, 2024 from its text, 198 sections. Both
  addenda are typed with their numbers and dates.
- Dates, with no model: the due date resolves to 2024-09-06 13:00 from the RFP (no zone is
  written, so none is assumed; noise such as a 1979 statute date is outranked); no pre-bid
  meeting.
- Addenda, by the model: Addendum 1 becomes a `replace` of the bid bond (10% bid security in
  cash, a certified cashier's check or a bid bond) and an `add_requirement` for its signed
  confirmation page; Addendum 2's approved substitute (HP Fortis 11" G10 Chromebook) is recorded
  as a `replace` of the product specification, where `amend` would be more accurate since the
  original model remains acceptable.
- Retrieval: Recall@5 0.80 and MRR 0.68 with reranking (table under "Retrieval evaluation").
- Extraction ([outputs/Bid3.json](outputs/Bid3.json), run `20261108T063550Z-932750`, on
  `openai/gpt-oss-20b` because the 120b daily quota went to Bid1 and Bid2): **13 of 20 (65%)**,
  with nothing tuned on it. That is the same score as the first run, with different misses.
  - Right: the number, due date, submission method, term (12 months), the 10% bid security from
    Addendum 1, delivery by October 31 (the first run read November 30), the substitute HP
    Chromebook from Addendum 2, model, manufacturer and agency.
  - Never reach the prompt: payment terms, the cooperative contracts and the substitute's SKU
    (see "Tuned with evidence reach").
  - Reported as not found: Product.
  - Rejected by the validator: three fields. Two of them were correct values it should have
    accepted: the title "Computer Equipment", quoted from OCR text that runs the words together
    ("RFP2025-003ComputerEquipment"), and the contact. The third failed because gpt-oss-20b
    twice returned output that did not match the schema. The validator now accepts run-together
    OCR words (see "Found in the re-runs").

  Most Bid3 values carry tier C, the cap for text read by OCR, so the record says where to look
  twice.

**Q&A** ([docs/qa_log.md](docs/qa_log.md)): 16 questions over the three bids, including the five
from the brief, answered on `openai/gpt-oss-20b` after the extractions above. 15 have cited
answers and one is a correct "Not found in documents" (the incumbent's price). Every sentence
carries its own verified quote; two citations across the 16 were dropped for failing
verification. When an answer draws on several bids, each statement names its bid ("In Bid3, a
bid bond is required ... Bid1 does not specify ..."). That rule was added after an earlier run
answered the bond question with Bid3's 10% as if it applied to every bid. Two answers are
incomplete. The bond answer does not mention Bid2, because none of Bid2's passages were
retrieved. Bid3's "when and how" answer gives the due date but not the submission method.

## Design decisions

### Ingestion

One parser per format (PyMuPDF for PDF, BeautifulSoup for HTML, python-docx for Word,
openpyxl for Excel, a plain reader for `.txt` and `.md`) produces the same model: blocks (heading, paragraph, label-value, table) in reading
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
- **Scanned pages are read by OCR.** A PDF page with almost no text layer whose content is an
  image (a scan, a fax, copier output) or vector outlines (text flattened into drawings, like
  Bid1's W-9) is rendered at 200 DPI and read by RapidOCR (ONNX models
  bundled with the package, CPU only, about 1.3 s per page). Each recognised line keeps its box,
  converted to PDF points, so headers, rows, headings and sections are found as for any PDF.
  Lines under 0.6 confidence are dropped. Chunks from OCR pages are flagged, and a value quoted
  from them is capped at confidence tier C. `RFP_OCR=false` turns it off. The unseen bid's
  70-page RFP is entirely scanned; without OCR it would be invisible.
- **Tables on scanned pages are found from layout.** With no ruling lines to detect, a table is a
  run of three or more rows split into segments whose starts line up in at least three shared
  columns; a one-segment row starting right of the first column is a wrapped cell and is merged
  into the row above. Two-column label / value rows are left to the row path, which keeps them
  together already.
- **Word and Excel attachments.** A `.docx` keeps body order, heading styles become sections,
  tables stay tables (all on page 1, since Word has no fixed pages). In an `.xlsx`, each
  worksheet is a "page" (the sheet name is in the page note and is the heading), its used range
  a table, formulas read as their computed values; price sheets and fill-in forms are indexed
  and citable like any PDF.
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

`eval/retrieval_gold.yaml` holds 42 questions: 32 over the two provided bids, 26 dev and 6
held out (written after the system and never used for tuning), and 10 about the unseen Bid3. Each expected passage is a locator (file,
phrase it must contain, optional pages) rather than a chunk id, so labels survive
re-chunking, and a unit test fails if any locator matches no chunk. Each question is searched
within its own bid. `uv run rfp eval retrieval` writes [docs/eval/retrieval.md](docs/eval/retrieval.md)
with per-question ranks and misses.

| Config | Recall@1 | Recall@5 | Recall@10 | MRR@10 | Median latency |
|---|---|---|---|---|---|
| `dense` | 0.438 | 0.760 | 0.854 | 0.579 | 4 ms |
| `sparse` (BM25) | 0.438 | 0.729 | 0.875 | 0.564 | 7 ms |
| `hybrid` (dense + BM25 + identifiers, RRF) | 0.500 | 0.792 | 0.906 | 0.645 | 11 ms |
| `hybrid_facts` (default) | 0.635 | 0.854 | 0.896 | 0.755 | 26 ms |
| `hybrid_facts_rerank`, bge-reranker-v2-m3-int8 | 0.698 | 0.927 | 0.958 | 0.821 | 5.0 s |
| `hybrid_facts_rerank`, ms-marco-MiniLM-L-12-v2 | 0.542 | 0.802 | 0.906 | 0.690 | 1.4 s |

What the rows show:

- **Fusion beats either retriever alone**, and dense and BM25 fail on different questions:
  BM25 misses paraphrases ("more time to respond"), dense misses exact strings (the
  solicitation number).
- **Fact routing is the largest single gain**: MRR 0.645 to 0.755. Restricting extra lists to
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

**An unseen bid.** To test generalization, a third bid was downloaded after the system was
finished: [Delano Union School District RFP 2025-003](https://duesd.org/domain/199), a
70-page RFP that is entirely a scan, plus two text addenda (one sets the bid security, one
approves a substitute product). It ran through the unchanged pipeline (`data/bids/Bid3`),
which is what showed OCR was needed. Ten questions about it were written afterwards (split
`unseen`); nothing was tuned on them:

| Config | Recall@1 | Recall@5 | Recall@10 | MRR@10 |
|---|---|---|---|---|
| `dense` | 0.200 | 0.300 | 0.400 | 0.233 |
| `sparse` (BM25) | 0.100 | 0.500 | 0.700 | 0.237 |
| `hybrid` | 0.200 | 0.400 | 0.600 | 0.287 |
| `hybrid_facts` (default) | 0.200 | 0.700 | 0.800 | 0.448 |
| `hybrid_facts_rerank` | 0.600 | 0.800 | 0.800 | 0.683 |

The ordering of configurations holds, and fact routing and reranking matter more here than
on the original bids: OCR text joins some words ("NOTICETOBIDDERS"), which hurts the dense
model most, while labelled facts survive. Both misses are vocabulary: "which purchasing
contracts can vendors propose under" did not reach the "NASPO, CMAS, WSCA, CALNET" sentence,
and "do bidders have to return anything for the addenda" did not reach "this form must be
signed and included with the RFP submittal". They are left unfixed on purpose; tuning on the
unseen bid would make it seen.

`eval/baseline.json` stores the default configuration's Recall@5 and MRR on the dev and
held-out questions (the unseen bid is reported, not gated). `uv run rfp eval retrieval --config
hybrid_facts --check` fails if either fell by more than 0.05. CI runs it in its own job: it
indexes the committed bids with the real embedding models (cached between runs), runs the
gate, and uploads the report as an artifact.

### Incremental indexing

A manifest table (in the same SQLite file as the facts) records each file's content hash,
document id, pipeline version and embedding model. `rfp index` re-processes a file only when
one of those changes, deletes the index entries of files that disappeared, and leaves other
bids untouched. A file that fails to parse keeps its previous entry and is reported.

### The multi-agent system

One LangGraph `StateGraph` serves both modes; the planner routes a goal to extraction or to
question answering. [docs/architecture.md](docs/architecture.md) has the diagrams.

```
START -> plan --(ask)-----> answer -> END
         plan --(extract)-> ingest -> reconcile --(dispatch)--> retrieve x N --> extract x N --> validate
         validate --(rejected fields, attempt <= max_retries)--> retrieve (with the reason) -> extract -> validate
         validate --(all settled)--> report -> END
```

| Agent (brief) | Module | Responsibility and output |
|---|---|---|
| Orchestrator / Planner | `nodes/orchestrator.py` | Writes the execution plan (`PlanStep`s), routes extract vs ask, splits fields into batches and fans them out in parallel, sends rejected fields back with the reason, decides when to report |
| Ingestion | `nodes/ingest.py` + `ingestion/` | Indexes the folder incrementally (new or changed files only) and lists documents with type, addendum number, date and pages |
| Retrieval / Search | `nodes/retrieve.py` + `evidence.py` | Plans queries per field (name, configured queries, and on a retry new queries a cheap model writes from the validator's reason), searches with the hybrid engine, adds a search filtered to the field's preferred document types, pulls every chunk holding a labelled fact, reranks the pool with the cross-encoder; returns ranked evidence with citations |
| Extraction (specialists) | `nodes/extract.py` | One structured call per batch of fields (the four groups are the specialists: identity and dates, commercial and legal, product and specs, parties and logistics); each value comes with verbatim quotes and passage ids |
| Addendum Reconciliation | `nodes/reconcile.py` + `addenda.py`, `reconcile.py` | Date changes from facts with no model; other changes by one model call per addendum over passages found by searching inside that addendum; folds the events in addendum order; resolves the date fields; produces the change log |
| Validator / Critic | `nodes/validate.py` + `validate.py`, `consistency.py` | Per field: cited, quotes verbatim, value supported by its quotes and well-formed for its type, "not found" justified by the search, model call succeeded. Across fields: dates in a consistent order. Failures go back for re-extraction with the reason |
| Q&A / Report | `nodes/answer.py` + `qa.py`; `nodes/report.py` + `assemble.py` | Answers questions with checked citations; assembles the record, applies text changes, scores confidence, writes the summary and the JSON |

**Why LangGraph.** The brief's flow is a graph with a loop (validator back to retrieval), a
fan-out (field batches in parallel) and a router (extract vs ask). LangGraph has these as
first-class parts: `Send` fans out with a per-branch payload, `Command(goto=Send(...))` hands
a task from the retrieval agent to the extraction agent, conditional edges express the retry
loop and the router, typed shared state with reducers makes parallel writes safe, and a
SQLite checkpointer makes a run resumable (`rfp extract --resume RUN_ID`). CrewAI and AutoGen
centre on conversational agents that decide their own next step, which makes the retry limit
and the cost of a run harder to bound; here the control flow is explicit and the agents are
plain functions over the state, testable without the framework or a model.

**Shared state.** `RunState` (in `agents/state.py`) holds the mode, plan, documents, change
events, resolved dates, evidence per field (chunk ids and the record of searches), drafts,
validations, attempts, retries, usage, a log, errors and the final output. Evidence text lives
in a store keyed by chunk id, so checkpoints and traces stay small. Messages between agents
are Pydantic models (`PlanStep`, `ExtractionTask`, the outputs in `agents/outputs.py`), and
every model response is requested with a JSON schema and validated.

**Prompt design** (`agents/prompts.py`).

- System prompts are constant per task (extraction, addendum events, query rewriting,
  summary, Q&A), so providers that cache prompts can reuse them; everything that varies goes
  in the user turn.
- Each states the task, the rules that make the output checkable by code (copy quotes
  verbatim, cite the passage id, return "not found" with a note rather than guess) and the
  traps of procurement documents (a questions deadline is not the due date, a vendor's credit
  terms are not the agency's payment terms, a bond-funded program is not a bid bond).
- Inputs are labelled blocks with an `[id]` header (file, pages, document type, addendum
  number), and candidate facts parsed at ingest are listed with their source sentence, so the
  model chooses among normalized values instead of re-reading raw text.
- A retry carries the validator's reason verbatim ("quote not found in its passage"), and new
  passages found with rewritten queries.
- A resolved date is given as a hint when the model is asked for the rest of a field (the
  pre-bid meeting's place and whether attendance is mandatory), so the model never re-decides
  a date the reconciler settled.
- Evidence is fitted to a token budget, taking each field's best passages in turn so no field
  is starved; a passage shared by several fields is paid for once.
- Field definitions are data (`config/fields.yaml`), written about procurement in general,
  never about these two bids.

**Guardrails.** A value without a verbatim quote never reaches the output. "Not found" is
accepted only after at least three searches and no labelled facts for the field, and the
note says what was searched. A field rejected on every attempt is reported as `failed` with
the reasons (tier X), never guessed; if every attempt said "not found" with the labelled facts
in view, it is reported as not found at tier NF-2 (unverified), with that explanation. Q&A
answers in statements, each with its own citations: a citation that does not reproduce its
passage is dropped, a statement left without one is removed, and an answer with no statement
left becomes "Not found in documents."

**Errors.** No model failure stops a run. `GuardedLLM` turns a timeout, rate limit (after
waiting as the server asks), invalid JSON after the repair round, refusal or truncation into
data: an extraction draft carries the error and the validator sends it back for a retry; an
addendum the model cannot read is skipped and listed in `errors`; a failed summary is marked
failed; a Q&A answer says it could not answer. Empty retrieval skips the model call and is
judged by the not-found rules. Parallel branches share one embedded index safely (its client
calls are serialized).

**Confidence** (`agents/confidence.py`) is a decision table, not a formula. A: grounded and
two documents agree or an addendum set it (0.95). B: grounded, one source (0.85). C: loosely
grounded, OCR, or assembled from two sources (0.70). D: sources differ but an addendum
explains it (0.60). E: unexplained conflict, or a failed cross-field check (0.40). NF-1: not
found after a thorough search (0.80). NF-2: not found, search incomplete (0.50). X: rejected
(0.20). The numbers label tiers; `rfp eval extraction` reports accuracy per tier against the
gold fields so a miscalibrated tier shows.

**Cost.** For a paid tier, extraction is four batch calls, one per addendum (cached by
document), one summary, and one call plus one cheap rewrite per retry. Usage, latency and an
estimated cost are recorded per call, on the spans and in the record's `usage`.

### Beyond extraction: comparison, go / no-go, semantic cache

- **Bid comparison agent** (`agents/compare.py`). The side-by-side table is built from the
  extraction records alone, so every cell is an extracted value with its tier and first
  citation. One call to the cheap model writes the key differences from that table; a
  difference naming a field that is not in the table is dropped, and a failed call leaves the
  table and recommendations intact. Example: [docs/comparison.md](docs/comparison.md).
- **Go / no-go** (`agents/gonogo.py`, profile in `config/company.yaml`). Eight checks: deadline
  vs preparation time, manufacturer authorization, products we sell, installation services,
  bid bond vs the bond we can post, delivery lead time, contract vehicles we hold, documents we
  cannot supply. Each returns pass, fail or review with the value it read and that value's
  citation. Any fail is a no-go; otherwise anything undecidable (a field not found, wording a
  rule cannot read) is a review. These are rules, not a model call: a bid decision should be
  repeatable and explainable, and it costs nothing. `--as-of` judges deadlines on another date.
- **Semantic cache for questions** (`agents/qa_cache.py`). A question whose embedding (the
  search engine's bge-small) has cosine similarity of at least `RFP_QA_CACHE_THRESHOLD` (0.95)
  with an earlier one in the same scope gets the earlier answer without a model call. Numbers
  and identifiers must match exactly, because "bid bond for Bid1" and "for Bid2" are
  near-identical sentences to an embedding model. An entry is reused only under the same
  fingerprint: the indexed files of the bids in scope, their extraction records, the answering
  model and a cache version; re-indexing or re-extracting makes old answers miss. A hit is
  marked in the answer (`cached_from`, `cache_similarity`) and in the trace (`qa.cache` span).
  `RFP_QA_CACHE_THRESHOLD=0` turns it off.

## Observability

Every run writes its spans to `traces/<run_id>.jsonl`: one span per agent step with its
input, output, timing and, for model calls, the model, prompt, response, tokens, cost and any
error (prompts and outputs are clipped to `RFP_TRACE_MAX_CHARS`). Emails and phone numbers are
masked before export unless `RFP_TRACE_REDACT_PII=false`. The web app's Runs page shows a
trace as a waterfall; `rfp trace <run_id>` renders it as text. The API server writes one file
per run too. To browse traces in Arize Phoenix or Langfuse, install the `obs` extra and set
`OTEL_EXPORTER_OTLP_ENDPOINT` (for Phoenix: `http://localhost:6006/v1/traces`).

## Docker

```bash
docker compose up                          # web app and API on :8000
docker compose run --rm app extract Bid1   # any CLI command runs in the same image
docker compose --profile qdrant up         # plus a Qdrant server; set RFP_QDRANT_URL=http://qdrant:6333
```

The image builds the web app in a Node stage, installs Python dependencies from the lock
file, and keeps models, the index and traces in the `/data` volume. Bid folders are mounted
read-only from `./data/bids`; records are written to `./outputs`.

## MCP server

`uv sync --extra mcp && uv run rfp-mcp` starts a Model Context Protocol server over stdio
with four tools: `list_bids`, `search`, `facts` and `ask` (which runs the agent graph).

## Documents

- [docs/architecture.md](docs/architecture.md): system and agent-graph diagrams, a run step
  by step, and where each requirement of the brief lives.
- [docs/eval/retrieval.md](docs/eval/retrieval.md), [docs/eval/extraction.md](docs/eval/extraction.md)
  and [docs/eval/evidence.md](docs/eval/evidence.md): the evaluations.
- [outputs/](outputs/): one JSON record per bid and `qa_log.jsonl`, the cited Q&A log
  ([docs/qa_log.md](docs/qa_log.md) is the readable version, from `rfp qa-report`).
- [docs/trace_example.md](docs/trace_example.md): one full extraction run's trace, rendered,
  with complete prompts and responses for one call of each kind; the raw span file is
  [docs/trace_example.jsonl](docs/trace_example.jsonl).
- [docs/demo.md](docs/demo.md): the demo script.

## Assumptions and limitations

- **Provider used for the submitted outputs.** Groq's free tier with `openai/gpt-oss-120b` and
  `openai/gpt-oss-20b` (see "Results of the live runs" for which output came from which run).
  The Anthropic client is covered by tests with a fake client but has not been run against the
  live API.
- **Free-tier daily quotas.** Groq allows 200k tokens per day per model on these models; one
  extraction uses about 60-75k, so three bids and the Q&A log need two models or two days.
  `qwen/qwen3.8-27b` was tried as a substitute and rejected: it often returned values without
  the required quotes.
- **One run per bid.** Each record comes from a single run, and model output varies between
  runs: Bid2's Model_no was right in one run and wrong in the next with the same prompt. A
  bid's score can therefore move by a field or two from run to run. The three fixes under
  "Found in the re-runs" came after the runs that produced `outputs/`.
- **Q&A checks that each sentence is cited, not that it is entailed.** Every sentence must
  carry a citation that reproduces passage text, or it is removed; whether the sentence says
  exactly what its quote says is left to the prompt's rules.
- **Windows path length.** From a deeply nested folder the Anthropic SDK cannot be imported
  (one of its module paths passes the 260-character limit). Use a short path or enable long
  paths; the OpenAI-compatible client needs no SDK, and Linux, Docker and CI are unaffected.
- The embedded Qdrant store allows one process at a time: run the API or the CLI against it,
  not both, or point both at a Qdrant server with `RFP_QDRANT_URL`.
- Extraction jobs started from the API run one at a time in the server process; the job list
  is kept in SQLite, and a job cut off by a restart is marked failed rather than resumed (the
  CLI's `--resume RUN_ID` resumes a run from its checkpoint).
- Token counts for budgets and pacing are estimated at 3.5 characters per token, high on
  purpose: tokenizers differ, and an underestimate turns into a provider's 413 or 429.
- US month-first numeric dates are assumed ("06/10/2024" is June 10). Time-zone handling covers
  US zones and UTC.
- Two-column prose layouts are not detected. OCR text can join words that the scan sets
  close together ("NOTICETOBIDDERS"), which costs keyword search a little on those pages.
  Other attachment types (`.pptx`, images, archives) are skipped and reported.
- Models are cached in `~/.cache/rfp-intel/models` (override with `RFP_MODEL_CACHE_DIR`).
