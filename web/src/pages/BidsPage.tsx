import { ChevronRight, FolderOpen } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { DecisionMark, PageHeader, ValidationBar } from "../components/domain";
import { EmptyState, ErrorState } from "../components/ui/feedback";
import { Panel, Skeleton, Tag } from "../components/ui/primitives";
import { ExtractButton } from "../features/ExtractButton";
import { docTypeLabel, formatCost, timeAgo } from "../lib/format";
import { useBids, useGoNoGo } from "../lib/queries";
import type { BidSummary } from "../lib/types";

function Verdict({ bid }: { bid: BidSummary }) {
  const rec = useGoNoGo(bid.bid_id, undefined, Boolean(bid.result));
  if (!bid.result) return <span className="text-xs text-line-strong">—</span>;
  if (rec.isPending) return <Skeleton className="h-4 w-16" />;
  if (rec.isError) return <span className="text-xs text-faint">—</span>;
  const open = rec.data.checks.filter((c) => c.verdict !== "pass");
  return (
    <>
      <DecisionMark decision={rec.data.decision} className="text-sm" />
      {open.length > 0 && <p className="mt-0.5 line-clamp-1 text-xs text-muted">{open.map((c) => c.name).join(", ")}</p>}
    </>
  );
}

function Row({ bid }: { bid: BidSummary }) {
  const navigate = useNavigate();
  const result = bid.result;
  const open = () => navigate(`/bids/${encodeURIComponent(bid.bid_id)}`);
  return (
    <tr className="group cursor-pointer border-t border-line align-top hover:bg-subtle" onClick={open}>
      <td className="py-3 pl-4 pr-3">
        <Link to={`/bids/${encodeURIComponent(bid.bid_id)}`} className="font-mono font-medium text-ink hover:underline" onClick={(e) => e.stopPropagation()}>
          {bid.bid_id}
        </Link>
        <p className={result?.title ? "font-medium" : "italic text-muted"}>
          {result ? (result.title ?? "Title not found") : bid.indexed ? "Not extracted yet" : "Not indexed yet"}
        </p>
      </td>
      <td className="num px-3 py-3 whitespace-nowrap">{result?.due_date ?? <span className="text-line-strong">—</span>}</td>
      <td className="px-3 py-3">
        <div className="flex max-w-[280px] flex-wrap gap-1">
          {Object.entries(bid.doc_types).map(([type, n]) => (
            <Tag key={type} tone={type === "addendum" ? "accent" : "neutral"}>
              {docTypeLabel(type)}
              {n > 1 && <span className="num font-mono text-faint">×{n}</span>}
            </Tag>
          ))}
          {bid.documents === 0 && <span className="text-xs text-line-strong">—</span>}
        </div>
        {bid.documents > 0 && (
          <p className="num mt-1 text-2xs text-faint">
            {bid.documents} {bid.documents === 1 ? "file" : "files"}
          </p>
        )}
      </td>
      <td className="px-3 py-3">{result ? <ValidationBar tally={result.validation} className="flex-col items-start" /> : <span className="text-xs text-line-strong">—</span>}</td>
      <td className="px-3 py-3">
        <Verdict bid={bid} />
      </td>
      <td className="num px-3 py-3 text-xs text-muted whitespace-nowrap">
        {result ? (
          <>
            <span title={result.generated_at}>{timeAgo(result.generated_at)}</span>
            <span className="block font-mono text-2xs text-faint">{formatCost(result.cost_usd)}</span>
          </>
        ) : (
          "—"
        )}
      </td>
      <td className="py-3 pl-3 pr-4 text-right" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-end gap-2">
          <ExtractButton bidId={bid.bid_id} hasResult={Boolean(result)} size="sm" />
          <ChevronRight className="size-4 text-faint group-hover:text-muted" aria-hidden />
        </div>
      </td>
    </tr>
  );
}

function LoadingRows() {
  return (
    <>
      {[0, 1, 2].map((i) => (
        <tr key={i} className="border-t border-line">
          {["w-32", "w-20", "w-28", "w-24", "w-16", "w-14", "w-20"].map((w, j) => (
            <td key={j} className="px-4 py-4">
              <Skeleton className={`h-3.5 ${w}`} />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

export function BidsPage() {
  const bids = useBids();
  const data = bids.data ?? [];
  const extracted = data.filter((b) => b.result);
  const totals = extracted.reduce(
    (acc, b) => ({
      passed: acc.passed + (b.result?.validation.passed ?? 0),
      fields: acc.fields + (b.result?.validation.fields ?? 0),
      cost: acc.cost + (b.result?.cost_usd ?? 0),
    }),
    { passed: 0, fields: 0, cost: 0 },
  );

  return (
    <>
      <PageHeader
        title="Bids"
        description="Each bid folder becomes one structured record: 20 fields, every value cited to a file and page, with addendum changes applied."
        actions={
          bids.isSuccess &&
          data.length > 0 && (
            <p className="num flex flex-wrap gap-x-3.5 gap-y-1 text-xs text-muted">
              <span>
                <strong className="font-semibold text-ink">{data.length}</strong> bids
              </span>
              <span>
                <strong className="font-semibold text-ink">{data.filter((b) => b.indexed).length}</strong> indexed
              </span>
              <span>
                <strong className="font-semibold text-ink">{extracted.length}</strong> extracted
              </span>
              {totals.fields > 0 && (
                <span>
                  <strong className="font-semibold text-ink">{totals.passed}</strong> of {totals.fields} fields passed ({Math.round((totals.passed / totals.fields) * 100)} %)
                </span>
              )}
              <span>
                <strong className="font-semibold text-ink">{formatCost(totals.cost)}</strong> model spend, latest run per bid
              </span>
            </p>
          )
        }
      />

      <Panel className="overflow-hidden">
        {bids.isError ? (
          <ErrorState error={bids.error} onRetry={() => bids.refetch()} />
        ) : bids.isSuccess && data.length === 0 ? (
          <EmptyState
            icon={<FolderOpen className="size-4" />}
            title="No bid folders yet"
            description={
              <>
                Put each bid's documents (PDF, HTML) in its own folder under <code className="font-mono">data/bids</code>, then run extraction here or with{" "}
                <code className="font-mono">python main.py --bid PATH</code>.
              </>
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[960px] text-left">
              <thead className="caps bg-canvas">
                <tr>
                  <th scope="col" className="py-2 pl-4 pr-3 font-medium">
                    Bid
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    Due
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    Documents
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    Record
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    Go / no-go
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    Last run
                  </th>
                  <th scope="col" className="py-2 pl-3 pr-4">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>{bids.isPending ? <LoadingRows /> : data.map((bid) => <Row key={bid.bid_id} bid={bid} />)}</tbody>
            </table>
          </div>
        )}
      </Panel>
      <p className="mt-3 text-xs text-faint">
        Record = the validator's outcome per field. Go / no-go is checked against <span className="font-mono">config/company.yaml</span>; open a bid for the checks and their citations.
      </p>
    </>
  );
}
