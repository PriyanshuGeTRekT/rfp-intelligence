import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Compass } from "lucide-react";
import { Component, type ErrorInfo, type ReactNode } from "react";
import { createBrowserRouter, Link, RouterProvider, useRouteError } from "react-router-dom";
import { Toaster } from "sonner";

import { AppShell } from "./components/layout/AppShell";
import { EmptyState } from "./components/ui/feedback";
import { TooltipProvider } from "./components/ui/overlay";
import { Button } from "./components/ui/primitives";
import { AskPage } from "./pages/AskPage";
import { BidDetailPage } from "./pages/BidDetailPage";
import { BidsPage } from "./pages/BidsPage";
import { ComparePage } from "./pages/ComparePage";
import { RunsPage } from "./pages/RunsPage";
import { SearchPage } from "./pages/SearchPage";
import { TracePage } from "./pages/TracePage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 15_000, refetchOnWindowFocus: false },
  },
});

function NotFound() {
  return (
    <EmptyState
      icon={<Compass className="size-4" />}
      title="Page not found"
      description="The address may be mistyped, or the page has moved."
      action={
        <Link to="/" className="text-[13px] font-medium text-accent hover:underline">
          Go to bids
        </Link>
      }
    />
  );
}

function RouteError() {
  const error = useRouteError() as Error | undefined;
  return (
    <AppShell>
      <EmptyState
        title="This page hit an unexpected error"
        description={error?.message ?? "Reload to try again."}
        action={<Button onClick={() => window.location.reload()}>Reload</Button>}
      />
    </AppShell>
  );
}

const router = createBrowserRouter([
  {
    element: <AppShell />,
    errorElement: <RouteError />,
    children: [
      { index: true, element: <BidsPage /> },
      { path: "bids/:bidId", element: <BidDetailPage /> },
      { path: "explore", element: <SearchPage /> },
      { path: "assistant", element: <AskPage /> },
      { path: "compare", element: <ComparePage /> },
      { path: "runs", element: <RunsPage /> },
      { path: "runs/:runId", element: <TracePage /> },
      { path: "*", element: <NotFound /> },
    ],
  },
]);

/** Last line of defence for errors outside the router (e.g. in providers). */
class RootBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(error, info.componentStack);
  }
  render() {
    if (this.state.error) {
      return (
        <EmptyState
          title="The app failed to start"
          description={this.state.error.message}
          action={<Button onClick={() => window.location.reload()}>Reload</Button>}
        />
      );
    }
    return this.props.children;
  }
}

export function App() {
  return (
    <RootBoundary>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <RouterProvider router={router} />
          <Toaster position="bottom-right" toastOptions={{ className: "!text-[13px] !border-line !bg-surface !text-ink" }} />
        </TooltipProvider>
      </QueryClientProvider>
    </RootBoundary>
  );
}
