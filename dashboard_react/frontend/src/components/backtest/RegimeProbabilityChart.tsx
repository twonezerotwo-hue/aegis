import React from "react";

interface RegimeProbabilityChartProps {
  distribution: Record<string, number>;
}

const COLORS: Record<string, string> = {
  risk_on: "#10b981",
  normalization: "#3b82f6",
  risk_off: "#ef4444",
  accumulation: "#f59e0b",
};

const LABELS: Record<string, string> = {
  risk_on: "Risk-On",
  normalization: "Normalization",
  risk_off: "Risk-Off",
  accumulation: "Accumulation",
};

export const RegimeProbabilityChart: React.FC<RegimeProbabilityChartProps> = ({
  distribution,
}) => {
  const sorted = Object.entries(distribution).sort((a, b) => b[1] - a[1]);
  const dominant = sorted[0];

  return (
    <div className="rounded-xl border border-slate-700/50 bg-slate-900/80 p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
          Regime Probability
        </h3>
        {dominant && (
          <span
            className="px-2 py-0.5 rounded-full text-xs font-semibold border"
            style={{
              color: COLORS[dominant[0]] || "#6b7280",
              borderColor: COLORS[dominant[0]] || "#6b7280",
              backgroundColor: `${COLORS[dominant[0]] || "#6b7280"}20`,
            }}
          >
            {LABELS[dominant[0]] || dominant[0]} {(dominant[1] * 100).toFixed(0)}%
          </span>
        )}
      </div>

      <div className="space-y-2.5">
        {sorted.map(([regime, prob]) => (
          <div key={regime} className="flex items-center gap-3">
            <span
              className="w-2.5 h-2.5 rounded-full flex-shrink-0"
              style={{ backgroundColor: COLORS[regime] || "#6b7280" }}
            />
            <span className="text-xs w-28 text-slate-400">
              {LABELS[regime] || regime}
            </span>
            <div className="flex-1 h-2 bg-slate-700/60 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${prob * 100}%`,
                  backgroundColor: COLORS[regime] || "#6b7280",
                }}
              />
            </div>
            <span className="w-12 text-right text-xs font-mono text-slate-300">
              {(prob * 100).toFixed(1)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};
