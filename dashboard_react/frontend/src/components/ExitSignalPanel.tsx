/**
 * ExitSignalPanel — Displays Touche AI exit signal with:
 *  - FULL_CLOSE / PARTIAL_CLOSE / HOLD recommendation
 *  - Structure break reason
 *  - Trailing stop level indicator
 *
 * Data: SSE /api/live-feed → exit_signal field.
 */
import React from "react";

export interface ExitSignalData {
  exit: boolean;
  reason: string;
  partial_close?: boolean;
  close_pct?: number;
  trailing_stop?: number;
  structure_level?: number;
}

interface ExitSignalPanelProps {
  data: ExitSignalData;
  entryPrice?: number;
  currentPrice?: number;
  positionSide?: "LONG" | "SHORT";
}

export const ExitSignalPanel: React.FC<ExitSignalPanelProps> = ({
  data,
  entryPrice = 0,
  currentPrice = 0,
  positionSide = "LONG",
}) => {
  const unrealizedPnlPct =
    entryPrice > 0
      ? positionSide === "LONG"
        ? ((currentPrice - entryPrice) / entryPrice) * 100
        : ((entryPrice - currentPrice) / entryPrice) * 100
      : null;

  const recommendation = data.exit
    ? data.partial_close
      ? "PARTIAL_CLOSE"
      : "FULL_CLOSE"
    : "HOLD";

  const recColor = {
    FULL_CLOSE: "text-red-400",
    PARTIAL_CLOSE: "text-yellow-400",
    HOLD: "text-green-400",
  }[recommendation];

  const recBg = {
    FULL_CLOSE: "bg-red-900/40 border-red-700",
    PARTIAL_CLOSE: "bg-yellow-900/40 border-yellow-700",
    HOLD: "bg-green-900/40 border-green-700",
  }[recommendation];

  const recIcon = {
    FULL_CLOSE: "🔴",
    PARTIAL_CLOSE: "🟡",
    HOLD: "🟢",
  }[recommendation];

  const humanReason: Record<string, string> = {
    higher_high_structure_intact: "Higher-high structure intact — trend healthy",
    lower_low_structure_intact: "Lower-low structure intact — downtrend healthy",
    higher_low_broken: "Higher-low broken → structure breach (LONG exit)",
    lower_high_broken: "Lower-high broken → structure breach (SHORT exit)",
    rsi_overbought_volume_declining: "RSI overbought + volume declining (partial)",
    rsi_oversold_volume_declining: "RSI oversold + volume declining (partial)",
    service_unreachable: "Touche AI service unreachable — using safe default",
  };

  return (
    <div
      className={`rounded-xl border ${recBg} p-4 flex flex-col gap-3`}
    >
      <div className="flex items-center justify-between">
        <p className="text-xs uppercase tracking-widest text-gray-400">
          Touche Exit Signal
        </p>
        <span className="text-xs text-gray-500">{positionSide} position</span>
      </div>

      {/* Main recommendation */}
      <div className="flex items-center gap-3">
        <span className="text-3xl">{recIcon}</span>
        <div>
          <p className={`text-xl font-extrabold ${recColor}`}>
            {recommendation.replace("_", " ")}
          </p>
          {recommendation === "PARTIAL_CLOSE" && (
            <p className="text-xs text-yellow-300">
              Close {data.close_pct ?? 50}% of position
            </p>
          )}
        </div>
      </div>

      {/* Reason */}
      <p className="text-sm text-gray-300">
        {humanReason[data.reason] ?? data.reason}
      </p>

      {/* Price context */}
      <div className="grid grid-cols-2 gap-2 text-xs">
        {entryPrice > 0 && (
          <div className="rounded bg-gray-800/60 px-2 py-1">
            <p className="text-gray-500">Entry</p>
            <p className="text-white font-mono">${entryPrice.toLocaleString()}</p>
          </div>
        )}
        {currentPrice > 0 && (
          <div className="rounded bg-gray-800/60 px-2 py-1">
            <p className="text-gray-500">Current</p>
            <p className="text-white font-mono">${currentPrice.toLocaleString()}</p>
          </div>
        )}
        {unrealizedPnlPct !== null && (
          <div className="rounded bg-gray-800/60 px-2 py-1">
            <p className="text-gray-500">Unrealized PnL</p>
            <p
              className={`font-semibold ${
                unrealizedPnlPct >= 0 ? "text-green-400" : "text-red-400"
              }`}
            >
              {unrealizedPnlPct >= 0 ? "+" : ""}
              {unrealizedPnlPct.toFixed(2)}%
            </p>
          </div>
        )}
        {data.trailing_stop && data.trailing_stop > 0 && (
          <div className="rounded bg-gray-800/60 px-2 py-1">
            <p className="text-gray-500">Trailing Stop</p>
            <p className="text-orange-400 font-mono">
              ${data.trailing_stop.toLocaleString()}
            </p>
          </div>
        )}
      </div>
    </div>
  );
};
