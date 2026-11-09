import type { ChangeOperation, FieldStatus, Tier } from "./types";

const DOC_TYPE_LABELS: Record<string, string> = {
  rfp: "Solicitation",
  addendum: "Addendum",
  bid_page: "Portal page",
  specs: "Specifications",
  affidavit: "Affidavit",
  form: "Form",
  other: "Other",
};

export const docTypeLabel = (t: string) => DOC_TYPE_LABELS[t] ?? t.replace(/_/g, " ");

export const TIER_INFO: Record<Tier, { label: string; description: string }> = {
  A: { label: "Corroborated", description: "Grounded, and two documents agree or an addendum sets it." },
  B: { label: "Grounded", description: "Grounded in one source." },
  C: { label: "Fair", description: "Loosely grounded, from OCR (OCR text is capped at C), or assembled from two sources." },
  D: { label: "Reconciled", description: "Sources differ; an addendum explains the difference." },
  E: { label: "Conflict", description: "Sources differ and nothing explains it, or a cross-field check failed." },
  "NF-1": { label: "Absent", description: "Not found after a thorough search." },
  "NF-2": { label: "Unverified", description: "Not found, and the search did not meet the coverage bar." },
  X: { label: "Rejected", description: "The validator rejected every attempt." },
};

export const STATUS_LABELS: Record<FieldStatus, string> = {
  found: "Found",
  not_found: "Not found",
  conflict: "Conflict",
  failed: "Failed",
};

export const OPERATION_LABELS: Record<ChangeOperation, string> = {
  replace: "Replaced",
  amend: "Amended",
  add_requirement: "Added requirement",
  confirm: "Confirmed",
  clarify: "Clarified",
};

const dateTime = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
const dateOnly = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });
const relative = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : dateTime.format(d);
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  return Number.isNaN(d.getTime()) ? iso : dateOnly.format(d);
}

export function timeAgo(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "—";
  const seconds = Math.round((new Date(iso).getTime() - now) / 1000);
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["day", 86_400],
    ["hour", 3_600],
    ["minute", 60],
  ];
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) return relative.format(Math.round(seconds / size), unit);
  }
  return "just now";
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1) return "<1 ms";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
  const m = Math.floor(ms / 60_000);
  return `${m} m ${Math.round((ms % 60_000) / 1000)} s`;
}

export const formatCost = (usd: number | undefined) =>
  usd === undefined ? "—" : usd === 0 || usd >= 0.01 ? `$${usd.toFixed(2)}` : `$${usd.toFixed(4)}`;

export const formatNumber = (n: number | undefined) =>
  n === undefined ? "—" : new Intl.NumberFormat().format(n);

export const pagesLabel = (start: number, end: number) => (start === end ? `p. ${start}` : `pp. ${start}–${end}`);

export function valueText(value: string | string[] | null): string {
  if (value === null) return "";
  return Array.isArray(value) ? value.join(", ") : value;
}

/** What the model wrote about its search, without the "Not found" or "Extraction failed" prefix. */
export function searchEffort(notes: string | null): string | null {
  if (!notes) return null;
  return notes.replace(/^Not found in documents\.\s*/i, "").replace(/^Extraction failed:\s*/i, "") || null;
}

/** A comparison cell's source arrives as "file, p. N"; split it so it can be a cite. */
export function parseSourceRef(source: string): { file: string; page: string } | null {
  const match = /^(.+), p\. (\S+)$/.exec(source);
  return match ? { file: match[1] ?? "", page: match[2] ?? "" } : null;
}

/** The first sentence of a paragraph, for a one-line lead. */
export function firstSentence(text: string): string {
  const match = /^.*?[.!?](?=\s|$)/.exec(text.trim());
  return match ? match[0] : text.trim();
}

/** Split text into plain and highlighted parts for the given terms (case-insensitive). */
export function highlight(text: string, terms: string[]): { text: string; hit: boolean }[] {
  const words = [...new Set(terms.map((t) => t.trim()).filter((t) => t.length > 2))];
  if (!words.length) return [{ text, hit: false }];
  const escaped = words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const re = new RegExp(`(${escaped.join("|")})`, "gi");
  return text
    .split(re)
    .filter((part) => part !== "")
    .map((part) => ({ text: part, hit: words.some((w) => w.toLowerCase() === part.toLowerCase()) }));
}
