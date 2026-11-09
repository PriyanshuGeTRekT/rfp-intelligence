// The secondary parts of a bid: documents (rail and tab), addendum changes, validation report.
import { ExternalLink, FileText, GitCompareArrows } from "lucide-react";
import { Fragment, useMemo } from "react";
import { toast } from "sonner";

import { ChangeMark, Cite, DocTypeTag, QuoteBlock } from "../components/domain";
import { EmptyState, InlineAlert } from "../components/ui/feedback";
import { SectionLabel, Tag } from "../components/ui/primitives";
import { openSource } from "../lib/api";
import { cn } from "../lib/cn";
import { buildDocLabels, labelFor, type DocLabels } from "../lib/docLabels";
import { formatDate } from "../lib/format";
import type { AddendumChange, BidResult, DocumentInfo } from "../lib/types";

const changeCounts = (changes: AddendumChange[]) => {
  const counts = new Map<string, number>();
  for (const c of changes) counts.set(c.source.file, (counts.get(c.source.file) ?? 0) + 1);
  return counts;
};

/** Addendum changes grouped by addendum, newest first: later addenda override earlier ones. */
export function ChangesPanel({
  changes,
  fieldNames,
  bidId,
  docLabels,
}: {
  changes: AddendumChange[];
  fieldNames: Record<string, string>;
  bidId: string;
  docLabels?: DocLabels;
}) {
  if (changes.length === 0) {
    return (
      <EmptyState
        compact
        icon={<GitCompareArrows className="size-4" />}
        title="No addendum changes"
        description="Either this bid has no addenda, or they change none of the extracted fields."
      />
    );
  }
  const groups = new Map<string, AddendumChange[]>();
  for (const c of changes) {
    const label = c.addendum_number ? `Addendum ${c.addendum_number}` : c.source.file;
    groups.set(label, [...(groups.get(label) ?? []), c]);
  }
  const ordered = [...groups.entries()].sort((a, b) => (b[1][0]?.addendum_number ?? 0) - (a[1][0]?.addendum_number ?? 0));
  return (
    <ol className="divide-y divide-line">
      {ordered.map(([label, items]) => (
        <li key={label} className="px-4 py-4">
          <div className="mb-3 flex items-baseline gap-2">
            <h3 className="text-sm font-semibold">{label}</h3>
            {items[0]?.doc_date && <span className="num text-xs text-muted">{formatDate(items[0].doc_date)}</span>}
            <span className="num font-mono text-2xs text-faint">
              {items.length} {items.length === 1 ? "change" : "changes"}
            </span>
          </div>
          <ul className="divide-y divide-line border-t border-line">
            {items.map((c, i) => (
              <li key={i} className="grid gap-x-6 gap-y-2 py-3 md:grid-cols-[220px_1fr]">
                <div>
                  <p className="text-sm font-medium">{fieldNames[c.field] ?? c.field}</p>
                  <ChangeMark change={c} className="mt-0.5" />
                </div>
                <div className="min-w-0">
                  {(c.old_value || c.new_value) && c.operation !== "clarify" && (
                    <p className="text-sm">
                      {c.old_value && <s className="text-muted decoration-line-strong">{c.old_value}</s>}
                      {c.old_value && c.new_value && <span className="mx-1.5 text-faint">→</span>}
                      {c.new_value && <span className="font-medium">{c.new_value}</span>}
                    </p>
                  )}
                  <QuoteBlock
                    className="mt-2"
                    quote={c.source.quote}
                    cite={<Cite bidId={bidId} doc={labelFor(docLabels, c.source.file)} page={c.source.page} />}
                  />
                </div>
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ol>
  );
}

/** The documents table: file, type, date, pages, open. */
export function DocumentsPanel({ documents, bidId, changes = [] }: { documents: DocumentInfo[]; bidId: string; changes?: AddendumChange[] }) {
  const labels = useMemo(() => buildDocLabels(documents), [documents]);
  const counts = changeCounts(changes);
  if (documents.length === 0) {
    return <EmptyState compact icon={<FileText className="size-4" />} title="No documents indexed" />;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-left">
        <thead className="caps">
          <tr className="border-b border-line">
            <th scope="col" className="py-2 pl-4 pr-3 font-medium">
              Label
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              File
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Type
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Document date
            </th>
            <th scope="col" className="px-3 py-2 text-right font-medium">
              Pages
            </th>
            <th scope="col" className="px-3 py-2 text-right font-medium">
              Changes
            </th>
            <th scope="col" className="py-2 pl-3 pr-4" />
          </tr>
        </thead>
        <tbody>
          {documents.map((d) => (
            <tr key={d.file} className="border-t border-line">
              <td className="py-2.5 pl-4 pr-3 font-medium">{labels.get(d.file)?.label}</td>
              <td className="max-w-[360px] truncate px-3 py-2.5 font-mono text-2xs text-muted" title={d.file}>
                {d.file}
              </td>
              <td className="px-3 py-2.5">
                <DocTypeTag type={d.doc_type} addendum={d.addendum_number} />
              </td>
              <td className="num px-3 py-2.5 text-muted">{formatDate(d.doc_date)}</td>
              <td className="num px-3 py-2.5 text-right text-muted">{d.pages || "—"}</td>
              <td className="num px-3 py-2.5 text-right text-muted">{counts.get(d.file) ?? "—"}</td>
              <td className="py-2.5 pl-3 pr-4 text-right">
                <Cite bidId={bidId} doc={labelFor(labels, d.file)} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** The documents rail beside the ledger: each document filters the fields it supports. */
export function DocumentsRail({
  documents,
  bidId,
  changes,
  active,
  onToggle,
}: {
  documents: DocumentInfo[];
  bidId: string;
  changes: AddendumChange[];
  active: string | null;
  onToggle: (file: string | null) => void;
}) {
  const labels = useMemo(() => buildDocLabels(documents), [documents]);
  const counts = changeCounts(changes);
  const open = (file: string) => openSource(bidId, file).catch((e: Error) => toast.error("Could not open the document", { description: e.message }));
  return (
    <div>
      <SectionLabel count={documents.length} className="mb-1.5">
        Documents
      </SectionLabel>
      <ul className="border-t border-line">
        {documents.map((d) => {
          const label = labels.get(d.file);
          const pressed = active === d.file;
          return (
            <li key={d.file} className="flex items-start border-b border-line">
              <button
                type="button"
                aria-pressed={pressed}
                onClick={() => onToggle(pressed ? null : d.file)}
                title={d.file}
                className={cn("min-w-0 flex-1 px-1.5 py-2 text-left hover:bg-subtle", pressed && "bg-accent-soft")}
              >
                <span className="flex items-baseline justify-between gap-2">
                  <span className={cn("font-medium", label?.kind === "addendum" && "text-accent")}>{label?.label}</span>
                  <span className="num text-2xs text-faint">
                    {d.pages ? `${d.pages} ${d.pages === 1 ? "p" : "pp"}` : "HTML"} · {formatDate(d.doc_date)}
                  </span>
                </span>
                <span className="block truncate font-mono text-2xs text-faint">{d.file}</span>
                {counts.get(d.file) && (
                  <span className="num block text-2xs text-accent">
                    {counts.get(d.file)} {counts.get(d.file) === 1 ? "change" : "changes"}
                  </span>
                )}
              </button>
              <button type="button" onClick={() => open(d.file)} className="mt-2 rounded p-1 text-faint hover:bg-subtle hover:text-ink" aria-label={`Open ${d.file}`}>
                <ExternalLink className="size-3.5" />
              </button>
            </li>
          );
        })}
      </ul>
      <p className="mt-1 text-2xs text-faint">Select a document to show only the fields it supports.</p>
    </div>
  );
}

const CHECKS: [string, string][] = [
  ["Cited.", "Every value carries at least one quote."],
  ["Verbatim.", "Each quote appears word for word in the passage it cites."],
  ["Supported.", "Numbers, dates and identifiers in the value appear in its quotes."],
  ["Not found is earned.", "Only after enough searches and no labelled facts."],
  ["Consistent.", "Dates in order: pre-bid before due date, addenda before due date."],
  ["Retried.", "A rejected field is searched again with the reason, up to the retry limit."],
];

export function ValidationPanel({ result }: { result: BidResult }) {
  const v = result.validation;
  const checks = Object.entries(v.checks_failed);
  const numbers: [string, number, string?][] = [
    ["Passed", v.passed],
    ["Not found", v.not_found, "after a thorough search"],
    ["Failed", v.failed],
    ["Conflicts", v.conflicts],
    ["Retries", v.retries, `${v.passed_after_retry} fixed by a retry`],
  ];
  return (
    <div className="space-y-5 p-4">
      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 border-b border-line pb-4 sm:grid-cols-5">
        {numbers.map(([label, n, hint]) => (
          <div key={label}>
            <dt className="caps">{label}</dt>
            <dd className={cn("num mt-0.5 text-2xl font-semibold tracking-[-0.01em]", label === "Failed" && n > 0 && "text-bad", label === "Conflicts" && n > 0 && "text-warn")}>
              {n}
            </dd>
            {hint && <dd className="text-2xs text-faint">{hint}</dd>}
          </div>
        ))}
      </dl>

      {v.consistency_issues.length > 0 && (
        <InlineAlert tone="warn" title="Cross-field checks">
          <ul className="list-disc space-y-0.5 pl-4">
            {v.consistency_issues.map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        </InlineAlert>
      )}
      {result.errors.length > 0 && (
        <InlineAlert tone="bad" title="Errors during the run">
          <ul className="list-disc space-y-0.5 pl-4 font-mono text-2xs">
            {result.errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </InlineAlert>
      )}

      <div>
        <SectionLabel className="mb-2">Checks applied to every value</SectionLabel>
        <dl className="grid gap-x-8 gap-y-1.5 text-xs text-muted md:grid-cols-2">
          {CHECKS.map(([name, what]) => (
            <Fragment key={name}>
              <div>
                <dt className="inline font-medium text-ink">{name}</dt> <dd className="inline">{what}</dd>
              </div>
            </Fragment>
          ))}
        </dl>
        {checks.length > 0 && (
          <p className="mt-3 flex flex-wrap items-center gap-1.5 text-xs text-muted">
            Checks that rejected a final value:
            {checks.map(([name, n]) => (
              <Tag key={name} tone="bad" className="font-mono">
                {name} ×{n}
              </Tag>
            ))}
          </p>
        )}
      </div>
    </div>
  );
}
