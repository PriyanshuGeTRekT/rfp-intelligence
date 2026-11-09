# Demo video: workflow and script (local only)

This file is git-ignored through `.git/info/exclude`, so it never reaches GitHub. Target length:
about 9 minutes (the brief asks for 5-10). Every number below was checked against the repo on
2026-11-09.

---

## Part 1. Workflow: before you press record

### The day before (or an hour before)

1. **Check the model works.** A live Q&A call is part of the demo.
   - `uv run rfp llm-check` should print OK.
   - If the Groq key is out of quota, swap in another key in `.env`.
   - Q&A uses `openai/gpt-oss-20b`, which costs very little.
2. **Build and start.**
   - `cd web && npm ci && npm run build && cd ..`
   - `uv run python main.py --serve`
   - Open http://localhost:8000. The index already exists; if not, run `uv run rfp index` once
     (a few minutes).
3. **Do not run a full extraction on camera.**
   - A Bid1 run takes about 11 minutes and around 70k tokens of the 120b daily quota.
   - Show the existing runs and their traces instead; the Re-run button is enough to point at.
4. **Rehearse Ask with a different question** (e.g. "Who is the procurement contact for
   Bid2?"), then click Clear.
   - Don't rehearse the Bid1 deadline question: on camera its first ask should be a live call,
     and its second a cache hit (section 6).

### Screen setup

- Browser at 1440×900 or larger, zoom 100%, **light theme** (the Settings dialog has
  System/Light/Dark). Switch to dark once, on the trace.
- Close other tabs. Turn off OS notifications (Windows: Focus assist / Do not disturb).
- Have these open, in this order:
  1. The app at `/` (Bids).
  2. GitHub: the repo README.
  3. GitHub: `docs/architecture.md` (GitHub renders the Mermaid diagrams).
  4. GitHub: `docs/eval/retrieval.md`.
  5. A terminal at the repo root, font size 16+, cleared.
  6. VS Code with the repo, `src/rfp_intel/agents/graph.py` open.
- **Recorder:**
  - OBS Studio (free), or the Windows Game Bar (Win+Alt+R) for the screen with system audio
    off and the microphone on.
  - Record at 1080p, 30 fps.
  - A webcam bubble is optional.
- **Mic:** a headset beats a laptop mic. Record 10 seconds and play it back first.

### Recording tips

- Record each section as its own clip; it's easier to redo one section than the whole video.
  Join the clips in Clipchamp (built into Windows 11) or DaVinci Resolve.
- Move the mouse slowly and pause one second after each click so the viewer sees the result.
- Say numbers as they are on screen. If something goes wrong live, say what happened. The
  system reports failures honestly, and so can you.

---

## Part 2. The script

Times are targets. **Show** is what's on screen; **Say** is what to say (loosely; use your own
words).

### 0. Opening (0:00-0:25)

**Show:** the Bids page.

**Say:** "This is RFP Intelligence. It takes a folder of public bid documents (portal pages,
RFPs, addenda, spec sheets, affidavits), indexes them in a hybrid search engine, and runs a
multi-agent system that extracts 20 fields per bid. Every value is cited to a file, a page and
a verbatim quote, with the addenda applied. It also answers questions with checked citations.
It runs on Groq's free tier."

### 1. The problem (0:25-1:00)

**Show:** `data/bids/Bid1` in the file explorer, then back to the app.

**Say:**
- "Bid1 is Dallas ISD's student and staff computing devices RFP, JA-207652: a BidNet portal
  page, a 62-page RFP and two addenda."
- "The hard part isn't reading one PDF. It's that Addendum 2 moves the due date from June 27 to
  July 9, the bond requirement is only referenced 'elsewhere', and the portal shows times in a
  different zone."
- "A system that answers from the RFP alone gets the deadline wrong."

### 2. Architecture (1:00-1:45)

**Show:** `docs/architecture.md` on GitHub, the System diagram, then the Agent graph.

**Say:**
- "Two layers run with no model at all."
  - "Ingestion: PyMuPDF, BeautifulSoup for the portal HTML, and RapidOCR for scanned pages.
    It detects the document type and addendum number, and extracts typed facts (dates with
    time zones, durations, money, identifiers, contacts) into SQLite."
  - "Structure-aware chunks go into Qdrant with a dense vector and a BM25 vector."
- "On top, a LangGraph state graph."
  - "The planner routes a bid to extraction or a question to Q&A."
  - "The reconciliation agent reads each addendum into change events."
  - "The fields are split into four batches that run in parallel. Each has a retrieval agent
    and an extraction agent."
  - "A validator checks every value in code. A rejected field goes back to retrieval with the
    reason, at most twice, and then the report agent writes the JSON."
