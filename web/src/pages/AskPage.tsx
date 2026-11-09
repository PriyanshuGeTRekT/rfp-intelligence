import { ArrowUp, CircleSlash, Quote, Trash2 } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { Cite, PageHeader, QuoteBlock } from "../components/domain";
import { InlineAlert } from "../components/ui/feedback";
import { Button, Panel, Select, Skeleton, Tag } from "../components/ui/primitives";
import { cn } from "../lib/cn";
import { labelFromFile } from "../lib/docLabels";
import { formatCost, formatDuration } from "../lib/format";
import { useAsk, useBids } from "../lib/queries";
import { KEYS, readStored, writeStored } from "../lib/storage";
import type { QAResult } from "../lib/types";

const SUGGESTED = [
  "What is the submission deadline for Bid1 after all addendums?",
  "Which affidavits are required for the Dell laptop bid?",
  "Compare the warranty requirements of both bids.",
  "Is a bid bond required, and if so, how much?",
  "What changed in Addendum 2 compared to the original RFP?",
];

interface Exchange {
  id: string;
  question: string;
  scope: string;
  result?: QAResult;
  error?: string;
}

function Provenance({ result }: { result: QAResult }) {
  const parts = [
    `${result.passages_reviewed} passages`,
    result.scope.join(", "),
    result.config,
    result.model,
    result.usage.latency_ms !== undefined ? formatDuration(result.usage.latency_ms) : null,
    result.cached_from
      ? `answered from the cache (same as “${result.cached_from}”, similarity ${result.cache_similarity?.toFixed(2)}), no model call`
      : formatCost(result.usage.cost_usd),
  ].filter(Boolean);
  return (
    <p className="num mt-3 font-mono text-2xs text-faint">
      {parts.join(" · ")}
      {result.dropped_citations > 0 && <span className="text-warn"> · {result.dropped_citations} unverifiable citations removed</span>}
      {result.removed_statements ? <span className="text-warn"> · {result.removed_statements} unsupported sentences removed</span> : null}
    </p>
  );
}

function Answer({ id, result }: { id: string; result: QAResult }) {
  return (
    <div>
      {result.found ? (
        <p className="text-md text-ink">
          {result.statements?.length
            ? result.statements.map((s, i) => (
                <span key={i}>
                  {s.text}
                  {s.citations.map((c) => (
                    <sup key={c} className="num ml-0.5 font-mono text-[10px] font-medium">
                      <a href={`#${id}-cite-${c + 1}`} className="text-accent no-underline hover:underline">
                        [{c + 1}]
                      </a>
                    </sup>
                  ))}{" "}
                </span>
              ))
            : result.answer}
        </p>
      ) : result.error ? (
        <InlineAlert tone="bad" title="The model call failed">
          {result.error}
        </InlineAlert>
      ) : (
        <p className="flex items-start gap-2 text-sm text-muted">
          <CircleSlash className="mt-0.5 size-4 shrink-0 text-faint" aria-hidden />
          <span>
            <span className="font-medium text-ink">Not found in the documents.</span> The passages reviewed do not answer this.
          </span>
        </p>
      )}
      {result.citations.length > 0 && (
        <ol className="mt-3 divide-y divide-line border-t border-line">
          {result.citations.map((c, i) => (
            <li key={`${c.evidence_id}-${i}`} id={`${id}-cite-${i + 1}`} className="grid grid-cols-[24px_1fr] gap-2.5 py-2.5">
              <span className="num mt-0.5 inline-flex size-5 items-center justify-center rounded-sm border border-control font-mono text-2xs font-medium text-muted" aria-hidden>
                {i + 1}
              </span>
              <QuoteBlock
                quote={c.quote}
                file={c.file}
                cite={
                  <span className="flex items-center gap-1.5">
                    <Tag className="font-mono">{c.bid_id}</Tag>
                    <Cite bidId={c.bid_id} doc={labelFromFile(c.file)} page={c.page} />
                  </span>
                }
              />
            </li>
          ))}
        </ol>
      )}
      <Provenance result={result} />
    </div>
  );
}

