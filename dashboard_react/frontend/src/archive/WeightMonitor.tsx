/**
 * components/WeightMonitor.tsx
 * AEGIS v7.0 — Module weight drift monitor (premium UI)
 * Bar charts per module, drift progress (green→amber→red),
 * Frozen / Active guard badge, backup badge, hover micro-interactions.
 */

import React from "react";
import type { WeightsResponse } from "../types/dashboardV2";
import { SkeletonLoader } from "../components/ui/SkeletonLoader";

interface WeightMonitorProps {
  weights: WeightsResponse | null;
  loading: boolean;
}

const MODULE_COLORS: Record<string, { bar: string; text: string }> = {
  touche:      { bar: "bg-violet-500",  text: "text-violet-300" },
  fundamental: { bar: "bg-sky-500",     text: "text-sky-300" },
  news:        { bar: "bg-amber-500",   text: "text-amber-300" },
  sentinel:    { bar: "bg-rose-400",    text: "text-rose-300" },
  quantum:     { bar: "bg-emerald-500", text: "text-emerald-300" },
};

const MODULE_LABELS: Record<string, string> = {
  touche:      "Touche",
  fundamental: "Fundamental",
  news:        "News",
  sentinel:    "Sentinel",
  quantum:     "Quantum",
};

export const WeightMonitor: React.FC<WeightMonitorProps> = ({ weights, loading }) => {
  if (loading && !weights) {
    return <SkeletonLoader variant="bar-chart" lines={5} />;
  }

  if (!weights) {
    return (
      <div className="rounded-2xl border border-slate-700/60 bg-slate-900 p-5 text-sm text-slate-500">
        Ağırlık verisi alınamadı.
      </div>
    );
  }

  const { drift_total, drift_limit, drift_frozen, backup_exists } = weights;
  const driftRatio = Math.min(1, drift_total / (drift_limit || 0.15));
  const driftBarPct = Math.round(driftRatio * 100);
  const driftBarColor =
    drift_frozen         ? "bg-rose-500" :
    driftRatio > 0.7     ? "bg-amber-500" :
    driftRatio > 0.4     ? "bg-amber-400/70" :
                           "bg-emerald-500";

  const moduleEntries = Object.entries(weights.weights) as [string, number][];

  return (
    <div
      className="rounded-2xl border border-slate-700/60 bg-slate-900 p-5 shadow-md shadow-slate-950/30
        transition-all duration-300 hover:border-slate-600 hover:shadow-lg hover:shadow-slate-950/40"
    >
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">
            Weight Monitor
          </p>
          <p className="mt-0.5 text-sm font-semibold text-white">Modül Ağırlıkları</p>
        </div>
        <div className="flex items-center gap-2">
          {backup_exists && (
            <span className="rounded-full border border-sky-500/30 bg-sky-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-widest text-sky-300">
              Backup ✓
            </span>
          )}
          <span
            className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-widest ${
              drift_frozen
                ? "border-rose-500/30 bg-rose-500/10 text-rose-400"
                : "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
            }`}
          >
            {drift_frozen ? "Frozen" : "Active"}
          </span>
        </div>
      </div>

      {/* Drift progress */}
      <div className="mt-4">
        <div className="flex items-center justify-between text-[10px] text-slate-500 uppercase tracking-[0.14em]">
          <span>Weekly Drift</span>
          <span className="font-mono text-slate-300">
            {(drift_total * 100).toFixed(1)}%&nbsp;/&nbsp;{(drift_limit * 100).toFixed(0)}%
          </span>
        </div>
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-700/70">
          <div
            className={`h-1.5 rounded-full transition-all duration-700 ease-out ${driftBarColor}`}
            style={{ width: `${driftBarPct}%` }}
          />
        </div>
      </div>

      {/* Divider */}
      <div className="my-4 border-t border-slate-700/50" />

      {/* Per-module bars */}
      <div className="flex flex-col gap-2.5">
        {moduleEntries.map(([mod, value]: [string, number]) => {
          const colors = MODULE_COLORS[mod] ?? { bar: "bg-slate-500", text: "text-slate-400" };
          const label = MODULE_LABELS[mod] ?? mod;
          const pct = Math.round(value * 100);
          // max weight is 50%, scale bar to fill appropriately
          const barWidth = Math.round((value / 0.5) * 100);

          return (
            <div key={mod} className="group flex items-center gap-3">
              <span className={`w-[72px] shrink-0 text-[10px] uppercase tracking-[0.1em] ${colors.text} opacity-70 group-hover:opacity-100 transition-opacity`}>
                {label}
              </span>
              <div className="flex-1 h-1.5 overflow-hidden rounded-full bg-slate-700/60">
                <div
                  className={`h-1.5 rounded-full transition-all duration-700 ease-out ${colors.bar}`}
                  style={{ width: `${Math.max(2, barWidth)}%` }}
                />
              </div>
              <span className="w-9 shrink-0 text-right font-mono text-[11px] text-slate-300">
                {pct}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};
