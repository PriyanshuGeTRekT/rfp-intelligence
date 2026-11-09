import { AlertTriangle, Copy, Workflow } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";

import { PageHeader } from "../components/domain";
import { EmptyState, ErrorState } from "../components/ui/feedback";
import { Input, Panel, SectionLabel, Skeleton } from "../components/ui/primitives";
import { laneFor, spanLabel, summarize, toRows, type Lane, type TraceRow } from "../features/traceTree";
import { ApiError } from "../lib/api";
import { cn } from "../lib/cn";
import { formatCost, formatDuration, formatNumber } from "../lib/format";
import { useTrace } from "../lib/queries";

// Engine-level spans: hundreds per run, useful only when studying retrieval itself.
const LOW_LEVEL = new Set(["search", "rerank", "index.file"]);

const TEXT_KEYS = ["llm.error", "llm.system", "llm.input", "llm.output", "agent.input", "agent.output"];

const LANE_CLASS: Record<Lane, string> = {
  error: "bg-bad",
  extract: "bg-accent",
  retrieve: "bg-faint",
  validate: "bg-ok",
  plain: "bg-line-strong",
};

const LEGEND: [Lane, string][] = [
  ["extract", "extract · summary · rewrite"],
  ["retrieve", "retrieve · search"],
  ["validate", "validate"],
  ["plain", "plan · ingest · reconcile · report"],
  ["error", "error"],
];

function copy(text: string) {
  navigator.clipboard
    .writeText(text)
    .then(() => toast.success("Copied"))
    .catch(() => toast.error("Could not copy"));
}

function SpanDetail({ row }: { row: TraceRow }) {
  const attrs = row.span.attributes;
  const error = row.span.status === "ERROR" || "llm.error" in attrs;
  const texts = TEXT_KEYS.filter((k) => typeof attrs[k] === "string" && attrs[k] !== "");
  const rest = Object.entries(attrs).filter(([k]) => !TEXT_KEYS.includes(k));
  return (
    <div className="divide-y divide-line">
      <div className="px-4 py-3">
        <p className="flex items-center gap-2 font-mono text-sm font-semibold">
          {error && <AlertTriangle className="size-3.5 shrink-0 text-bad" aria-label="error" />}
          {row.span.name}
        </p>
        <p className="num mt-0.5 text-xs text-muted">
          {formatDuration(row.span.duration_ms)} · starts at +{formatDuration(row.offsetMs)} ·{" "}
          <span className={cn(error && "text-bad")}>{row.span.status}</span>
        </p>
      </div>
      {rest.length > 0 && (
        <div className="px-4 py-3">
          <SectionLabel className="mb-1.5">Attributes</SectionLabel>
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
        </div>
      )}
      {texts.map((k) => {
        const text = String(attrs[k]);
        const isError = k === "llm.error";
        return (
          <div key={k} className="px-4 py-3">
            <p className="mb-1.5 flex items-center justify-between">
              <span className={cn("caps", isError && "text-bad")}>{k}</span>
              <button type="button" onClick={() => copy(text)} className="inline-flex items-center gap-1 rounded-sm border border-control px-1.5 py-0.5 text-2xs font-medium text-muted hover:text-ink" aria-label={`Copy ${k}`}>
                <Copy className="size-3" aria-hidden />
                Copy
              </button>
            </p>
            <pre
              className={cn(
                "scrollbar-thin max-h-72 overflow-auto whitespace-pre-wrap break-words border p-2.5 font-mono text-2xs leading-relaxed",
                isError ? "border-bad/40 bg-bad-soft text-bad" : "border-line bg-subtle",
              )}
            >
              {text}
            </pre>
          </div>
        );
      })}
    </div>
  );
}

