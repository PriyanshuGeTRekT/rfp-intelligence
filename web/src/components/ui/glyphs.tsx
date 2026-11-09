// Shapes that carry state without colour: tier squares, verdict circles, job circles.
import type { Decision, JobStatus, Tier, Verdict } from "../../lib/types";

/** The fill meter: solid, half, hatched, dotted, dashed-hollow, dotted-hollow or crossed. */
export function TierGlyph({ tier, size = 10, className }: { tier: Tier; size?: number; className?: string }) {
  const box = <rect x="0.5" y="0.5" width="9" height="9" fill="none" stroke="currentColor" />;
  const inner = (() => {
    switch (tier) {
      case "A":
        return <rect x="0.5" y="0.5" width="9" height="9" fill="currentColor" stroke="currentColor" />;
      case "B":
        return (
          <>
            {box}
            <rect x="0.5" y="5" width="9" height="4.5" fill="currentColor" />
          </>
        );
      case "C":
        return (
          <>
            {box}
            <path d="M0.5 6.5L6.5 0.5M3.5 9.5L9.5 3.5" stroke="currentColor" strokeWidth="1.2" />
          </>
        );
      case "D":
        return (
          <>
            {box}
            <circle cx="5" cy="5" r="1.8" fill="currentColor" />
          </>
        );
      case "E":
        return <path d="M5 0.8L9.5 9.2H0.5Z" fill="currentColor" />;
      case "NF-1":
        return <rect x="0.5" y="0.5" width="9" height="9" fill="none" stroke="currentColor" strokeDasharray="2 1.5" />;
      case "NF-2":
        return <rect x="0.5" y="0.5" width="9" height="9" fill="none" stroke="currentColor" strokeDasharray="1 1.6" />;
      case "X":
        return (
          <>
            {box}
            <path d="M2.5 2.5l5 5M7.5 2.5l-5 5" stroke="currentColor" strokeWidth="1.3" />
          </>
        );
    }
  })();
  return (
    <svg width={size} height={size} viewBox="0 0 10 10" className={className} aria-hidden data-tier={tier}>
      {inner}
    </svg>
  );
}

type Outcome = Verdict | Decision;

const OUTCOME_PATH: Record<Outcome, string> = {
  pass: "m8 12 3 3 5-6",
  go: "m8 12 3 3 5-6",
  review: "M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .9-1 1.7M12 17h.01",
  fail: "M9 9l6 6M15 9l-6 6",
  "no-go": "M9 9l6 6M15 9l-6 6",
};

/** Check, question mark or cross in a circle: pass/go, review, fail/no-go. */
export function OutcomeGlyph({ outcome, size = 14, className, label }: { outcome: Outcome; size?: number; className?: string; label?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden={label ? undefined : true}
      aria-label={label}
      role={label ? "img" : undefined}
    >
      <circle cx="12" cy="12" r="9" />
      <path d={OUTCOME_PATH[outcome]} />
    </svg>
  );
}

/** Hollow, half, full or crossed circle: queued, running, succeeded, failed. */
export function JobGlyph({ status, size = 14, className }: { status: JobStatus; size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <circle cx="12" cy="12" r="9" />
      {status === "running" && <path d="M12 3a9 9 0 0 1 0 18z" fill="currentColor" />}
      {status === "succeeded" && <path d="m8 12 3 3 5-6" />}
      {status === "failed" && <path d="M9 9l6 6M15 9l-6 6" />}
    </svg>
  );
}
