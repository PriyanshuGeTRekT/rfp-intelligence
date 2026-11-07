import { summarize, toRows } from "../features/traceTree";
import { formatDuration, highlight, pagesLabel, timeAgo } from "../lib/format";
import type { TraceSpan } from "../lib/types";

describe("highlight", () => {
  it("marks query terms case-insensitively and keeps the text intact", () => {
    const parts = highlight("Bid Bond: Not required. A bond is not needed.", ["bond", "required"]);
    expect(parts.map((p) => p.text).join("")).toBe("Bid Bond: Not required. A bond is not needed.");
    expect(parts.filter((p) => p.hit).map((p) => p.text)).toEqual(["Bond", "required", "bond"]);
  });

  it("ignores short terms and escapes regex characters", () => {
    expect(highlight("a (b) c", ["a", "(b)"])).toEqual([
      { text: "a ", hit: false },
      { text: "(b)", hit: true },
      { text: " c", hit: false },
    ]);
  });
});

describe("formatting", () => {
  it("formats durations at every scale", () => {
    expect(formatDuration(0.4)).toBe("<1 ms");
    expect(formatDuration(250)).toBe("250 ms");
    expect(formatDuration(4_200)).toBe("4.2 s");
    expect(formatDuration(125_000)).toBe("2 m 5 s");
    expect(formatDuration(null)).toBe("—");
  });

  it("labels page ranges and relative times", () => {
    expect(pagesLabel(3, 3)).toBe("p. 3");
    expect(pagesLabel(3, 5)).toBe("pp. 3–5");
    const now = Date.parse("2024-07-01T12:00:00Z");
    expect(timeAgo("2024-07-01T11:59:50Z", now)).toBe("just now");
    expect(timeAgo("2024-07-01T10:00:00Z", now)).toBe("2 hours ago");
  });
});

const span = (id: string, parent: string | null, startMs: number, duration: number, attributes = {}): TraceSpan => ({
  span_id: id,
  parent_span_id: parent,
  name: `agent.${id}`,
  start: new Date(Date.UTC(2024, 0, 1) + startMs).toISOString(),
  duration_ms: duration,
  status: "UNSET",
  attributes,
});

describe("trace tree", () => {
  const spans = [
    span("extract", "run", 30, 50, { "llm.model": "m", "llm.input_tokens": 100, "llm.output_tokens": 20, "llm.cost_usd": 0.01 }),
    span("run", null, 0, 100),
    span("plan", "run", 5, 5),
    span("retry", "run", 90, 5, { "llm.model": "m", "llm.error": "TimeoutError" }),
  ];

  it("orders parents before children and siblings by start", () => {
    const rows = toRows(spans);
    expect(rows.map((r) => [r.span.span_id, r.depth, r.offsetMs])).toEqual([
      ["run", 0, 0],
      ["plan", 1, 5],
      ["extract", 1, 30],
      ["retry", 1, 90],
    ]);
  });

  it("sums model calls, tokens, cost and errors", () => {
    expect(summarize(spans)).toEqual({
      durationMs: 100,
      llmCalls: 2,
      inputTokens: 100,
      outputTokens: 20,
      costUsd: 0.01,
      errors: 1,
    });
  });
});
