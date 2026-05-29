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
  gold:      { label: "ALTIN / GOLD",       subtitle: "XAU · Gold futures / physical gold proxy",            icon: "Au", bar: "bg-amber-400" },
  btc:       { label: "BITCOIN / BTC",       subtitle: "Crypto core risk asset",                              icon: "₿",  bar: "bg-orange-400" },
  bond:      { label: "TAHVİL / BONDS",      subtitle: "Short-to-medium duration bonds · defensive ballast",  icon: "T",  bar: "bg-sky-400" },
  commodity: { label: "EMTİA / COMMODITIES", subtitle: "Energy + industrial metals · Brent/WTI · Copper/HG", icon: "C",  bar: "bg-emerald-400" },
  cash:      { label: "NAKİT / CASH",        subtitle: "Liquidity reserve · opportunity capital",             icon: "$",  bar: "bg-slate-400" },
};

const ASSETS = ["gold", "btc", "bond", "commodity", "cash"] as const;

const ASSET_TIP_LABEL: Record<string, string> = {
  gold: "Altın",
  btc: "BTC",
  bond: "Tahvil",
  commodity: "Emtia",
  cash: "Nakit",
};

/** Convert raw basis strings to human-readable labels. */
const formatBasisItem = (value: string): string => {
  const lower = value.toLowerCase();
  if (lower.startsWith("horizon_base:")) {
    const h = lower.split(":")[1];
    return `Vade: ${{ short: "Kısa", medium: "Orta", long: "Uzun" }[h] ?? h}`;
  }
  if (lower.startsWith("regime_overlay:")) return `Rejim: ${value.split(":")[1]}`;
  if (lower.startsWith("profile:")) {
    const p = lower.split(":")[1];
    return `Profil: ${{ defensive: "Defansif", balanced: "Dengeli", structural: "Yapısal", fallback_illustrative: "İllüstratif" }[p] ?? p}`;
  }
  if (lower.startsWith("event_risk_overlay:")) {
    const pct = Math.round(parseFloat(value.split(":")[1]) * 100);
    return `Olay riski: %${pct}`;
  }
  if (lower.startsWith("hedge_overlay:")) return `Hedge: ${lower.includes("on") ? "Aktif" : "Kapalı"}`;
  if (lower.startsWith("volatility_overlay:")) return lower.includes("high") ? "Yüksek VIX" : "Düşük VIX";
  if (lower.startsWith("data_quality_overlay:")) return "Veri kalite düzeltmesi";
  if (lower.startsWith("ai_signal:")) {
    // ai_signal:T=0.54,F=0.55,N=0.72,S=0.49
    try {
      const params = value.split(":")[1].split(",");
      const map: Record<string, string> = { T: "Touche", F: "Fund", N: "Haber", S: "Sentinel" };
      const parts = params.map((p) => {
        const [k, v] = p.split("=");
        return `${map[k] ?? k} ${Math.round(parseFloat(v) * 100)}`;
      });
      return `AI Sinyal: ${parts.join(" / ")}`;
    } catch { return "AI Sinyal"; }
  }
  // generic fallback
  return value
    .split(/[_:]/)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
};

