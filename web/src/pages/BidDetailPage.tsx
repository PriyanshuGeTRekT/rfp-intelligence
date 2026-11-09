import { Download, FileSearch, Workflow } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { ChangeMark, PageHeader, ValidationBar } from "../components/domain";
import { EmptyState, ErrorState, InlineAlert } from "../components/ui/feedback";
import { TabList, TabPanel, Tabs } from "../components/ui/overlay";
import { Button, Panel, SectionLabel, Skeleton } from "../components/ui/primitives";
import { ChangesPanel, DocumentsPanel, DocumentsRail, ValidationPanel } from "../features/BidPanels";
import { ExtractButton } from "../features/ExtractButton";
import { GoNoGoPanel, VerdictStrip } from "../features/GoNoGo";
import { Ledger } from "../features/ledger/Ledger";
import { PARAM } from "../features/ledger/params";
import { ApiError, downloadJson } from "../lib/api";
import { buildDocLabels } from "../lib/docLabels";
import { groupFields } from "../lib/fieldGroups";
import { firstSentence, formatCost, formatDateTime, formatDuration } from "../lib/format";
import { useActiveJob, useBid, useResult } from "../lib/queries";
import type { BidResult } from "../lib/types";

const fieldByKey = (record: BidResult, key: string) => Object.values(record.fields).find((f) => f.key === key);

function LoadingLedger() {
  return (
    <Panel className="p-4">
      <div className="space-y-3">
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="grid grid-cols-[190px_1fr_112px_210px] gap-3">
            <Skeleton className="h-3.5 w-28" />
            <Skeleton className="h-3.5" />
            <Skeleton className="h-3.5 w-12" />
            <Skeleton className="h-5 w-24" />
          </div>
        ))}
      </div>
    </Panel>
  );
}

