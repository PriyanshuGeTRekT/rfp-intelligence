import { ChevronDown, ChevronRight, Search } from "lucide-react";
import { Fragment, useMemo, useState } from "react";

import { SourceChip, StatusBadge, TierBadge } from "../components/domain";
import { EmptyState } from "../components/ui/feedback";
import { Input } from "../components/ui/primitives";
import { cn } from "../lib/cn";
import { STATUS_LABELS } from "../lib/format";
import type { FieldResult, FieldStatus } from "../lib/types";

type Filter = "all" | FieldStatus;
const FILTERS: Filter[] = ["all", "found", "not_found", "conflict", "failed"];

function Value({ field }: { field: FieldResult }) {
  if (field.value === null) {
    return <span className="text-faint">{field.status === "failed" ? "No value" : "Not found in documents"}</span>;
  }
  if (Array.isArray(field.value)) {
    return (
      <ul className="space-y-0.5">
        {field.value.map((item, i) => (
          <li key={i} className="flex gap-1.5">
            <span className="text-faint" aria-hidden>
              ·
            </span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    );
  }
  const display = typeof field.normalized?.display === "string" ? field.normalized.display : null;
  return (
    <div>
      <span className={cn(field.key === "bid_summary" ? "leading-relaxed" : "font-medium")}>{field.value}</span>
      {display && display !== field.value && <span className="block text-xs text-muted">{display}</span>}
    </div>
  );
}

function Detail({ field, bidId }: { field: FieldResult; bidId: string }) {
  return (
    <div className="grid gap-4 px-4 pb-4 pt-1 md:grid-cols-[1fr_280px]">
      <div className="space-y-2">
        <p className="text-2xs font-medium uppercase tracking-wide text-faint">Evidence</p>
        {field.sources.length === 0 && <p className="text-xs text-muted">No quotes: nothing in the documents supports a value.</p>}
        {field.sources.map((src, i) => (
          <figure key={i} className="rounded-md border border-line bg-surface">
            <blockquote className="border-l-2 border-accent/50 px-3 py-2 text-[13px] leading-relaxed text-ink">“{src.quote}”</blockquote>
            <figcaption className="flex items-center gap-2 border-t border-line px-3 py-1.5">
              <SourceChip bidId={bidId} file={src.file} page={src.page} />
              {src.addendum_number && <span className="text-2xs text-accent">Addendum {src.addendum_number}</span>}
            </figcaption>
          </figure>
        ))}
      </div>
      <div className="space-y-3 text-xs">
        {field.notes && (
          <div>
            <p className="mb-1 text-2xs font-medium uppercase tracking-wide text-faint">Notes</p>
            <p className="leading-relaxed text-muted">{field.notes}</p>
          </div>
        )}
        {field.normalized && (
          <div>
            <p className="mb-1 text-2xs font-medium uppercase tracking-wide text-faint">Normalized</p>
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 font-mono text-2xs">
              {Object.entries(field.normalized)
                .filter(([, v]) => v !== null && v !== "" && typeof v !== "object")
                .map(([k, v]) => (
                  <Fragment key={k}>
                    <dt className="text-faint">{k}</dt>
                    <dd className="break-all text-ink">{String(v)}</dd>
                  </Fragment>
                ))}
            </dl>
          </div>
        )}
        <p className="font-mono text-2xs text-faint">key: {field.key}</p>
      </div>
    </div>
  );
}

export function FieldsTable({ fields, bidId }: { fields: Record<string, FieldResult>; bidId: string }) {
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<Set<string>>(new Set());

  const entries = Object.entries(fields);
  const counts = useMemo(() => {
    const c: Record<Filter, number> = { all: entries.length, found: 0, not_found: 0, conflict: 0, failed: 0 };
    entries.forEach(([, f]) => (c[f.status] += 1));
    return c;
  }, [entries]);

  const visible = entries.filter(([name, f]) => {
    if (filter !== "all" && f.status !== filter) return false;
    const q = query.trim().toLowerCase();
    if (!q) return true;
    const value = Array.isArray(f.value) ? f.value.join(" ") : (f.value ?? "");
    return name.toLowerCase().includes(q) || value.toLowerCase().includes(q);
  });

  const toggle = (name: string) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-2.5">
        <div className="flex flex-wrap gap-1" role="group" aria-label="Filter by status">
          {FILTERS.filter((f) => f === "all" || counts[f] > 0).map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFilter(f)}
              aria-pressed={filter === f}
              className={cn(
                "flex h-7 items-center gap-1.5 rounded-md px-2.5 text-xs font-medium",
                filter === f ? "bg-subtle text-ink ring-1 ring-line" : "text-muted hover:text-ink",
              )}
            >
              {f === "all" ? "All" : STATUS_LABELS[f]}
              <span className="num text-faint">{counts[f]}</span>
            </button>
          ))}
        </div>
        <div className="relative w-56">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-faint" aria-hidden />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter fields" aria-label="Filter fields" className="h-7 pl-8 text-xs" />
        </div>
      </div>

      {visible.length === 0 ? (
        <EmptyState compact title="No fields match" description="Clear the filter to see all fields." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left">
            <thead className="text-2xs font-medium uppercase tracking-wide text-muted">
              <tr className="border-b border-line">
                <th className="w-[200px] py-2 pl-4 pr-3 font-medium">Field</th>
                <th className="px-3 py-2 font-medium">Value</th>
                <th className="w-[110px] px-3 py-2 font-medium">Confidence</th>
                <th className="w-[230px] py-2 pl-3 pr-4 font-medium">Sources</th>
              </tr>
            </thead>
            <tbody>
              {visible.map(([name, field]) => {
                const expanded = open.has(name);
                return (
                  <Fragment key={name}>
                    <tr
                      className={cn("cursor-pointer border-t border-line align-top hover:bg-subtle/50", expanded && "bg-subtle/50")}
                      onClick={() => toggle(name)}
                    >
                      <td className="py-3 pl-4 pr-3">
                        <button
                          type="button"
                          className="flex items-start gap-1.5 text-left"
                          aria-expanded={expanded}
                          onClick={(e) => {
                            e.stopPropagation();
                            toggle(name);
                          }}
                        >
                          {expanded ? (
                            <ChevronDown className="mt-0.5 size-3.5 shrink-0 text-muted" aria-hidden />
                          ) : (
                            <ChevronRight className="mt-0.5 size-3.5 shrink-0 text-faint" aria-hidden />
                          )}
                          <span>
                            <span className="block font-medium text-ink">{name}</span>
                            <span className="mt-0.5 block">
                              <StatusBadge status={field.status} />
                            </span>
                          </span>
                        </button>
                      </td>
                      <td className="max-w-[460px] px-3 py-3 text-[13px] text-ink">
                        <Value field={field} />
                      </td>
                      <td className="px-3 py-3" onClick={(e) => e.stopPropagation()}>
                        <TierBadge tier={field.tier} confidence={field.confidence} />
                      </td>
                      <td className="py-3 pl-3 pr-4" onClick={(e) => e.stopPropagation()}>
                        <div className="flex flex-wrap gap-1">
                          {uniqueSources(field).slice(0, 3).map((s) => (
                            <SourceChip key={`${s.file}-${s.page}`} bidId={bidId} file={s.file} page={s.page} />
                          ))}
                          {uniqueSources(field).length > 3 && (
                            <span className="num self-center text-2xs text-faint">+{uniqueSources(field).length - 3}</span>
                          )}
                          {field.sources.length === 0 && <span className="text-xs text-faint">—</span>}
                        </div>
                      </td>
                    </tr>
                    {expanded && (
                      <tr className="bg-subtle/50">
                        <td colSpan={4}>
                          <Detail field={field} bidId={bidId} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function uniqueSources(field: FieldResult) {
  const seen = new Set<string>();
  return field.sources.filter((s) => {
    const key = `${s.file}#${s.page}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
