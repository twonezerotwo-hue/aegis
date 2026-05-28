import React from "react";

interface LiquidityScoreCardProps {
  liquidity: {
    liquidity_composite_score: number;
    components: Record<string, number>;
    interpretation: string;
  };
}

const LABELS: Record<string, string> = {
  m2sl: "M2 Supply",
  rrp: "Reverse Repo",
  cb_balance_sheet: "CB Balance",
  funding_rate_impact: "Funding Rate",
};

export const LiquidityScoreCard: React.FC<LiquidityScoreCardProps> = ({
  liquidity,
}) => {
  const score = liquidity?.liquidity_composite_score ?? 50;
  const color =
    score > 70
      ? "text-emerald-400"
      : score > 40
        ? "text-amber-400"
        : "text-red-400";
  const barColor =
    score > 70 ? "bg-emerald-500" : score > 40 ? "bg-amber-500" : "bg-red-500";
  const badgeColor =
    score > 70
      ? "text-emerald-300 bg-emerald-500/20 border-emerald-500/30"
      : score > 40
        ? "text-amber-300 bg-amber-500/20 border-amber-500/30"
        : "text-red-300 bg-red-500/20 border-red-500/30";

  return (
    <div className="rounded-xl border border-slate-700/50 bg-slate-900/80 p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
          Liquidity Score
        </h3>
        <span
          className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${badgeColor}`}
        >
          {liquidity?.interpretation || "N/A"}
        </span>
      </div>

      {/* Composite Score Bar */}
      <div className="mb-4">
        <div className="flex justify-between text-xs mb-1.5">
          <span className="text-slate-500">Composite</span>
          <span className={`font-mono font-semibold ${color}`}>
            {score.toFixed(1)}/100
          </span>
        </div>
        <div className="h-2.5 bg-slate-700/60 rounded-full overflow-hidden">
          <div
            className={`h-full ${barColor} rounded-full transition-all duration-700`}
            style={{ width: `${score}%` }}
          />
        </div>
      </div>

      {/* Component breakdown */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-2">
        {Object.entries(liquidity?.components || {}).map(([key, val]) => (
          <div key={key} className="flex items-center justify-between text-xs">
            <span className="text-slate-500">{LABELS[key] || key}</span>
            <span
              className={`font-mono ${val > 70 ? "text-emerald-400" : val > 40 ? "text-amber-400" : "text-red-400"}`}
            >
              {val.toFixed(0)}
            </span>
          </div>
        ))}
      </div>

      <div className="mt-3 text-xs text-slate-600">
        High liquidity favors risk assets
      </div>
    </div>
  );
};