export function BidDetailPage() {
  const { bidId = "" } = useParams();
  const bid = useBid(bidId);
  const result = useResult(bidId);
  const active = useActiveJob(bidId);
  const [tab, setTab] = useState("fields");
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();

  const record = result.data;
  const documents = useMemo(() => (bid.data?.files.length ? bid.data.files : (record?.documents ?? [])), [bid.data, record]);
  const docLabels = useMemo(() => buildDocLabels(documents), [documents]);
  const groups = useMemo(() => (record ? groupFields(record.fields) : []), [record]);

  if (bid.isError) {
    const missing = bid.error instanceof ApiError && bid.error.status === 404;
    return missing ? (
      <EmptyState
        title={`No bid named “${bidId}”`}
        description="It may have been removed from the data directory."
        action={
          <Link to="/" className="text-sm font-medium text-accent hover:underline">
            Back to bids
          </Link>
        }
      />
    ) : (
      <ErrorState error={bid.error} onRetry={() => bid.refetch()} />
    );
  }

  const noResult = result.isError && result.error instanceof ApiError && result.error.status === 404;
  const title = record ? fieldByKey(record, "title")?.value : null;
  const summary = record ? fieldByKey(record, "bid_summary")?.value : null;
  const number = record ? fieldByKey(record, "bid_number")?.value : null;
  const company = record ? fieldByKey(record, "company_name")?.value : null;
  const due = record ? fieldByKey(record, "due_date") : undefined;
  const dueChange = record ? [...record.addendum_changes].reverse().find((c) => c.field === "due_date") : undefined;
  const fieldNames = record ? Object.fromEntries(Object.entries(record.fields).map(([name, f]) => [f.key, name])) : {};

  const setParam = (name: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    setParams(next, { replace: true });
  };

  return (
    <>
      <PageHeader
        breadcrumb={
          <>
            <Link to="/" className="hover:text-ink">
              Bids
            </Link>
            <span className="mx-1.5 text-line-strong">/</span>
            <span className="font-mono">{bidId}</span>
          </>
        }
        title={typeof title === "string" ? title : bidId}
        meta={
          record && (
            <>
              {typeof title !== "string" && <span className="italic">Title not found</span>}
              {typeof number === "string" && <span className="font-mono text-ink">{number}</span>}
              {typeof company === "string" && <span>{company}</span>}
              {typeof due?.value === "string" && (
                <span className="flex items-center gap-2">
                  Due <span className="num font-medium text-ink">{due.value}</span>
                  {dueChange && <ChangeMark change={dueChange} />}
                </span>
              )}
            </>
          )
        }
        lead={
          typeof summary === "string" && (
            <>
              {firstSentence(summary)}{" "}
              <button type="button" onClick={() => setParam(PARAM.field, "bid_summary")} className="font-medium text-accent hover:underline">
                Full summary
              </button>
            </>
          )
        }
        actions={
          <>
            {record && (
              <>
                <Button variant="ghost" icon={<Workflow className="size-3.5" aria-hidden />} onClick={() => navigate(`/runs/${encodeURIComponent(record.run_id)}`)}>
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
            This page shows the previous record (run <span className="font-mono">{record.run_id}</span>) until it finishes.
          </InlineAlert>
        </div>
      )}

      {record && (
        <div className="mb-1 flex flex-wrap items-center justify-between gap-x-8 gap-y-2 border-y border-line py-2.5">
          <VerdictStrip bidId={bidId} onOpen={() => setTab("gonogo")} />
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <ValidationBar
              tally={record.validation}
              width="w-40"
              onPick={(status) => {
                setTab("fields");
                setParam(PARAM.status, status);
              }}
            />
            <span className="num text-xs text-faint">
              {record.validation.retries} retries, {record.validation.passed_after_retry} fixed by retry
            </span>
          </div>
        </div>
      )}

      {result.isPending || bid.isPending ? (
        <LoadingLedger />
      ) : noResult ? (
        <Panel>
          <EmptyState
            icon={<FileSearch className="size-4" />}
            title={active ? "Extraction in progress" : "Not extracted yet"}
            description={
              active
                ? "The agents are reading the documents. On a free model tier this can take several minutes."
                : "Use Run extraction to produce the cited 20-field record for this bid."
            }
          />
          {documents.length > 0 && (
            <div className="border-t border-line">
              <SectionLabel className="px-4 pb-1 pt-3">Documents in this bid</SectionLabel>
              <DocumentsPanel documents={documents} bidId={bidId} />
            </div>
          )}
        </Panel>
      ) : result.isError ? (
        <ErrorState error={result.error} onRetry={() => result.refetch()} />
      ) : (
        record && (
          <Tabs value={tab} onValueChange={setTab}>
            <TabList
              items={[
                { value: "fields", label: "Fields", count: Object.keys(record.fields).length },
                { value: "changes", label: "Changes", count: record.addendum_changes.length },
                { value: "documents", label: "Documents", count: documents.length },
                { value: "validation", label: "Validation" },
                { value: "gonogo", label: "Go / no-go" },
              ]}
            />
            <TabPanel value="fields">
              <div className="flex flex-wrap items-start gap-6">
                <aside aria-label="Documents and record" className="sticky top-16 hidden w-60 shrink-0 space-y-5 lg:block">
                  <DocumentsRail
                    documents={documents}
                    bidId={bidId}
                    changes={record.addendum_changes}
                    active={params.get(PARAM.doc)}
                    onToggle={(file) => setParam(PARAM.doc, file)}
                  />
                  <div>
                    <SectionLabel className="mb-1">Jump to</SectionLabel>
                    <ul className="text-xs">
                      {groups.map(({ group, entries }) => {
                        const failed = entries.filter(([, f]) => f.status === "failed" || f.status === "conflict").length;
                        const notFound = entries.filter(([, f]) => f.status === "not_found").length;
                        return (
                          <li key={group.id} className="flex justify-between gap-2 px-1.5 py-1">
                            <a href={`#group-${group.id}`} className="text-ink hover:underline">
                              {group.name}
                              {failed > 0 && <span className="ml-1.5 text-bad">· {failed} failed</span>}
                              {notFound > 0 && <span className="ml-1.5 text-muted">· {notFound} not found</span>}
                            </a>
                            <span className="num font-mono text-faint">{entries.length}</span>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                  <div>
                    <SectionLabel className="mb-1">Record</SectionLabel>
                    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs text-muted">
                      <dt>Run</dt>
                      <dd className="truncate font-mono text-2xs text-ink" title={record.run_id}>
                        {record.run_id}
                      </dd>
                      <dt>Extracted</dt>
                      <dd className="num text-ink">
                        <time dateTime={record.generated_at}>{formatDateTime(record.generated_at)}</time>
                      </dd>
                      {record.models?.extract && (
                        <>
                          <dt>Model</dt>
                          <dd className="truncate font-mono text-2xs text-ink">{record.models.extract}</dd>
                        </>
                      )}
                      <dt>Calls</dt>
                      <dd className="num text-ink">
                        {record.usage.calls ?? 0} · {formatCost(record.usage.cost_usd)}
                        {record.usage.latency_ms !== undefined && ` · ${formatDuration(record.usage.latency_ms)} model time`}
                      </dd>
                    </dl>
                  </div>
                </aside>
                <div className="min-w-0 flex-1 basis-[560px]">
                  <Ledger fields={record.fields} bidId={bidId} documents={documents} changes={record.addendum_changes} />
                </div>
              </div>
            </TabPanel>
            <TabPanel value="changes">
              <Panel>
                <ChangesPanel changes={record.addendum_changes} fieldNames={fieldNames} bidId={bidId} docLabels={docLabels} />
              </Panel>
            </TabPanel>
            <TabPanel value="documents">
              <Panel className="overflow-hidden">
                <DocumentsPanel documents={documents} bidId={bidId} changes={record.addendum_changes} />
              </Panel>
            </TabPanel>
            <TabPanel value="validation">
              <Panel>
                <ValidationPanel result={record} />
              </Panel>
            </TabPanel>
            <TabPanel value="gonogo">
              <Panel className="overflow-hidden">
                <GoNoGoPanel bidId={bidId} docLabels={docLabels} />
              </Panel>
            </TabPanel>
          </Tabs>
        )
      )}
    </>
  );
}
