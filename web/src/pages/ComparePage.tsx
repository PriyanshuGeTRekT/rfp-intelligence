import { Columns3 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { Cite, DecisionMark, PageHeader, TierMeter, VerdictIcon } from "../components/domain";
import { EmptyState, ErrorState, InlineAlert } from "../components/ui/feedback";
import { Button, Input, Panel, SectionLabel, Skeleton } from "../components/ui/primitives";
import { cn } from "../lib/cn";
import { labelFromFile } from "../lib/docLabels";
import { formatCost, parseSourceRef } from "../lib/format";
import { useBids, useCompare } from "../lib/queries";
import type { Comparison, ComparisonCell } from "../lib/types";

const differs = (cells: ComparisonCell[]) => new Set(cells.map((c) => (c.status === "found" ? c.value : null))).size > 1;

function Cell({ bid, cell }: { bid: string; cell: ComparisonCell | undefined }) {
  if (!cell) return <td className="px-3 py-2.5 text-line-strong">—</td>;
  const missing = cell.status !== "found";
  const src = cell.source ? parseSourceRef(cell.source) : null;
  return (
    <td className="px-3 py-2.5 align-top">
      <div className="max-w-[18rem]">
        <p className={cn("break-words", missing && "italic", cell.status === "failed" ? "text-bad" : missing ? "text-muted" : "text-ink")}>
          {missing ? (cell.status === "failed" ? "Failed" : cell.status === "conflict" ? `Conflict: ${cell.value}` : "Not found") : cell.value}
        </p>
        <p className="mt-1 flex min-w-0 flex-wrap items-center gap-2">
          <TierMeter tier={cell.tier} size="sm" />
          {src ? (
            <Cite bidId={bid} doc={labelFromFile(src.file)} page={src.page} size="sm" />
          ) : (
            cell.source && (
              <span className="min-w-0 truncate font-mono text-[10.5px] text-faint" title={cell.source}>
                {cell.source}
              </span>
            )
          )}
        </p>
      </div>
    </td>
  );
}

function GoNoGoGrid({ data }: { data: Comparison }) {
  const names = [...new Set(data.recommendations.flatMap((r) => r.checks.map((c) => c.name)))];
  const first = data.recommendations[0];
  return (
    <section aria-labelledby="gng" className="mt-6">
      <SectionLabel id="gng" className="mb-2">
        Go / no-go
        {first && (
          <span className="ml-2 font-normal normal-case tracking-normal">
            checked against {first.company} as of {first.as_of} · rules, not a model call
          </span>
        )}
      </SectionLabel>
      <Panel className="overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-left text-xs">
          <thead className="bg-canvas">
            <tr>
              <th scope="col" className="caps w-40 px-3 py-2 font-medium">
                Check
              </th>
              {data.recommendations.map((r) => (
                <th key={r.bid_id} scope="col" className="px-3 py-2 font-mono text-sm font-medium">
                  <Link to={`/bids/${encodeURIComponent(r.bid_id)}`} className="hover:underline">
                    {r.bid_id}
                  </Link>
                  <DecisionMark decision={r.decision} className="ml-2.5 font-sans text-sm" />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {names.map((name) => (
              <tr key={name} className="border-t border-line align-top">
                <th scope="row" className="px-3 py-2 text-left font-medium">
                  {name}
                </th>
                {data.recommendations.map((r) => {
                  const check = r.checks.find((c) => c.name === name);
                  if (!check) return <td key={r.bid_id} className="px-3 py-2 text-line-strong">—</td>;
                  return (
                    <td key={r.bid_id} className={cn("px-3 py-2", check.verdict === "fail" && "bg-bad-soft", check.verdict === "review" && "bg-warn-soft")}>
                      <span className="flex items-start gap-1.5">
                        <VerdictIcon verdict={check.verdict} />
                        <span>
                          <span className={cn(check.verdict === "fail" && "font-semibold")}>{check.detail}</span>
                          {check.value && check.verdict !== "pass" && <span className="text-muted"> Extracted: {check.value}</span>}
                          {check.sources[0] && (
                            <Cite bidId={r.bid_id} doc={labelFromFile(check.sources[0].file)} page={check.sources[0].page} size="sm" className="ml-1.5 align-middle" />
                          )}
                        </span>
                      </span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </section>
  );
}

function SideBySide({ data }: { data: Comparison }) {
  return (
    <section aria-labelledby="sbs" className="mt-6">
      <SectionLabel id="sbs" className="mb-2">
        Side by side<span className="ml-2 font-normal normal-case tracking-normal">{data.rows.length} fields · a dot marks a row where the bids differ · tier and cite under each value</span>
      </SectionLabel>
      <Panel className="overflow-x-auto">
        <table className="w-full min-w-[760px] border-collapse text-left text-xs">
          <thead className="bg-canvas">
            <tr>
              <th scope="col" className="caps w-52 px-3 py-2 font-medium">
                Field
              </th>
              {data.bids.map((b) => (
                <th key={b} scope="col" className="px-3 py-2 font-mono text-sm font-medium">
                  <Link to={`/bids/${encodeURIComponent(b)}`} className="hover:underline">
                    {b}
                  </Link>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row) => {
              const cells = data.bids.map((b) => row.cells[b]).filter((c): c is ComparisonCell => Boolean(c));
              return (
                <tr key={row.key} className="border-t border-line align-top">
                  <th scope="row" className="px-3 py-2.5 text-left font-medium text-ink">
                    {differs(cells) && <span className="mr-2 inline-block size-1.5 rounded-full bg-ink align-[2px]" title="Values differ" aria-label="Values differ" />}
                    {row.name}
                  </th>
                  {data.bids.map((b) => (
                    <Cell key={b} bid={b} cell={row.cells[b]} />
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </Panel>
    </section>
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
      <PageHeader title="Compare bids" description="The extracted records side by side, each bid's go / no-go, and optionally the key differences written by the model." />
      <div className="border-y border-line py-3">
        {bids.isPending ? (
          <Skeleton className="h-8" />
        ) : bids.isError ? (
          <ErrorState compact error={bids.error} onRetry={() => bids.refetch()} />
        ) : extracted.length < 2 ? (
          <EmptyState compact icon={<Columns3 className="size-4" />} title="Two extracted bids are needed" description="Run extraction on at least two bids first." />
        ) : (
          <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
            <fieldset>
              <legend className="caps mb-1.5">Bids</legend>
              <div role="group" className="inline-flex overflow-hidden rounded border border-control">
                {extracted.map((b, i) => {
                  const on = chosen.includes(b.bid_id);
                  return (
                    <button
                      key={b.bid_id}
                      type="button"
                      aria-pressed={on}
                      onClick={() => toggle(b.bid_id)}
                      className={cn("h-7 px-3 font-mono text-xs font-medium", i > 0 && "border-l border-control", on ? "bg-ink text-canvas" : "bg-surface text-muted hover:text-ink")}
                    >
                      {b.bid_id}
                    </button>
                  );
                })}
              </div>
            </fieldset>
            <label className="flex items-center gap-2 pb-1.5 text-xs text-muted">
              <input type="checkbox" checked={summary} onChange={(e) => setSummary(e.target.checked)} className="size-3.5 accent-[rgb(var(--accent))]" />
              Write key differences (one model call)
            </label>
            <label className="flex items-center gap-2 text-xs text-muted">
              Deadlines as of
              <Input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} className="h-7 w-36" />
            </label>
            <Button variant="primary" disabled={chosen.length < 2 || compare.isPending} onClick={run} loading={compare.isPending}>
              {compare.isPending ? "Comparing…" : "Compare"}
            </Button>
          </div>
        )}
      </div>

      {compare.isError && <ErrorState error={compare.error} onRetry={run} />}
      {compare.data && (
        <>
          {compare.data.error && (
            <div className="mt-4">
              <InlineAlert tone="warn" title="The key differences could not be written">
                {compare.data.error}. The table below is complete.
              </InlineAlert>
            </div>
          )}
          {compare.data.recommendations.length > 0 && <GoNoGoGrid data={compare.data} />}
          {compare.data.summary && (
            <Panel className="mt-6 px-4 py-3.5">
              <SectionLabel className="mb-1.5">
                Key differences
                <span className="ml-2 font-normal normal-case tracking-normal">written by the model from the records below · {formatCost(compare.data.usage.cost_usd)}</span>
              </SectionLabel>
              <p className="max-w-4xl text-md text-ink">{compare.data.summary}</p>
              <dl className="mt-3 grid gap-x-8 gap-y-1 text-xs md:grid-cols-2">
                {compare.data.differences.map((d) => (
                  <div key={d.field} className="grid grid-cols-[150px_1fr] gap-2 border-t border-line py-1">
                    <dt className="font-medium text-ink">{compare.data.rows.find((r) => r.key === d.field)?.name ?? d.field}</dt>
                    <dd className="text-muted">{d.statement}</dd>
                  </div>
                ))}
              </dl>
            </Panel>
          )}
          <SideBySide data={compare.data} />
        </>
      )}
    </>
  );
}
