import React, { useEffect, useState, Suspense, lazy } from "react";
import { Dashboard } from "./pages/Dashboard";
import { DashboardV2 } from "./pages/DashboardV2";
import { ConsensusStoreProvider } from "./store/consensusStore";
import { SkeletonLoader } from "./components/ui/SkeletonLoader";
import { ThemeProvider } from "./components/ui/ThemeToggle";

const BacktestV2 = lazy(() =>
  import("./pages/BacktestV2").then((m) => ({ default: m.BacktestV2 }))
);

const getActivePath = (): string => window.location.pathname;

/** Navigate within the SPA without full reload */
export function navigateTo(path: string) {
  window.history.pushState(null, "", path);
  window.dispatchEvent(new CustomEvent("aegis:navigate"));
}

const V2Fallback: React.FC = () => (
  <div className="min-h-screen bg-slate-950 p-4">
    <div className="grid gap-4 grid-cols-1 md:grid-cols-2 xl:grid-cols-3">
      <div className="col-span-1 md:col-span-2 xl:col-span-3">
        <SkeletonLoader variant="stat" />
      </div>
      <SkeletonLoader variant="card" lines={3} />
      <SkeletonLoader variant="card" lines={3} />
      <SkeletonLoader variant="bar-chart" lines={5} />
    </div>
  </div>
);

const App: React.FC = () => {
  const [path, setPath] = useState<string>(getActivePath);

  useEffect(() => {
    const handleLocationChange = () => {
      setPath(getActivePath());
    };

    window.addEventListener("popstate", handleLocationChange);
    window.addEventListener("aegis:navigate", handleLocationChange as EventListener);

    return () => {
      window.removeEventListener("popstate", handleLocationChange);
      window.removeEventListener("aegis:navigate", handleLocationChange as EventListener);
    };
  }, []);

  // V2 backtest route (lazy-loaded)
  if (path === "/v2/backtest") {
    return (
      <ThemeProvider>
        <Suspense fallback={<V2Fallback />}>
          <BacktestV2 />
        </Suspense>
      </ThemeProvider>
    );
  }

  // V2 dashboard
  if (path === "/v2" || path.startsWith("/v2/")) {
    return (
      <ThemeProvider>
        <ConsensusStoreProvider>
          <Suspense fallback={<V2Fallback />}>
            <DashboardV2 />
          </Suspense>
        </ConsensusStoreProvider>
      </ThemeProvider>
    );
  }

  // V1 legacy
  return <Dashboard />;
};

export default App;