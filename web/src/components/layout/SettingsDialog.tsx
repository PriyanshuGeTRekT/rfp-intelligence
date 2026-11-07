import { useQueryClient } from "@tanstack/react-query";
import { Monitor, Moon, Sun } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { KEYS, readStored, writeStored } from "../../lib/storage";
import { useTheme, type ThemePreference } from "../../lib/theme";
import { useHealth } from "../../lib/queries";
import { Dialog } from "../ui/overlay";
import { Button, Input } from "../ui/primitives";
import { cn } from "../../lib/cn";

const THEMES: { value: ThemePreference; label: string; icon: typeof Sun }[] = [
  { value: "system", label: "System", icon: Monitor },
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
];

export function SettingsDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const client = useQueryClient();
  const [theme, setTheme] = useTheme();
  const [key, setKey] = useState(() => readStored<string>(KEYS.apiKey, ""));
  const health = useHealth();

  const save = () => {
    writeStored(KEYS.apiKey, key.trim() || null);
    void client.invalidateQueries();
    toast.success("Settings saved");
    onOpenChange(false);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Settings"
      description="Stored in this browser only."
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" onClick={save}>
            Save
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        <label className="block">
          <span className="text-xs font-medium text-ink">API key</span>
          <span className="mb-1.5 block text-xs text-muted">Needed only when the server sets RFP_API_KEY. Sent as X-API-Key.</span>
          <Input
            type="password"
            autoComplete="off"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="Not set"
          />
        </label>

        <fieldset>
          <legend className="mb-1.5 text-xs font-medium text-ink">Appearance</legend>
          <div className="inline-flex rounded-md border border-line bg-subtle p-0.5" role="radiogroup">
            {THEMES.map(({ value, label, icon: Icon }) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={theme === value}
                onClick={() => setTheme(value)}
                className={cn(
                  "flex h-7 items-center gap-1.5 rounded px-2.5 text-xs font-medium",
                  theme === value ? "bg-surface text-ink shadow-card" : "text-muted hover:text-ink",
                )}
              >
                <Icon className="size-3.5" aria-hidden />
                {label}
              </button>
            ))}
          </div>
        </fieldset>

        <div className="rounded-md border border-line bg-subtle px-3 py-2.5 text-xs">
          <p className="mb-1 font-medium text-ink">Server</p>
          {health.data ? (
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-0.5 text-muted">
              <dt>Version</dt>
              <dd className="font-mono text-ink">{health.data.version}</dd>
              <dt>Model provider</dt>
              <dd className="text-ink">{health.data.llm_provider}</dd>
              <dt>Extraction model</dt>
              <dd className="font-mono text-ink">{health.data.extract_model}</dd>
              <dt>Reranker</dt>
              <dd className="text-ink">{health.data.reranker === null ? "Loads on first search" : health.data.reranker ? "Loaded" : "Off"}</dd>
            </dl>
          ) : (
            <p className="text-muted">{health.isError ? "Unreachable" : "Checking…"}</p>
          )}
        </div>
      </div>
    </Dialog>
  );
}