const deriveTip = (macro: MacroViewModel, vade: Vade): string => {
  if (!macro.rebalance_required || macro.rebalance_actions.length === 0) {
    return "Dağılım dengede, rebalance gerekmiyor.";
  }
  const top3 = macro.rebalance_actions.slice(0, 3);
  const parts = top3.map((action) => {
    const label = ASSET_TIP_LABEL[action.asset] ?? action.asset;
    const sign = action.delta > 0 ? "+" : "";
    return `${label} ${sign}${(action.delta * 100).toFixed(1)}%`;
  });
  const suffix =
    vade === "short"
      ? " Kısa vadede spread maliyetine dikkat."
      : vade === "long"
        ? " Uzun vade için kademeli giriş önerilir."
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
  const allocationWarnings = (macro.warnings ?? []).filter(
    (w) => !w.startsWith("Illustrative allocation")
  );
  const tip = liveVerifiedMacro
    ? deriveTip(macro, vade)
    : "Doğrulanmış veri olmadan kesin rebalance önerisi yapılamaz.";

  return (
    <div className="rounded-2xl border border-slate-700/60 bg-slate-900 p-5 shadow-md shadow-slate-950/20 transition-all duration-300 hover:border-slate-600">

      {/* Header row */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">
          Portföy Dağılımı
        </p>
        <div className="flex flex-wrap gap-1.5">
          <span className="inline-flex rounded-full border border-slate-600 bg-slate-800 px-2.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-slate-300">
            {{short:"Kısa", medium:"Orta", long:"Uzun"}[allocationHorizon] ?? allocationHorizon}
            {" · "}
            {{defensive:"Defansif", balanced:"Dengeli", structural:"Yapısal", fallback_illustrative:"İllüstratif"}[allocationProfile] ?? allocationProfile}
          </span>
          {fallbackLike && (
            <span className="inline-flex rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-amber-200">
              Eksik veri
            </span>
          )}
          {!liveVerifiedMacro && !fallbackLike && (
            <span className="inline-flex rounded-full border border-rose-500/30 bg-rose-500/10 px-2.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-rose-200">
              Doğrulanmamış
            </span>
          )}
        </div>
      </div>

      {/* Basis — human-readable */}
      {allocationBasis.length > 0 && (
        <p className="mb-3 text-[9px] leading-5 text-slate-500">
          {allocationBasis.map(formatBasisItem).join(" · ")}
        </p>
      )}

      {/* Alerts */}
      {fallbackLike && (
        <div className="mb-3 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[10px] text-amber-100">
          İllüstratif dağılım — eksik/fallback makro veriye dayalı.
        </div>
      )}

      {!fallbackLike && allocationWarnings.length > 0 && (
        <div className="mb-3 rounded-xl border border-slate-700 bg-slate-800/60 px-3 py-2 text-[10px] text-slate-300">
          {allocationWarnings.join(" ")}
        </div>
      )}

      {/* Asset bars */}
      <div className="space-y-3.5">
        {ASSETS.map((asset) => {
          const meta = ASSET_META[asset];
          const current = macro.allocation_current[asset];
          const target = macro.allocation_target[asset];
          const delta = target - current;

          return (
            <div key={asset}>
              <div className="mb-1.5 flex items-start justify-between gap-2">
                {/* Label with badge icon */}
                <div className="flex items-center gap-2 min-w-0">
                  <span className="inline-flex h-5 w-7 shrink-0 items-center justify-center rounded bg-slate-700/80 font-mono text-[9px] font-bold text-slate-300">
                    {meta.icon}
                  </span>
                  <div className="min-w-0">
                    <p className="text-[11px] font-semibold text-slate-100 leading-none">{meta.label}</p>
                    <p className="text-[9px] text-slate-500 leading-tight mt-0.5 truncate">{meta.subtitle}</p>
                  </div>
                </div>
                {/* Weight display */}
                <div className="flex shrink-0 items-center gap-1.5 font-mono text-[11px]">
                  <span className="text-slate-400 font-semibold">{(target * 100).toFixed(0)}%</span>
                  {liveVerifiedMacro && Math.abs(delta) >= 0.01 && (
                    <span className={`text-[10px] ${delta > 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {delta > 0 ? "▲" : "▼"}{Math.abs(delta * 100).toFixed(1)}pp
                    </span>
                  )}
                </div>
              </div>
              <div className="h-2 rounded-full bg-slate-700/50">
                <div
                  className={`h-2 rounded-full ${meta.bar} transition-all duration-500`}
                  style={{ width: `${Math.min(100, target * 100)}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>

      {/* Position tracking note */}
      <p className="mt-2 text-right text-[9px] italic text-slate-600">
        * Mevcut pozisyon takibi yok — gösterilen hedef ağırlıktır
      </p>

      {/* AI tip */}
      <div className="mt-4 rounded-r-lg border-l-4 border-blue-400 bg-slate-800/50 px-4 py-3">
        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-blue-400">
          AI Öneri
        </p>
        <p className="text-xs italic leading-5 text-slate-300">{tip}</p>
      </div>
    </div>
  );
};
