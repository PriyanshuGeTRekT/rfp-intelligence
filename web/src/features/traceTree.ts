import type { TraceSpan } from "../lib/types";

export interface TraceRow {
  span: TraceSpan;
  depth: number;
  offsetMs: number;
}

export interface TraceSummary {
  durationMs: number;
  llmCalls: number;
  inputTokens: number;
  outputTokens: number;
  costUsd: number;
  errors: number;
}

const startMs = (s: TraceSpan) => (s.start ? new Date(s.start).getTime() : 0);
const num = (v: unknown) => (typeof v === "number" ? v : 0);

/** Spans in tree order (parents before children, siblings by start time) with depth and offset. */
export function toRows(spans: TraceSpan[]): TraceRow[] {
  if (spans.length === 0) return [];
  const ids = new Set(spans.map((s) => s.span_id));
  const children = new Map<string | null, TraceSpan[]>();
  for (const s of spans) {
    const parent = s.parent_span_id && ids.has(s.parent_span_id) ? s.parent_span_id : null;
    children.set(parent, [...(children.get(parent) ?? []), s]);
  }
  const origin = Math.min(...spans.map(startMs));
  const rows: TraceRow[] = [];
  const visit = (parent: string | null, depth: number) => {
    const kids = (children.get(parent) ?? []).sort((a, b) => startMs(a) - startMs(b));
    for (const span of kids) {
      rows.push({ span, depth, offsetMs: startMs(span) - origin });
      if (span.span_id) visit(span.span_id, depth + 1);
    }
  };
  visit(null, 0);
  return rows;
}

export function summarize(spans: TraceSpan[]): TraceSummary {
  const llm = spans.filter((s) => typeof s.attributes["llm.model"] === "string");
  const starts = spans.map(startMs);
  const ends = spans.map((s) => startMs(s) + (s.duration_ms ?? 0));
  return {
    durationMs: spans.length ? Math.max(...ends) - Math.min(...starts) : 0,
    llmCalls: llm.length,
    inputTokens: llm.reduce((n, s) => n + num(s.attributes["llm.input_tokens"]), 0),
    outputTokens: llm.reduce((n, s) => n + num(s.attributes["llm.output_tokens"]), 0),
    costUsd: llm.reduce((n, s) => n + num(s.attributes["llm.cost_usd"]), 0),
    errors: spans.filter((s) => s.status === "ERROR" || "llm.error" in s.attributes).length,
  };
}

/** A readable label for a span name: agent.extract.identity_dates -> extract · identity_dates */
export function spanLabel(name: string): string {
  const parts = name.replace(/^agent\./, "").split(".");
  return parts.join(" · ");
}