export function TracePage() {
  const { runId = "" } = useParams();
  const trace = useTrace(runId);
  const allRows = useMemo(() => toRows(trace.data ?? []), [trace.data]);
  const [showSearch, setShowSearch] = useState(false);
  const [filter, setFilter] = useState("");
  const searchCount = allRows.filter((r) => LOW_LEVEL.has(r.span.name)).length;
  const f = filter.trim().toLowerCase();
  const rows = allRows.filter((r) => (showSearch || !LOW_LEVEL.has(r.span.name)) && (!f || r.span.name.toLowerCase().includes(f)));
  const summary = useMemo(() => summarize(trace.data ?? []), [trace.data]);
  const [selected, setSelected] = useState<string | null>(null);
  const total = Math.max(summary.durationMs, 1);
  const current = rows.find((r) => r.span.span_id === selected) ?? rows[0];
  const root = allRows[0]?.span.attributes;
  const bidId = typeof root?.["rfp.bid_id"] === "string" ? root["rfp.bid_id"] : null;
  const mode = typeof root?.["agent.mode"] === "string" ? root["agent.mode"] : null;
  const model = trace.data?.find((s) => typeof s.attributes["llm.model"] === "string")?.attributes["llm.model"];

  return (
    <>
      <PageHeader
        breadcrumb={
          <>
            <Link to="/runs" className="hover:text-ink">
              Runs
            </Link>
            <span className="mx-1.5 text-line-strong">/</span>
            <span className="font-mono">{runId}</span>
          </>
        }
        title={
          <>
            Run trace
            {bidId && (
              <span className="ml-2 font-mono text-sm font-normal text-muted">
                {bidId}
                {mode && ` · ${mode}`}
              </span>
            )}
          </>
        }
        meta={
          trace.data && (
            <span className="num flex flex-wrap gap-x-3.5 gap-y-1 text-xs">
              <span>
                <strong className="font-semibold text-ink">{formatDuration(summary.durationMs)}</strong> wall time
              </span>
              <span>
                <strong className="font-semibold text-ink">{formatNumber(allRows.length - searchCount)}</strong> agent steps <span className="text-faint">({formatNumber(allRows.length)} spans)</span>
              </span>
              <span>
                <strong className="font-semibold text-ink">{summary.llmCalls}</strong> model calls
                {summary.errors > 0 && <span className="text-bad">, {summary.errors} failed</span>}
              </span>
              <span>
                <strong className="font-semibold text-ink">{formatNumber(summary.inputTokens + summary.outputTokens)}</strong> tokens{" "}
                <span className="text-faint">
                  ({formatNumber(summary.inputTokens)} in · {formatNumber(summary.outputTokens)} out)
                </span>
              </span>
              <span>
                <strong className="font-semibold text-ink">{formatCost(summary.costUsd)}</strong> <span className="text-faint">estimated from token prices</span>
              </span>
              {typeof model === "string" && <span className="font-mono">{model}</span>}
            </span>
          )
        }
        actions={
          bidId && (
            <Link to={`/bids/${encodeURIComponent(bidId)}`} className="inline-flex h-8 items-center rounded border border-control bg-surface px-3 text-sm font-medium hover:border-ink">
              Open {bidId} →
            </Link>
          )
        }
      />

      {trace.isError ? (
        trace.error instanceof ApiError && trace.error.status === 404 ? (
          <Panel>
            <EmptyState icon={<Workflow className="size-4" />} title="No trace for this run" description="Traces are written to the server's traces folder; this run's file is not there." />
          </Panel>
        ) : (
          <ErrorState error={trace.error} onRetry={() => trace.refetch()} />
        )
      ) : trace.isPending ? (
        <Panel className="space-y-2 p-4">
          {[0, 1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-5" />
          ))}
        </Panel>
      ) : (
        <div className="flex flex-wrap items-start gap-6">
          <Panel className="min-w-0 flex-[999_1_560px] overflow-hidden">
            <div className="flex flex-wrap items-center gap-3 border-b border-line px-3 py-2 text-xs text-muted">
              <span className="num">
                <strong className="font-semibold text-ink">{rows.length}</strong> of {allRows.length} steps
              </span>
              {searchCount > 0 && (
                <label className="flex cursor-pointer items-center gap-1.5">
                  <input type="checkbox" checked={showSearch} onChange={(e) => setShowSearch(e.target.checked)} className="size-3.5 accent-[rgb(var(--accent))]" />
                  Show {searchCount} search-engine calls
                </label>
              )}
              <Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter steps" aria-label="Filter steps" className="ml-auto h-6 w-48 text-xs" />
              <span className="hidden gap-2.5 text-2xs text-faint xl:flex">
                {LEGEND.map(([lane, label]) => (
                  <span key={lane} className="flex items-center gap-1">
                    <span className={cn("inline-block h-1.5 w-2.5", LANE_CLASS[lane])} aria-hidden />
                    {label}
                  </span>
                ))}
              </span>
            </div>
            <div className="scrollbar-thin max-h-[70vh] overflow-auto">
              <table className="w-full min-w-[640px] text-left">
                <thead className="caps sticky top-0 bg-surface">
                  <tr className="border-b border-line">
                    <th className="py-2 pl-3 pr-2 font-medium">Step</th>
                    <th className="w-[40%] px-2 py-2 font-medium">
                      Timeline <span className="num ml-1 font-mono normal-case tracking-normal text-faint">0 → {formatDuration(summary.durationMs)}</span>
                    </th>
                    <th className="px-2 py-2 text-right font-medium">Time</th>
                    <th className="py-2 pl-2 pr-3 text-right font-medium">Tokens</th>
                  </tr>
                </thead>
                <tbody className="font-mono text-xs">
                  {rows.map((row) => {
                    const a = row.span.attributes;
                    const error = row.span.status === "ERROR" || "llm.error" in a;
                    const tokens = (Number(a["llm.input_tokens"]) || 0) + (Number(a["llm.output_tokens"]) || 0);
                    const isSelected = current?.span.span_id === row.span.span_id;
                    return (
                      <tr
                        key={row.span.span_id ?? `${row.span.name}-${row.offsetMs}`}
                        onClick={() => setSelected(row.span.span_id)}
                        className={cn("cursor-pointer border-t border-line hover:bg-subtle", isSelected && "bg-accent-soft hover:bg-accent-soft")}
                      >
                        <td className={cn("py-1.5 pl-3 pr-2", isSelected && "shadow-[inset_3px_0_0_rgb(var(--accent))]")}>
                          <span className="flex items-center gap-1.5 whitespace-nowrap" style={{ paddingLeft: row.depth * 14 }}>
                            {error && <AlertTriangle className="size-3.5 shrink-0 text-bad" aria-label="error" />}
                            <span className={cn(row.depth === 0 && "font-semibold")}>{spanLabel(row.span.name)}</span>
                          </span>
                        </td>
                        <td className="px-2 py-1.5">
                          <div className="relative h-1.5 bg-subtle">
                            <div
                              className={cn("absolute top-0 h-full min-w-[2px]", LANE_CLASS[laneFor(row.span.name, error)])}
                              style={{ left: `${(row.offsetMs / total) * 100}%`, width: `${((row.span.duration_ms ?? 0) / total) * 100}%` }}
                            />
                          </div>
                        </td>
                        <td className="num whitespace-nowrap px-2 py-1.5 text-right text-muted">{formatDuration(row.span.duration_ms)}</td>
                        <td className="num py-1.5 pl-2 pr-3 text-right text-muted">{tokens ? formatNumber(tokens) : error ? <span className="text-faint">—</span> : ""}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Panel>
          <Panel className="scrollbar-thin max-h-[70vh] w-full flex-1 basis-[380px] overflow-auto xl:sticky xl:top-16 xl:max-w-[440px]">
            {current ? <SpanDetail row={current} /> : <EmptyState compact title="Select a step" />}
          </Panel>
        </div>
      )}
    </>
  );
}
