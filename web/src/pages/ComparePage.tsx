import { Columns3 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { PageHeader } from "../components/domain";
import { EmptyState, ErrorState, InlineAlert } from "../components/ui/feedback";
import { Badge, Button, Card, Input, Skeleton } from "../components/ui/primitives";
import { DecisionBadge } from "../features/GoNoGo";
import { formatCost } from "../lib/format";
import { useBids, useCompare } from "../lib/queries";
import type { Comparison } from "../lib/types";

function SideBySide({ data }: { data: Comparison }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-collapse text-left text-[13px]">
        <thead>
          <tr className="text-2xs uppercase tracking-wide text-faint">
            <th className="w-48 px-4 py-2 font-medium">Field</th>
            {data.bids.map((b) => (
              <th key={b} className="px-4 py-2 font-medium">
                <Link to={`/bids/${encodeURIComponent(b)}`} className="hover:underline">
                  {b}
                </Link>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.recommendations.length > 0 && (
            <tr className="border-t border-line bg-subtle/40">
              <td className="px-4 py-2.5 font-medium text-ink">Go / no-go</td>
              {data.recommendations.map((r) => (
                <td key={r.bid_id} className="px-4 py-2.5">
                  <DecisionBadge decision={r.decision} />
                  <span className="ml-2 text-xs text-muted">
                    {r.checks
                      .filter((c) => c.verdict !== "pass")
                      .map((c) => c.name)
                      .join(", ") || "all checks pass"}
                  </span>
                </td>
              ))}
            </tr>
          )}
          {data.rows.map((row) => (
            <tr key={row.key} className="border-t border-line align-top">
              <td className="px-4 py-2.5 font-medium text-ink">{row.name}</td>
              {data.bids.map((b) => {
                const cell = row.cells[b];
                if (!cell) return <td key={b} className="px-4 py-2.5 text-faint">—</td>;
                const missing = cell.status !== "found";
                return (
                  <td key={b} className="px-4 py-2.5">
                    <div className="max-w-[17rem]">
                      <p className={`break-words ${missing ? "text-faint" : "text-ink"}`}>{cell.value}</p>
                      <p className="mt-1 flex min-w-0 items-center gap-1.5 text-2xs text-faint">
                        <Badge className="shrink-0 font-mono">{cell.tier}</Badge>
                        {cell.source && (
                          <span className="min-w-0 truncate" title={cell.source}>
                            {cell.source}
                          </span>
                        )}
                      </p>
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ComparePage() {
  const bids = useBids();
  const compare = useCompare();
  const [chosen, setChosen] = useState<string[]>([]);
  const [summary, setSummary] = useState(false);
  const [asOf, setAsOf] = useState("");
  const extracted = (bids.data ?? []).filter((b) => b.result);

  const toggle = (id: string) => setChosen((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]));
  const run = () => compare.mutate({ bids: chosen, summary, asOf: asOf || undefined });

  return (
    <>
      <PageHeader
        title="Compare bids"
        description="The extracted records side by side, each bid's go / no-go, and optionally the key differences written by the model."
      />
      <Card className="mb-4 p-4">
        {bids.isPending ? (
          <Skeleton className="h-8" />
        ) : bids.isError ? (
          <ErrorState compact error={bids.error} onRetry={() => bids.refetch()} />
        ) : extracted.length < 2 ? (
          <EmptyState compact icon={<Columns3 className="size-4" />} title="Two extracted bids are needed" description="Run extraction on at least two bids first." />
        ) : (
          <div className="flex flex-wrap items-end gap-4">
            <fieldset>
              <legend className="mb-1.5 text-xs text-muted">Bids</legend>
              <div className="flex flex-wrap gap-1.5">
                {extracted.map((b) => (
                  <button
                    key={b.bid_id}
                    type="button"
                    aria-pressed={chosen.includes(b.bid_id)}
                    onClick={() => toggle(b.bid_id)}
                    className="rounded-md border border-line px-2.5 py-1 text-[13px] text-muted hover:border-line-strong aria-pressed:border-accent aria-pressed:bg-accent-soft aria-pressed:text-accent-ink"
                  >
                    {b.bid_id}
                  </button>
                ))}
              </div>
            </fieldset>
            <label className="flex items-center gap-2 text-xs text-muted">
              <input type="checkbox" checked={summary} onChange={(e) => setSummary(e.target.checked)} />
              Write key differences (one model call)
            </label>
            <label className="flex items-center gap-2 text-xs text-muted">
              Deadlines as of
              <Input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} className="h-7 w-36" />
            </label>
            <Button variant="primary" disabled={chosen.length < 2 || compare.isPending} onClick={run}>
              {compare.isPending ? "Comparing…" : "Compare"}
            </Button>
          </div>
        )}
      </Card>

      {compare.isError && <ErrorState error={compare.error} onRetry={run} />}
      {compare.data && (
        <>
          {compare.data.error && (
            <div className="mb-4">
              <InlineAlert tone="warn" title="The key differences could not be written">
                {compare.data.error}. The table below is complete.
              </InlineAlert>
            </div>
          )}
          {compare.data.summary && (
            <Card className="mb-4 px-4 py-3">
              <p className="mb-1 text-2xs font-medium uppercase tracking-wide text-faint">Key differences</p>
              <p className="max-w-3xl text-[13px] leading-relaxed text-ink">{compare.data.summary}</p>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-[13px] text-ink">
                {compare.data.differences.map((d) => (
                  <li key={d.field}>
                    <span className="font-medium">{compare.data.rows.find((r) => r.key === d.field)?.name ?? d.field}:</span> {d.statement}
                  </li>
                ))}
              </ul>
              <p className="num mt-2 text-2xs text-faint">{formatCost(compare.data.usage.cost_usd)}</p>
            </Card>
          )}
          <Card className="overflow-hidden">
            <SideBySide data={compare.data} />
          </Card>
        </>
      )}
    </>
  );
}
