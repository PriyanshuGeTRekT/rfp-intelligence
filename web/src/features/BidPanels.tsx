// The secondary tabs of a bid: addendum changes, documents, validation report.
import { ArrowRight, FileText, GitCompareArrows, ShieldCheck } from "lucide-react";

import { DocTypeTag, SourceChip, Stat } from "../components/domain";
import { EmptyState, InlineAlert } from "../components/ui/feedback";
import { Badge, type Tone } from "../components/ui/primitives";
import { formatDate, OPERATION_LABELS } from "../lib/format";
import type { AddendumChange, BidResult, ChangeOperation, DocumentInfo } from "../lib/types";

const OP_TONE: Record<ChangeOperation, Tone> = {
  replace: "warn",
  amend: "warn",
  add_requirement: "accent",
  confirm: "ok",
  clarify: "info",
};

export function ChangesPanel({ changes, fieldNames, bidId }: { changes: AddendumChange[]; fieldNames: Record<string, string>; bidId: string }) {
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
  return (
    <ol className="space-y-6 p-4">
      {[...groups.entries()].map(([label, items]) => (
        <li key={label}>
          <div className="mb-2 flex items-baseline gap-2">
            <h3 className="text-[13px] font-semibold">{label}</h3>
            {items[0]?.doc_date && <span className="text-xs text-muted">{formatDate(items[0].doc_date)}</span>}
          </div>
          <ul className="space-y-2 border-l border-line pl-4">
            {items.map((c, i) => (
              <li key={i} className="relative rounded-md border border-line bg-surface p-3">
                <span className="absolute -left-[21px] top-4 size-2 rounded-full border-2 border-canvas bg-line-strong" aria-hidden />
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={OP_TONE[c.operation]}>{OPERATION_LABELS[c.operation]}</Badge>
                  <span className="text-[13px] font-medium">{fieldNames[c.field] ?? c.field}</span>
                </div>
                {(c.old_value || c.new_value) && c.operation !== "clarify" && (
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-[13px]">
                    {c.old_value && <span className="text-muted line-through decoration-faint">{c.old_value}</span>}
                    {c.old_value && c.new_value && <ArrowRight className="size-3.5 text-faint" aria-hidden />}
                    {c.new_value && <span className="font-medium text-ink">{c.new_value}</span>}
                  </div>
                )}
                <blockquote className="mt-2 border-l-2 border-line pl-2.5 text-xs leading-relaxed text-muted">“{c.source.quote}”</blockquote>
                <div className="mt-2">
                  <SourceChip bidId={bidId} file={c.source.file} page={c.source.page} />
                </div>
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ol>
  );
}

export function DocumentsPanel({ documents, bidId }: { documents: DocumentInfo[]; bidId: string }) {
  if (documents.length === 0) {
    return <EmptyState compact icon={<FileText className="size-4" />} title="No documents indexed" />;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-left">
        <thead className="text-2xs font-medium uppercase tracking-wide text-muted">
          <tr className="border-b border-line">
            <th className="py-2 pl-4 pr-3 font-medium">File</th>
            <th className="px-3 py-2 font-medium">Type</th>
            <th className="px-3 py-2 font-medium">Document date</th>
            <th className="px-3 py-2 text-right font-medium">Pages</th>
            <th className="py-2 pl-3 pr-4" />
          </tr>
        </thead>
        <tbody>
          {documents.map((d) => (
            <tr key={d.file} className="border-t border-line">
              <td className="py-2.5 pl-4 pr-3 font-medium">{d.file}</td>
              <td className="px-3 py-2.5">
                <DocTypeTag type={d.doc_type} addendum={d.addendum_number} />
              </td>
              <td className="px-3 py-2.5 text-muted">{formatDate(d.doc_date)}</td>
              <td className="num px-3 py-2.5 text-right text-muted">{d.pages || "—"}</td>
              <td className="py-2.5 pl-3 pr-4 text-right">
                <SourceChip bidId={bidId} file={d.file} label="Open" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ValidationPanel({ result }: { result: BidResult }) {
  const v = result.validation;
  const checks = Object.entries(v.checks_failed);
  return (
    <div className="space-y-5 p-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Passed" value={v.passed} tone="ok" />
        <Stat label="Not found" value={v.not_found} hint="after a thorough search" />
        <Stat label="Failed" value={v.failed} tone={v.failed ? "bad" : undefined} />
        <Stat label="Conflicts" value={v.conflicts} tone={v.conflicts ? "warn" : undefined} />
        <Stat label="Retries" value={v.retries} hint={`${v.passed_after_retry} fixed by a retry`} />
      </div>

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
        <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold">
          <ShieldCheck className="size-3.5 text-muted" aria-hidden />
          Checks applied to every value
        </h3>
        <ul className="grid gap-2 text-xs text-muted md:grid-cols-2">
          <li><span className="font-medium text-ink">Cited.</span> Every value carries at least one quote.</li>
          <li><span className="font-medium text-ink">Verbatim.</span> Each quote appears word for word in the passage it cites.</li>
          <li><span className="font-medium text-ink">Supported.</span> Numbers, dates and identifiers in the value appear in its quotes.</li>
          <li><span className="font-medium text-ink">Not found is earned.</span> Only after enough searches and no labelled facts.</li>
          <li><span className="font-medium text-ink">Consistent.</span> Dates in order: pre-bid before due date, addenda before due date.</li>
          <li><span className="font-medium text-ink">Retried.</span> A rejected field is searched again with the reason, up to the retry limit.</li>
        </ul>
        {checks.length > 0 && (
          <p className="mt-3 text-xs text-muted">
            Checks that rejected a final value:{" "}
            {checks.map(([name, n]) => (
              <Badge key={name} tone="bad" className="mr-1 font-mono">
                {name} ×{n}
              </Badge>
            ))}
          </p>
        )}
      </div>
    </div>
  );
}
