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


def scrub_paths(text: str) -> str:
    """Show paths under the working directory relative to it (traces from before paths were
    stored relative still carry the absolute form, including the local user name)."""
    cwd = str(Path.cwd())
    # The path as written and JSON-escaped up to three times (JSON inside a JSON attribute):
    # at level i every backslash is 2**i backslashes. Most escaped first.
    for level in (3, 2, 1, 0):
        sep = "\\" * (2**level)
        form = cwd.replace("\\", sep)
        text = text.replace(form + sep, "").replace(form + "/", "").replace(form, ".")
    return text


def _fmt(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    text = scrub_paths(text)
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

    # Per-call costs only: the run's root span carries the total again.
    llm_spans = [
        s for s in spans if "llm.cost_usd" in s.get("attributes", {}) and s["name"] != "agent.run"
    ]
    cost = sum(float(s["attributes"].get("llm.cost_usd", 0) or 0) for s in llm_spans)
    run_id = next(
        (
            s.get("resource", {}).get("rfp.run_id") or s.get("attributes", {}).get("rfp.run_id")
            for s in spans
            if s.get("resource", {}).get("rfp.run_id") or s.get("attributes", {}).get("rfp.run_id")
        ),
        "unknown",
    )
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
    lines += _full_calls(spans)
    return "\n".join(lines)


FULL_CALL_KINDS = (
    "agent.reconcile.addendum",
    "agent.extract.",
    "agent.retrieve.rewrite",
    "agent.summary",
    "agent.answer",
)
MAX_FULL = 6000


def _full_calls(spans: list[dict[str, Any]]) -> list[str]:
    """The first model call of each kind, with its prompt and answer in full (clipped at
    MAX_FULL characters), so a reader sees exactly what an agent sent and received."""
    out: list[str] = []
    for kind in FULL_CALL_KINDS:
        span = next(
            (
                s
                for s in sorted(spans, key=lambda s: s.get("start") or "")
                if s["name"].startswith(kind) and "llm.input" in s.get("attributes", {})
            ),
            None,
        )
        if span is None:
            continue
        a = span["attributes"]
        if not out:
            out += ["## Model calls in full", ""]
        out += [
            f"### {span['name']}",
            "",
            f"Model `{a.get('llm.model')}`, {a.get('llm.input_tokens', '?')} input and "
            f"{a.get('llm.output_tokens', '?')} output tokens.",
            "",
            "Prompt (user turn):",
            "",
            "```text",
            _clip(scrub_paths(str(a.get("llm.input", "")))),
            "```",
            "",
            "Response:" if "llm.output" in a else "Error:",
            "",
            "```json" if "llm.output" in a else "```text",
            _clip(_pretty(a.get("llm.output", a.get("llm.error", "")))),
            "```",
            "",
        ]
    return out


def _pretty(value: Any) -> str:
    try:
        return json.dumps(json.loads(value), indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _clip(text: str) -> str:
    return (
        text if len(text) <= MAX_FULL else text[:MAX_FULL] + f"\n... [{len(text) - MAX_FULL} more]"
    )
