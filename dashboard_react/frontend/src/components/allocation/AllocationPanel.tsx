import React from "react";
import { AllocationWeights, MacroResponse } from "../../types/dashboardV2";

interface AllocationPanelProps {
  macro: MacroResponse | null;
  loading: boolean;
}

const assetLabels: Record<keyof AllocationWeights, string> = {
  gold: "Gold",
  btc: "BTC",
  bond: "Bond",
  commodity: "Commodity",
  cash: "Cash",
};

const assetEmoji: Record<keyof AllocationWeights, string> = {
  gold: "🥇",
  btc: "₿",
  bond: "📊",
  commodity: "🛢",
  cash: "💵",
};

const assets: Array<keyof AllocationWeights> = ["gold", "btc", "bond", "commodity", "cash"];

const LoadingBar: React.FC = () => (
  <div className="animate-pulse rounded-xl border border-slate-700 bg-slate-900 p-3">
    <div className="h-3 w-16 rounded bg-slate-700" />
    <div className="mt-3 h-3 rounded bg-slate-700" />
    <div className="mt-2 h-3 rounded bg-slate-800" />
  </div>
);

export const AllocationPanel: React.FC<AllocationPanelProps> = ({ macro, loading }) => {
  if (loading && !macro) {
    return (
      <div className="rounded-2xl border border-slate-700 bg-slate-800 p-5 shadow-lg shadow-slate-950/30">
        <div className="space-y-3">
          <LoadingBar />
          <LoadingBar />
          <LoadingBar />
        </div>
      </div>
    );
  }

  if (!macro) {
    return <div className="rounded-2xl border border-slate-700 bg-slate-800 p-5 text-sm text-slate-400">Allocation verisi alinmadi.</div>;
  }

  // Generate dynamic rebalance tip
  const generateRebalanceTip = (): string => {
    if (!macro.rebalance_required || macro.rebalance_actions.length === 0) {
      return "Dağılım dengede, rebalance gerekmiyor.";
    }

    const actions = macro.rebalance_actions
      .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))
      .slice(0, 3)
      .map((action) => {
        const delta = Math.abs(action.delta) * 100;
        const emoji = assetEmoji[action.asset];
        return `${emoji} ${assetLabels[action.asset]} ${action.action === "BUY" ? "+" : "-"}${delta.toFixed(1)}%`;
      });

    return actions.join(", ");
  };

  return (
    <div className="rounded-2xl border border-slate-700 bg-slate-800 p-5 shadow-md shadow-slate-950/20 transition-all duration-300 hover:border-slate-500 hover:shadow-lg hover:shadow-slate-950/40">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">Allocation Panel</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">Macro Allocation</h2>
          <p className="mt-2 text-sm leading-6 text-slate-300">{generateRebalanceTip()}</p>
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-semibold flex-shrink-0 ${macro.rebalance_required ? "bg-amber-500/10 text-amber-400" : "bg-emerald-500/10 text-emerald-400"}`}>
          {macro.rebalance_required ? "Rebalance Required" : "Allocation Stable"}
        </span>
      </div>

      <div className="mt-4 space-y-3">
        {assets.map((asset) => {
          const target = macro.allocation_target[asset] * 100;
          const current = macro.allocation_current[asset] * 100;
          const delta = target - current;
          return (
            <div key={asset} className="rounded-xl border border-slate-700 bg-slate-900 p-4 transition-all duration-300 hover:border-slate-500">
              <div className="flex items-center justify-between text-xs uppercase tracking-[0.16em] text-slate-400">
                <span>{assetLabels[asset]}</span>
                <span className={`font-mono ${delta >= 0 ? "text-emerald-400" : "text-rose-400"}`}>{delta >= 0 ? "+" : ""}{delta.toFixed(1)}%</span>
              </div>
              <div className="mt-3 space-y-2">
                <div>
                  <div className="mb-1 flex items-center justify-between text-[11px] uppercase tracking-[0.16em] text-slate-500">
                    <span>Current</span>
                    <span className="font-mono text-slate-300">{current.toFixed(1)}%</span>
                  </div>
                  <div className="h-2.5 rounded-full bg-slate-700">
                    <div className="h-2.5 rounded-full bg-blue-500" style={{ width: `${Math.max(0, Math.min(100, current))}%` }} />
                  </div>
                </div>
                <div>
                  <div className="mb-1 flex items-center justify-between text-[11px] uppercase tracking-[0.16em] text-slate-500">
                    <span>Target</span>
                    <span className="font-mono text-slate-300">{target.toFixed(1)}%</span>
                  </div>
                  <div className="h-2.5 rounded-full bg-slate-700">
                    <div className="h-2.5 rounded-full bg-emerald-500" style={{ width: `${Math.max(0, Math.min(100, target))}%` }} />
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-4 rounded-xl border border-slate-700 bg-slate-900 p-4">
        <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Rebalance Actions</p>
        <div className="mt-3 space-y-2">
          {macro.rebalance_actions.length > 0 ? (
            macro.rebalance_actions.map((item) => (
              <div key={`${item.asset}-${item.action}`} className="flex items-center justify-between rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm transition-colors duration-300 hover:border-slate-500">
                <div>
                  <span className="font-medium text-slate-100">{assetLabels[item.asset]}</span>
                  <span className="ml-2 text-slate-400">{item.action}</span>
                </div>
                <span className={`font-mono ${item.action === "BUY" ? "text-emerald-400" : "text-rose-400"}`}>{(Math.abs(item.delta) * 100).toFixed(1)}%</span>
              </div>
            ))
          ) : (
            <p className="text-sm text-slate-400">Esik ustu drift yok. Rebalance gerekmiyor.</p>
          )}
        </div>
      </div>
    </div>
  );
};