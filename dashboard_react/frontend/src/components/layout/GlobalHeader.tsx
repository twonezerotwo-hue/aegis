/**
 * components/layout/GlobalHeader.tsx
 * AEGIS v7.0 — Premium app-level header
 * Regime badge (color-coded), system health pill, live dot, last-updated,
 * mode toggle, responsive (collapses cleanly on mobile).
 * Data: props-only. No logic changes.
 */

import React, { useEffect, useState } from "react";

interface GlobalHeaderProps {
  regime: string;
  systemHealth: string;
  lastUpdated: string | null;
  liveStatus: "live" | "reconnecting" | "fallback";
  liveMessage?: string | null;
  alertCount?: number;
  killSwitchActive?: boolean;
  dailyPnl?: number | null;
  dailyTradeCount?: number;
}

const getLiveConfig = (
  status: GlobalHeaderProps["liveStatus"],
  msg?: string | null
): { dotCls: string; label: string } => {
  if (status === "live") return { dotCls: "bg-emerald-400 animate-pulse", label: "Live" };
  if (status === "reconnecting") return { dotCls: "bg-amber-400 animate-pulse", label: msg ?? "Reconnecting…" };
  return { dotCls: "bg-rose-500", label: msg ?? "Manual Sync" };
};

const regimeBadgeCls = (regime: string): string => {
  const n = regime.toLowerCase();
  if (n.includes("risk_on") || n.includes("risk on") || n.includes("liquidity"))
    return "border-emerald-500/40 bg-emerald-500/10 text-emerald-300";
  if (n.includes("risk_off") || n.includes("risk off"))
    return "border-rose-500/40 bg-rose-500/10 text-rose-300";
  if (n.includes("stag"))
    return "border-amber-500/40 bg-amber-500/10 text-amber-300";
  return "border-sky-500/40 bg-sky-500/10 text-sky-300";
};

const healthCls = (h: string): string => {
  const n = h.toLowerCase();
  if (n.includes("healthy") || n.includes("ok")) return "text-emerald-400";
  if (n.includes("degraded") || n.includes("warning")) return "text-amber-400";
  return "text-rose-400";
};

export const GlobalHeader: React.FC<GlobalHeaderProps> = ({
  regime,
  systemHealth,
  lastUpdated,
  liveStatus,
  liveMessage,
  alertCount = 0,
  killSwitchActive = false,
  dailyPnl = null,
  dailyTradeCount = 0,
}) => {
  const [clock, setClock] = useState(() => new Date().toLocaleTimeString("tr-TR"));
  const live = getLiveConfig(liveStatus, liveMessage);

  useEffect(() => {
    const id = window.setInterval(() => setClock(new Date().toLocaleTimeString("tr-TR")), 1000);
    return () => window.clearInterval(id);
  }, []);

  return (
    <header
      className="rounded-2xl border border-slate-700/60 bg-slate-900/95 shadow-xl shadow-slate-950/40 backdrop-blur-md
        transition-all duration-300 hover:border-slate-600 hover:shadow-2xl hover:shadow-slate-950/50"
    >
      <div className="flex flex-col gap-4 p-5 xl:flex-row xl:items-center xl:justify-between">

        {/* Brand + regime */}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-3">
            {/* Live pill */}
            <span
              className="inline-flex items-center gap-1.5 rounded-full border border-slate-700 bg-slate-800 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-widest text-slate-300"
              aria-live="polite"
            >
              <span className={`h-2 w-2 rounded-full ${live.dotCls}`} />
              {live.label}
            </span>
            {/* Regime badge */}
            <span
              className={`inline-flex rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-widest ${regimeBadgeCls(regime)}`}
            >
              {regime}
            </span>
            {/* Kill Switch badge */}
            <span
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide ${
                killSwitchActive
                  ? "border-rose-500/60 bg-rose-500/15 text-rose-300 animate-pulse"
                  : "border-slate-700 bg-slate-800/50 text-slate-500"
              }`}
              title="Günlük kayıp limiti durumu"
            >
              <span className={`h-1.5 w-1.5 rounded-full ${killSwitchActive ? "bg-rose-400 animate-ping" : "bg-emerald-400"}`} />
              {killSwitchActive ? "Kill Switch AKTİF" : "Kill Switch: Kapalı"}
            </span>

            {/* Daily P&L */}
            {dailyPnl !== null && (
              <span
                className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-mono font-semibold ${
                  dailyPnl >= 0
                    ? "border-emerald-500/30 bg-emerald-500/8 text-emerald-300"
                    : "border-rose-500/30 bg-rose-500/8 text-rose-300"
                }`}
                title={`Günlük gerçekleşen P&L — ${dailyTradeCount} işlem`}
              >
                {dailyPnl >= 0 ? "+" : ""}${dailyPnl.toFixed(2)}
                <span className="text-[9px] font-normal text-slate-500 ml-0.5">/{dailyTradeCount}i</span>
              </span>
            )}

            {/* Alert badge */}
            {alertCount > 0 && (
              <span
                aria-label={`${alertCount} aktif uyarı`}
                className="inline-flex items-center gap-1 rounded-full border border-rose-500/40 bg-rose-500/10 px-2.5 py-1 text-[11px] font-semibold text-rose-300"
              >
                <span className="h-1.5 w-1.5 rounded-full bg-rose-400 animate-pulse" />
                {alertCount} Alert
              </span>
            )}
          </div>

          <h1 className="mt-2 text-xl font-semibold tracking-tight text-white sm:text-2xl">
            AEGIS&nbsp;
            <span className="text-slate-400">Operational Control</span>
          </h1>

          <div className="mt-1.5 flex flex-wrap items-center gap-4 text-[11px] text-slate-500">
            <span>
              Sistem:{" "}
              <span className={`font-semibold ${healthCls(systemHealth)}`}>{systemHealth}</span>
            </span>
            <span className="font-mono">{clock}</span>
            {lastUpdated && (
              <span>
                Son veri:{" "}
                <span className="font-mono text-slate-400">
                  {new Date(lastUpdated).toLocaleTimeString("tr-TR")}
                </span>
              </span>
            )}
          </div>
        </div>

      </div>
    </header>
  );
};
