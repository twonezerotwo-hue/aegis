/**
 * CBRMatches — Displays the 5 most similar historical cases from CBR engine.
 *
 * Shows: similarity %, outcome (WIN/LOSS), PnL %, days ago, regime context.
 * Data fed from SSE /api/live-feed → cbr_matches field.
 */
import React from "react";

export interface CBRMatch {
  case_id: string;
  similarity: number;
  outcome: "WIN" | "LOSS";
  regime: string;
  pnl_pct: number;
  days_ago: number;
  signal: "BUY" | "SELL";
}

interface CBRMatchesProps {
  matches: CBRMatch[];
}

const REGIME_COLORS: Record<string, string> = {
  LIQUIDITY_EXPANSION: "text-green-400",
  NORMALIZATION: "text-blue-400",
  STAGFLATION: "text-yellow-400",
  RISK_OFF: "text-red-400",
};

export const CBRMatches: React.FC<CBRMatchesProps> = ({ matches }) => {
  const totalWins = matches.filter((m) => m.outcome === "WIN").length;
  const avgSim =
    matches.length > 0
      ? Math.round(
          (matches.reduce((s, m) => s + m.similarity, 0) / matches.length) *
            100
        )
      : 0;

  return (
    <div className="rounded-xl border border-gray-700 bg-gray-900/60 p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <p className="text-xs uppercase tracking-widest text-gray-400">
          CBR — Similar Cases
        </p>
        <div className="flex gap-3 text-xs">
          <span className="text-gray-400">
            Win Rate:{" "}
            <span className="text-white font-semibold">
              {totalWins}/{matches.length}
            </span>
          </span>
          <span className="text-gray-400">
            Avg Similarity:{" "}
            <span className="text-white font-semibold">{avgSim}%</span>
          </span>
        </div>
      </div>

      {matches.length === 0 ? (
        <p className="text-sm text-gray-500 italic">No similar cases found.</p>
      ) : (
        <div className="flex flex-col gap-2">
          {matches.map((m) => (
            <div
              key={m.case_id}
              className="flex items-center justify-between rounded-lg bg-gray-800/60 px-3 py-2"
            >
              {/* Left: case id + similarity bar */}
              <div className="flex flex-col gap-0.5 min-w-[110px]">
                <span className="text-xs text-gray-400 font-mono">
                  {m.case_id}
                </span>
                <div className="w-full bg-gray-700 rounded-full h-1.5 mt-0.5">
                  <div
                    className="h-1.5 rounded-full bg-cyan-500"
                    style={{ width: `${Math.round(m.similarity * 100)}%` }}
                  />
                </div>
                <span className="text-xs text-cyan-400">
                  {Math.round(m.similarity * 100)}% similar
                </span>
              </div>

              {/* Middle: outcome badge + signal */}
              <div className="flex flex-col items-center gap-1">
                <span
                  className={`text-xs font-bold px-2 py-0.5 rounded-full ${
                    m.outcome === "WIN"
                      ? "bg-green-900/60 text-green-300"
                      : "bg-red-900/60 text-red-300"
                  }`}
                >
                  {m.outcome}
                </span>
                <span
                  className={`text-xs font-mono ${
                    m.signal === "BUY" ? "text-green-400" : "text-red-400"
                  }`}
                >
                  {m.signal}
                </span>
              </div>

              {/* Right: PnL + regime + time */}
              <div className="text-right flex flex-col gap-0.5">
                <span
                  className={`text-sm font-bold ${
                    m.pnl_pct >= 0 ? "text-green-400" : "text-red-400"
                  }`}
                >
                  {m.pnl_pct >= 0 ? "+" : ""}
                  {m.pnl_pct.toFixed(2)}%
                </span>
                <span
                  className={`text-xs ${
                    REGIME_COLORS[m.regime] ?? "text-gray-400"
                  }`}
                >
                  {m.regime.replace("_", " ")}
                </span>
                <span className="text-xs text-gray-500">{m.days_ago}d ago</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
