import React, { useEffect, useState, Suspense } from "react";
import { DashboardV2 } from "./pages/DashboardV2";
import { ConsensusStoreProvider } from "./store/consensusStore";
import { SkeletonLoader } from "./components/ui/SkeletonLoader";
import { ThemeProvider } from "./components/ui/ThemeToggle";

const getActivePath = (): string => window.location.pathname;

/** Navigate within the SPA without full reload */
export function navigateTo(path: string) {
  window.history.pushState(null, "", path);
  window.dispatchEvent(new CustomEvent("aegis:navigate"));
}

const PageFallback: React.FC = () => (
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
    const handleLocationChange = () => setPath(getActivePath());
    window.addEventListener("popstate", handleLocationChange);
    window.addEventListener("aegis:navigate", handleLocationChange as EventListener);
    return () => {
      window.removeEventListener("popstate", handleLocationChange);
      window.removeEventListener("aegis:navigate", handleLocationChange as EventListener);
    };
  }, []);

  // All routes render DashboardV2 (tabs handle sub-navigation)
  return (
    <ThemeProvider>
      <ConsensusStoreProvider>
        <Suspense fallback={<PageFallback />}>
          <DashboardV2 />
        </Suspense>
      </ConsensusStoreProvider>
    </ThemeProvider>
  );
};

export default App;
