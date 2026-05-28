import React from "react";

export const BacktestTab: React.FC = () => {
  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-slate-700 bg-slate-900/90 p-5">
        <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Backtest Workspace</p>
        <h3 className="mt-2 text-xl font-semibold text-white">Walk-forward ve rapor kumesi hazir</h3>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-300">
          Bu sekme code-splitting icin ayri chunk olarak yuklenir. Backtest verileri ve rapor panelleri aktiflestirildiginde ilk acilista ana bundle'i sisirmez.
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <div className="rounded-2xl border border-slate-700 bg-slate-900/90 p-4">
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Symbol Scope</p>
          <p className="mt-2 font-mono text-sm text-slate-200">BTC/USDT, ETH/USDT, SOL/USDT</p>
        </div>
        <div className="rounded-2xl border border-slate-700 bg-slate-900/90 p-4">
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Window</p>
          <p className="mt-2 font-mono text-sm text-slate-200">5m - 1W</p>
        </div>
        <div className="rounded-2xl border border-slate-700 bg-slate-900/90 p-4">
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Mode</p>
          <p className="mt-2 font-mono text-sm text-emerald-300">Ready for on-demand load</p>
        </div>
      </div>
    </div>
  );
};
