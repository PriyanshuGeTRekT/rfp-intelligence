// Go / no-go: the bid's record checked against the company profile (config/company.yaml).
import { useState } from "react";

import { Cite, DecisionMark, VerdictIcon } from "../components/domain";
import { ErrorState } from "../components/ui/feedback";
import { Input, Skeleton } from "../components/ui/primitives";
import { cn } from "../lib/cn";
import { labelFor, type DocLabels } from "../lib/docLabels";
import { useGoNoGo } from "../lib/queries";
import type { Recommendation } from "../lib/types";

const failing = (rec: Recommendation) => rec.checks.filter((c) => c.verdict !== "pass");

/** One line under the bid header: the decision, the first check to look at, and the count. */
export function VerdictStrip({ bidId, onOpen }: { bidId: string; onOpen: () => void }) {
  const rec = useGoNoGo(bidId);
  if (rec.isError) return null;
  if (!rec.data) return <Skeleton className="h-4 w-64" />;
  const open = failing(rec.data);
  const first = open[0];
  return (
    <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-sm">
      <DecisionMark decision={rec.data.decision} />
      {first ? (
        <span>
          {first.name}: {first.detail}
        </span>
      ) : (
        <span>Every check passes.</span>
      )}
      <span className="num text-muted">
        {rec.data.checks.length - open.length} of {rec.data.checks.length} checks pass
      </span>
      <span className="num text-faint">as of {rec.data.as_of}</span>
      <button type="button" onClick={onOpen} className="font-medium text-accent hover:underline">
        Go / no-go →
      </button>
    </div>
  );
}

export function ChecksList({ rec, docLabels }: { rec: Recommendation; docLabels?: DocLabels }) {
  return (
    <ul className="divide-y divide-line">
      {rec.checks.map((c) => (
        <li
          key={c.name}
          className={cn("grid grid-cols-[20px_1fr] gap-x-3 gap-y-1 px-4 py-3 sm:grid-cols-[20px_140px_1fr_auto]", c.verdict === "fail" && "bg-bad-soft", c.verdict === "review" && "bg-warn-soft")}
        >
          <span className="mt-0.5">
            <VerdictIcon verdict={c.verdict} />
          </span>
          <p className="text-sm font-medium text-ink">{c.name}</p>
          <div className="col-start-2 min-w-0 sm:col-start-3">
            <p className="text-sm text-ink">{c.detail}</p>
            {c.value && (
              <p className="mt-0.5 truncate text-xs text-muted" title={c.value}>
                Extracted: {c.value}
              </p>
            )}
          </div>
          <div className="col-start-2 sm:col-start-4">
            {c.sources[0] ? (
              <Cite bidId={rec.bid_id} doc={labelFor(docLabels, c.sources[0].file)} page={c.sources[0].page} />
            ) : (
              <span className="text-2xs text-faint">no citation</span>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

export function GoNoGoPanel({ bidId, docLabels }: { bidId: string; docLabels?: DocLabels }) {
  const [asOf, setAsOf] = useState("");
  const rec = useGoNoGo(bidId, asOf || undefined);

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
        <div className="flex flex-wrap items-center gap-2.5">
          {rec.data && <DecisionMark decision={rec.data.decision} />}
          <p className="text-sm text-muted">
            {rec.data ? `Checked against ${rec.data.company}'s capabilities as of ${rec.data.as_of}. Rules, not a model call.` : "Checking the record against the company profile…"}
          </p>
        </div>
        <label className="flex items-center gap-2 text-xs text-muted">
          As of
          <Input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} className="h-7 w-36" />
        </label>
      </div>
      {rec.isPending ? (
        <div className="space-y-2 p-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-10" />
          ))}
        </div>
      ) : rec.isError ? (
        <ErrorState compact error={rec.error} onRetry={() => rec.refetch()} />
      ) : (
        <ChecksList rec={rec.data} docLabels={docLabels} />
      )}
      <p className="border-t border-line px-4 py-2 text-2xs text-faint">
        The company profile is <span className="font-mono">config/company.yaml</span>: authorized manufacturers, bond limit, delivery lead time, contract vehicles and more.
      </p>
    </div>
  );
}
