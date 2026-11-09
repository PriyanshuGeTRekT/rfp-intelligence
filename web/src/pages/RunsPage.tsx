import { Activity } from "lucide-react";
import { Link } from "react-router-dom";

import { JobBadge, PageHeader, ValidationBar } from "../components/domain";
import { EmptyState, ErrorState } from "../components/ui/feedback";
import { Panel, Skeleton } from "../components/ui/primitives";
import { formatCost, formatDateTime, formatDuration } from "../lib/format";
import { useBids, useJobs } from "../lib/queries";

function SectionRow({ title, note }: { title: string; note?: string }) {
  return (
    <tr>
      <th colSpan={7} scope="rowgroup" className="caps border-t border-line px-4 pb-1 pt-3.5 text-left">
        {title}
        {note && <span className="ml-2 font-normal normal-case tracking-normal text-faint">{note}</span>}
      </th>
    </tr>
  );
}

export function RunsPage() {
  const jobs = useJobs();
  const bids = useBids();
  const latest = (bids.data ?? []).filter((b) => b.result);
  const running = jobs.data?.filter((j) => j.status === "running" || j.status === "queued").length ?? 0;

  return (
    <div className="mx-auto max-w-[1200px]">
      <PageHeader
        title="Runs"
        description="Extraction runs started here, and the latest run behind each bid's record. Every run leaves a trace: each agent step with its input, output, tokens and latency."
      />

      <Panel className="overflow-hidden">
        {jobs.isError ? (
          <ErrorState compact error={jobs.error} onRetry={() => jobs.refetch()} />
        ) : jobs.isPending ? (
          <div className="space-y-2 p-4">
            <Skeleton className="h-6" />
            <Skeleton className="h-6" />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[880px] text-left">
              <thead className="caps bg-canvas">
                <tr>
                  <th scope="col" className="w-28 py-2 pl-4 pr-3 font-medium">
                    Status
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    Bid · run
                  </th>
                  <th scope="col" className="w-40 px-3 py-2 font-medium">
                    Started
                  </th>
                  <th scope="col" className="w-24 px-3 py-2 text-right font-medium">
                    Duration
                  </th>
                  <th scope="col" className="w-20 px-3 py-2 text-right font-medium">
                    Cost
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    Result
                  </th>
                  <th scope="col" className="w-20 py-2 pl-3 pr-4">
                    <span className="sr-only">Trace</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                <SectionRow title="This session" note={jobs.data.length ? `${jobs.data.length} ${jobs.data.length === 1 ? "run" : "runs"} · ${running} running` : undefined} />
                {jobs.data.length === 0 && (
                  <tr>
                    <td colSpan={7}>
                      <EmptyState compact icon={<Activity className="size-4" />} title="No runs since the server started" description="Start one from a bid with Run extraction." />
                    </td>
                  </tr>
                )}
                {jobs.data.map((job) => {
                  const end = job.finished_at ? new Date(job.finished_at).getTime() : Date.now();
                  const duration = job.started_at ? end - new Date(job.started_at).getTime() : null;
                  return (
                    <tr key={job.job_id} className="border-t border-line align-top">
                      <td className="py-2.5 pl-4 pr-3">
                        <JobBadge status={job.status} />
                      </td>
                      <td className="px-3 py-2.5">
                        <Link className="font-mono font-medium hover:underline" to={`/bids/${encodeURIComponent(job.bid_id)}`}>
                          {job.bid_id}
                        </Link>
                        <span className="block font-mono text-2xs text-faint">{job.run_id}</span>
                      </td>
                      <td className="num px-3 py-2.5 text-xs text-muted">{formatDateTime(job.started_at ?? job.submitted_at)}</td>
                      <td className="num px-3 py-2.5 text-right text-xs text-muted">{formatDuration(duration)}</td>
                      <td className="px-3 py-2.5 text-right text-xs text-line-strong">—</td>
                      <td className="px-3 py-2.5">
                        {job.validation ? (
                          <ValidationBar tally={job.validation} className="flex-col items-start" />
                        ) : job.error ? (
                          <span className="line-clamp-2 max-w-xs font-mono text-2xs text-bad">{job.error}</span>
                        ) : (
                          <span className="text-xs text-line-strong">—</span>
                        )}
                      </td>
                      <td className="py-2.5 pl-3 pr-4 text-right">
                        <Link to={`/runs/${encodeURIComponent(job.run_id)}`} className="whitespace-nowrap text-xs font-medium text-accent hover:underline">
                          Trace →
                        </Link>
                      </td>
                    </tr>
                  );
                })}

                {latest.length > 0 && <SectionRow title="Latest record per bid" note="what the Bids page shows; may predate this server session" />}
                {latest.map((b) => (
                  <tr key={b.bid_id} className="border-t border-line align-top">
                    <td className="py-2.5 pl-4 pr-3 text-xs text-muted">Record</td>
                    <td className="px-3 py-2.5">
                      <Link className="font-mono font-medium hover:underline" to={`/bids/${encodeURIComponent(b.bid_id)}`}>
                        {b.bid_id}
                      </Link>
                      <span className="block font-mono text-2xs text-faint">{b.result?.run_id}</span>
                    </td>
                    <td className="num px-3 py-2.5 text-xs text-muted">{formatDateTime(b.result?.generated_at)}</td>
                    <td className="px-3 py-2.5 text-right text-xs text-line-strong">—</td>
                    <td className="num px-3 py-2.5 text-right text-xs text-muted">{formatCost(b.result?.cost_usd)}</td>
                    <td className="px-3 py-2.5">{b.result && <ValidationBar tally={b.result.validation} className="flex-col items-start" />}</td>
                    <td className="py-2.5 pl-3 pr-4 text-right">
                      <Link to={`/runs/${encodeURIComponent(b.result?.run_id ?? "")}`} className="whitespace-nowrap text-xs font-medium text-accent hover:underline">
                        Trace →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      <p className="mt-3 text-xs text-faint">
        Jobs are polled every 2 s while one is queued or running; a finished job refreshes its bid and raises a toast. Traces are read from the server's{" "}
        <span className="font-mono">traces/</span> folder.
      </p>
    </div>
  );
}
