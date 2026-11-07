import { ChevronLeft, CircleAlert, Workflow } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { PageHeader, Stat } from "../components/domain";
import { EmptyState, ErrorState } from "../components/ui/feedback";
import { Card, Skeleton } from "../components/ui/primitives";
import { cn } from "../lib/cn";
import { spanLabel, summarize, toRows, type TraceRow } from "../features/traceTree";
import { ApiError } from "../lib/api";
import { formatCost, formatDuration, formatNumber } from "../lib/format";
import { useTrace } from "../lib/queries";

// Engine-level spans: hundreds per run, useful only when studying retrieval itself.
const LOW_LEVEL = new Set(["search", "rerank", "index.file"]);

const TEXT_KEYS = ["llm.system", "llm.input", "llm.output", "agent.input", "agent.output", "llm.error"];

function barColor(name: string, error: boolean) {
  if (error) return "bg-bad";
  if (name.startsWith("agent.extract") || name.startsWith("agent.summary") || name.includes("rewrite")) return "bg-accent";
  if (name.startsWith("agent.retrieve") || name === "search" || name === "rerank") return "bg-info";
  if (name.startsWith("agent.validate")) return "bg-ok";
  if (name.startsWith("agent.reconcile")) return "bg-warn";
  return "bg-line-strong";
}

function SpanDetail({ row }: { row: TraceRow }) {
  const attrs = row.span.attributes;
  const texts = TEXT_KEYS.filter((k) => typeof attrs[k] === "string" && attrs[k] !== "");
  const rest = Object.entries(attrs).filter(([k]) => !TEXT_KEYS.includes(k));
  return (
    <div className="space-y-4 p-4">
      <div>
        <p className="font-mono text-xs font-semibold">{row.span.name}</p>
        <p className="num mt-0.5 text-xs text-muted">
          {formatDuration(row.span.duration_ms)} · starts at +{formatDuration(row.offsetMs)} · {row.span.status}
        </p>
      </div>
      {rest.length > 0 && (
        <dl className="grid grid-cols-[minmax(0,140px)_1fr] gap-x-3 gap-y-1 text-2xs">
          {rest.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="truncate font-mono text-faint" title={k}>
                {k}
              </dt>
              <dd className="break-words font-mono text-ink">{Array.isArray(v) ? v.join(", ") : String(v)}</dd>
            </div>
          ))}
        </dl>
      )}
      {texts.map((k) => (
        <div key={k}>
          <p className="mb-1 font-mono text-2xs font-medium text-faint">{k}</p>
          <pre
            className={cn(
              "scrollbar-thin max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-md border border-line bg-subtle p-2.5 font-mono text-2xs leading-relaxed",
              k === "llm.error" && "border-bad/30 bg-bad-soft text-bad",
            )}
          >
            {String(attrs[k])}
          </pre>
        </div>
      ))}
    </div>
  );
}

