import { Activity, Columns3, FolderKanban, Menu, MessageSquareText, Search, Settings, X } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { useHealth, useJobs } from "../../lib/queries";
import { Tooltip } from "../ui/overlay";
import { Dot, Kbd } from "../ui/primitives";
import { cn } from "../../lib/cn";
import { SettingsDialog } from "./SettingsDialog";

const NAV = [
  { to: "/", label: "Bids", icon: FolderKanban, end: true },
  { to: "/explore", label: "Search", icon: Search },
  { to: "/assistant", label: "Ask", icon: MessageSquareText },
  { to: "/compare", label: "Compare", icon: Columns3 },
  { to: "/runs", label: "Runs", icon: Activity },
];

function Wordmark() {
  return (
    <Link to="/" className="flex items-center gap-2 px-2">
      <img src="/favicon.svg" alt="" className="size-6" />
      <span className="text-[13px] font-semibold tracking-tight text-ink">RFP Intelligence</span>
    </Link>
  );
}

function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const jobs = useJobs();
  const running = jobs.data?.filter((j) => j.status === "running" || j.status === "queued").length ?? 0;
  return (
    <nav aria-label="Main" className="mt-6 space-y-0.5">
      {NAV.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              "flex h-8 items-center gap-2.5 rounded-md px-2 text-[13px] font-medium transition-colors",
              isActive ? "bg-surface text-ink shadow-card ring-1 ring-line" : "text-muted hover:bg-subtle hover:text-ink",
            )
          }
        >
          <Icon className="size-4" aria-hidden />
          {label}
          {to === "/runs" && running > 0 && (
            <span className="num ml-auto rounded bg-info-soft px-1.5 text-2xs font-semibold text-info" aria-label={`${running} running`}>
              {running}
            </span>
          )}
        </NavLink>
      ))}
    </nav>
  );
}

function ServerStatus({ onSettings }: { onSettings: () => void }) {
  const health = useHealth();
  const tone = health.isError ? "bad" : health.data ? "ok" : "neutral";
  const label = health.isError ? "Server unreachable" : health.data ? health.data.extract_model : "Connectingâ€¦";
  return (
    <div className="flex items-center gap-1 border-t border-line pt-3">
      <Tooltip content={health.data ? `${health.data.llm_provider} Â· v${health.data.version}` : label} side="right">
        <div className="flex min-w-0 flex-1 items-center gap-2 px-2 text-xs text-muted" tabIndex={0}>
          <Dot tone={tone} />
          <span className="truncate font-mono text-2xs">{label}</span>
        </div>
      </Tooltip>
      <button
        type="button"
        onClick={onSettings}
        className="rounded-md p-1.5 text-muted hover:bg-subtle hover:text-ink"
        aria-label="Settings"
      >
        <Settings className="size-4" />
      </button>
    </div>
  );
}

const IS_MAC = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.userAgent);

function GlobalSearch() {
  const navigate = useNavigate();
  const ref = useRef<HTMLInputElement>(null);
  const [q, setQ] = useState("");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        ref.current?.focus();
        ref.current?.select();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!q.trim()) return;
    navigate(`/explore?q=${encodeURIComponent(q.trim())}`);
    ref.current?.blur();
  };

  return (
    <form onSubmit={submit} role="search" className="relative w-full max-w-sm">
      <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-faint" aria-hidden />
      <input
        ref={ref}
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search all documents"
        aria-label="Search all documents"
        className="h-8 w-full rounded-md border border-line bg-surface pl-8 pr-14 text-[13px] placeholder:text-faint hover:border-line-strong focus:border-accent"
      />
      <span className="pointer-events-none absolute right-2 top-1/2 hidden -translate-y-1/2 gap-0.5 sm:flex">
        <Kbd>{IS_MAC ? "⌘" : "Ctrl"}</Kbd>
        <Kbd>K</Kbd>
      </span>
    </form>
  );
}

export function AppShell({ children }: { children?: ReactNode }) {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  const sidebar = (
    <div className="flex h-full flex-col px-3 py-4">
      <Wordmark />
      <SidebarNav onNavigate={() => setMobileOpen(false)} />
      <div className="mt-auto">
        <ServerStatus onSettings={() => setSettingsOpen(true)} />
      </div>
    </div>
  );

  return (
    <div className="flex min-h-screen">
      <a
        href="#main"
        className="sr-only z-50 rounded bg-surface px-3 py-2 focus:not-sr-only focus:fixed focus:left-3 focus:top-3"
      >
        Skip to content
      </a>
      <aside className="sticky top-0 hidden h-screen w-56 shrink-0 border-r border-line bg-canvas lg:block">{sidebar}</aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/30" onClick={() => setMobileOpen(false)} aria-hidden />
          <aside className="absolute inset-y-0 left-0 w-64 border-r border-line bg-canvas shadow-pop">
            <button
              type="button"
              className="absolute right-3 top-4 rounded p-1 text-muted hover:bg-subtle"
              onClick={() => setMobileOpen(false)}
              aria-label="Close menu"
            >
              <X className="size-4" />
            </button>
            {sidebar}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-12 items-center gap-3 border-b border-line bg-canvas/85 px-4 backdrop-blur lg:px-8">
          <button
            type="button"
            className="rounded p-1.5 text-muted hover:bg-subtle lg:hidden"
            onClick={() => setMobileOpen(true)}
            aria-label="Open menu"
          >
            <Menu className="size-4" />
          </button>
          <GlobalSearch />
        </header>
        <main id="main" className="mx-auto w-full max-w-[1200px] flex-1 px-4 py-6 lg:px-8 lg:py-8">
          {children ?? <Outlet />}
        </main>
      </div>
      <SettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} />
    </div>
  );
}
