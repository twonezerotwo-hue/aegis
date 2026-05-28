/**
 * components/AttributionPanel.tsx
 * AEGIS v7.0 — Per-trade module attribution (premium UI)
 * Symmetric bar chart (positive = green, negative = red),
 * winner/loser badges, expandable trade detail section.
 */

import React, { useState } from "react";
import type { TradeAttributionResult } from "../types/dashboardV2";
import { SkeletonLoader } from "../components/ui/SkeletonLoader";

interface AttributionPanelProps {
  attribution: TradeAttributionResult | null;
  loading: boolean;
}

export const AttributionPanel: React.FC<AttributionPanelProps> = ({ attribution, loading }) => {
  const [detailOpen, setDetailOpen] = useState(false);

  if (loading && !attribution) {
    return <SkeletonLoader variant="bar-chart" lines={5} />;
  }

  if (!attribution) {
    return (
      <div className="rounded-2xl border border-slate-700/60 bg-slate-900 p-5">
        <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">Attribution</p>
        <p className="mt-2 text-sm font-semibold text-white">Trade Attribution</p>
        <p className="mt-3 text-xs text-slate-500">
          Trade kapandıktan sonra modül katkı yüzdeleri burada gösterilir.
        </p>
      </div>
    );
  }

  const {
    contribution_pct,
    winning_modules,
    losing_modules,
    attribution_ref,
    error,
  } = attribution;

  const entries: [string, number][] = (Object.entries(contribution_pct) as [string, number][]).sort(
    (a, b) => Math.abs(b[1]) - Math.abs(a[1])
  );
  const maxAbs = entries.reduce((m, [, v]) => Math.max(m, Math.abs(v)), 0.0001);

  return (
    <div
      className="rounded-2xl border border-slate-700/60 bg-slate-900 shadow-md shadow-slate-950/30
        transition-all duration-300 hover:border-slate-600"
    >
      {/* Header */}
      <div className="p-5 pb-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">Attribution</p>
            <p className="mt-0.5 text-sm font-semibold text-white">Trade Attribution</p>
          </div>
          <div className="flex items-center gap-2">
            {error && (
              <span className="rounded-full border border-rose-500/30 bg-rose-500/10 px-2 py-0.5 text-[10px] font-semibold text-rose-400">
                Error
              </span>
            )}
            {attribution_ref && (
              <span className="max-w-[140px] truncate rounded-full border border-slate-700 bg-slate-800 px-2 py-0.5 font-mono text-[9px] text-slate-500">
                {attribution_ref}
              </span>
            )}
          </div>
        </div>

        {/* Winner / loser badges */}
        {(winning_modules.length > 0 || losing_modules.length > 0) && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {winning_modules.map((mod: string) => (
              <span
                key={mod}
                className="rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-300"
              >
                ↑ {mod}
              </span>
            ))}
            {losing_modules.map((mod: string) => (
              <span
                key={mod}
                className="rounded-full border border-rose-500/25 bg-rose-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-rose-300"
              >
                ↓ {mod}
              </span>
            ))}
          </div>
        )}

        {/* Contribution bars */}
        <div className="mt-4 flex flex-col gap-2.5">
          {entries.map(([mod, value]: [string, number]) => {
            const pct = value / maxAbs;
            const isPos = value >= 0;
            const barW = Math.abs(pct) * 100;
            const label = mod.charAt(0).toUpperCase() + mod.slice(1);
            const valStr = value >= 0
              ? `+${(value * 100).toFixed(1)}%`
              : `${(value * 100).toFixed(1)}%`;

            return (
              <div key={mod} className="group flex items-center gap-3">
                <span className="w-[72px] shrink-0 text-[10px] uppercase tracking-[0.1em] text-slate-500 group-hover:text-slate-300 transition-colors">
                  {label}
                </span>
                <div className="flex-1 h-1.5 overflow-hidden rounded-full bg-slate-700/60">
                  <div
                    className={`h-1.5 rounded-full transition-all duration-700 ease-out ${isPos ? "bg-emerald-500" : "bg-rose-500"}`}
                    style={{ width: `${Math.max(2, barW)}%` }}
                  />
                </div>
                <span className={`w-12 shrink-0 text-right font-mono text-[11px] ${isPos ? "text-emerald-400" : "text-rose-400"}`}>
                  {valStr}
                </span>
              </div>
            );
          })}
        </div>

        {entries.length === 0 && (
          <p className="mt-4 text-xs text-slate-500">Henüz attribution verisi yok.</p>
        )}
      </div>

      {/* Expandable detail */}
      {attribution_ref && (
        <>
          <button
            type="button"
            onClick={() => setDetailOpen((v) => !v)}
            aria-expanded={detailOpen}
            className="flex w-full items-center justify-between border-t border-slate-700/50 px-5 py-3 text-left transition-colors hover:bg-slate-800/40"
          >
            <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
              Trade Detay
            </span>
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
              className={`h-3.5 w-3.5 text-slate-500 transition-transform duration-200 ${detailOpen ? "rotate-180" : "rotate-0"}`}
            >
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>
          <div
            className={`overflow-hidden transition-all duration-250 ease-in-out ${detailOpen ? "max-h-[300px]" : "max-h-0"}`}
          >
            <div className="px-5 pb-5 pt-3">
              <div className="rounded-xl border border-slate-700/50 bg-slate-800/50 p-3 font-mono text-[10px] text-slate-400 space-y-1">
                <div className="flex justify-between">
                  <span>Ref:</span>
                  <span className="text-slate-300">{attribution_ref}</span>
                </div>
                <div className="flex justify-between">
                  <span>Winners:</span>
                  <span className="text-emerald-400">{winning_modules.join(", ") || "—"}</span>
                </div>
                <div className="flex justify-between">
                  <span>Losers:</span>
                  <span className="text-rose-400">{losing_modules.join(", ") || "—"}</span>
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
