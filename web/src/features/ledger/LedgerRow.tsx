import { ChevronDown, ChevronRight } from "lucide-react";
import { forwardRef, type KeyboardEvent } from "react";

import { ChangeMark, Cite, TierMeter } from "../../components/domain";
import { cn } from "../../lib/cn";
import { labelFor, type DocLabels } from "../../lib/docLabels";
import { firstSentence, searchEffort } from "../../lib/format";
import type { AddendumChange, FieldResult, Source } from "../../lib/types";
import { FieldEvidence } from "./FieldEvidence";

const SHOWN_ITEMS = 3;
const SHOWN_CITES = 3;

/** One source per file and page, in order of first appearance. */
function uniqueSources(sources: Source[]): Source[] {
  const seen = new Set<string>();
  return sources.filter((s) => {
    const key = `${s.file}#${s.page}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function ValueCell({ field, changes }: { field: FieldResult; changes: AddendumChange[] }) {
  const display = typeof field.normalized?.display === "string" ? field.normalized.display : null;
  const effort = field.status === "found" ? null : searchEffort(field.notes);
  return (
    <div className="min-w-0">
      {field.value === null ? (
        <>
          <span className={cn("italic", field.status === "failed" ? "text-bad" : "text-muted")}>
            {field.status === "failed" ? "Failed" : "Not found in documents"}
          </span>
          {effort && <span className="mt-0.5 block text-xs text-faint">{firstSentence(effort)}</span>}
        </>
      ) : Array.isArray(field.value) ? (
        <>
          <ol className="list-decimal space-y-0.5 pl-5 font-medium">
            {field.value.slice(0, SHOWN_ITEMS).map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ol>
          {field.value.length > SHOWN_ITEMS && (
            <span className="mt-0.5 block text-xs text-muted">
              +{field.value.length - SHOWN_ITEMS} more: {field.value.slice(SHOWN_ITEMS).join("; ")}
            </span>
          )}
        </>
      ) : (
        <>
          <span className={cn(field.key === "bid_summary" ? "line-clamp-3" : "font-medium", field.key === "bid_number" && "font-mono")}>{field.value}</span>
          {display && display !== field.value && <span className="mt-0.5 block text-xs text-muted">{display}</span>}
        </>
      )}
      {changes.length > 0 && (
        <span className="mt-1 flex flex-wrap gap-x-2.5 gap-y-0.5">
          {changes.map((c, i) => (
            <ChangeMark key={i} change={c} />
          ))}
        </span>
      )}
    </div>
  );
}

export interface LedgerRowProps {
  index: number;
  name: string;
  field: FieldResult;
  bidId: string;
  docLabels?: DocLabels;
  changes: AddendumChange[];
  /** `pane`: a click selects the row and the evidence pane shows it. `inline`: a click expands it in place. */
  mode: "pane" | "inline";
  selected: boolean;
  expanded: boolean;
  onActivate: () => void;
  onKeyDown?: (e: KeyboardEvent<HTMLTableRowElement>) => void;
}

export const LedgerRow = forwardRef<HTMLTableRowElement, LedgerRowProps>(function LedgerRow(
  { index, name, field, bidId, docLabels, changes, mode, selected, expanded, onActivate, onKeyDown },
  ref,
) {
  const cites = uniqueSources(field.sources);
  const open = mode === "inline" && expanded;
  const active = mode === "pane" ? selected : expanded;
  return (
    <>
      <tr
        ref={ref}
        tabIndex={0}
        aria-selected={mode === "pane" ? selected : undefined}
        aria-expanded={mode === "inline" ? expanded : undefined}
        data-field={field.key}
        onClick={onActivate}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onActivate();
          } else onKeyDown?.(e);
        }}
        className={cn(
          "grid cursor-pointer grid-cols-[1.75rem_minmax(0,1fr)] border-t border-line py-1.5 align-top transition-colors hover:bg-subtle sm:table-row sm:py-0",
          active && "bg-accent-soft hover:bg-accent-soft",
        )}
      >
        <td className={cn("row-span-4 py-1 pl-3 font-mono text-2xs leading-5 text-faint sm:py-2.5", active && "shadow-[inset_3px_0_0_rgb(var(--accent))]")}>
          {mode === "inline" ? (
            expanded ? <ChevronDown className="mt-0.5 size-3.5 text-muted" aria-hidden /> : <ChevronRight className="mt-0.5 size-3.5" aria-hidden />
          ) : (
            index
          )}
        </td>
        <td className="px-3 py-1 sm:py-2.5">
          <span className="block font-medium text-ink">{name}</span>
          <span className="block font-mono text-2xs text-faint">{field.key}</span>
        </td>
        <td className="px-3 py-1 text-ink sm:py-2.5">
          <ValueCell field={field} changes={changes} />
        </td>
        <td className="px-3 py-1 sm:py-2.5" onClick={(e) => e.stopPropagation()}>
          <TierMeter tier={field.tier} confidence={field.confidence} />
        </td>
        <td className="px-3 py-1 sm:py-2" onClick={(e) => e.stopPropagation()}>
          {cites.length === 0 ? (
            <span className="text-xs text-line-strong">—</span>
          ) : (
            <div className="flex flex-wrap items-center gap-1">
              {cites.slice(0, SHOWN_CITES).map((s) => (
                <Cite key={`${s.file}#${s.page}`} bidId={bidId} doc={labelFor(docLabels, s.file)} page={s.page} />
              ))}
              {cites.length > SHOWN_CITES && <span className="num font-mono text-2xs text-faint">+{cites.length - SHOWN_CITES}</span>}
              {field.sources.length > 1 && <span className="num font-mono text-2xs text-faint">{field.sources.length} quotes</span>}
            </div>
          )}
        </td>
      </tr>
      {open && (
        <tr className="block border-t border-line bg-surface sm:table-row">
          <td colSpan={5} className="block p-0 sm:table-cell">
            <div className="border-l-[3px] border-accent">
              <FieldEvidence name={name} field={field} bidId={bidId} docLabels={docLabels} changes={changes} heading={false} />
            </div>
          </td>
        </tr>
      )}
    </>
  );
});
