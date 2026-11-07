// Components that know the domain: tiers, statuses, document types, citations, validation.
import { ExternalLink, FileText } from "lucide-react";
import type { ReactNode } from "react";
import { toast } from "sonner";

import { openSource } from "../lib/api";
import { docTypeLabel, STATUS_LABELS, TIER_INFO } from "../lib/format";
import type { FieldStatus, JobStatus, Tier, ValidationTally } from "../lib/types";
import { Tooltip } from "./ui/overlay";
import { Badge, Dot, type Tone } from "./ui/primitives";
import { cn } from "../lib/cn";

const TIER_TONE: Record<Tier, Tone> = {
  A: "ok",
  B: "ok",
  C: "info",
  D: "warn",
  E: "bad",
  "NF-1": "neutral",
  "NF-2": "warn",
  X: "bad",
};

export function TierBadge({ tier, confidence }: { tier: Tier; confidence: number }) {
  const info = TIER_INFO[tier];
  return (
    <Tooltip
      content={
        <span>
          <span className="font-semibold">
            Tier {tier} · {info.label}
          </span>
          <span className="mt-0.5 block text-muted">{info.description}</span>
        </span>
      }
    >
      <span className="inline-flex cursor-default items-center gap-1.5" tabIndex={0}>
        <Badge tone={TIER_TONE[tier]} className="font-mono">
          {tier}
        </Badge>
        <span className="num text-xs text-muted">{confidence.toFixed(2)}</span>
      </span>
    </Tooltip>
  );
}

const STATUS_TONE: Record<FieldStatus, Tone> = { found: "ok", not_found: "neutral", conflict: "warn", failed: "bad" };

export function StatusBadge({ status }: { status: FieldStatus }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted">
      <Dot tone={STATUS_TONE[status]} />
      {STATUS_LABELS[status]}
    </span>
  );
}

const JOB_TONE: Record<JobStatus, Tone> = { queued: "neutral", running: "info", succeeded: "ok", failed: "bad" };
const JOB_LABEL: Record<JobStatus, string> = { queued: "Queued", running: "Running", succeeded: "Succeeded", failed: "Failed" };

export function JobBadge({ status }: { status: JobStatus }) {
  return (
    <Badge tone={JOB_TONE[status]}>
      {status === "running" && <span className="size-1.5 animate-pulse rounded-full bg-info" aria-hidden />}
      {JOB_LABEL[status]}
    </Badge>
  );
}

export function DocTypeTag({ type, addendum }: { type: string; addendum?: number | null }) {
  return (
    <Badge tone={type === "addendum" ? "accent" : "neutral"}>
      {docTypeLabel(type)}
      {addendum ? ` ${addendum}` : ""}
    </Badge>
  );
}

export function SourceChip({ bidId, file, page, label }: { bidId: string; file: string; page?: number | string; label?: ReactNode }) {
  const open = () => openSource(bidId, file, page).catch((e: Error) => toast.error("Could not open the document", { description: e.message }));
  return (
    <button
      type="button"
      onClick={open}
      title={`Open ${file}${page ? ` at page ${page}` : ""}`}
      className="group inline-flex max-w-[240px] items-center gap-1 rounded border border-line bg-surface px-1.5 py-0.5 text-2xs text-muted hover:border-line-strong hover:text-ink"
    >
      <FileText className="size-3 shrink-0" aria-hidden />
      <span className="truncate">{label ?? file}</span>
      {page !== undefined && <span className="num shrink-0 text-faint">p.{page}</span>}
      <ExternalLink className="size-3 shrink-0 opacity-0 transition-opacity group-hover:opacity-100" aria-hidden />
    </button>
  );
}

export function ValidationBar({ tally, className }: { tally: ValidationTally; className?: string }) {
  const total = Math.max(tally.fields, tally.passed + tally.not_found + tally.failed + tally.conflicts, 1);
  const parts = [
    { n: tally.passed, cls: "bg-ok", label: "passed" },
    { n: tally.conflicts, cls: "bg-warn", label: "conflicts" },
    { n: tally.not_found, cls: "bg-line-strong", label: "not found" },
    { n: tally.failed, cls: "bg-bad", label: "failed" },
  ];
  const summary = parts.filter((p) => p.n).map((p) => `${p.n} ${p.label}`).join(", ");
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="flex h-1.5 w-28 overflow-hidden rounded-full bg-subtle" role="img" aria-label={summary}>
        {parts.map((p) => (p.n ? <div key={p.label} className={p.cls} style={{ width: `${(p.n / total) * 100}%` }} /> : null))}
      </div>
      <span className="num text-xs text-muted">
        {tally.passed}/{total}
      </span>
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
  meta,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  meta?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-lg font-semibold tracking-tight text-ink">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-[13px] text-muted">{description}</p>}
        {meta && <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">{meta}</div>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: Tone }) {
  const ink = tone ? { neutral: "text-ink", accent: "text-accent", ok: "text-ok", warn: "text-warn", bad: "text-bad", info: "text-info" }[tone] : "text-ink";
  return (
    <div className="rounded-lg border border-line bg-surface px-4 py-3 shadow-card">
      <p className="text-xs text-muted">{label}</p>
      <p className={cn("num mt-1 text-xl font-semibold tracking-tight", ink)}>{value}</p>
      {hint && <p className="mt-0.5 text-2xs text-faint">{hint}</p>}
    </div>
  );
}
