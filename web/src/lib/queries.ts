import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { toast } from "sonner";

import { api, ApiError, type SearchParams } from "./api";
import type { Job } from "./types";

export const keys = {
  health: ["health"] as const,
  bids: ["bids"] as const,
  bid: (id: string) => ["bids", id] as const,
  result: (id: string) => ["bids", id, "result"] as const,
  jobs: ["jobs"] as const,
  trace: (runId: string) => ["trace", runId] as const,
  configs: ["search", "configs"] as const,
  search: (p: SearchParams) => ["search", p] as const,
  goNoGo: (id: string, asOf?: string) => ["bids", id, "go-no-go", asOf ?? "today"] as const,
};

const noRetryOn404 = (count: number, error: unknown) =>
  !(error instanceof ApiError && [400, 401, 404].includes(error.status)) && count < 2;

export const useHealth = () =>
  useQuery({ queryKey: keys.health, queryFn: api.health, refetchInterval: 30_000, retry: 1 });

export const useBids = () => useQuery({ queryKey: keys.bids, queryFn: api.bids });

export const useBid = (bidId: string) =>
  useQuery({ queryKey: keys.bid(bidId), queryFn: () => api.bid(bidId), retry: noRetryOn404 });

export const useResult = (bidId: string) =>
  useQuery({ queryKey: keys.result(bidId), queryFn: () => api.result(bidId), retry: noRetryOn404 });

export const useTrace = (runId: string) =>
  useQuery({ queryKey: keys.trace(runId), queryFn: () => api.trace(runId), retry: noRetryOn404 });

export const useSearchConfigs = () =>
  useQuery({ queryKey: keys.configs, queryFn: api.searchConfigs, staleTime: Infinity });

export const useSearch = (params: SearchParams | null) =>
  useQuery({
    queryKey: params ? keys.search(params) : ["search", "idle"],
    queryFn: () => api.search(params as SearchParams),
    enabled: params !== null && params.q.trim().length > 0,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });

const isActive = (job: Job) => job.status === "queued" || job.status === "running";

/** Jobs, polled every 2 s while any is active. Finished jobs refresh the bid they ran on. */
export function useJobs() {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: keys.jobs,
    queryFn: api.jobs,
    refetchInterval: (q) => (q.state.data?.some(isActive) ? 2_000 : false),
  });
  const seen = useRef(new Map<string, Job["status"]>());

  useEffect(() => {
    for (const job of query.data ?? []) {
      const before = seen.current.get(job.job_id);
      seen.current.set(job.job_id, job.status);
      if (!before || before === job.status || isActive(job)) continue;
      void client.invalidateQueries({ queryKey: keys.bids });
      if (job.status === "succeeded") {
        toast.success(`Extraction finished for ${job.bid_id}`, {
          description: job.validation
            ? `${job.validation.passed} passed · ${job.validation.not_found} not found · ${job.validation.failed} failed`
            : undefined,
        });
      } else {
        toast.error(`Extraction failed for ${job.bid_id}`, { description: job.error ?? undefined });
      }
    }
  }, [query.data, client]);

  return query;
}

export function useActiveJob(bidId: string): Job | undefined {
  const { data } = useJobs();
  return data?.find((j) => j.bid_id === bidId && isActive(j));
}

export function useStartExtraction() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (bidId: string) => api.extract(bidId),
    onSuccess: (job) => {
      client.setQueryData<Job[]>(keys.jobs, (jobs) => [job, ...(jobs ?? []).filter((j) => j.job_id !== job.job_id)]);
      void client.invalidateQueries({ queryKey: keys.jobs });
      toast(`Extraction started for ${job.bid_id}`, {
        description: "Runs in the background. You can keep working.",
      });
    },
    onError: (error) => toast.error("Could not start extraction", { description: (error as Error).message }),
  });
}

export const useAsk = () =>
  useMutation({ mutationFn: ({ question, bidId }: { question: string; bidId?: string }) => api.ask(question, bidId) });

export const useGoNoGo = (bidId: string, asOf?: string, enabled = true) =>
  useQuery({
    queryKey: keys.goNoGo(bidId, asOf),
    queryFn: () => api.goNoGo(bidId, asOf),
    enabled,
    retry: noRetryOn404,
  });

/** A comparison is requested explicitly (the written differences cost a model call). */
export const useCompare = () =>
  useMutation({
    mutationFn: ({ bids, summary, asOf }: { bids: string[]; summary: boolean; asOf?: string }) =>
      api.compare(bids, summary, asOf),
  });
