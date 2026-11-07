import { KEYS, readStored } from "./storage";
import type {
  BidDetail,
  BidResult,
  BidSummary,
  Comparison,
  Health,
  Job,
  QAResult,
  Recommendation,
  SearchConfigInfo,
  SearchResult,
  TraceSpan,
} from "./types";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function headers(extra?: HeadersInit): Headers {
  const h = new Headers(extra);
  const key = readStored<string | null>(KEYS.apiKey, null);
  if (key) h.set("X-API-Key", key);
  return h;
}

async function detail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((d: { msg?: string; loc?: unknown[] }) => `${d.loc?.slice(1).join(".") ?? ""} ${d.msg ?? ""}`.trim())
        .join("; ");
    }
  } catch {
    // not JSON
  }
  return response.statusText || `Request failed (${response.status})`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { ...init, headers: headers(init.headers) });
  } catch {
    throw new ApiError(0, "The server could not be reached. Check that the API is running.");
  }
  if (!response.ok) throw new ApiError(response.status, await detail(response));
  return (await response.json()) as T;
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

export interface SearchParams {
  q: string;
  bidId?: string;
  docTypes?: string[];
  config?: string;
  topK?: number;
}

export const api = {
  health: () => request<Health>("/api/health"),
  bids: () => request<BidSummary[]>("/api/bids"),
  bid: (bidId: string) => request<BidDetail>(`/api/bids/${encodeURIComponent(bidId)}`),
  result: (bidId: string) => request<BidResult>(`/api/bids/${encodeURIComponent(bidId)}/result`),
  extract: (bidId: string) => post<Job>(`/api/bids/${encodeURIComponent(bidId)}/extract`),
  jobs: () => request<Job[]>("/api/jobs"),
  job: (jobId: string) => request<Job>(`/api/jobs/${encodeURIComponent(jobId)}`),
  trace: (runId: string) => request<TraceSpan[]>(`/api/runs/${encodeURIComponent(runId)}/trace`),
  searchConfigs: () => request<SearchConfigInfo[]>("/api/search/configs"),
  search: ({ q, bidId, docTypes, config, topK }: SearchParams) => {
    const params = new URLSearchParams({ q });
    if (bidId) params.set("bid_id", bidId);
    docTypes?.forEach((t) => params.append("doc_type", t));
    if (config) params.set("config", config);
    if (topK) params.set("top_k", String(topK));
    return request<SearchResult>(`/api/search?${params}`);
  },
  ask: (question: string, bidId?: string) =>
    post<QAResult>("/api/ask", { question, bid_id: bidId || null }),
  goNoGo: (bidId: string, asOf?: string) => {
    const params = asOf ? `?${new URLSearchParams({ as_of: asOf })}` : "";
    return request<Recommendation>(`/api/bids/${encodeURIComponent(bidId)}/go-no-go${params}`);
  },
  compare: (bids: string[], summary: boolean, asOf?: string) => {
    const params = new URLSearchParams({ summary: String(summary) });
    bids.forEach((b) => params.append("bids", b));
    if (asOf) params.set("as_of", asOf);
    return request<Comparison>(`/api/compare?${params}`);
  },
};

function fileUrl(bidId: string, file: string): string {
  const path = file.split("/").map(encodeURIComponent).join("/");
  return `/api/bids/${encodeURIComponent(bidId)}/files/${path}`;
}

/** Open a cited source document at its page. With an API key set, the file is fetched with the
 * key and opened from a blob URL, since a plain link cannot send the header. */
export async function openSource(bidId: string, file: string, page?: number | string): Promise<void> {
  const anchor = page && file.toLowerCase().endsWith(".pdf") ? `#page=${String(page).split("-")[0]}` : "";
  const key = readStored<string | null>(KEYS.apiKey, null);
  if (!key) {
    window.open(fileUrl(bidId, file) + anchor, "_blank", "noopener");
    return;
  }
  const response = await fetch(fileUrl(bidId, file), { headers: headers() });
  if (!response.ok) throw new ApiError(response.status, await detail(response));
  const url = URL.createObjectURL(await response.blob());
  window.open(url + anchor, "_blank", "noopener");
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export function downloadJson(name: string, data: unknown): void {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  URL.revokeObjectURL(url);
}
