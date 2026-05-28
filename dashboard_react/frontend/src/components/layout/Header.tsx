import React, { useEffect, useState } from "react";

type DashboardMode = "legacy" | "v2";

interface HeaderProps {
  regime: string;
  systemHealth: string;
  lastUpdated: string | null;
  currentMode: DashboardMode;
  liveStatus: "live" | "reconnecting" | "fallback";
  liveMessage?: string | null;
}

const getLiveIndicator = (status: HeaderProps["liveStatus"], liveMessage?: string | null): { dot: string; label: string } => {
  if (status === "live") {
    return { dot: "bg-emerald-400 animate-pulse", label: "Live" };
  }

  if (status === "reconnecting") {
    return { dot: "bg-rose-400", label: liveMessage || "Reconnecting..." };
  }

  return { dot: "bg-rose-400", label: liveMessage || "Manual Sync" };
};

const navigateTo = (path: string) => {
  if (window.location.pathname === path) {
    return;
  }

  window.history.pushState({}, "", path);
  window.dispatchEvent(new Event("aegis:navigate"));
};

const getHealthClasses = (systemHealth: string): string => {
  const normalized = systemHealth.toLowerCase();

  if (normalized.includes("healthy") || normalized.includes("ok")) {
    return "border-emerald-500/30 bg-emerald-500/10 text-emerald-300";
  }

  if (normalized.includes("degraded") || normalized.includes("warning")) {
    return "border-amber-500/30 bg-amber-500/10 text-amber-300";
  }

  return "border-rose-500/30 bg-rose-500/10 text-rose-300";
};

const getRegimeBadgeClasses = (regime: string): string => {
  const normalized = regime.toLowerCase();

  if (normalized.includes("stag")) {
    return "border-amber-500/30 bg-amber-500/10 text-amber-400";
  }

  if (normalized.includes("risk_off") || normalized.includes("risk off")) {
    return "border-rose-500/30 bg-rose-500/10 text-rose-400";
  }

  if (normalized.includes("liquidity") || normalized.includes("risk_on") || normalized.includes("risk on")) {
    return "border-emerald-500/30 bg-emerald-500/10 text-emerald-400";
  }

  return "border-blue-500/30 bg-blue-500/10 text-blue-400";
};

export const Header: React.FC<HeaderProps> = ({
  regime,
  systemHealth,
  lastUpdated,
  currentMode,
  liveStatus,
  liveMessage,
}) => {
  const [clock, setClock] = useState<string>(new Date().toLocaleTimeString("tr-TR"));
  const liveIndicator = getLiveIndicator(liveStatus, liveMessage);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      setClock(new Date().toLocaleTimeString("tr-TR"));
    }, 1000);

    return () => window.clearInterval(intervalId);
  }, []);

  return (
    <header className="rounded-2xl border border-slate-700 bg-slate-800/95 p-5 shadow-xl shadow-slate-950/30 backdrop-blur-sm transition-all duration-300 hover:border-slate-500 hover:shadow-2xl hover:shadow-slate-950/40">
      <div className="flex flex-col gap-5 xl:flex-row xl:items-center xl:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-400">
              AEGIS Dashboard V2
            </p>
            <div className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.16em] text-slate-200">
              <span className={`h-2.5 w-2.5 rounded-full ${liveIndicator.dot}`} />
              <span>{liveIndicator.label}</span>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold text-white sm:text-3xl">Operational Control Surface</h1>
            <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] ${getRegimeBadgeClasses(regime)}`}>
              [{regime}]
            </span>
          </div>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">
            Consensus ve macro akisi birlikte izlenir, eski dashboard ise kok rotada aynen korunur.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-xl border border-slate-700 bg-slate-900 px-4 py-3 transition-all duration-300 hover:border-slate-500 hover:shadow-lg hover:shadow-slate-950/30">
            <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Rejim</p>
            <p className={`mt-2 inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.16em] ${getRegimeBadgeClasses(regime)}`}>
              {regime}
            </p>
          </div>

          <div className={`rounded-xl border px-4 py-3 transition-all duration-300 hover:border-slate-500 hover:shadow-lg hover:shadow-slate-950/30 ${getHealthClasses(systemHealth)}`}>
            <p className="text-xs uppercase tracking-[0.2em] opacity-80">Sistem Sagligi</p>
            <p className="mt-2 text-sm font-medium">{systemHealth}</p>
          </div>

          <div className="rounded-xl border border-slate-700 bg-slate-900 px-4 py-3 transition-all duration-300 hover:border-slate-500 hover:shadow-lg hover:shadow-slate-950/30">
            <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Saat</p>
            <p className="mt-2 font-mono text-sm font-medium text-white">{clock}</p>
            <p className="mt-1 font-mono text-xs text-slate-500">
              {lastUpdated ? `Son veri ${new Date(lastUpdated).toLocaleTimeString("tr-TR")}` : "Veri bekleniyor"}
            </p>
          </div>

          <div className="rounded-xl border border-slate-700 bg-slate-900 p-2 transition-all duration-300 hover:border-slate-500 hover:shadow-lg hover:shadow-slate-950/30">
            <p className="px-2 pt-1 text-xs uppercase tracking-[0.2em] text-slate-500">Mod</p>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => navigateTo("/")}
                className={`rounded-lg px-3 py-2 text-sm font-medium transition-all duration-300 ${
                  currentMode === "legacy"
                    ? "bg-amber-500 text-slate-900"
                    : "bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white"
                }`}
              >
                Legacy
              </button>
              <button
                type="button"
                onClick={() => navigateTo("/v2")}
                className={`rounded-lg px-3 py-2 text-sm font-medium transition-all duration-300 ${
                  currentMode === "v2"
                    ? "bg-emerald-500 text-slate-900"
                    : "bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white"
                }`}
              >
                V2
              </button>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
};