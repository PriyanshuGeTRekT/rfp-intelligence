import { ChevronLeft, Download, FileSearch, Workflow } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { PageHeader } from "../components/domain";
import { EmptyState, ErrorState, InlineAlert } from "../components/ui/feedback";
import { TabList, TabPanel, Tabs } from "../components/ui/overlay";
import { Button, Card, Skeleton } from "../components/ui/primitives";
import { ChangesPanel, DocumentsPanel, ValidationPanel } from "../features/BidPanels";
import { ExtractButton } from "../features/ExtractButton";
import { FieldsTable } from "../features/FieldsTable";
import { GoNoGoPanel } from "../features/GoNoGo";
import { ApiError, downloadJson } from "../lib/api";
import { formatCost, formatDateTime } from "../lib/format";
import { useActiveJob, useBid, useResult } from "../lib/queries";

export function BidDetailPage() {
  const { bidId = "" } = useParams();
  const bid = useBid(bidId);
  const result = useResult(bidId);
  const active = useActiveJob(bidId);
  const [tab, setTab] = useState("fields");
  const navigate = useNavigate();

  if (bid.isError) {
    const missing = bid.error instanceof ApiError && bid.error.status === 404;
    return missing ? (
      <EmptyState
        title={`No bid named “${bidId}”`}
        description="It may have been removed from the data directory."
        action={
          <Link to="/" className="text-[13px] font-medium text-accent hover:underline">
            Back to bids
          </Link>
        }
      />
    ) : (
      <ErrorState error={bid.error} onRetry={() => bid.refetch()} />
    );
  }

  const record = result.data;
  const noResult = result.isError && result.error instanceof ApiError && result.error.status === 404;
  const summary = record ? Object.values(record.fields).find((f) => f.key === "bid_summary") : undefined;
  const title = record ? Object.values(record.fields).find((f) => f.key === "title")?.value : null;
  const fieldNames = record ? Object.fromEntries(Object.entries(record.fields).map(([name, f]) => [f.key, name])) : {};

  return (
    <>
      <Link to="/" className="mb-3 inline-flex items-center gap-1 text-xs text-muted hover:text-ink">
        <ChevronLeft className="size-3.5" aria-hidden />
        Bids
      </Link>
      <PageHeader
        title={typeof title === "string" ? title : bidId}
        description={typeof title === "string" ? <span className="font-mono text-xs">{bidId}</span> : undefined}
        meta={
          record && (
            <>
              <span>
                Extracted <time dateTime={record.generated_at}>{formatDateTime(record.generated_at)}</time>
              </span>
              <span className="num">{record.usage.calls ?? 0} model calls</span>
              {record.models?.extract && <span className="font-mono">{record.models.extract}</span>}
              <span className="num">{formatCost(record.usage.cost_usd)}</span>
            </>
          )
        }
        actions={
          <>
            {record && (
              <>
                <Button
                  variant="ghost"
                  icon={<Workflow className="size-3.5" aria-hidden />}
                  onClick={() => navigate(`/runs/${encodeURIComponent(record.run_id)}`)}
                >
                  Trace
                </Button>
                <Button icon={<Download className="size-3.5" aria-hidden />} onClick={() => downloadJson(`${bidId}.json`, record)}>
                  JSON
                </Button>
              </>
            )}
            <ExtractButton bidId={bidId} hasResult={Boolean(record)} />
          </>
        }
      />

      {active && record && (
        <div className="mb-4">
          <InlineAlert tone="info" title="A new extraction is running">
            This page shows the previous record until it finishes.
          </InlineAlert>
        </div>
      )}

      {summary?.value && typeof summary.value === "string" && (
        <Card className="mb-4 px-4 py-3">
          <p className="mb-1 text-2xs font-medium uppercase tracking-wide text-faint">Summary</p>
          <p className="max-w-3xl text-[13px] leading-relaxed text-ink">{summary.value}</p>
        </Card>
      )}

      {result.isPending || bid.isPending ? (
        <Card className="space-y-3 p-4">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-8" />
          ))}
        </Card>
      ) : noResult ? (
        <Card>
          <EmptyState
            icon={<FileSearch className="size-4" />}
            title={active ? "Extraction in progress" : "Not extracted yet"}
            description={
              active
                ? "The agents are reading the documents. On a free model tier this can take several minutes."
                : "Use Run extraction to produce the cited 20-field record for this bid."
            }
          />
          {bid.data && bid.data.files.length > 0 && (
            <div className="border-t border-line">
              <p className="px-4 pb-1 pt-3 text-2xs font-medium uppercase tracking-wide text-faint">Documents in this bid</p>
              <DocumentsPanel documents={bid.data.files} bidId={bidId} />
            </div>
          )}
        </Card>
      ) : result.isError ? (
        <ErrorState error={result.error} onRetry={() => result.refetch()} />
      ) : (
        record && (
          <Tabs value={tab} onValueChange={setTab}>
            <TabList
              items={[
                { value: "fields", label: "Fields", count: Object.keys(record.fields).length },
                { value: "changes", label: "Addendum changes", count: record.addendum_changes.length },
                { value: "documents", label: "Documents", count: record.documents.length },
                { value: "validation", label: "Validation" },
                { value: "gonogo", label: "Go / no-go" },
              ]}
            />
            <TabPanel value="fields">
              <Card className="overflow-hidden">
                <FieldsTable fields={record.fields} bidId={bidId} />
              </Card>
            </TabPanel>
            <TabPanel value="changes">
              <Card>
                <ChangesPanel changes={record.addendum_changes} fieldNames={fieldNames} bidId={bidId} />
              </Card>
            </TabPanel>
            <TabPanel value="documents">
              <Card className="overflow-hidden">
                <DocumentsPanel documents={bid.data?.files.length ? bid.data.files : record.documents} bidId={bidId} />
              </Card>
            </TabPanel>
            <TabPanel value="validation">
              <Card>
                <ValidationPanel result={record} />
              </Card>
            </TabPanel>
            <TabPanel value="gonogo">
              <Card className="overflow-hidden">
                <GoNoGoPanel bidId={bidId} />
              </Card>
            </TabPanel>
          </Tabs>
        )
      )}
    </>
  );
}
