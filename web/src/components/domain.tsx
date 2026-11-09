// Components that know the domain: tiers, citations, quotes, addendum changes, validation, verdicts.
import { ArrowRight, Check, ExternalLink, FileText, Globe, MessageSquare, Pen, Plus, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { toast } from "sonner";

import { openSource } from "../lib/api";
import { cn } from "../lib/cn";
import type { DocLabel } from "../lib/docLabels";
import { OPERATION_LABELS, TIER_INFO, docTypeLabel } from "../lib/format";
import type { AddendumChange, ChangeOperation, Decision, FieldStatus, JobStatus, Tier, ValidationTally, Verdict } from "../lib/types";
import { JobGlyph, OutcomeGlyph, TierGlyph } from "./ui/glyphs";
import { Tooltip } from "./ui/overlay";
import { Tag } from "./ui/primitives";

const TIER_INK: Record<Tier, string> = {
  A: "text-ink",
  B: "text-ink",
  C: "text-warn",
  D: "text-ink",
  E: "text-warn",
  "NF-1": "text-muted",
  "NF-2": "text-warn",
  X: "text-bad",
};

/** The fill-meter glyph with the tier letters, and the confidence number when given. */
export function TierMeter({ tier, confidence, size = "md", showLabel }: { tier: Tier; confidence?: number; size?: "sm" | "md"; showLabel?: boolean }) {
  const info = TIER_INFO[tier];
  const label = `Tier ${tier}, ${info.label.toLowerCase()}${confidence !== undefined ? `, confidence ${confidence.toFixed(2)}` : ""}`;
  return (
    <Tooltip
      content={
        <span>
          <span className="font-semibold">
            Tier {tier} · {info.label}
          </span>
          <span className="mt-0.5 block opacity-80">{info.description}</span>
        </span>
      }
    >
      <span
        className={cn("inline-flex cursor-default items-center gap-1.5 font-mono font-medium", size === "sm" ? "text-[10.5px]" : "text-2xs", TIER_INK[tier])}
        tabIndex={0}
        aria-label={label}
      >
        <TierGlyph tier={tier} size={size === "sm" ? 8 : 10} />
        <span aria-hidden>{tier}</span>
        {confidence !== undefined && (
          <span className="num font-normal text-muted" aria-hidden>
            {confidence.toFixed(2)}
          </span>
        )}
        {showLabel && <span className="font-sans font-medium text-ink">{info.label}</span>}
      </span>
    </Tooltip>
  );
}

/** A pinpoint cite: short document label and page, the full file name on hover; opens the source. */
export function Cite({
  bidId,
  doc,
  page,
  pages,
  size = "md",
  className,
}: {
  bidId: string;
  doc: DocLabel;
  page?: number | string;
  pages?: string;
  size?: "sm" | "md";
  className?: string;
}) {
  const open = () => openSource(bidId, doc.file, page).catch((e: Error) => toast.error("Could not open the document", { description: e.message }));
  const Icon = doc.kind === "portal" ? Globe : FileText;
  const pageText = pages ?? (page !== undefined ? `p. ${page}` : undefined);
  return (
    <button
      type="button"
      onClick={open}
      title={`Open ${doc.file}${pageText ? ` at ${pageText}` : ""}`}
      aria-label={`Open ${doc.file}${pageText ? ` at ${pageText}` : ""}`}
      className={cn(
        "group inline-flex max-w-[200px] shrink-0 items-center gap-1 rounded-sm border border-control bg-surface font-medium hover:border-ink",
        size === "sm" ? "h-5 px-1 text-[10.5px]" : "h-[22px] px-1.5 text-2xs",
        doc.kind === "addendum" ? "text-accent" : "text-ink",
        className,
      )}
    >
      <Icon className="size-3 shrink-0" aria-hidden />
      <span className="truncate group-hover:underline">{doc.label}</span>
      {pageText && <span className="num shrink-0 font-mono font-normal text-muted">{pageText}</span>}
      <ExternalLink className="hidden size-3 shrink-0 group-hover:inline" aria-hidden />
    </button>
  );
}

/** A verbatim quote in the documents' voice, with its cite and the full file name. */
export function QuoteBlock({
  quote,
  cite,
  file,
  action,
  className,
}: {
  quote: string;
  cite: ReactNode;
  file?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <figure className={cn("m-0", className)}>
      <blockquote className="quote m-0">“{quote}”</blockquote>
      <figcaption className="mt-1.5 flex flex-wrap items-center gap-x-2.5 gap-y-1.5 text-2xs text-faint">
        {cite}
        {file && <span className="max-w-[220px] truncate font-mono">{file}</span>}
        {action && <span className="ml-auto">{action}</span>}
      </figcaption>
    </figure>
  );
}

const OPERATION_ICON: Record<ChangeOperation, LucideIcon> = {
  replace: ArrowRight,
  amend: Pen,
  add_requirement: Plus,
  confirm: Check,
  clarify: MessageSquare,
};

/** "Add. 2 · Replaced": the stamp drawn wherever a changed value appears. */
export function ChangeMark({ change, className }: { change: Pick<AddendumChange, "operation" | "addendum_number">; className?: string }) {
  const Icon = OPERATION_ICON[change.operation];
  return (
    <span className={cn("inline-flex items-center gap-1 whitespace-nowrap text-2xs font-medium text-accent", className)}>
      <Icon className="size-3" aria-hidden />
      {change.addendum_number ? `Add. ${change.addendum_number}` : "Addendum"} · {OPERATION_LABELS[change.operation]}
    </span>
  );
}

export function DocTypeTag({ type, addendum }: { type: string; addendum?: number | null }) {
  return (
    <Tag tone={type === "addendum" ? "accent" : "neutral"}>
      {docTypeLabel(type)}
      {addendum ? ` ${addendum}` : ""}
    </Tag>
  );
}

const JOB_INK: Record<JobStatus, string> = { queued: "text-muted", running: "text-accent", succeeded: "text-ok", failed: "text-bad" };
const JOB_LABEL: Record<JobStatus, string> = { queued: "Queued", running: "Running", succeeded: "Succeeded", failed: "Failed" };

export function JobBadge({ status }: { status: JobStatus }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs font-medium", JOB_INK[status])}>
      <JobGlyph status={status} />
      {JOB_LABEL[status]}
    </span>
  );
}

