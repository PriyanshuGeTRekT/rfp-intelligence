import { Menu, Search, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { cn } from "../../lib/cn";
import { useHealth, useJobs } from "../../lib/queries";
import { Tooltip } from "../ui/overlay";
import { Dot, Kbd } from "../ui/primitives";
import { SettingsDialog } from "./SettingsDialog";

const NAV = [
  { to: "/", label: "Bids", end: true },
  { to: "/explore", label: "Search" },
  { to: "/assistant", label: "Ask" },
  { to: "/compare", label: "Compare" },
  { to: "/runs", label: "Runs" },
];

function Wordmark() {
  return (
    <Link to="/" className="flex shrink-0 items-center gap-2 text-sm font-semibold tracking-[-0.01em] text-ink">
      <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden className="text-ink">
        <rect x="0.5" y="0.5" width="13" height="13" fill="none" stroke="currentColor" />
        <rect x="3.5" y="3.5" width="7" height="7" fill="currentColor" />
      </svg>
      RFP Intelligence
    </Link>
  );
}

function NavLinks({ vertical, onNavigate }: { vertical?: boolean; onNavigate?: () => void }) {
  const jobs = useJobs();
  const running = jobs.data?.filter((j) => j.status === "running" || j.status === "queued").length ?? 0;
  return (
    <nav aria-label="Main" className={cn("flex", vertical ? "flex-col gap-0.5" : "h-11 items-stretch gap-1")}>
      {NAV.map(({ to, label, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              "flex items-center gap-2 text-sm font-medium transition-colors",
              vertical ? "h-9 rounded px-2" : "px-2.5",
              isActive ? cn("text-ink", vertical ? "bg-subtle" : "shadow-[inset_0_-2px_0_rgb(var(--ink))]") : "text-muted hover:text-ink",
            )
          }
        >
          {label}
          {to === "/runs" && running > 0 && (
            <span className="num inline-flex items-center gap-1 font-mono text-2xs text-accent" aria-label={`${running} running`}>
              <Dot tone="accent" />
              {running}
            </span>
          )}
        </NavLink>
      ))}
    </nav>
  );
}

function ServerStatus() {
  const health = useHealth();
  const label = health.isError ? "Unreachable" : health.data ? health.data.extract_model : "Connecting…";
  return (
    <Tooltip content={health.data ? `${health.data.llm_provider} · v${health.data.version}` : label} side="bottom">
      <div className={cn("hidden min-w-0 items-center gap-2 font-mono text-2xs md:flex", health.isError ? "text-bad" : "text-muted")} tabIndex={0}>
        {health.isError ? <Dot tone="bad" /> : health.data ? <span className="inline-block size-1.5 rounded-full bg-ink" aria-hidden /> : <Dot tone="neutral" hollow />}
        <span className="max-w-[200px] truncate">{label}</span>
      </div>
    </Tooltip>
  );
}

const IS_MAC = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.userAgent);

function GlobalSearch({ className }: { className?: string }) {
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
    <form onSubmit={submit} role="search" className={cn("relative w-full max-w-[360px]", className)}>
      <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-faint" aria-hidden />
      <input
        ref={ref}
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search all documents"
        aria-label="Search all documents"
        className="h-7 w-full rounded border border-control bg-surface pl-7 pr-16 text-xs placeholder:text-faint hover:border-ink focus:border-accent"
      />
      <span className="pointer-events-none absolute right-1.5 top-1/2 hidden -translate-y-1/2 gap-0.5 sm:flex">
        <Kbd>{IS_MAC ? "⌘" : "Ctrl"}</Kbd>
        <Kbd>K</Kbd>
      </span>
    </form>
  );
}

export function AppShell({ children }: { children?: ReactNode }) {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="sr-only z-50 rounded bg-surface px-3 py-2 focus:not-sr-only focus:fixed focus:left-3 focus:top-3">
        Skip to content
      </a>

      <header className="sticky top-0 z-30 flex h-11 items-center gap-5 border-b border-line bg-canvas px-4 lg:px-6">
        <button type="button" className="-ml-1 rounded p-1.5 text-muted hover:bg-subtle lg:hidden" onClick={() => setMenuOpen(true)} aria-label="Open menu">
          <Menu className="size-4" />
        </button>
        <Wordmark />
        <div className="hidden lg:block">
          <NavLinks />
        </div>
        <GlobalSearch className="ml-auto hidden sm:block" />
        <ServerStatus />
        <button type="button" onClick={() => setSettingsOpen(true)} className="rounded p-1.5 text-muted hover:bg-subtle hover:text-ink" aria-label="Settings">
          <SlidersHorizontal className="size-4" />
        </button>
      </header>

      {menuOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/30" onClick={() => setMenuOpen(false)} aria-hidden />
          <aside className="absolute inset-y-0 left-0 flex w-64 flex-col gap-4 border-r border-line bg-canvas p-4 shadow-dialog">
            <div className="flex items-center justify-between">
              <Wordmark />
              <button type="button" className="rounded p-1 text-muted hover:bg-subtle" onClick={() => setMenuOpen(false)} aria-label="Close menu">
                <X className="size-4" />
              </button>
            </div>
            <GlobalSearch />
            <NavLinks vertical onNavigate={() => setMenuOpen(false)} />
          </aside>
        </div>
      )}

      <main id="main" className="w-full flex-1 px-4 py-5 lg:px-6 lg:py-6">
        {children ?? <Outlet />}
      </main>
      <SettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} />
    </div>
  );
}
