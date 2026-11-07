"""Render a run's span file (traces/<run_id>.jsonl) as a readable tree in Markdown.

The JSONL is the raw deliverable; this view is what a reviewer reads: every node of the run in
order, with durations, what each search did, what each model call cost, and where a field
failed validation and went back for another attempt.
"""

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

SHOWN_PREFIXES = ("agent.", "llm.", "rfp.", "qa.", "index.", "search.")
HIDDEN = {"search.filters", "search.top_chunk_ids"}
MAX_VALUE = 160


def load_spans(path: Path) -> list[dict[str, Any]]:
    spans = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            spans.append(json.loads(line))
    return spans


def _fmt(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    return text if len(text) <= MAX_VALUE else text[: MAX_VALUE - 3] + "..."


def _attrs(span: dict[str, Any]) -> list[str]:
    out = []
    for key, value in sorted(span.get("attributes", {}).items()):
        if key in HIDDEN or not key.startswith(SHOWN_PREFIXES):
            continue
        out.append(f"{key}={_fmt(value)}")
    return out


def render_trace(spans: list[dict[str, Any]]) -> str:
    by_parent: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
    for s in spans:
        by_parent[s.get("parent_span_id")].append(s)
    for children in by_parent.values():
        children.sort(key=lambda s: s.get("start") or "")

    ids = {s["span_id"] for s in spans}
    roots = [s for s in spans if s.get("parent_span_id") not in ids]
    roots.sort(key=lambda s: s.get("start") or "")

    llm_spans = [s for s in spans if "llm.cost_usd" in s.get("attributes", {})]
    cost = sum(float(s["attributes"].get("llm.cost_usd", 0) or 0) for s in llm_spans)
    run_id = next((s["resource"].get("rfp.run_id") for s in spans if s.get("resource")), "unknown")
    total_ms = max((s.get("duration_ms") or 0) for s in roots) if roots else 0

    lines = [
        f"# Trace {run_id}",
        "",
        f"{len(spans)} spans, {len(llm_spans)} with model usage, estimated cost ${cost:.4f}, "
        f"longest root span {total_ms / 1000:.1f} s.",
        "",
        "```",
    ]

    def walk(span: dict[str, Any], depth: int) -> None:
        dur = span.get("duration_ms")
        dur_text = (
            f"{dur / 1000:.2f}s"
            if dur and dur >= 1000
            else f"{dur:.0f}ms"
            if dur is not None
            else "-"
        )
        status = "" if span.get("status") in ("UNSET", "OK") else f" [{span.get('status')}]"
        lines.append(f"{'  ' * depth}{span['name']} ({dur_text}){status}")
        for attr in _attrs(span):
            lines.append(f"{'  ' * depth}  {attr}")
        for event in span.get("events", []):
            detail = ", ".join(f"{k}={_fmt(v)}" for k, v in event.get("attributes", {}).items())
            lines.append(f"{'  ' * depth}  * {event['name']}: {detail}")
        for child in by_parent.get(span["span_id"], []):
            walk(child, depth + 1)

    for root in roots:
        walk(root, 0)
    lines += ["```", ""]
    return "\n".join(lines)
