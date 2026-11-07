// Go / no-go: the bid's record checked against the company profile (config/company.yaml).
import { CircleCheck, CircleHelp, CircleX } from "lucide-react";
import { useState } from "react";

import { SourceChip } from "../components/domain";
import { ErrorState } from "../components/ui/feedback";
import { Badge, Input, Skeleton, type Tone } from "../components/ui/primitives";
import { useGoNoGo } from "../lib/queries";
import type { Decision, Recommendation, Verdict } from "../lib/types";

const DECISION_TONE: Record<Decision, Tone> = { go: "ok", "no-go": "bad", review: "warn" };
const DECISION_LABEL: Record<Decision, string> = { go: "Go", "no-go": "No-go", review: "Review" };

const VERDICT_ICON: Record<Verdict, JSX.Element> = {
  pass: <CircleCheck className="size-4 text-ok" aria-label="Pass" />,
  fail: <CircleX className="size-4 text-bad" aria-label="Fail" />,
  review: <CircleHelp className="size-4 text-warn" aria-label="Review" />,
};

export function DecisionBadge({ decision }: { decision: Decision }) {
  return <Badge tone={DECISION_TONE[decision]}>{DECISION_LABEL[decision]}</Badge>;
}

export function ChecksList({ rec }: { rec: Recommendation }) {
  return (
    <ul className="divide-y divide-line">
      {rec.checks.map((c) => (
        <li key={c.name} className="flex gap-3 px-4 py-3">
          <span className="mt-0.5 shrink-0">{VERDICT_ICON[c.verdict]}</span>
          <div className="min-w-0 flex-1">
            <p className="text-[13px] font-medium text-ink">{c.name}</p>
            <p className="text-[13px] text-muted">{c.detail}</p>
            {c.value && <p className="mt-1 truncate text-xs text-faint" title={c.value}>Extracted: {c.value}</p>}
            {c.sources[0] && (
              <div className="mt-1.5">
                <SourceChip bidId={rec.bid_id} file={c.sources[0].file} page={c.sources[0].page} />
              </div>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

export function GoNoGoPanel({ bidId }: { bidId: string }) {
  const [asOf, setAsOf] = useState("");
  const rec = useGoNoGo(bidId, asOf || undefined);

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
        <div className="flex items-center gap-2">
          {rec.data && <DecisionBadge decision={rec.data.decision} />}
          <p className="text-[13px] text-muted">
            {rec.data
              ? `Checked against ${rec.data.company}'s capabilities as of ${rec.data.as_of}. Rules, not a model call.`
              : "Checking the record against the company profile…"}
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
        <ChecksList rec={rec.data} />
      )}
      <p className="border-t border-line px-4 py-2 text-2xs text-faint">
        The company profile is <span className="font-mono">config/company.yaml</span>: authorized manufacturers, bond limit, delivery lead time,
        contract vehicles and more.
      </p>
    </div>
  );
}