- "The agents communicate through the graph's shared state and LangGraph's Send and Command.
  Every step is traced."

### 3. The search engine (1:45-3:00)

**Show:** the Search page. Type `bid bond requirement`.

**Say / point at:**
- "How it searched": "The query is routed to the bond-and-insurance facts and expanded with
  synonyms like bid security and surety."
- Each hit: "file, page, the passage, and its rank in every retrieval list: dense, BM25 and the
  fact lists, fused with reciprocal rank fusion."
- Search `JA-207652`: "Identifiers are matched exactly; embeddings are bad at those."
- Switch the configuration dropdown to dense-only, then back: "This is what fusion buys."

**Show:** `docs/eval/retrieval.md` on GitHub, the "All questions" table.

**Say:**
- "42 questions with hand-labelled passages, including 6 held out and 10 on an unseen bid."
- "MRR@10 goes from 0.496 dense-only, to 0.559 hybrid, 0.681 with fact routing, and 0.788
  with the bge-reranker. Recall@5 goes from 0.651 to 0.897."
- "On the unseen Bid3 alone, MRR goes from 0.233 to 0.683."
- "CI re-runs this evaluation on every push."

### 4. The extraction record (3:00-5:00)

**Show:** Bids page, then open Bid1.

**Say / do:**
- Header: "No-go: as of today the deadline has passed. I'll show the go/no-go properly
  later."
- Click **Due Date**. The evidence pane opens.
  - "2024-07-09 14:00 CDT, tier A."
  - "The change mark shows Addendum 2 replaced June 27 with July 9."
  - "The serif text is always a verbatim quote from a document."
  - Click a citation chip, such as `Add. 2 · p. 1`: "The PDF opens at that page."
  - Or click "Preview page 1 of Add. 2 here" to show the page inline.
  - The portal's "Closing Date: 07/09/2024 03:00 PM EDT" is the same instant as 2:00 PM CDT,
    and the record notes it.
- Press `j` a few times: "The keyboard moves through the fields."
- Click **Bid Bond Requirement**.
  - "Not found, tier NF-1. Not a guess: the notes say which queries were searched."
  - "The RFP only says bond requirements are 'elsewhere', and unstated isn't 'not required'."
- Explain the tiers briefly:
  - "A: two documents agree, or an addendum sets it."
  - "B: one verified source."
  - "C: OCR or a loose match."
  - "D and E: the sources conflict."
  - "NF-1: not found after a thorough search; NF-2: not found, but the search wasn't thorough
    enough."
  - "X: the validator rejected every attempt."
- Click **Product Specification** (tier X).
  - "This one failed, and the record says so."
  - "Bid1's spec list has ten device tiers. On the free tier a call may output 3,500 tokens
    including reasoning, and it got cut off. That limit is in the README."
- Click a document in the left rail: "Filter to the fields one document supports."
- **Changes** tab: "Every addendum change, old value to new, with its quote."
- **Validation** tab: "14 passed, 5 not found, 1 failed; 9 retries."
- Open **Bid2**, then **Product Specification**.
  - "Bid2's specs, including the 3-year extended warranty."
  - "That warranty was lost in an earlier run because the validator rejected numbers in product
    labels. I traced it to the code and fixed it."

**Say:**
- "On the provided bids, 37 of 40 fields match a hand-built answer key: Bid1 90%, Bid2 95%."
- "With the unseen Bid3, 50 of 60. Bid3 was never used for tuning."
- "Bid1 cost about 2 cents."

### 5. The agents, in the trace (5:00-6:15)

**Show:** Runs, then open the Bid2 run `…2c640f`. Switch the theme to dark here.

**Say / point at:**
- Summary line: "193 spans, 15 model calls, about 46 thousand tokens, roughly a cent."
- Timeline: "plan, ingest, reconcile, then the four retrieve-and-extract batches in parallel:
  blue is extraction, grey retrieval, green validation."
- The red bar, `extract · product_specs`: "This call was cut off at the output limit. The
  validator rejected it, and you can see the retry, `product_specs/2`, which succeeded."
- Click an extract span: "The full prompt, with id-headed passages and candidate facts, the
  model's JSON answer, tokens and cost."
- **Optional:** VS Code, `agents/graph.py` (about 200 lines): "The whole graph is wired here.
  The nodes are plain functions over a typed state, in `agents/nodes/`."

### 6. Q&A, with the cache (6:15-7:20)

**Show:** Ask page, scope "All bids".

**Do / say:**
1. Click "What is the submission deadline for Bid1 after all addendums?"
   - "Each sentence carries numbered citations. Every citation is checked to be a verbatim
     quote from a retrieved passage; a sentence without one is removed."
   - "It knows Addendum 2 moved the date."
