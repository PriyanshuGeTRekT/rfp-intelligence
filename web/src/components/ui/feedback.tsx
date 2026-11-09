import { AlertTriangle, KeyRound, RotateCw } from "lucide-react";
import type { ReactNode } from "react";

import { ApiError } from "../../lib/api";
import { cn } from "../../lib/cn";
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
    <div className={cn("px-6 text-center", compact ? "py-8" : "py-16")}>
      {icon && <div className="mx-auto mb-3 flex size-8 items-center justify-center border border-line text-muted">{icon}</div>}
      <p className="text-sm font-medium text-ink">{title}</p>
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
        description="Open Settings in the top bar and enter the key the server was started with (RFP_API_KEY)."
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
  const styles = { warn: "bg-warn-soft", bad: "bg-bad-soft", info: "bg-accent-soft" }[tone];
  const ink = { warn: "text-warn", bad: "text-bad", info: "text-accent-ink" }[tone];
  return (
    <div role={tone === "bad" ? "alert" : "status"} className={cn("flex gap-2.5 border border-line px-3 py-2.5", styles)}>
      <AlertTriangle className={cn("mt-0.5 size-3.5 shrink-0", ink)} aria-hidden />
      <div className="min-w-0">
        <p className={cn("text-xs font-semibold", ink)}>{title}</p>
        {children && <div className="mt-0.5 text-xs text-ink">{children}</div>}
      </div>
    </div>
  );
}
