// The field ledger: the 20 fields in agent groups, filters, keyboard selection and the evidence pane.
import { Search, X } from "lucide-react";
import { useCallback, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

import { EmptyState } from "../../components/ui/feedback";
import { Input, Kbd, Segmented } from "../../components/ui/primitives";
import { cn } from "../../lib/cn";
import { buildDocLabels, labelFor } from "../../lib/docLabels";
import { groupFields, type FieldEntry } from "../../lib/fieldGroups";
import { STATUS_LABELS } from "../../lib/format";
import type { AddendumChange, DocumentInfo, FieldResult, FieldStatus } from "../../lib/types";
import { useMediaQuery } from "../../lib/useMediaQuery";
import { FieldEvidence } from "./FieldEvidence";
import { LedgerRow } from "./LedgerRow";
import { PARAM } from "./params";

type Filter = "all" | FieldStatus;
const FILTERS: Filter[] = ["all", "found", "not_found", "conflict", "failed"];
const isFilter = (v: string | null): v is Filter => v !== null && (FILTERS as string[]).includes(v);

/** Rows whose status matches, that cite the document, and that match the text. */
function matches([name, f]: FieldEntry, filter: Filter, doc: string | null, query: string): boolean {
  if (filter !== "all" && f.status !== filter) return false;
  if (doc && !f.sources.some((s) => s.file === doc)) return false;
  if (!query) return true;
  const value = Array.isArray(f.value) ? f.value.join(" ") : (f.value ?? "");
  return name.toLowerCase().includes(query) || f.key.includes(query) || value.toLowerCase().includes(query);
}

function attention(entries: FieldEntry[]): string[] {
  const failed = entries.filter(([, f]) => f.status === "failed").length;
  const conflicts = entries.filter(([, f]) => f.status === "conflict").length;
  const notFound = entries.filter(([, f]) => f.status === "not_found").length;
  const out: string[] = [];
  if (failed) out.push(`${failed} failed`);
  if (conflicts) out.push(`${conflicts} in conflict`);
  if (notFound) out.push(`${notFound} not found`);
  return out;
}

export function Ledger({
  fields,
  bidId,
  documents,
  changes,
}: {
  fields: Record<string, FieldResult>;
  bidId: string;
  documents: DocumentInfo[];
  changes: AddendumChange[];
}) {
  const [params, setParams] = useSearchParams();
  const wide = useMediaQuery("(min-width: 1280px)");
  const mode = wide ? "pane" : "inline";
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const filterRef = useRef<HTMLInputElement>(null);
  const rowRefs = useRef(new Map<string, HTMLTableRowElement>());

  const filter: Filter = isFilter(params.get(PARAM.status)) ? (params.get(PARAM.status) as Filter) : "all";
  const doc = params.get(PARAM.doc);
  const selectedKey = params.get(PARAM.field);

  const setParam = useCallback(
    (name: string, value: string | null) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (value) next.set(name, value);
          else next.delete(name);
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  const docLabels = useMemo(() => buildDocLabels(documents), [documents]);
  const groups = useMemo(() => groupFields(fields), [fields]);
  const entries = useMemo(() => groups.flatMap((g) => g.entries), [groups]);
  const changesByKey = useMemo(() => {
    const map = new Map<string, AddendumChange[]>();
    for (const c of changes) map.set(c.field, [...(map.get(c.field) ?? []), c]);
    return map;
  }, [changes]);

  const counts = useMemo(() => {
    const c: Record<Filter, number> = { all: entries.length, found: 0, not_found: 0, conflict: 0, failed: 0 };
    entries.forEach(([, f]) => (c[f.status] += 1));
    return c;
  }, [entries]);

  const q = query.trim().toLowerCase();
  const visible = entries.filter((e) => matches(e, filter, doc, q));
  const visibleKeys = visible.map(([, f]) => f.key);
  const selected = entries.find(([, f]) => f.key === selectedKey);

  const activate = (key: string) => {
    if (mode === "pane") setParam(PARAM.field, key === selectedKey ? null : key);
    else
      setExpanded((prev) => {
        const next = new Set(prev);
        if (next.has(key)) next.delete(key);
        else next.add(key);
        return next;
      });
  };

  const focusRow = (key: string | undefined) => {
    if (!key) return;
    rowRefs.current.get(key)?.focus();
    if (mode === "pane") setParam(PARAM.field, key);
  };

  const onRowKey = (key: string) => (e: KeyboardEvent<HTMLTableRowElement>) => {
    const i = visibleKeys.indexOf(key);
    if (e.key === "j" || e.key === "ArrowDown") {
      e.preventDefault();
      focusRow(visibleKeys[Math.min(i + 1, visibleKeys.length - 1)]);
    } else if (e.key === "k" || e.key === "ArrowUp") {
      e.preventDefault();
      focusRow(visibleKeys[Math.max(i - 1, 0)]);
    } else if (e.key === "/") {
      e.preventDefault();
      filterRef.current?.focus();
    } else if (e.key === "Escape") {
      setParam(PARAM.field, null);
    }
  };

  let index = 0;

  return (
    <div className="flex flex-wrap items-start gap-6">
      <section aria-label="Extracted fields" className="min-w-0 flex-[999_1_560px]">
        <div className="flex flex-wrap items-center gap-3 pb-2.5">
          <Segmented
            aria-label="Filter by status"
            value={filter}
            onChange={(f) => setParam(PARAM.status, f === "all" ? null : f)}
            items={FILTERS.filter((f) => f === "all" || counts[f] > 0).map((f) => ({ value: f, label: f === "all" ? "All" : STATUS_LABELS[f], count: counts[f] }))}
          />
          <div className="relative w-56">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-faint" aria-hidden />
            <Input ref={filterRef} value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter fields" aria-label="Filter fields" className="h-7 pl-8 text-xs" />
          </div>
          {doc && (
            <button
              type="button"
              onClick={() => setParam(PARAM.doc, null)}
              className="inline-flex h-7 items-center gap-1.5 rounded border border-control bg-accent-soft px-2 text-xs font-medium text-accent-ink hover:border-ink"
            >
              Cited in {labelFor(docLabels, doc).label}
              <X className="size-3" aria-hidden />
              <span className="sr-only">Clear the document filter</span>
            </button>
          )}
          <span className="ml-auto hidden items-center gap-1 text-2xs text-faint lg:flex">
            <Kbd>j</Kbd>
            <Kbd>k</Kbd> to move · <Kbd>Enter</Kbd> opens evidence
          </span>
        </div>

        {visible.length === 0 ? (
          <div className="border border-line bg-surface">
            <EmptyState compact title="No fields match" description="Clear the filter to see all fields." />
          </div>
        ) : (
          <div className="overflow-x-auto border border-line bg-surface">
            {/* Below sm the rows stack (name, value, tier, sources) instead of scrolling sideways. */}
            <table className="block w-full text-left sm:table sm:min-w-[720px]">
              <thead className="caps hidden sm:table-header-group">
                <tr>
                  <th scope="col" className="w-7 py-2 pl-3 font-medium">
                    <span className="sr-only">Row</span>
                  </th>
                  <th scope="col" className="w-[190px] px-3 py-2 font-medium">
                    Field
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    Value
                  </th>
                  <th scope="col" className="w-[112px] px-3 py-2 font-medium">
                    Tier
                  </th>
                  <th scope="col" className="w-[210px] px-3 py-2 font-medium">
                    Sources
                  </th>
                </tr>
              </thead>
              <tbody className="block sm:table-row-group">
                {groups.map(({ group, entries: groupEntries }) => {
                  const rows = groupEntries.filter((e) => matches(e, filter, doc, q));
                  if (rows.length === 0) return null;
                  const notes = attention(groupEntries);
                  return (
                    <GroupRows key={group.id} id={group.id} name={group.name} count={groupEntries.length} notes={notes}>
                      {rows.map(([name, field]) => {
                        index += 1;
                        return (
                          <LedgerRow
                            key={field.key}
                            ref={(el) => {
                              if (el) rowRefs.current.set(field.key, el);
                              else rowRefs.current.delete(field.key);
                            }}
                            index={index}
                            name={name}
                            field={field}
                            bidId={bidId}
                            docLabels={docLabels}
                            changes={changesByKey.get(field.key) ?? []}
                            mode={mode}
                            selected={field.key === selectedKey}
                            expanded={expanded.has(field.key) || (mode === "inline" && field.key === selectedKey)}
                            onActivate={() => activate(field.key)}
                            onKeyDown={onRowKey(field.key)}
                          />
                        );
                      })}
                    </GroupRows>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {mode === "pane" && (
        <aside aria-label="Evidence" aria-live="polite" className="sticky top-16 w-[400px] shrink-0 border border-line bg-surface">
          {selected ? (
            <FieldEvidence name={selected[0]} field={selected[1]} bidId={bidId} docLabels={docLabels} changes={changesByKey.get(selected[1].key) ?? []} />
          ) : (
            <EmptyState
              compact
              title="Select a field to see its evidence"
              description={
                <>
                  Click a row, or use <Kbd>j</Kbd> <Kbd>k</Kbd> and <Kbd>Enter</Kbd>. Every quote opens its page.
                </>
              }
            />
          )}
        </aside>
      )}
    </div>
  );
}

function GroupRows({ id, name, count, notes, children }: { id: string; name: string; count: number; notes: string[]; children: ReactNode }) {
  return (
    <>
      <tr id={`group-${id}`} className="block sm:table-row">
        <th colSpan={5} scope="rowgroup" className="caps block border-t border-line bg-canvas px-3 pb-1 pt-3.5 text-left sm:table-cell">
          {name}
          <span className="num ml-2 font-mono normal-case tracking-normal text-faint">
            {count} {count === 1 ? "field" : "fields"}
          </span>
          {notes.map((n) => (
            <span key={n} className={cn("ml-2 font-normal normal-case tracking-normal", n.includes("failed") || n.includes("conflict") ? "text-bad" : "text-muted")}>
              {n}
            </span>
          ))}
        </th>
      </tr>
      {children}
    </>
  );
}
