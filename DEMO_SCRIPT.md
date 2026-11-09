# Demo video: workflow and script (local only)

This file is on GitHub only temporarily, so it can be read from another laptop. Delete it before
submitting. Target length: about 9 minutes (the brief asks for 5-10). Every number below was
checked against the repo on 2026-11-09.

---

## Part 1. Workflow: before you press record

### The day before (or an hour before)

1. **Check the model works.** A live Q&A call is part of the demo.
   - `uv run rfp llm-check` should print OK.
   - If the Groq key is out of quota, swap in another key in `.env`.
   - Q&A uses `openai/gpt-oss-20b`, which costs very little.
2. **Start with the local quick start, not Docker.**
   - Only if `web/dist` is missing or the web code changed: `cd web && npm ci && npm run build && cd ..`
   - `uv run python main.py --serve`. It starts in a few seconds: the index, records and traces
     already exist, so there is nothing to index (it only indexes bid folders that are new).
   - Open http://localhost:8000.
   - Don't use `docker compose up` for the recording. The first run builds the image, downloads
     the models and indexes all three bids: about 5 minutes before the page loads. Section 8
     explains it in words instead.
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

Times are targets. The quoted paragraphs are what you say; the lines in *[italic brackets]* are
what you do on screen. Read it naturally and pause after each click, so the viewer sees what
changed.

### 0. Opening (0:00-0:25)

*[The Bids page is on screen.]*

> Hi, I'm Priyanshu, and this is RFP Intelligence.
>
> You give it a folder of public bid documents: the portal page, the RFP, its addenda, spec
> sheets and affidavits. It indexes everything in a hybrid search engine, and then a team of
> agents extracts twenty fields for each bid. Every value comes with the file, the page and the
> exact quote it came from, with the addenda already applied. You can also ask it questions,
> and it answers with citations that are checked against the documents. The whole thing runs on
> Groq's free tier.

### 1. The problem (0:25-1:00)

*[Open `data/bids/Bid1` in the file explorer, then come back to the app.]*

> Let me start with why this is harder than it looks. Bid1 is the Dallas ISD request for
> student and staff computing devices, RFP JA-207652. The folder has the BidNet portal page, a
> sixty-two-page RFP and two addenda.
>
> Reading one PDF isn't the hard part. The hard part is that Addendum 2 moves the due date from
> June 27 to July 9, the bond requirement is only said to be covered "elsewhere," and the portal
> shows its times in a different time zone. So a system that only reads the RFP gets the
> deadline wrong.

### 2. Architecture (1:00-1:45)

*[Show `docs/architecture.md` on GitHub: the System diagram first, then the Agent graph.]*

> Here's how it's put together. There are two layers that don't use a language model at all.
>
> The first is ingestion. PyMuPDF reads the PDFs, BeautifulSoup reads the portal HTML, and
> RapidOCR handles scanned pages. It works out each document's type and addendum number, and it
> pulls out typed facts, such as dates with their time zones, durations, amounts of money,
> identifiers and contacts, and stores them in SQLite.
>
> The second is search. Each document is split into chunks that follow its structure, and every
> chunk goes into Qdrant with two vectors: a dense embedding, and a BM25 vector for keywords.
>
> On top of that sits a LangGraph state graph. A planner decides whether we're extracting a bid
> or answering a question. For an extraction, a reconciliation agent first reads each addendum
> and turns it into a list of changes. Then the fields are split into four batches that run in
> parallel, and each batch has its own retrieval agent and extraction agent. A validator checks
> every value in code. If it rejects a field, that field goes back to retrieval with the reason,
> at most twice, and at the end a report agent writes the JSON.
>
> The agents communicate through the graph's shared state, using LangGraph's Send and Command,
> and every step is traced.

### 3. The search engine (1:45-3:00)

*[Open the Search page and type `bid bond requirement`.]*

> Let's look at the search engine on its own. I'll search for "bid bond requirement."

*[Point at "How it searched".]*

> You can see that it routed the query to the bond and insurance facts, and expanded it with
> synonyms like "bid security" and "surety."

*[Point at one of the hits.]*