const OUTCOME_INK: Record<Decision | Verdict, string> = { go: "text-ok", pass: "text-ok", review: "text-warn", "no-go": "text-bad", fail: "text-bad" };
const DECISION_LABEL: Record<Decision, string> = { go: "Go", "no-go": "No-go", review: "Review" };
const VERDICT_LABEL: Record<Verdict, string> = { pass: "Pass", fail: "Fail", review: "Review" };

export function DecisionMark({ decision, className }: { decision: Decision; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 font-semibold", OUTCOME_INK[decision], className)}>
      <OutcomeGlyph outcome={decision} size={16} />
      {DECISION_LABEL[decision]}
    </span>
  );
}

export function VerdictIcon({ verdict }: { verdict: Verdict }) {
  return <OutcomeGlyph outcome={verdict} className={cn("shrink-0", OUTCOME_INK[verdict])} label={VERDICT_LABEL[verdict]} />;
}


const SEGMENTS: { pick: FieldStatus; cls: string; label: string }[] = [
  { pick: "found", cls: "bg-ink", label: "passed" },
  { pick: "conflict", cls: "bg-warn", label: "conflicts" },
  { pick: "not_found", cls: "box-border border border-control bg-surface", label: "not found" },
  { pick: "failed", cls: "bg-bad", label: "failed" },
];

const tallyCount = (t: ValidationTally, s: FieldStatus) =>
  s === "found" ? t.passed : s === "conflict" ? t.conflicts : s === "not_found" ? t.not_found : t.failed;

/** Passed / conflicts / not found / failed as a segmented bar, always followed by the counts in words. */
export function ValidationBar({
  tally,
  onPick,
  width = "w-36",
  className,
}: {
  tally: ValidationTally;
  onPick?: (status: FieldStatus) => void;
  width?: string;
  className?: string;
}) {
  const total = Math.max(tally.fields, tally.passed + tally.not_found + tally.failed + tally.conflicts, 1);
  const parts = SEGMENTS.map((s) => ({ ...s, n: tallyCount(tally, s.pick) })).filter((p) => p.n > 0);
  const summary = parts.map((p) => `${p.n} ${p.label}`).join(", ");
  return (
    <div className={cn("flex flex-wrap items-center gap-x-2.5 gap-y-1", className)}>
      <div className={cn("flex h-2 gap-px overflow-hidden rounded-[1px]", width)} role="img" aria-label={`${summary} of ${total} fields`}>
        {parts.map((p) => (
          <div key={p.pick} className={p.cls} style={{ flex: p.n }} />
        ))}
      </div>
      <span className="num flex flex-wrap gap-x-2 text-xs text-muted">
        {parts.map((p) => {
          const text = (
            <>
              <strong className={cn("font-semibold", p.pick === "failed" ? "text-bad" : "text-ink")}>{p.n}</strong> {p.label}
            </>
          );
          return onPick ? (
            <button key={p.pick} type="button" onClick={() => onPick(p.pick)} className="hover:text-ink hover:underline">
              {text}
            </button>
          ) : (
            <span key={p.pick}>{text}</span>
          );
        })}
      </span>
    </div>
  );
}

export function PageHeader({
  title,
  description,
  lead,
  actions,
  meta,
  breadcrumb,
}: {
  title: ReactNode;
  description?: ReactNode;
  lead?: ReactNode;
  actions?: ReactNode;
  meta?: ReactNode;
  breadcrumb?: ReactNode;
}) {
  return (
    <div className="mb-5">
      {breadcrumb && <nav aria-label="Breadcrumb" className="mb-1.5 text-xs text-muted">{breadcrumb}</nav>}
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="min-w-0 flex-1 basis-[480px]">
          <h1 className="text-xl font-semibold leading-7 tracking-[-0.01em] text-ink">{title}</h1>
          {meta && <div className="mt-1 flex flex-wrap items-center gap-x-3.5 gap-y-1 text-sm text-muted">{meta}</div>}
          {description && <p className="mt-1 max-w-3xl text-sm text-muted">{description}</p>}
          {lead && <p className="mt-2 max-w-3xl text-sm text-muted">{lead}</p>}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
    </div>
  );
}
