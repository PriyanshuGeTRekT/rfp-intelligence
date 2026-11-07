# Demo script (about 8 minutes)

A walk-through for the recorded demo or a live session. Before starting: `uv sync`, a `.env`
with a working provider (`uv run rfp llm-check`), `uv run rfp index`, the web app built
(`cd web && npm ci && npm run build`), and `python main.py --serve` running.

## 1. The problem and the shape of the answer (1 min)

- Open `data/bids/Bid1`: a portal page, a 62-page RFP and two addenda. The due date in the RFP
  is wrong after Addendum 2; the bond requirement is "elsewhere"; the SKU table is split
  across columns in Bid2.
- Open `outputs/Bid1.json`: one record, 20 fields in the brief's names, each with value,
  sources (file, page, verbatim quote), confidence tier and notes; the addendum change log;
  the validation tally (passed, failed, not found).

## 2. Search engine (1.5 min)

Web app, Search page:

- `JA-207652`: the identifier is detected and matched exactly (the "Exact ID" list).
- `bid bond requirement`: routed to bond and insurance facts, expanded with "bid security,
  surety"; each hit shows file, page, section and its rank in every retrieval list.
- Filter to Bid2 and Specifications; switch the configuration to `dense` and back to show the
  difference fusion makes.
- Mention the evaluation table in the README: hybrid with fact routing MRR 0.755 vs 0.578
  dense-only, reranker 0.823.

## 3. Extraction (2.5 min)

Bids page, Bid1:

- Fields tab: Due Date `2024-07-09 14:00 CDT`, tier A, sources Addendum 2 and the portal;
  expand it: the quote, "Extended by Addendum 2 (original date: 2024-06-27 ...)", the portal's
  3:00 PM EDT recognised as the same instant.
- Bid Bond Requirement: open the notes, which say what was searched.
- Click a source chip: the PDF opens at the cited page.
- Addendum changes tab: the timeline per addendum.
- Validation tab: the tally, retries, the checks every value passed.
- Run extraction again: the job runs in the background (toast when done); show the Runs page.

## 4. Agents and the trace (1.5 min)

Runs page, open the latest trace:

- plan, ingest, reconcile (one call per addendum, cached), the parallel retrieve and extract
  branches, validate, the retry branches with rewritten queries, report.
- Click an extract span: the prompt with [id]-headed passages, the JSON answer, tokens, cost.
- Show a retry: the validator's reason in the prompt, and the rewrite call before it.
- Architecture diagram in `docs/architecture.md`; why LangGraph (README).

## 5. Q&A (1 min)

Ask page: the five questions from the brief.

- "What is the submission deadline for Bid1 after all addendums?" (addendum-aware retrieval)
- "Compare the warranty requirements of both bids." (searched per bid, cited per bid)
- A question the documents do not answer, e.g. "What is the incumbent vendor's price?":
  "Not found in documents."

## 6. Robustness and engineering (0.5 min)

- `python main.py --bid <any folder>`: an unseen bid needs no code change.
- Provider switch: `RFP_LLM_PROVIDER=groq|openai|ollama|claude ...`; free-tier pacing settings.
- Tests: `uv run pytest` (Python), `npm test` (web), CI runs both plus lint and type checks.
