import React, { useState } from "react";

interface ActionEngineCardProps {
  consensusScore?: number;
  action: "BUY" | "SELL" | "HOLD";
  confidence: number;
  onExecute?: (action: string, size: number) => void;
  position?: {
    side: string;
    quantity: number;
    entry_price: number;
    pnl: number;
  } | null;
}

export const ActionEngineCard: React.FC<ActionEngineCardProps> = ({
  consensusScore,
  action,
  confidence,
  onExecute,
  position,
}) => {
  const [size, setSize] = useState(0.001);
  const canExecute = action !== "HOLD" && consensusScore !== undefined;

  const actionStyles: Record<string, string> = {
    BUY: "bg-emerald-600 hover:bg-emerald-500",
    SELL: "bg-red-600 hover:bg-red-500",
    HOLD: "bg-slate-700 cursor-not-allowed",
  };

  const badgeStyles: Record<string, string> = {
    BUY: "text-emerald-300 bg-emerald-500/20 border-emerald-500/30",
    SELL: "text-red-300 bg-red-500/20 border-red-500/30",
    HOLD: "text-slate-400 bg-slate-500/20 border-slate-500/30",
  };

  return (
    <div className="rounded-xl border border-slate-700/50 bg-slate-900/80 p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
          Action Engine
        </h3>
        <span
          className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${badgeStyles[action] || badgeStyles.HOLD}`}
        >
          {action}
        </span>
      </div>

      {/* Signal Info */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="text-center p-2 rounded-lg bg-slate-800/60">
          <div className="text-lg font-bold font-mono text-slate-200">
            {consensusScore?.toFixed(3) ?? "—"}
          </div>
          <div className="text-xs text-slate-500 mt-0.5">Consensus</div>
        </div>
        <div className="text-center p-2 rounded-lg bg-slate-800/60">
          <div className="text-lg font-bold font-mono text-slate-200">
            {(confidence * 100).toFixed(0)}%
          </div>
          <div className="text-xs text-slate-500 mt-0.5">Confidence</div>
        </div>
      </div>

      {/* Position Display */}
      {position && (
        <div className="mb-4 p-3 rounded-lg bg-slate-800/60 border border-slate-700/30">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
            Active Position
          </div>
          <div className="grid grid-cols-3 gap-2 text-xs">
            <div>
              <span className="text-slate-500">Side</span>
              <div
                className={`font-mono font-semibold ${position.side === "BUY" ? "text-emerald-400" : "text-red-400"}`}
              >
                {position.side}
              </div>
            </div>
            <div>
              <span className="text-slate-500">Entry</span>
              <div className="font-mono text-slate-300">
                ${position.entry_price?.toLocaleString()}
              </div>
            </div>
            <div>
              <span className="text-slate-500">PnL</span>
              <div
                className={`font-mono font-semibold ${position.pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}
              >
                ${position.pnl?.toFixed(2)}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Execute Controls */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <label className="text-xs text-slate-500">Size (BTC):</label>
          <input
            type="number"
            step="0.001"
            min="0.001"
            value={size}
            onChange={(e) => setSize(parseFloat(e.target.value) || 0.001)}
            className="w-24 px-2 py-1.5 rounded-lg border border-slate-600 bg-slate-800 text-white text-xs font-mono focus:ring-2 focus:ring-blue-500 outline-none"
            disabled={!canExecute}
          />
        </div>
        <button
          onClick={() => canExecute && onExecute?.(action, size)}
          disabled={!canExecute}
          className={`w-full py-2.5 rounded-lg text-sm font-semibold transition-all duration-200 ${actionStyles[action] || actionStyles.HOLD} ${!canExecute ? "opacity-50" : ""}`}
        >
          {action === "HOLD"
            ? "No Signal — Hold"
            : `${action} ${size} BTC`}
        </button>
        <div className="text-xs text-slate-600 text-center">
          {position ? "Position active" : "Paper Trading mode"}
        </div>
      </div>
    </div>
  );
};
