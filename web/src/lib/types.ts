// Mirrors of the API's Pydantic models (src/rfp_intel/agents/schema.py, api/schemas.py).

export type FieldStatus = "found" | "not_found" | "conflict" | "failed";
export type Tier = "A" | "B" | "C" | "D" | "E" | "NF-1" | "NF-2" | "X";

export interface Source {
  file: string;
  page: number;
  quote: string;
  doc_type: string | null;
  addendum_number: number | null;
  evidence_id: string | null;
}

export interface FieldResult {
  key: string;
  value: string | string[] | null;
  status: FieldStatus;
  sources: Source[];
  confidence: number;
  tier: Tier;
  normalized: Record<string, unknown> | null;
  notes: string | null;
}

export type ChangeOperation = "replace" | "amend" | "confirm" | "clarify" | "add_requirement";

export interface AddendumChange {
  field: string;
  operation: ChangeOperation;
  addendum_number: number | null;
  doc_date: string | null;
  old_value: string | null;
  new_value: string | null;
  source: Source;
}

export interface ValidationTally {
  passed: number;
  failed: number;
  not_found: number;
  conflicts: number;
  fields: number;
  passed_first_time: number;
  passed_after_retry: number;
  retries: number;
  checks_failed: Record<string, number>;
  consistency_issues: string[];
}

export interface DocumentInfo {
  file: string;
  doc_type: string;
  addendum_number: number | null;
  doc_date: string | null;
  pages: number;
}

export interface Usage {
  calls?: number;
  input_tokens?: number;
  output_tokens?: number;
  cache_read_tokens?: number;
  latency_ms?: number;
  cost_usd?: number;
}

export interface BidResult {
  bid_id: string;
  run_id: string;
  generated_at: string;
  documents: DocumentInfo[];
  fields: Record<string, FieldResult>;
  addendum_changes: AddendumChange[];
  validation: ValidationTally;
  usage: Usage;
  models?: Record<string, string>;
  errors: string[];
}

export interface ResultSummary {
  run_id: string;
  generated_at: string;
  validation: ValidationTally;
  due_date: string | null;
  title: string | null;
  cost_usd: number;
}

export interface BidSummary {
  bid_id: string;
  indexed: boolean;
  documents: number;
  doc_types: Record<string, number>;
  indexed_at: string | null;
  result: ResultSummary | null;
}

export interface BidDetail extends BidSummary {
  files: DocumentInfo[];
}

export type JobStatus = "queued" | "running" | "succeeded" | "failed";

export interface Job {
  job_id: string;
  kind: "extract";
  bid_id: string;
  run_id: string;
  status: JobStatus;
  submitted_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  validation: ValidationTally | null;
}

export interface Hit {
  rank: number;
  score: number;
  chunk_id: string;
  bid_id: string;
  file_name: string;
  page_start: number;
  page_end: number;
  doc_type: string;
  addendum_number: number | null;
  section_path: string[];
  chunk_type: string;
  text: string;
  signals: { ranks?: Record<string, number>; rrf?: number; rerank?: number; boilerplate?: boolean };
}

export interface SearchResult {
  query: {
    query: string;
    identifiers: string[];
    fact_types: string[];
    sparse_query: string;
    expansions: string[];
  };
  config: string;
  hits: Hit[];
  timings_ms: Record<string, number>;
}

export interface SearchConfigInfo {
  name: string;
  description: string;
  default: boolean;
}

export interface Citation {
  bid_id: string;
  file: string;
  page: string;
  quote: string;
  evidence_id: string;
}

export interface QAResult {
  question: string;
  bid_id: string | null;
  found: boolean;
  answer: string;
  statements?: { text: string; citations: number[] }[];
  citations: Citation[];
  passages_reviewed: number;
  dropped_citations: number;
  removed_statements?: number;
  config: string;
  model?: string;
  scope: string[];
  error: string | null;
  usage: Usage;
  cached_from?: string | null; // the earlier question whose answer the semantic cache returned
  cache_similarity?: number | null;
}

export interface TraceSpan {
  span_id: string | null;
  parent_span_id: string | null;
  name: string;
  start: string | null;
  duration_ms: number | null;
  status: string;
  attributes: Record<string, unknown>;
}

export interface Health {
  status: string;
  version: string;
  llm_provider: string;
  extract_model: string;
  reranker: boolean | null;
}

export type Verdict = "pass" | "fail" | "review";
export type Decision = "go" | "no-go" | "review";

export interface DecisionCheck {
  name: string;
  verdict: Verdict;
  detail: string;
  field: string | null;
  value: string | null;
  sources: Source[];
}

export interface Recommendation {
  bid_id: string;
  company: string;
  decision: Decision;
  as_of: string;
  checks: DecisionCheck[];
}

export interface ComparisonCell {
  value: string;
  status: FieldStatus;
  tier: Tier;
  source: string | null;
}

export interface Comparison {
  bids: string[];
  rows: { key: string; name: string; cells: Record<string, ComparisonCell> }[];
  summary: string | null;
  differences: { field: string; statement: string }[];
  recommendations: Recommendation[];
  usage: Usage;
  error: string | null;
}
