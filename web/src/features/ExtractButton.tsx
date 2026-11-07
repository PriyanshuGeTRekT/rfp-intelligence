import { Play } from "lucide-react";

import { Button } from "../components/ui/primitives";
import { useActiveJob, useStartExtraction } from "../lib/queries";

/** Starts an extraction run, or shows that one is under way for this bid. */
export function ExtractButton({ bidId, hasResult, size = "md" }: { bidId: string; hasResult: boolean; size?: "sm" | "md" }) {
  const active = useActiveJob(bidId);
  const start = useStartExtraction();
  const busy = Boolean(active) || (start.isPending && start.variables === bidId);
  return (
    <Button
      size={size}
      variant={hasResult ? "secondary" : "primary"}
      loading={busy}
      icon={<Play className="size-3.5" aria-hidden />}
      onClick={() => start.mutate(bidId)}
      aria-live="polite"
    >
      {busy ? (active?.status === "queued" ? "Queued" : "Extracting") : hasResult ? "Re-run" : "Run extraction"}
    </Button>
  );
}
