import { Activity, ChevronRight } from "lucide-react";
import { Link } from "react-router-dom";

import { JobBadge, PageHeader, ValidationBar } from "../components/domain";
import { EmptyState, ErrorState } from "../components/ui/feedback";
import { Card, Skeleton } from "../components/ui/primitives";
import { formatDateTime, formatDuration } from "../lib/format";
import { useBids, useJobs } from "../lib/queries";

export function RunsPage() {
  const jobs = useJobs();
  const bids = useBids();
  const latest = (bids.data ?? []).filter((b) => b.result);

  return (
    <>
      <PageHeader
        title="Runs"
        description="Extraction runs started here, and the latest run behind each bid's record. Every run leaves a trace: each agent step with its input, output, tokens and latency."
      />

      <Card className="mb-6 overflow-hidden">
        <div className="border-b border-line px-4 py-2.5 text-xs font-semibold">This session</div>
        {jobs.isError ? (
          <ErrorState compact error={jobs.error} onRetry={() => jobs.refetch()} />
        ) : jobs.isPending ? (
          <div className="space-y-2 p-4">
            <Skeleton className="h-6" />
            <Skeleton className="h-6" />
          </div>
        ) : jobs.data.length === 0 ? (
          <EmptyState
            compact
            icon={<Activity className="size-4" />}
            title="No runs since the server started"
            description="Start one from a bid with Run extraction."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left">
              <thead className="text-2xs font-medium uppercase tracking-wide text-muted">
                <tr className="border-b border-line">
                  <th className="py-2 pl-4 pr-3 font-medium">Status</th>
                  <th className="px-3 py-2 font-medium">Bid</th>
                  <th className="px-3 py-2 font-medium">Started</th>
                  <th className="px-3 py-2 font-medium">Duration</th>
                  <th className="px-3 py-2 font-medium">Result</th>
                  <th className="py-2 pl-3 pr-4" />
                </tr>
              </thead>
              <tbody>
                {jobs.data.map((job) => {
                  const end = job.finished_at ? new Date(job.finished_at).getTime() : Date.now();
                  const duration = job.started_at ? end - new Date(job.started_at).getTime() : null;
                  return (
                    <tr key={job.job_id} className="border-t border-line align-top">
                      <td className="py-3 pl-4 pr-3">
                        <JobBadge status={job.status} />
                      </td>
                      <td className="px-3 py-3">
                        <Link className="font-medium hover:underline" to={`/bids/${encodeURIComponent(job.bid_id)}`}>
                          {job.bid_id}
                        </Link>
                        <span className="block font-mono text-2xs text-faint">{job.run_id}</span>
                      </td>
                      <td className="px-3 py-3 text-xs text-muted">{formatDateTime(job.started_at ?? job.submitted_at)}</td>
                      <td className="num px-3 py-3 text-xs text-muted">{formatDuration(duration)}</td>
                      <td className="px-3 py-3">
                        {job.validation ? (
                          <ValidationBar tally={job.validation} />
                        ) : job.error ? (
                          <span className="line-clamp-2 max-w-xs text-xs text-bad">{job.error}</span>
                        ) : (
                          <span className="text-xs text-faint">—</span>
                        )}
                      </td>
                      <td className="py-3 pl-3 pr-4 text-right">
                        <Link to={`/runs/${encodeURIComponent(job.run_id)}`} className="inline-flex items-center gap-0.5 text-xs font-medium text-accent hover:underline">
                          Trace
                          <ChevronRight className="size-3.5" aria-hidden />
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {latest.length > 0 && (
        <Card className="overflow-hidden">
          <div className="border-b border-line px-4 py-2.5 text-xs font-semibold">Latest record per bid</div>
          <ul>
            {latest.map((b) => (
              <li key={b.bid_id} className="flex items-center justify-between gap-4 border-t border-line px-4 py-2.5 first:border-t-0">
                <div>
                  <Link className="font-medium hover:underline" to={`/bids/${encodeURIComponent(b.bid_id)}`}>
                    {b.bid_id}
                  </Link>
                  <span className="ml-2 font-mono text-2xs text-faint">{b.result?.run_id}</span>
                </div>
                <div className="flex items-center gap-4">
                  {b.result && <ValidationBar tally={b.result.validation} />}
                  <Link
                    to={`/runs/${encodeURIComponent(b.result?.run_id ?? "")}`}
                    className="inline-flex items-center gap-0.5 text-xs font-medium text-accent hover:underline"
                  >
                    Trace
                    <ChevronRight className="size-3.5" aria-hidden />
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}
