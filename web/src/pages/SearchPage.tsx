import { ChevronDown, Search as SearchIcon, SearchX } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { Cite, DocTypeTag, PageHeader } from "../components/domain";
import { EmptyState, ErrorState } from "../components/ui/feedback";
import { Tooltip } from "../components/ui/overlay";
import { Button, Input, Panel, Select, Skeleton, Tag } from "../components/ui/primitives";
import type { SearchParams } from "../lib/api";
import { cn } from "../lib/cn";
import { labelFromMeta } from "../lib/docLabels";
import { docTypeLabel, formatDuration, highlight, pagesLabel } from "../lib/format";
import { useBids, useSearch, useSearchConfigs } from "../lib/queries";
import type { Hit } from "../lib/types";

const EXAMPLES = ["bid bond requirement", "JA-207652", "warranty terms", "pre-proposal conference", "delivery after award"];
const LIST_LABELS: Record<string, string> = {
  dense: "Dense",
  bm25: "BM25",
  identifiers: "Exact ID",
  facts_dense: "Facts · dense",
  facts_bm25: "Facts · BM25",
};

function Signals({ hit }: { hit: Hit }) {
  const ranks = Object.entries(hit.signals.ranks ?? {});
  return (
    <span className="ml-auto flex items-center gap-1 font-mono text-2xs text-muted">
      {ranks.length > 0 && (
        <Tooltip
          content={
            <div className="space-y-0.5">
              <p className="font-semibold">Rank in each retrieval list</p>
              {ranks.map(([list, rank]) => (
                <p key={list} className="num flex justify-between gap-6">
                  <span className="opacity-80">{LIST_LABELS[list] ?? list}</span>#{rank}
                </p>
              ))}
              {hit.signals.rerank !== undefined && (
                <p className="num flex justify-between gap-6">
                  <span className="opacity-80">Cross-encoder</span>
                  {hit.signals.rerank.toFixed(2)}
                </p>
              )}
            </div>
          }
        >
          <span tabIndex={0} className="flex cursor-default gap-1">
            {ranks.slice(0, 4).map(([list]) => (
              <span key={list} className="rounded-sm border border-line bg-subtle px-1.5 py-px">
                {LIST_LABELS[list] ?? list}
              </span>
            ))}
            {hit.signals.rerank !== undefined && <span className="rounded-sm border border-line bg-subtle px-1.5 py-px">Rerank</span>}
          </span>
        </Tooltip>
      )}
      <span className="num ml-1.5 text-faint" title="Fused score">
        {hit.score.toFixed(3)}
      </span>
    </span>
  );
}

function Passage({ hit, terms }: { hit: Hit; terms: string[] }) {
  const [expanded, setExpanded] = useState(false);
  const parts = useMemo(() => highlight(hit.text, terms), [hit.text, terms]);
  const doc = labelFromMeta(hit.file_name, hit.doc_type, hit.addendum_number);
  return (
    <li className="border-b border-line py-3.5">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
        <span className="num w-5 font-mono text-xs font-medium text-faint">{hit.rank}</span>
        <Tag className="font-mono">{hit.bid_id}</Tag>
        <Cite bidId={hit.bid_id} doc={doc} page={hit.page_start} pages={pagesLabel(hit.page_start, hit.page_end)} />
        <span className="max-w-[320px] truncate font-mono text-2xs text-faint" title={hit.file_name}>
          {hit.file_name}
        </span>
        <DocTypeTag type={hit.doc_type} addendum={hit.addendum_number} />
        {hit.signals.boilerplate && <Tag>boilerplate</Tag>}
        <Signals hit={hit} />
      </div>
      {hit.section_path.length > 0 && <p className="mt-1.5 truncate pl-7 text-xs text-muted">{hit.section_path.join(" › ")}</p>}
      <p className={cn("mt-1.5 whitespace-pre-line pl-7 text-sm text-ink", !expanded && "line-clamp-5")}>
        {parts.map((p, i) =>
          p.hit ? (
            <mark key={i} className="hl">
              {p.text}
            </mark>
          ) : (
            <span key={i}>{p.text}</span>
          ),
        )}
      </p>
      <div className="mt-1.5 flex flex-wrap gap-4 pl-7 text-xs font-medium">
        {hit.text.length > 420 && (
          <button type="button" onClick={() => setExpanded((e) => !e)} className="flex items-center gap-1 text-accent hover:underline">
            {expanded ? "Show less" : "Show full passage"}
            <ChevronDown className={cn("size-3.5 transition-transform", expanded && "rotate-180")} aria-hidden />
          </button>
        )}
        <Link to={`/bids/${encodeURIComponent(hit.bid_id)}`} className="text-muted hover:text-ink hover:underline">
          Open {hit.bid_id}
        </Link>
      </div>
    </li>
  );
}

