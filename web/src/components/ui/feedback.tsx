import { AlertTriangle, KeyRound, RotateCw } from "lucide-react";
import type { ReactNode } from "react";

import { ApiError } from "../../lib/api";
import { Button } from "./primitives";

export function EmptyState({
  icon,
  title,
  description,
  action,
  compact,
}: {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  compact?: boolean;
}) {
  return (
    <div className={compact ? "px-6 py-8 text-center" : "px-6 py-16 text-center"}>
      {icon && (
        <div className="mx-auto mb-3 flex size-9 items-center justify-center rounded-lg border border-line bg-subtle text-muted">
          {icon}
        </div>
      )}
      <p className="text-[13px] font-medium text-ink">{title}</p>
      {description && <p className="mx-auto mt-1 max-w-md text-xs text-muted">{description}</p>}
      {action && <div className="mt-4 flex justify-center gap-2">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry, compact }: { error: unknown; onRetry?: () => void; compact?: boolean }) {
  const status = error instanceof ApiError ? error.status : undefined;
  const message = error instanceof Error ? error.message : "Something went wrong.";
  if (status === 401) {
    return (
      <EmptyState
        compact={compact}
        icon={<KeyRound className="size-4" />}
        title="This server requires an API key"
        description="Open Settings in the sidebar and enter the key the server was started with (RFP_API_KEY)."
      />
    );
  }
  return (
    <EmptyState
      compact={compact}
      icon={<AlertTriangle className="size-4 text-bad" />}
      title={status === 503 ? "The language model is not configured" : "Could not load this"}
      description={message}
      action={
        onRetry && (
          <Button size="sm" icon={<RotateCw className="size-3.5" />} onClick={onRetry}>
            Try again
          </Button>
        )
      }
    />
  );
}

export function InlineAlert({ tone, title, children }: { tone: "warn" | "bad" | "info"; title: string; children?: ReactNode }) {
  const styles = {
    warn: "border-warn/30 bg-warn-soft",
    bad: "border-bad/30 bg-bad-soft",
    info: "border-info/30 bg-info-soft",
  }[tone];
  const ink = { warn: "text-warn", bad: "text-bad", info: "text-info" }[tone];
  return (
    <div role={tone === "bad" ? "alert" : "status"} className={`rounded-md border px-3 py-2.5 ${styles}`}>
      <p className={`flex items-center gap-1.5 text-xs font-semibold ${ink}`}>
        <AlertTriangle className="size-3.5" aria-hidden />
        {title}
      </p>
      {children && <div className="mt-1 text-xs text-ink/80">{children}</div>}
    </div>
  );
}