> Each result shows the file, the page and the passage, and where it ranked in each retrieval
> list: dense, BM25 and the fact lists. Those lists are merged with reciprocal rank fusion.

*[Search `JA-207652`.]*

> Identifiers like this RFP number are matched exactly, because embeddings are bad at that kind
> of string.

*[Switch the configuration dropdown to dense-only, then back.]*

> And if I switch to dense-only search, you can see what the fusion adds.

*[Show `docs/eval/retrieval.md` on GitHub, the "All questions" table.]*

> To measure all this, I built a set of forty-two questions with hand-labelled passages. Six of
> them are held out, and ten are on a bid the system had never seen.
>
> MRR at ten goes from 0.496 with dense search alone, to 0.559 with hybrid search, 0.681 with
> fact routing, and 0.788 with the bge reranker. Recall at five goes from 0.651 to 0.897. On the
> unseen Bid3 by itself, MRR goes from 0.233 to 0.683. CI re-runs this evaluation on every push.

### 4. The extraction record (3:00-5:00)

*[Go to the Bids page and open Bid1.]*

> Now for the extraction record. I'll open Bid1.
>
> The header says no-go, because as of today the deadline has passed. I'll come back to go/no-go
> properly in a minute.

*[Click **Due Date**. The evidence pane opens.]*

> When I click Due Date, the evidence pane opens. The value is July 9, 2024, at 2:00 PM Central
> time, and it's tier A, the highest confidence. This change mark shows that Addendum 2 replaced
> June 27 with July 9. Any text in this serif font is always a word-for-word quote from a
> document.

*[Click the citation chip `Add. 2 · p. 1`. Or click "Preview page 1 of Add. 2 here".]*

> If I click a citation, the PDF opens right at that page. I can also preview the page here,
> without leaving the record.
>
> Notice that the portal says "Closing Date: 07/09/2024 03:00 PM EDT." That's actually the same
> moment as 2:00 PM Central, and the record notes it.

*[Press `j` a few times.]*

> You can also move through the fields with the keyboard.

*[Click **Bid Bond Requirement**.]*

> Here's a field it didn't find: the bid bond requirement. It's tier NF-1, and that isn't a
> guess. The notes list exactly which searches it ran. The RFP only says that bond requirements
> are covered "elsewhere," and a requirement that isn't stated is not the same as one that isn't
> required.
>
> Let me quickly explain the tiers. A means two documents agree, or an addendum sets the value.
> B means one verified source. C means the value came from OCR or a looser match. D and E mean
> the sources conflict. NF-1 means not found after a thorough search, and NF-2 means not found,
> but the search wasn't thorough enough to be sure. Finally, X means the validator rejected
> every attempt.

*[Click **Product Specification** (tier X).]*

> This one is an X, and the record is upfront about it. Bid1's spec list has ten device tiers.
> On the free tier, a single call can output at most 3,500 tokens, including the model's
> reasoning, so this answer was cut off. That limit is documented in the README.

*[Click a document in the left rail.]*

> If I click a document on the left, the list shows only the fields that document supports.

*[Open the **Changes** tab.]*

> The Changes tab lists every change the addenda made, from the old value to the new one, each
> with its quote.

*[Open the **Validation** tab.]*

> And the Validation tab shows that 14 fields passed, 5 were not found and 1 failed, with 9
> retries along the way.

*[Open **Bid2**, then **Product Specification**.]*

> Here's Bid2's product specification, including the three-year extended warranty. In an earlier
> run, that warranty went missing, because the validator was rejecting numbers inside product
> names. I traced the problem to the code and fixed it.
>
> So, how accurate is it? On the two provided bids, 37 of 40 fields match an answer key I built
> by hand: 90 percent for Bid1 and 95 percent for Bid2. With the unseen Bid3 included, it's 50
> out of 60, and I never used Bid3 for tuning. The whole Bid1 run cost about two cents.

### 5. The agents, in the trace (5:00-6:15)

*[Go to Runs and open the Bid2 run ending in `2c640f`. Switch the theme to dark here.]*