2. Ask the **exact same question again**: "Answered from the semantic cache: no model call.
   The cache key includes the indexed files and the records, so re-indexing invalidates it."
3. Ask "What price did the incumbent vendor charge last year?": "Not found in documents. It
   doesn't invent an answer."

**Say:** "The Q&A log in the repo has 16 questions with their cited answers."

### 7. Compare and go / no-go (7:20-8:15)

**Show:** Compare. Select Bid1, Bid2 and Bid3, set "Deadlines as of" to **2024-05-20**, then
Compare.

**Say:**
- "Go/no-go is rules, not a model: repeatable and explainable. Each check is against a company
  profile in `config/company.yaml`."
- "As of May 20, 2024:"
  - "Bid1 is review: no manufacturer is named, and the bid bond isn't stated."
  - "Bid2 is review: the Maryland master contract isn't one we hold, and no bond is stated."
  - "Bid3 is no-go: it requires a 10% bid security, and our profile can post 5%."
- "Each verdict cites the value it read."
- Scroll to the side-by-side table: "All 20 fields per bid; a dot marks rows where the bids
  differ."
- "Ticking 'key differences' adds one cheap model call that writes a summary."

### 8. Engineering (8:15-8:50)

**Show:** the terminal, then the GitHub Actions tab.

**Say:**
- "Any new folder works with no code change: `python main.py --bid data/bids/Bid3`."
- "The provider is one setting: Groq, OpenAI, Ollama, Claude or any OpenAI-compatible API, with
  free-tier pacing built in."
- "418 Python tests and 24 web tests. CI runs them, type checks, lint, the web build, and the
  retrieval evaluation."
- "`docker compose up` runs everything in one container."
- "The README lists the assumptions and limitations: the free-tier quotas, one run per record,
  and the output limit."

### 9. Close (8:50-9:05)

**Say:** "So: a hybrid search engine measured on 42 labelled questions, a LangGraph agent system
whose every value is checked and cited, and a UI built so you can verify any value in two
clicks. Thanks for watching."

---

## Part 3. Questions to be ready for in the review

The brief says you must be able to explain every part. Short answers, all true of this repo:

- **Why LangGraph?** The flow needs:
  - a loop (validator back to retrieval);
  - a fan-out (field batches in parallel, with `Send`);
  - a router (extract vs ask).

  LangGraph has these natively, plus checkpoints (`--resume RUN_ID`) and tracing.
- **Chunking.**
  - Structure-aware: sections, tables and headers are kept together.
  - At most 480 tokens, about 60 tokens of overlap; bge-small reads 512 word pieces.
  - Each chunk carries file, pages, doc type, addendum number and section.
- **Embedding model.**
  - `BAAI/bge-small-en-v1.5`: small, fast on CPU, strong for its size.
  - Dense and BM25 cover each other's misses: dense misses exact strings, BM25 misses
    paraphrases.
- **Retrieval strategy.**
  - Dense + BM25 + exact identifiers, fused with RRF.
  - Plus fact routing: the query's intent picks typed-fact lists (deadline, bond, warranty).
  - Optional cross-encoder rerank (bge-reranker-v2-m3 int8).
  - The small MiniLM reranker made results worse, and that is measured in the README.
- **What does the validator check?**
  - Each quote is a verbatim substring of its passage.
  - The value parses as its type and follows from the quotes.
  - Numbers in the value appear in the quotes.
  - Then cross-field consistency.
- **Confidence.**
  - A decision table, not a formula: tiers A-E, NF-1, NF-2 and X, each a sentence you can say
    out loud.
  - The tiers are checked against the answer key: accuracy per tier.
- **Addenda.**
  - The reconciliation agent turns each addendum into change events (replace, amend,
    add_requirement, confirm, clarify) with quotes.
  - Later addenda override earlier ones; the change log is in the JSON.
- **Prompts.**
  - Constant system prompts (cacheable), with variable evidence in the user turn.
  - Passages carry `[id]` headers so citations can be checked by code.
  - The prompts name known traps ("a questions deadline is not the due date").
  - Evidence is fitted to a 3,800-token budget.
- **What would you do with more budget?**
  - A higher output limit (fixes the Bid1 spec cut-off).
  - Voting across 3 runs per field.
  - The paid 120b model for Bid3.
- **Where did it fail, honestly?**
  - Bid1 Product quantities: fixed after the run, untested live.
  - Bid1 product spec: the output limit.
  - Bid2 warranty certificate: a retrieval miss between near-duplicate chunks.
  - Bid1's signed-addenda requirement never reaches the prompt.
