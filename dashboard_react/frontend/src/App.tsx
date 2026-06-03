import React, { Suspense } from "react";
import { DashboardV2 } from "./pages/DashboardV2";
import { ConsensusStoreProvider } from "./store/consensusStore";
import { SkeletonLoader } from "./components/ui/SkeletonLoader";
import { ThemeProvider } from "./components/ui/ThemeToggle";

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

const App: React.FC = () => (
  <ThemeProvider>
    <ConsensusStoreProvider>
      <Suspense fallback={<PageFallback />}>
        <DashboardV2 />
      </Suspense>
    </ConsensusStoreProvider>
  </ThemeProvider>
);

export default App;
