import { ChevronRight, FolderOpen } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { PageHeader, Stat, ValidationBar } from "../components/domain";
import { EmptyState, ErrorState } from "../components/ui/feedback";
import { Badge, Card, Skeleton } from "../components/ui/primitives";
import { ExtractButton } from "../features/ExtractButton";
import { docTypeLabel, formatCost, timeAgo } from "../lib/format";
import { useBids } from "../lib/queries";
import type { BidSummary } from "../lib/types";

function Row({ bid }: { bid: BidSummary }) {
  const navigate = useNavigate();
  const result = bid.result;
  const open = () => navigate(`/bids/${encodeURIComponent(bid.bid_id)}`);
  return (
    <tr className="group cursor-pointer border-t border-line hover:bg-subtle/60" onClick={open}>
      <td className="py-3 pl-4 pr-3">
        <Link
          to={`/bids/${encodeURIComponent(bid.bid_id)}`}
          className="font-medium text-ink hover:underline"
          onClick={(e) => e.stopPropagation()}
        >
          {bid.bid_id}
        </Link>
        <p className="mt-0.5 line-clamp-1 max-w-sm text-xs text-muted">{result ? (result.title ?? "Title not found") : bid.indexed ? "Not extracted yet" : "Not indexed yet"}</p>
      </td>
      <td className="num px-3 py-3 text-[13px]">{result?.due_date ?? <span className="text-faint">—</span>}</td>
      <td className="px-3 py-3">
        <div className="flex max-w-[260px] flex-wrap gap-1">
          {Object.entries(bid.doc_types)
            .slice(0, 4)
            .map(([type, n]) => (
              <Badge key={type} tone={type === "addendum" ? "accent" : "neutral"}>
                {docTypeLabel(type)}
                {n > 1 && <span className="num text-faint">×{n}</span>}
              </Badge>
            ))}
          {bid.documents === 0 && <span className="text-xs text-faint">—</span>}
        </div>
        {bid.documents > 0 && <p className="num mt-1 text-2xs text-faint">{bid.documents} files</p>}
      </td>
      <td className="px-3 py-3">{result ? <ValidationBar tally={result.validation} /> : <span className="text-xs text-faint">—</span>}</td>
      <td className="px-3 py-3 text-xs text-muted">
        {result ? (
          <>
            <span title={result.generated_at}>{timeAgo(result.generated_at)}</span>
            <span className="num block text-2xs text-faint">{formatCost(result.cost_usd)}</span>
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
          {["w-32", "w-20", "w-28", "w-24", "w-14", "w-20"].map((w, j) => (
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
      failed: acc.failed + (b.result?.validation.failed ?? 0),
      cost: acc.cost + (b.result?.cost_usd ?? 0),
    }),
    { passed: 0, fields: 0, failed: 0, cost: 0 },
  );

  return (
    <>
      <PageHeader
        title="Bids"
        description="Each bid folder becomes one structured record: 20 fields, every value cited to a file and page, with addendum changes applied."
      />

      {bids.isSuccess && data.length > 0 && (
        <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Bids" value={data.length} hint={`${data.filter((b) => b.indexed).length} indexed`} />
          <Stat label="Extracted" value={extracted.length} hint={`${data.length - extracted.length} pending`} />
          <Stat
            label="Fields validated"
            value={totals.fields ? `${Math.round((totals.passed / totals.fields) * 100)}%` : "—"}
            hint={totals.fields ? `${totals.passed} of ${totals.fields}` : "no records yet"}
            tone="ok"
          />
          <Stat label="Model spend" value={formatCost(totals.cost)} hint="latest run per bid" />
        </div>
      )}

      <Card className="overflow-hidden">
        {bids.isError ? (
          <ErrorState error={bids.error} onRetry={() => bids.refetch()} />
        ) : bids.isSuccess && data.length === 0 ? (
          <EmptyState
            icon={<FolderOpen className="size-4" />}
            title="No bid folders yet"
            description={
              <>
                Put each bid's documents (PDF, HTML) in its own folder under <code className="font-mono">data/bids</code>, then run
                extraction here or with <code className="font-mono">python main.py --bid PATH</code>.
              </>
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-left">
              <thead className="bg-subtle/60 text-2xs font-medium uppercase tracking-wide text-muted">
                <tr>
                  <th className="py-2 pl-4 pr-3 font-medium">Bid</th>
                  <th className="px-3 py-2 font-medium">Due date</th>
                  <th className="px-3 py-2 font-medium">Documents</th>
                  <th className="px-3 py-2 font-medium">Validation</th>
                  <th className="px-3 py-2 font-medium">Last run</th>
                  <th className="py-2 pl-3 pr-4">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>{bids.isPending ? <LoadingRows /> : data.map((bid) => <Row key={bid.bid_id} bid={bid} />)}</tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