export function TracePage() {
  const { runId = "" } = useParams();
  const trace = useTrace(runId);
  const allRows = useMemo(() => toRows(trace.data ?? []), [trace.data]);
  const [showSearch, setShowSearch] = useState(false);
  const searchCount = allRows.filter((r) => LOW_LEVEL.has(r.span.name)).length;
  const rows = showSearch ? allRows : allRows.filter((r) => !LOW_LEVEL.has(r.span.name));
  const summary = useMemo(() => summarize(trace.data ?? []), [trace.data]);
  const [selected, setSelected] = useState<string | null>(null);
  const total = Math.max(summary.durationMs, 1);
  const current = rows.find((r) => r.span.span_id === selected) ?? rows[0];

  return (
    <>
      <Link to="/runs" className="mb-3 inline-flex items-center gap-1 text-xs text-muted hover:text-ink">
        <ChevronLeft className="size-3.5" aria-hidden />
        Runs
      </Link>
      <PageHeader title="Run trace" description={<span className="font-mono text-xs">{runId}</span>} />

      {trace.isError ? (
        trace.error instanceof ApiError && trace.error.status === 404 ? (
          <Card>
            <EmptyState
              icon={<Workflow className="size-4" />}
              title="No trace for this run"
              description="Traces are written to the server's traces folder; this run's file is not there."
            />
          </Card>
        ) : (
          <ErrorState error={trace.error} onRetry={() => trace.refetch()} />
        )
      ) : trace.isPending ? (
        <Card className="space-y-2 p-4">
          {[0, 1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-5" />
          ))}
        </Card>
      ) : (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-6">
            <Stat label="Duration" value={formatDuration(summary.durationMs)} />
            <Stat label="Agent steps" value={formatNumber(allRows.length - searchCount)} hint={`${formatNumber(allRows.length)} spans`} />
            <Stat label="Model calls" value={summary.llmCalls} />
            <Stat
              label="Tokens"
              value={formatNumber(summary.inputTokens + summary.outputTokens)}
              hint={`${formatNumber(summary.inputTokens)} in · ${formatNumber(summary.outputTokens)} out`}
            />
            <Stat label="Cost" value={formatCost(summary.costUsd)} hint="estimated from token prices" />
            <Stat
              label="Errors"
              value={summary.errors}
              hint={summary.errors ? "recovered; see red steps" : "none"}
              tone={summary.errors ? "warn" : undefined}
            />
          </div>

          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_400px]">
            <Card className="overflow-hidden">
              <div className="flex items-center justify-between border-b border-line px-4 py-2 text-xs text-muted">
                <span className="num">
                  {rows.length} of {allRows.length} steps
                </span>
                {searchCount > 0 && (
                  <label className="flex cursor-pointer items-center gap-1.5">
                    <input
                      type="checkbox"
                      checked={showSearch}
                      onChange={(e) => setShowSearch(e.target.checked)}
                      className="size-3.5 accent-[rgb(var(--accent))]"
                    />
                    Show {searchCount} search-engine calls
                  </label>
                )}
              </div>
              <div className="scrollbar-thin max-h-[70vh] overflow-auto">
                <table className="w-full min-w-[640px] text-left">
                  <thead className="sticky top-0 bg-surface text-2xs font-medium uppercase tracking-wide text-muted">
                    <tr className="border-b border-line">
                      <th className="py-2 pl-4 pr-2 font-medium">Step</th>
                      <th className="w-[40%] px-2 py-2 font-medium">Timeline</th>
                      <th className="px-2 py-2 text-right font-medium">Time</th>
                      <th className="py-2 pl-2 pr-4 text-right font-medium">Tokens</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => {
                      const a = row.span.attributes;
                      const error = row.span.status === "ERROR" || "llm.error" in a;
                      const tokens = (Number(a["llm.input_tokens"]) || 0) + (Number(a["llm.output_tokens"]) || 0);
                      const isSelected = current?.span.span_id === row.span.span_id;
                      return (
                        <tr
                          key={row.span.span_id ?? `${row.span.name}-${row.offsetMs}`}
                          onClick={() => setSelected(row.span.span_id)}
                          className={cn("cursor-pointer border-t border-line/60 text-xs hover:bg-subtle/60", isSelected && "bg-accent-soft/60")}
                        >
                          <td className="py-1.5 pl-4 pr-2">
                            <span className="flex items-center gap-1.5 whitespace-nowrap" style={{ paddingLeft: row.depth * 14 }}>
                              {error && <CircleAlert className="size-3.5 text-bad" aria-label="error" />}
                              <span className={cn("font-mono", row.depth === 0 && "font-semibold")}>{spanLabel(row.span.name)}</span>
                            </span>
                          </td>
                          <td className="px-2 py-1.5">
                            <div className="relative h-2.5 rounded-sm bg-subtle">
                              <div
                                className={cn("absolute top-0 h-full min-w-[2px] rounded-sm", barColor(row.span.name, error))}
                                style={{
                                  left: `${(row.offsetMs / total) * 100}%`,
                                  width: `${((row.span.duration_ms ?? 0) / total) * 100}%`,
                                }}
                              />
                            </div>
                          </td>
                          <td className="num whitespace-nowrap px-2 py-1.5 text-right text-muted">{formatDuration(row.span.duration_ms)}</td>
                          <td className="num py-1.5 pl-2 pr-4 text-right text-muted">{tokens ? formatNumber(tokens) : ""}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Card>
            <Card className="scrollbar-thin max-h-[70vh] overflow-auto xl:sticky xl:top-16">
              {current ? <SpanDetail row={current} /> : <EmptyState compact title="Select a step" />}
            </Card>
          </div>
        </>
      )}
    </>
  );
}
