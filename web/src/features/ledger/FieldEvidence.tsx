// The evidence for one field: value, tier, addendum changes, verbatim quotes, note, normalized values.
import { Check, ChevronDown, ChevronRight } from "lucide-react";
import { Fragment, useState } from "react";

import { ChangeMark, Cite, QuoteBlock, TierMeter } from "../../components/domain";
import { SectionLabel } from "../../components/ui/primitives";
import { canLinkFiles, fileUrl } from "../../lib/api";
import { cn } from "../../lib/cn";
import { labelFor, type DocLabels } from "../../lib/docLabels";
import { formatDate, searchEffort, TIER_INFO } from "../../lib/format";
import type { AddendumChange, FieldResult, Source } from "../../lib/types";

const isShort = (value: string) => value.length <= 40 && !value.includes("\n");

function OpenAtPage({ bidId, source, docLabels }: { bidId: string; source: Source; docLabels?: DocLabels }) {
  return <Cite bidId={bidId} doc={labelFor(docLabels, source.file)} page={source.page} />;
}

/** An inline view of the cited page; a plain iframe cannot send the API key, so it is offered only without one. */
function PagePreview({ bidId, source, docLabels }: { bidId: string; source: Source; docLabels?: DocLabels }) {
  const [open, setOpen] = useState(false);
  if (!canLinkFiles() || !source.file.toLowerCase().endsWith(".pdf")) return null;
  const doc = labelFor(docLabels, source.file);
  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="inline-flex h-7 items-center gap-1.5 rounded border border-control bg-surface px-2 text-xs font-medium text-ink hover:border-ink"
      >
        {open ? <ChevronDown className="size-3.5" aria-hidden /> : <ChevronRight className="size-3.5" aria-hidden />}
        {open ? "Hide the page" : `Preview page ${source.page} of ${doc.label} here`}
      </button>
      {open && (
        <iframe
          title={`${doc.file}, page ${source.page}`}
          src={`${fileUrl(bidId, source.file)}#page=${source.page}`}
          className="mt-2 h-[480px] w-full border border-line bg-surface"
        />
      )}
    </div>
  );
}

export function FieldEvidence({
  name,
  field,
  bidId,
  docLabels,
  changes,
  heading = true,
}: {
  name: string;
  field: FieldResult;
  bidId: string;
  docLabels?: DocLabels;
  changes: AddendumChange[];
  heading?: boolean;
}) {
  const info = TIER_INFO[field.tier];
  const display = typeof field.normalized?.display === "string" ? field.normalized.display : null;
  const normalized = Object.entries(field.normalized ?? {}).filter(([k, v]) => k !== "display" && v !== null && v !== "" && typeof v !== "object");
  const effort = field.status === "found" ? null : searchEffort(field.notes);
  const firstPdf = field.sources.find((s) => s.file.toLowerCase().endsWith(".pdf"));

  return (
    <div className="divide-y divide-line text-sm">
      {heading && (
        <div className="px-4 py-3">
          <h2 className="text-base font-semibold leading-6">{name}</h2>
          <p className="font-mono text-2xs text-faint">{field.key}</p>
        </div>
      )}

      <section className="px-4 py-3.5">
        {field.value === null ? (
          <p className={cn("italic", field.status === "failed" ? "text-bad" : "text-muted")}>{field.status === "failed" ? "Failed" : "Not found in documents"}</p>
        ) : Array.isArray(field.value) ? (
          <ol className="list-decimal space-y-0.5 pl-5 font-medium">
            {field.value.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ol>
        ) : (
          <p className={cn(isShort(field.value) ? "num text-2xl font-semibold tracking-[-0.01em]" : "text-md", field.key === "bid_summary" && "font-normal")}>
            {field.value}
          </p>
        )}
        {display && display !== field.value && <p className="mt-1 text-xs text-muted">{display}</p>}
        <p className="mt-2.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
          <TierMeter tier={field.tier} confidence={field.confidence} />
          <span className="font-medium">{info.label}</span>
          <span className="text-muted">— {info.description}</span>
        </p>
      </section>

      {changes.length > 0 && (
        <section className="px-4 py-3.5">
          <SectionLabel className="mb-2">Changed by addendum</SectionLabel>
          <ol className="space-y-3">
            {changes.map((c, i) => (
              <li key={i} className={cn(i > 0 && "border-t border-line pt-3")}>
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <ChangeMark change={c} />
                  {c.doc_date && <span className="num text-faint">{formatDate(c.doc_date)}</span>}
                </div>
                {(c.old_value || c.new_value) && c.operation !== "clarify" && (
                  <p className="mt-1.5">
                    {c.old_value && <s className="text-muted decoration-line-strong">{c.old_value}</s>}
                    {c.old_value && c.new_value && <span className="mx-1.5 text-faint">→</span>}
                    {c.new_value && <span className="font-medium">{c.new_value}</span>}
                  </p>
                )}
                <QuoteBlock
                  className="mt-2 border-t border-line pt-2"
                  quote={c.source.quote}
                  cite={<OpenAtPage bidId={bidId} source={c.source} docLabels={docLabels} />}
                />
              </li>
            ))}
          </ol>
        </section>
      )}

      <section className="px-4 py-3.5">
        <SectionLabel count={field.sources.length}>Evidence</SectionLabel>
        {field.sources.length === 0 ? (
          <p className="mt-1.5 text-xs text-muted">No quotes: nothing in the documents supports a value.</p>
        ) : (
          <div className="mt-1.5 divide-y divide-line">
            {field.sources.map((src, i) => (
              <QuoteBlock
                key={i}
                className="py-2 first:pt-0"
                quote={src.quote}
                file={src.file}
                cite={<OpenAtPage bidId={bidId} source={src} docLabels={docLabels} />}
              />
            ))}
          </div>
        )}
        {firstPdf && <PagePreview bidId={bidId} source={firstPdf} docLabels={docLabels} />}
      </section>

      {field.notes && (
        <section className="px-4 py-3.5">
          <SectionLabel className="mb-1">Note</SectionLabel>
          <p className="text-muted">{field.notes}</p>
        </section>
      )}

      {normalized.length > 0 && (
        <section className="px-4 py-3.5">
          <SectionLabel className="mb-1.5">Normalized</SectionLabel>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 font-mono text-2xs">
            {normalized.map(([k, v]) => (
              <Fragment key={k}>
                <dt className="text-faint">{k}</dt>
                <dd className="break-all text-ink">{String(v)}</dd>
              </Fragment>
            ))}
          </dl>
        </section>
      )}

      <section className="px-4 py-3.5">
        <SectionLabel className="mb-1">Validation</SectionLabel>
        {field.status === "found" ? (
          <p className="flex items-center gap-1.5 text-xs text-ok">
            <Check className="size-3.5" aria-hidden />
            Passed: cited · verbatim · supported
          </p>
        ) : field.status === "failed" ? (
          <p className="text-xs text-bad">{effort ?? "The validator rejected every attempt."}</p>
        ) : field.status === "conflict" ? (
          <p className="text-xs text-warn">{effort ?? "Sources disagree."}</p>
        ) : (
          <p className="text-xs text-muted">{effort ?? "Not found after a thorough search."}</p>
        )}
      </section>
    </div>
  );
}
