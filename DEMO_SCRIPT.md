# Demo video: workflow and script

This file is on GitHub only temporarily, so it can be read from another laptop. Delete it before
submitting. Target length: about 3½ minutes. The brief asks for 5-10 minutes; this shorter cut
is a deliberate choice. Every number below was checked against the repo on 2026-11-09.

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
     the models and indexes all three bids: about 5 minutes before the page loads. Section 6
     mentions it in words instead.
3. **Do not run a full extraction on camera.**
   - A Bid1 run takes about 11 minutes and around 70k tokens of the 120b daily quota.
   - Show the existing runs and their traces instead; the Re-run button is enough to point at.
4. **Rehearse Ask with a different question** (e.g. "Who is the procurement contact for
   Bid2?"), then click Clear.
   - Don't rehearse the Bid1 deadline question: on camera its first ask should be a live call,
     and its second a cache hit (section 5).

### Screen setup

- Browser at 1440×900 or larger, zoom 100%, **light theme** (the Settings dialog has
  System/Light/Dark).
- Close other tabs. Turn off OS notifications (Windows: Focus assist / Do not disturb).
- Have these open, in this order:
  1. The app at `/` (Bids).
  2. GitHub: the repo README, scrolled to Quick start.
  3. GitHub: `docs/architecture.md` (GitHub renders the Mermaid diagrams).
  4. GitHub: `docs/eval/retrieval.md`.
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

About 3½ minutes. The quoted paragraphs are what you say; the lines in *[italic brackets]* are
what you do on screen. Click first, then speak, and keep moving: every section is one or two
clicks.

### 0. Opening and the problem (0:00-0:30)

*[The Bids page is on screen.]*

> Hi, I'm Priyanshu, and this is RFP Intelligence. You give it a folder of public bid
> documents, and it extracts twenty fields for each bid. Every value is cited to a file, a page
> and an exact quote, with the addenda already applied. It also answers questions with checked
> citations, and it all runs on Groq's free tier.
>
> The tricky part is that bids change. In Bid1, Addendum 2 moves the due date from June 27 to
> July 9, so a system that only reads the RFP gets the deadline wrong.

### 1. Architecture (0:30-0:55)

*[Show `docs/architecture.md` on GitHub, scrolled to the Agent graph.]*

> Under the hood, ingestion parses PDFs, portal pages and scanned pages, and pulls out typed
> facts such as dates and amounts. Search combines dense embeddings, BM25 and those facts. On
> top, a LangGraph graph runs the agents: one reads the addenda, four retrieval-and-extraction
> batches run in parallel, and a validator checks every value in code and sends rejected fields
> back for another try.

### 2. Search (0:55-1:25)

*[Open the Search page and search `bid bond requirement`.]*

> Here's the search engine on its own. It routes this query to the bond facts and adds synonyms
> like "bid security." Each hit shows the file, the page, and how it ranked in each retrieval
> list.

*[Show `docs/eval/retrieval.md` on GitHub, the "All questions" table.]*

> On forty-two hand-labelled questions, combining these signals with a reranker raises MRR from
> 0.496 with dense search alone to 0.788. On Bid3, which the system had never seen, it goes from
> 0.233 to 0.683.

### 3. The extraction record (1:25-2:10)

*[Open Bid1 and click **Due Date**.]*

> This is Bid1's extraction record. The due date is July 9 at 2:00 PM Central, tier A, the
> highest confidence, and the change mark shows that Addendum 2 replaced June 27.

*[Click the citation chip `Add. 2 · p. 1`.]*

> Every citation opens the source PDF at the right page.

*[Go back and click **Bid Bond Requirement**.]*

> When it can't find something, it says so. The bid bond is "not found," tier NF-1, and instead
> of a guess, the notes list the searches it ran.

*[Open the **Validation** tab.]*

> Here, 14 fields passed, 5 were not found and 1 failed. Across the two provided bids, 37 of 40
> fields match an answer key I built by hand, and this Bid1 run cost about two cents.

### 4. The trace (2:10-2:35)

*[Go to Runs and open the Bid2 run ending in `2c640f`.]*

> Every run is traced. This Bid2 run made 15 model calls, and you can see the four batches
> running in parallel. This red bar is a call that was cut off at the output limit. The
> validator rejected it, and the retry right after it succeeded.

### 5. Q&A and go/no-go (2:35-3:10)

*[Open the Ask page and click "What is the submission deadline for Bid1 after all
addendums?"]*

> Questions work the same way. Every sentence carries a citation that's checked word for word
> against the documents. If I ask the same question again, the answer comes from the cache,
> with no model call.

*[Ask it again. Then ask "What price did the incumbent vendor charge last year?"]*

> And when the answer isn't in the documents, it says so instead of making one up.

*[Open Compare, select all three bids, set "Deadlines as of" to **2024-05-20**, then click
Compare.]*

> Comparison puts the bids side by side with a rule-based go/no-go. Bid3 is a no-go, because it
> needs a 10 percent bid security and our company profile allows 5.

### 6. Running it, and close (3:10-3:30)

*[Show the README's Quick start on GitHub.]*

> Everything runs with one command: `docker compose up`, or `python main.py`, which is what I'm
> using here. There are 420 Python tests and 24 web tests, and CI also re-runs the retrieval
> evaluation on every push. Thanks for watching.

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
