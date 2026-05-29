/**
 * src/components/portfolio/AllocationWithTip.tsx
 * Illustrative portfolio allocation card with horizon-aware metadata.
 */

import React from "react";
import type { MacroViewModel } from "../../types/dashboardV2";
import type { Vade } from "../../context/VadeContext";

interface Props {
  macro: MacroViewModel;
  vade: Vade;
}

const ASSET_META: Record<string, { label: string; subtitle: string; icon: string; bar: string }> = {
  gold:      { label: "ALTIN / GOLD",           subtitle: "XAU · Gold futures / physical gold proxy",                        icon: "Au", bar: "bg-amber-400" },
  btc:       { label: "BITCOIN / BTC",           subtitle: "Crypto core risk asset",                                          icon: "₿",  bar: "bg-orange-400" },
  bond:      { label: "TAHVİL / BONDS",          subtitle: "Short-to-medium duration bonds · defensive ballast",              icon: "T",  bar: "bg-sky-400" },
  commodity: { label: "EMTİA / COMMODITIES",     subtitle: "Energy + industrial metals · Brent/WTI · Copper/HG",             icon: "C",  bar: "bg-emerald-400" },
  cash:      { label: "NAKİT / CASH",            subtitle: "Liquidity reserve · opportunity capital · error margin",          icon: "$",  bar: "bg-slate-400" },
};

const ASSETS = ["gold", "btc", "bond", "commodity", "cash"] as const;

const ASSET_TIP_LABEL: Record<string, string> = {
  gold: "Gold",
  btc: "BTC",
  bond: "Bond",
  commodity: "Commodity",
  cash: "Cash",
};

const formatLabel = (value: string): string =>
  value
    .split("_")
    .map((part) => (part.length > 0 ? part.charAt(0).toUpperCase() + part.slice(1).toLowerCase() : part))
    .join(" ");

const deriveTip = (macro: MacroViewModel, vade: Vade): string => {
  if (!macro.rebalance_required || macro.rebalance_actions.length === 0) {
    return "Dagilim dengede, rebalance gerekmiyor.";
  }

  const top3 = macro.rebalance_actions.slice(0, 3);
  const parts = top3.map((action) => {
    const label = ASSET_TIP_LABEL[action.asset] ?? action.asset;
    const sign = action.delta > 0 ? "+" : "";
    return `${label} ${sign}${(action.delta * 100).toFixed(1)}%`;
  });

  const suffix =
    vade === "short"
      ? " Kisa vadede spread maliyetine dikkat."
      : vade === "long"
        ? " Uzun vadeli icin kademeli giris onerilir."
        : "";

  return parts.join(", ") + "." + suffix;
};

export const AllocationWithTip: React.FC<Props> = ({ macro, vade }) => {
  const partialFallback = macro.data_status === "PARTIAL_FALLBACK";
  const fallbackLike = macro.data_status === "FALLBACK" || partialFallback;
  const liveVerifiedMacro =
    macro.data_status === "LIVE" &&
    macro.verified === true &&
    macro.live === true;
  const allocationHorizon = macro.allocation_horizon ?? vade;
  const allocationProfile =
    macro.allocation_profile ??
    (fallbackLike ? "fallback_illustrative" : allocationHorizon === "short" ? "defensive" : allocationHorizon === "long" ? "structural" : "balanced");
  const allocationBasis = macro.allocation_basis ?? [];
  const allocationWarnings = macro.warnings ?? [];
  const tip = liveVerifiedMacro
    ? deriveTip(macro, vade)
    : "Verified allocation decision unavailable because macro data is not fully verified.";
  const sourceLabel = macro.source?.trim() || "unknown";

  return (
    <div
      className="rounded-2xl border border-slate-700/60 bg-slate-900 p-5 shadow-md shadow-slate-950/20
      transition-all duration-300 hover:border-slate-600"
    >
      <p className="mb-4 text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">
        Portfoy Dagilimi
      </p>

      <div className="mb-4 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex rounded-full border border-slate-600 bg-slate-800 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-200">
            Allocation horizon: {allocationHorizon}
          </span>
          <span className="inline-flex rounded-full border border-slate-600 bg-slate-800 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-200">
            Allocation profile: {formatLabel(allocationProfile)}
          </span>
          <span className="inline-flex rounded-full border border-slate-600 bg-slate-800 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-300">
            SOURCE: {sourceLabel}
          </span>
          {partialFallback && (
            <span className="inline-flex rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-amber-100">
              PARTIAL FALLBACK DATA
            </span>
          )}
          {fallbackLike && (
            <span className="inline-flex rounded-full border border-orange-500/30 bg-orange-500/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-orange-200">
              FALLBACK-BASED
            </span>
          )}
          {!liveVerifiedMacro && (
            <span className="inline-flex rounded-full border border-rose-500/30 bg-rose-500/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-rose-200">
              NOT VERIFIED
            </span>
          )}
        </div>

        {allocationBasis.length > 0 && (
          <p className="text-xs leading-5 text-slate-400">
            <span className="font-semibold text-slate-300">Basis:</span>{" "}
            {allocationBasis.map(formatLabel).join(" · ")}
          </p>
        )}

        {fallbackLike && (
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-100">
            Illustrative allocation based on incomplete/fallback macro data.
          </div>
        )}

        {!fallbackLike && allocationWarnings.length > 0 && (
          <div className="rounded-xl border border-slate-700 bg-slate-800/60 px-4 py-3 text-xs text-slate-300">
            {allocationWarnings.join(" ")}
          </div>
        )}
      </div>

      <div className="space-y-3">
        {ASSETS.map((asset) => {
          const meta = ASSET_META[asset];
          const current = macro.allocation_current[asset];
          const target = macro.allocation_target[asset];
          const delta = target - current;

          return (
            <div key={asset}>
              <div className="mb-1 flex items-start justify-between gap-2">
                <div>
                  <span className="text-[11px] font-semibold text-slate-200">
                    <span className="mr-1.5 font-mono text-slate-500">{meta.icon}</span>
                    {meta.label}
                  </span>
                  <p className="text-[9px] text-slate-500 leading-tight mt-0.5">{meta.subtitle}</p>
                </div>
                <div className="flex items-center gap-2 font-mono text-[11px]">
                  <span className="text-slate-500">{(current * 100).toFixed(0)}%</span>
                  <span className="text-slate-700">-&gt;</span>
                  <span className="font-semibold text-white">{(target * 100).toFixed(0)}%</span>
                  {liveVerifiedMacro && Math.abs(delta) >= 0.01 && (
                    <span className={delta > 0 ? "text-emerald-400" : "text-rose-400"}>
                      {delta > 0 ? "+" : ""}
                      {(delta * 100).toFixed(1)}%
                    </span>
                  )}
                </div>
              </div>
              <div className="mb-0.5 h-1 rounded-full bg-slate-700/50">
                <div
                  className={`h-1 rounded-full ${meta.bar} opacity-40 transition-all duration-500`}
                  style={{ width: `${Math.min(100, current * 100)}%` }}
                />
              </div>
              <div className="h-1.5 rounded-full bg-slate-700/50">
                <div
                  className={`h-1.5 rounded-full ${meta.bar} transition-all duration-500`}
                  style={{ width: `${Math.min(100, target * 100)}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-4 rounded-r-lg border-l-4 border-blue-400 bg-slate-800/50 px-4 py-3">
        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-blue-400">
          AI Oneri
        </p>
        <p className="text-xs italic leading-5 text-slate-300">{tip}</p>
      </div>
    </div>
  );
};
