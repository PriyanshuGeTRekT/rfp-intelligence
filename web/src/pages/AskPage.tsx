import { ArrowUp, CircleSlash, Quote, Trash2 } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { PageHeader, SourceChip } from "../components/domain";
import { InlineAlert } from "../components/ui/feedback";
import { Badge, Button, Card, Select, Skeleton } from "../components/ui/primitives";
import { cn } from "../lib/cn";
import { formatCost } from "../lib/format";
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

function Answer({ result }: { result: QAResult }) {
  return (
    <div className="space-y-3">
      {result.found ? (
        <p className="text-[13px] leading-relaxed text-ink">
          {result.statements?.length
            ? result.statements.map((s, i) => (
                <span key={i}>
                  {s.text}
                  {s.citations.map((c) => (
                    <sup key={c} className="num ml-0.5 font-semibold text-accent">
                      [{c + 1}]
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
        <p className="flex items-center gap-2 text-[13px] text-muted">
          <CircleSlash className="size-4 text-faint" aria-hidden />
          Not found in the documents. The passages reviewed do not answer this.
        </p>
      )}
      {result.citations.length > 0 && (
        <ol className="space-y-2">
          {result.citations.map((c, i) => (
            <li key={`${c.evidence_id}-${i}`} className="flex gap-2.5 rounded-md border border-line bg-subtle/50 px-3 py-2">
              <span className="num mt-0.5 text-2xs font-semibold text-faint">{i + 1}</span>
              <div className="min-w-0 flex-1">
                <p className="text-xs leading-relaxed text-ink">“{c.quote}”</p>
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                  <Badge>{c.bid_id}</Badge>
                  <SourceChip bidId={c.bid_id} file={c.file} page={c.page} />
                </div>
              </div>
            </li>
          ))}
        </ol>
      )}
      <p className="num text-2xs text-faint">
        {result.passages_reviewed} passages from {result.scope.join(", ")}
        {result.dropped_citations > 0 && ` · ${result.dropped_citations} unverifiable citations removed`}
        {result.removed_statements ? ` · ${result.removed_statements} unsupported sentences removed` : ""} ·{" "}
        {result.cached_from
          ? `answered from the cache (same as “${result.cached_from}”, similarity ${result.cache_similarity?.toFixed(2)}), no model call`
          : formatCost(result.usage.cost_usd)}
      </p>
    </div>
  );
}

export function AskPage() {
  const bids = useBids();
  const ask = useAsk();
  const [history, setHistory] = useState<Exchange[]>(() =>
    readStored<Exchange[]>(KEYS.conversation, []).map((x) =>
      x.result || x.error ? x : { ...x, error: "The page was closed before the answer arrived." },
    ),
  );
  const [question, setQuestion] = useState("");
  const [scope, setScope] = useState("");
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
    }
  };

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="Ask"
        description="Answers come only from the documents. Every citation is checked word for word against its passage; an answer without a valid citation is reported as not found."
        actions={
          history.length > 0 && (
            <Button variant="ghost" size="sm" icon={<Trash2 className="size-3.5" aria-hidden />} onClick={() => setHistory([])}>
              Clear
            </Button>
          )
        }
      />

      <div className="space-y-4" aria-live="polite">
        {history.length === 0 && (
          <Card className="p-4">
            <p className="mb-2 text-xs font-medium text-muted">Questions from the brief</p>
            <div className="grid gap-1.5">
              {SUGGESTED.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => send(s)}
                  className="flex items-center gap-2 rounded-md px-2 py-1.5 text-left text-[13px] text-ink hover:bg-subtle"
                >
                  <Quote className="size-3.5 shrink-0 text-faint" aria-hidden />
                  {s}
                </button>
              ))}
            </div>
          </Card>
        )}

        {history.map((x) => (
          <article key={x.id} className="space-y-2">
            <div className="flex justify-end">
              <div className="max-w-[85%] rounded-lg bg-accent-soft px-3 py-2 text-[13px] text-accent-ink">
                {x.question}
                <span className="mt-0.5 block text-right text-2xs opacity-70">{x.scope}</span>
              </div>
            </div>
            <Card className="px-4 py-3">
              {x.result ? (
                <Answer result={x.result} />
              ) : x.error ? (
                <InlineAlert tone="bad" title="Could not get an answer">
                  {x.error}
                </InlineAlert>
              ) : (
                <div className="space-y-2" aria-label="Answering">
                  <p className="text-xs text-muted">Searching the documents and checking citations…</p>
                  <Skeleton className="h-3" />
                  <Skeleton className="h-3 w-4/5" />
                </div>
              )}
            </Card>
          </article>
        ))}
        <div ref={endRef} />
      </div>

      <form onSubmit={onSubmit} className="sticky bottom-4 mt-6">
        <Card className="p-2 shadow-pop">
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
            className="w-full resize-none rounded-md bg-transparent px-2 py-1.5 text-[13px] placeholder:text-faint focus:ring-0"
          />
          <div className="flex items-center justify-between gap-2 px-1">
            <Select aria-label="Scope" value={scope} onChange={(e) => setScope(e.target.value)} className="h-7 text-xs">
              <option value="">All bids</option>
              {(bids.data ?? []).filter((b) => b.indexed).map((b) => (
                <option key={b.bid_id} value={b.bid_id}>
                  {b.bid_id}
                </option>
              ))}
            </Select>
            <div className="flex items-center gap-2">
              <span className="hidden text-2xs text-faint sm:inline">Enter to send · Shift+Enter for a new line</span>
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
        </Card>
      </form>
    </div>
  );
}
