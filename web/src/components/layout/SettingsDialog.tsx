import { useQueryClient } from "@tanstack/react-query";
import { Monitor, Moon, Sun } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { useHealth } from "../../lib/queries";
import { KEYS, readStored, writeStored } from "../../lib/storage";
import { useTheme, type ThemePreference } from "../../lib/theme";
import { Dialog } from "../ui/overlay";
import { Button, Input, Kbd, Segmented, SectionLabel } from "../ui/primitives";

const THEMES: { value: ThemePreference; label: string; icon: typeof Sun }[] = [
  { value: "system", label: "System", icon: Monitor },
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
];

const SHORTCUTS: [string[], string][] = [
  [["Ctrl", "K"], "Search all documents"],
  [["j", "k"], "Move between fields in a bid"],
  [["Enter"], "Open the selected field's evidence"],
  [["/"], "Filter the fields"],
  [["Esc"], "Close the evidence pane or a dialog"],
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
          <SectionLabel>API key</SectionLabel>
          <span className="mb-1.5 mt-0.5 block text-xs text-muted">Needed only when the server sets RFP_API_KEY. Sent as X-API-Key.</span>
          <Input type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} placeholder="Not set" />
        </label>

        <fieldset>
          <legend className="caps mb-1.5">Appearance</legend>
          <Segmented
            aria-label="Appearance"
            value={theme}
            onChange={setTheme}
            items={THEMES.map(({ value, label, icon: Icon }) => ({
              value,
              label: (
                <>
                  <Icon className="size-3.5" aria-hidden />
                  {label}
                </>
              ),
            }))}
          />
        </fieldset>

        <div>
          <SectionLabel>Server</SectionLabel>
          {health.data ? (
            <dl className="mt-1.5 grid grid-cols-[auto_1fr] gap-x-4 gap-y-0.5 text-xs text-muted">
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
            <p className="mt-1.5 text-xs text-muted">{health.isError ? "Unreachable" : "Checking…"}</p>
          )}
        </div>

        <div>
          <SectionLabel>Keyboard</SectionLabel>
          <dl className="mt-1.5 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs text-muted">
            {SHORTCUTS.map(([keys, what]) => (
              <div key={what} className="contents">
                <dt className="flex gap-0.5">
                  {keys.map((k) => (
                    <Kbd key={k}>{k}</Kbd>
                  ))}
                </dt>
                <dd>{what}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </Dialog>
  );
}