export function SearchPage() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const [draft, setDraft] = useState(q);
  useEffect(() => {
    setDraft(q);
  }, [q]);

  const bids = useBids();
  const configs = useSearchConfigs();
  const docTypes = useMemo(() => [...new Set((bids.data ?? []).flatMap((b) => Object.keys(b.doc_types)))].sort(), [bids.data]);

  const request: SearchParams | null = q
    ? {
        q,
        bidId: params.get("bid") ?? undefined,
        docTypes: params.getAll("type"),
        config: params.get("config") ?? undefined,
        topK: Number(params.get("k") ?? 10),
      }
    : null;
  const search = useSearch(request);

  // A new query is a history entry (Back returns to it); a filter change replaces it.
  const update = (changes: Record<string, string | string[] | null>, newEntry = false) => {
    const next = new URLSearchParams(params);
    for (const [name, value] of Object.entries(changes)) {
      next.delete(name);
      if (Array.isArray(value)) value.forEach((v) => next.append(name, v));
      else if (value) next.set(name, value);
    }
    setParams(next, { replace: !newEntry });
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    update({ q: draft.trim() || null }, true);
  };

  const selectedTypes = params.getAll("type");
  const toggleType = (t: string) => update({ type: selectedTypes.includes(t) ? selectedTypes.filter((x) => x !== t) : [...selectedTypes, t] });

  const analysis = search.data?.query;
  const terms = useMemo(() => (analysis ? [...analysis.query.split(/\s+/), ...analysis.identifiers, ...analysis.expansions] : []), [analysis]);

  return (
    <div className="mx-auto max-w-[1040px]">
      <PageHeader
        title="Search"
        description="Hybrid retrieval over every indexed document: semantic and keyword search fused with reciprocal rank fusion, exact matches for identifiers, optional cross-encoder reranking."
      />

      <form onSubmit={submit} className="mb-2.5 flex gap-2" role="search">
        <div className="relative flex-1">
          <SearchIcon className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-faint" aria-hidden />
          <Input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Search for a requirement, date, part number…"
            aria-label="Search query"
            className="h-9 pl-9 text-md"
            autoFocus={!q}
          />
        </div>
        <Button type="submit" variant="primary" className="h-9">
          Search
        </Button>
      </form>

      <div className="mb-5 flex flex-wrap items-center gap-2">
        <Select aria-label="Bid" value={params.get("bid") ?? ""} onChange={(e) => update({ bid: e.target.value || null })} className="h-7 text-xs">
          <option value="">All bids</option>
          {(bids.data ?? [])
            .filter((b) => b.indexed)
            .map((b) => (
              <option key={b.bid_id} value={b.bid_id}>
                {b.bid_id}
              </option>
            ))}
        </Select>
        <Select aria-label="Retrieval configuration" value={params.get("config") ?? ""} onChange={(e) => update({ config: e.target.value || null })} className="h-7 text-xs">
          <option value="">Default retrieval</option>
          {(configs.data ?? []).map((c) => (
            <option key={c.name} value={c.name} title={c.description}>
              {c.name}
              {c.default ? " (default)" : ""}
            </option>
          ))}
        </Select>
        <Select aria-label="Number of results" value={params.get("k") ?? "10"} onChange={(e) => update({ k: e.target.value })} className="h-7 text-xs">
          {[5, 10, 20].map((n) => (
            <option key={n} value={n}>
              Top {n}
            </option>
          ))}
        </Select>
        <span className="mx-1 h-5 w-px bg-line" aria-hidden />
        <div className="flex flex-wrap gap-1" role="group" aria-label="Document types">
          {docTypes.map((t) => {
            const on = selectedTypes.includes(t);
            return (
              <button
                key={t}
                type="button"
                aria-pressed={on}
                onClick={() => toggleType(t)}
                className={cn("h-7 rounded border px-2 text-xs font-medium", on ? "border-ink bg-ink text-canvas" : "border-control text-muted hover:border-ink hover:text-ink")}
              >
                {docTypeLabel(t)}
              </button>
            );
          })}
        </div>
      </div>

      {!q ? (
        <Panel>
          <EmptyState
            icon={<SearchIcon className="size-4" />}
            title="Search the bid documents"
            description="Results come back as passages with their file, page and section, ranked by every retrieval signal."
            action={
              <div className="flex flex-wrap justify-center gap-1.5">
                {EXAMPLES.map((ex) => (
                  <button key={ex} type="button" onClick={() => update({ q: ex }, true)} className="rounded border border-control px-2 py-1 text-xs text-muted hover:border-ink hover:text-ink">
                    {ex}
                  </button>
                ))}
              </div>
            }
          />
        </Panel>
      ) : search.isError ? (
        <Panel>
          <ErrorState error={search.error} onRetry={() => search.refetch()} />
        </Panel>
      ) : search.isPending ? (
        <ul className="border-t border-line">
          {[0, 1, 2].map((i) => (
            <li key={i} className="space-y-2 border-b border-line py-4">
              <Skeleton className="h-4 w-64" />
              <Skeleton className="h-3" />
              <Skeleton className="h-3 w-5/6" />
            </li>
          ))}
        </ul>
      ) : (
        <div className={cn("transition-opacity", search.isFetching && "opacity-60")} aria-busy={search.isFetching}>
          {analysis && (
            <div className="flex flex-wrap items-center gap-x-3.5 gap-y-1.5 border-y border-line py-2 text-xs text-muted">
              <span className="caps">How it searched</span>
              <span className="num text-ink">
                <strong className="font-semibold">{search.data.hits.length}</strong> passages · {formatDuration(search.data.timings_ms.total)} ·{" "}
                <span className="font-mono">{search.data.config}</span>
              </span>
              {analysis.identifiers.length > 0 && (
                <span className="flex items-center gap-1">
                  Identifiers
                  {analysis.identifiers.map((id) => (
                    <Tag key={id} tone="accent" className="font-mono">
                      {id}
                    </Tag>
                  ))}
                </span>
              )}
              {analysis.fact_types.length > 0 && (
                <span className="flex items-center gap-1">
                  Routed to
                  {analysis.fact_types.map((t) => (
                    <Tag key={t} className="font-mono">
                      {t}
                    </Tag>
                  ))}
                </span>
              )}
              {analysis.expansions.length > 0 && (
                <span className="truncate" title={analysis.expansions.join(", ")}>
                  Expanded with <span className="text-ink">{analysis.expansions.slice(0, 4).join(", ")}</span>
                  {analysis.expansions.length > 4 && "…"}
                </span>
              )}
            </div>
          )}
          {search.data.hits.length === 0 ? (
            <Panel className="mt-3">
              <EmptyState icon={<SearchX className="size-4" />} title="No passages matched" description="Try other words, remove a filter, or search all bids." />
            </Panel>
          ) : (
            <ol>
              {search.data.hits.map((hit) => (
                <Passage key={hit.chunk_id} hit={hit} terms={terms} />
              ))}
            </ol>
          )}
        </div>
      )}
    </div>
  );
}