export function AskPage() {
  const bids = useBids();
  const ask = useAsk();
  const [history, setHistory] = useState<Exchange[]>(() =>
    readStored<Exchange[]>(KEYS.conversation, []).map((x) => (x.result || x.error ? x : { ...x, error: "The page was closed before the answer arrived." })),
  );
  const [question, setQuestion] = useState("");
  const [scope, setScope] = useState("");
  const [showSuggested, setShowSuggested] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    writeStored(KEYS.conversation, history.slice(-30));
  }, [history]);
  // A block body on purpose: newer browsers return a Promise from scrollIntoView, and an
  // effect must return nothing or a cleanup function.
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [history.length, ask.isPending]);

  const send = (text: string) => {
    const q = text.trim();
    if (q.length < 3 || ask.isPending) return;
    // randomUUID exists only in secure contexts (https or localhost); a LAN address is neither.
    const id = typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
    setHistory((h) => [...h, { id, question: q, scope: scope || "All bids" }]);
    setQuestion("");
    setShowSuggested(false);
    ask.mutate(
      { question: q, bidId: scope || undefined },
      {
        onSuccess: (result) => setHistory((h) => h.map((x) => (x.id === id ? { ...x, result } : x))),
        onError: (error) => setHistory((h) => h.map((x) => (x.id === id ? { ...x, error: (error as Error).message } : x))),
      },
    );
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    send(question);
  };
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(question);
    } else if (e.key === "ArrowUp" && !question && history.length) {
      e.preventDefault();
      setQuestion(history[history.length - 1]?.question ?? "");
    }
  };

  const suggestions = history.length === 0 || showSuggested;

  return (
    <div className="mx-auto max-w-[840px]">
      <PageHeader
        title="Ask"
        description="Answers come only from the documents. Every citation is checked word for word against its passage; an answer without a valid citation is reported as not found."
        actions={
          history.length > 0 && (
            <>
              <Button size="sm" icon={<Quote className="size-3.5" aria-hidden />} onClick={() => setShowSuggested((s) => !s)} aria-pressed={showSuggested}>
                Questions from the brief
              </Button>
              <Button variant="ghost" size="sm" icon={<Trash2 className="size-3.5" aria-hidden />} onClick={() => setHistory([])}>
                Clear
              </Button>
            </>
          )
        }
      />

      <div className="space-y-7" aria-live="polite">
        {suggestions && (
          <Panel className="p-4">
            <p className="caps mb-2">Questions from the brief</p>
            <div className="grid gap-1">
              {SUGGESTED.map((s) => (
                <button key={s} type="button" onClick={() => send(s)} className="flex items-center gap-2 rounded px-2 py-1.5 text-left text-sm text-ink hover:bg-subtle">
                  <Quote className="size-3.5 shrink-0 text-faint" aria-hidden />
                  {s}
                </button>
              ))}
            </div>
          </Panel>
        )}

        {history.map((x) => (
          <article key={x.id}>
            <div className="flex justify-end">
              <div className="max-w-[85%] rounded border border-line bg-subtle px-3 py-2 text-sm text-ink">
                {x.question}
                <span className="mt-0.5 block text-right text-2xs text-faint">{x.scope}</span>
              </div>
            </div>
            <Panel className="mt-2.5 px-4 py-3.5">
              {x.result ? (
                <Answer id={x.id} result={x.result} />
              ) : x.error ? (
                <InlineAlert tone="bad" title="Could not get an answer">
                  {x.error}
                </InlineAlert>
              ) : (
                <div className="space-y-2" aria-label="Answering">
                  <p className="text-xs text-muted">Searching the documents and checking citations…</p>
                  <Skeleton className="h-2.5" />
                  <Skeleton className="h-2.5 w-4/5" />
                </div>
              )}
            </Panel>
          </article>
        ))}
        <div ref={endRef} />
      </div>

      <form onSubmit={onSubmit} className="sticky bottom-4 mt-7">
        <Panel className="border-control shadow-pop">
          <label htmlFor="question" className="sr-only">
            Question
          </label>
          <textarea
            id="question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={onKeyDown}
            rows={2}
            maxLength={2000}
            placeholder="Ask about deadlines, requirements, specifications, addenda…"
            className="block w-full resize-none bg-transparent px-3 py-2.5 text-sm placeholder:text-faint focus:outline-none"
          />
          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line px-2 py-1.5">
            <label className="flex items-center gap-2 text-xs text-muted">
              Scope
              <Select aria-label="Scope" value={scope} onChange={(e) => setScope(e.target.value)} className="h-7 text-xs">
                <option value="">All bids</option>
                {(bids.data ?? [])
                  .filter((b) => b.indexed)
                  .map((b) => (
                    <option key={b.bid_id} value={b.bid_id}>
                      {b.bid_id}
                    </option>
                  ))}
              </Select>
            </label>
            <div className="flex items-center gap-2.5">
              <span className="hidden text-2xs text-faint sm:inline">Enter to send · Shift+Enter for a new line · ↑ recalls the last question</span>
              <Button
                type="submit"
                variant="primary"
                size="sm"
                loading={ask.isPending}
                disabled={question.trim().length < 3}
                icon={<ArrowUp className="size-3.5" aria-hidden />}
                className={cn(ask.isPending && "w-20")}
              >
                Ask
              </Button>
            </div>
          </div>
        </Panel>
      </form>
    </div>
  );
}
