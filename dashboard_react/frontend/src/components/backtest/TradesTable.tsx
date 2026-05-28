/**
 * components/backtest/TradesTable.tsx
 * AEGIS v7.3 — Responsive trades table with horizontal scroll on mobile
 * Columns: entry/exit time, price, PnL, regime
 */
import React from "react";
import type { BacktestTrade } from "../../types/backtestV2";

interface TradesTableProps {
  trades: BacktestTrade[];
}

export const TradesTable: React.FC<TradesTableProps> = ({ trades }) => {
  if (!trades || trades.length === 0) {
    return (
      <div className="text-center py-8 text-slate-500 text-sm">
        No trades executed in this period
      </div>
    );
  }

  return (
    <div className="overflow-x-auto -mx-1 scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-transparent">
      <table className="w-full min-w-[700px] text-sm" role="table">
        <thead>
          <tr className="border-b border-slate-700/50">
            <th className="text-left py-2 px-3 text-xs font-semibold uppercase tracking-wider text-slate-500">#</th>
            <th className="text-left py-2 px-3 text-xs font-semibold uppercase tracking-wider text-slate-500">Entry</th>
            <th className="text-left py-2 px-3 text-xs font-semibold uppercase tracking-wider text-slate-500">Exit</th>
            <th className="text-right py-2 px-3 text-xs font-semibold uppercase tracking-wider text-slate-500">Entry $</th>
            <th className="text-right py-2 px-3 text-xs font-semibold uppercase tracking-wider text-slate-500">Exit $</th>
            <th className="text-right py-2 px-3 text-xs font-semibold uppercase tracking-wider text-slate-500">PnL</th>
            <th className="text-right py-2 px-3 text-xs font-semibold uppercase tracking-wider text-slate-500">PnL %</th>
            <th className="text-center py-2 px-3 text-xs font-semibold uppercase tracking-wider text-slate-500">Side</th>
            {trades.some(t => t.regime) && (
              <th className="text-center py-2 px-3 text-xs font-semibold uppercase tracking-wider text-slate-500">Regime</th>
            )}
          </tr>
        </thead>
        <tbody>
          {trades.map((trade, idx) => {
            const isWin = trade.pnl >= 0;
            return (
              <tr
                key={idx}
                className="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors"
              >
                <td className="py-2 px-3 text-slate-500 font-mono text-xs">{idx + 1}</td>
                <td className="py-2 px-3 text-slate-300 font-mono text-xs whitespace-nowrap">
                  {formatTime(trade.entry_time)}
                </td>
                <td className="py-2 px-3 text-slate-300 font-mono text-xs whitespace-nowrap">
                  {formatTime(trade.exit_time)}
                </td>
                <td className="py-2 px-3 text-right text-slate-300 font-mono">
                  {fmtPrice(trade.entry_price)}
                </td>
                <td className="py-2 px-3 text-right text-slate-300 font-mono">
                  {fmtPrice(trade.exit_price)}
                </td>
                <td className={`py-2 px-3 text-right font-mono font-semibold ${isWin ? "text-emerald-400" : "text-red-400"}`}>
                  {isWin ? "+" : ""}{trade.pnl.toFixed(2)}
                </td>
                <td className={`py-2 px-3 text-right font-mono text-xs ${isWin ? "text-emerald-400" : "text-red-400"}`}>
                  {isWin ? "+" : ""}{trade.pnl_pct.toFixed(2)}%
                </td>
                <td className="py-2 px-3 text-center">
                  <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold ${
                    trade.position === "LONG"
                      ? "bg-emerald-500/20 text-emerald-300"
                      : "bg-red-500/20 text-red-300"
                  }`}>
                    {trade.position}
                  </span>
                </td>
                {trades.some(t => t.regime) && (
                  <td className="py-2 px-3 text-center">
                    <span className="inline-block px-2 py-0.5 rounded bg-slate-700/50 text-xs text-slate-400">
                      {trade.regime || "—"}
                    </span>
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

function formatTime(ts: string): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString("en-GB", {
      month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return ts.slice(0, 16);
  }
}

function fmtPrice(p: number): string {
  if (p >= 1000) return p.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return p.toFixed(4);
}