> Now let me show you what the agents actually did, using the trace of this Bid2 run. I'll
> switch to the dark theme for this part.
>
> The summary line says the run had 193 spans and 15 model calls, used about 46 thousand
> tokens, and cost roughly a cent.
>
> On the timeline, you can see the plan, ingest and reconcile steps, and then the four
> retrieve-and-extract batches running side by side. Blue is extraction, grey is retrieval and
> green is validation.

*[Point at the red bar, `extract · product_specs`.]*

> This red bar is the product specs extraction. The call was cut off at the output limit, so
> the validator rejected it. Right after it, you can see the retry, `product_specs/2`, which
> succeeded.

*[Click an extract span.]*

> When I open a step, I can see the full prompt, with the passages labelled by ID and the
> candidate facts, followed by the model's JSON answer, its tokens and its cost.

*[Optional: switch to VS Code with `agents/graph.py` open.]*

> The whole graph is wired up in this one file, which is about two hundred lines. The nodes
> themselves are plain functions over a typed state, and they live in `agents/nodes`.

### 6. Q&A, with the cache (6:15-7:20)

*[Open the Ask page with the scope set to "All bids". Click "What is the submission deadline
for Bid1 after all addendums?"]*

> Now for questions. I'll ask: "What is the submission deadline for Bid1 after all addendums?"
>
> Each sentence in the answer has numbered citations, and every citation is checked to make
> sure it's a word-for-word quote from a passage the system actually retrieved. If a sentence
> has no valid citation, it's removed. And you can see that it knows Addendum 2 moved the date.

*[Ask the **exact same question** again.]*

> If I ask the exact same question again, the answer comes straight from the semantic cache,
> without a model call. The cache key includes the indexed files and the extraction records, so
> re-indexing a bid automatically invalidates it.

*[Ask "What price did the incumbent vendor charge last year?"]*

> Finally, let me ask something the documents don't cover: "What price did the incumbent vendor
> charge last year?" It says "Not found in documents." It doesn't make up an answer.
>
> The repo also includes a Q&A log with sixteen questions and their cited answers.

### 7. Compare and go / no-go (7:20-8:15)

*[Open Compare. Select Bid1, Bid2 and Bid3, set "Deadlines as of" to **2024-05-20**, then
click Compare.]*

> Next, comparison and go/no-go. I'll select all three bids and set the date to May 20, 2024, so
> that none of the deadlines have passed yet.
>
> Go/no-go is based on rules, not a model, so it's repeatable and easy to explain. Each check
> compares the bid against a company profile in `config/company.yaml`.
>
> As of May 20, Bid1 comes out as "review," because no manufacturer is named and the bid bond
> isn't stated. Bid2 is also "review": its Maryland master contract isn't one we hold, and it
> doesn't state a bond either. Bid3 is a no-go, because it requires a 10 percent bid security
> and our profile can only post 5 percent.
>
> Every verdict also cites the value it was based on.

*[Scroll down to the side-by-side table.]*

> Below that is a side-by-side table of all twenty fields for each bid, with a dot on every row
> where the bids differ. If I tick "key differences," it adds one cheap model call that writes a
> short summary.

### 8. Running it, and engineering (8:15-9:00)

*[Show the README's Docker section on GitHub.]*

> Finally, a word on how you run it. After setup, everything runs with a single command, as the
> brief asks.
>
> With Docker, that command is `docker compose up`. It builds the web app and the API into one
> image, indexes the bid folders the first time it starts, and serves both on port 8000. The
> index and the models are kept in a volume, so later starts are quick.

*[Show the README's Quick start.]*

> Without Docker, `main.py` has three modes: `--bid` extracts a bid to JSON, `--question`
> answers a question with citations, and `--serve` starts the API and the web app. What you've
> been watching is that local quick start, `python main.py --serve`. It started instantly
> because the bids were already indexed.

*[Switch to the terminal.]*

> Any new bid folder works without a code change, for example `python main.py --bid
> data/bids/Bid3`. Whichever mode you use, it first indexes any bid folder it hasn't seen
> before.
>
> The model provider is a single setting. It works with Groq, OpenAI, Ollama, Claude or any
> OpenAI-compatible API, and it paces its calls to stay within free-tier limits.

*[Show the GitHub Actions tab.]*

> There are 420 Python tests and 24 web tests. CI runs them along with type checks, linting,
> the web build and the retrieval evaluation.
>
> The README also lists my assumptions and the known limitations, such as the free-tier quotas,
> the fact that each record comes from a single run, and the output limit.

### 9. Close (9:00-9:15)

> So, to sum up: a hybrid search engine measured on forty-two labelled questions, a LangGraph
> agent system that checks and cites every value, and a UI designed so that you can verify any
> value in two clicks. Thanks for watching.

---

## Part 3. Questions to be ready for in the review

The brief says you must be able to explain every part. Each answer below is short enough to say
out loud, and all of them are true of this repo.

**How does someone run it?**

> After cloning, you run `uv sync`, copy `.env.example` to `.env` and add a provider key. From
> there it's one command: either `docker compose up`, or `python main.py` with `--serve`,
> `--bid` or `--question`. There's no separate indexing step. `serve` indexes any new bid folder
> before it starts, and a question, a search or an extraction indexes whichever folder it needs.
> I tested this on a fresh clone with an empty Docker volume: it indexed all three bids and then
> answered a question with the date from Addendum 2.

**Why LangGraph?**

> The flow needed three things: a loop, because the validator sends fields back to retrieval; a
> fan-out, because the field batches run in parallel; and a router, to choose between extraction
> and Q&A. LangGraph has all three built in, with Send for the fan-out. It also gives me
> checkpoints, so a run can be resumed with `--resume`, and it works well with tracing.

**How did you chunk the documents?**

> The chunking is structure-aware, so sections, tables and headers stay together. Each chunk is
> at most 480 tokens, with about 60 tokens of overlap, because bge-small reads at most 512 word
> pieces. Every chunk also carries its file, pages, document type, addendum number and section.

**Why that embedding model?**

> I used BAAI's bge-small-en-v1.5. It's small, fast on a CPU, and strong for its size. I paired
> it with BM25 because each one covers the other's blind spot: dense search misses exact
> strings, and BM25 misses paraphrases.

**What's the retrieval strategy?**

> Dense search, BM25 and exact identifier matching, merged with reciprocal rank fusion. On top
> of that there's fact routing, where the intent of the query decides which typed-fact lists to
> include, such as deadlines, bonds or warranties. There's also an optional cross-encoder
> reranker, bge-reranker-v2-m3 in int8. I tried the smaller MiniLM reranker as well, but it made
> the results worse, and that measurement is in the README.

**What does the validator check?**

> It checks that every quote is an exact substring of its passage, that the value parses as the
> right type and actually follows from the quotes, and that any numbers in the value appear in
> the quotes. After that, it runs consistency checks across fields.

**How is confidence decided?**

> With a decision table, not a formula. There are tiers A to E, NF-1, NF-2 and X, and each one
> is a rule you can say in one sentence. I also checked the tiers against the answer key, so
> there's an accuracy figure for each tier.

**How are addenda handled?**

> A reconciliation agent turns each addendum into change events, such as replace, amend, add a
> requirement, confirm or clarify, each with its quote. Later addenda override earlier ones, and
> the full change log is in the JSON.

**How did you design the prompts?**

> The system prompts are constant, so they can be cached, and the evidence goes in the user
> turn. Every passage has an ID header, which lets the code check the citations. The prompts
> also name known traps, for example that a deadline for questions isn't the due date. And the
> evidence is fitted to a budget of 3,800 tokens.

**What would you do with more budget?**

> First, a higher output limit, which would fix the cut-off on Bid1's product specification.
> After that, voting across three runs for each field, and the paid 120b model for Bid3.

**Where did it fail?**

> There are four places. For Bid1's product quantities, I fixed the cause after the run, but I
> haven't re-run it live. Bid1's product specification hit the output limit. Bid2's warranty
> certificate was a retrieval miss between two nearly identical chunks. And Bid1's requirement
> for signed addenda never makes it into the prompt.
