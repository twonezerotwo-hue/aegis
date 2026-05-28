import React from "react";

interface AttributionEntry {
  feature: string;
  value: string | number;
  impact: number;
}

interface ExplainabilityPanelProps {
  attribution: Record<string, AttributionEntry[]>;
}

export const ExplainabilityPanel: React.FC<ExplainabilityPanelProps> = ({ attribution }) => {
  if (!attribution || Object.keys(attribution).length === 0) return null;
  return (
    <div className="rounded-xl border border-slate-700/50 bg-slate-900/80 p-5">
      <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500 mb-3">
        🔍 Score Explainability (Top 3 Drivers)
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {Object.entries(attribution).map(([mod, drivers]) => (
          <div key={mod} className="bg-slate-800/60 rounded-lg p-3">
            <div className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
              {mod} Module
            </div>
            {drivers.map((d, i) => (
              <div
                key={i}
                className="flex justify-between text-xs py-1 border-b border-slate-700/40 last:border-0"
              >
                <span className="text-slate-400">
                  {d.feature}:{" "}
                  <span className="text-white font-mono">
                    {typeof d.value === "number" ? d.value.toFixed(2) : d.value}
                  </span>
                </span>
                <span
                  className={`font-mono font-semibold ${
                    d.impact >= 0 ? "text-emerald-400" : "text-red-400"
                  }`}
                >
                  {d.impact > 0 ? "+" : ""}
                  {d.impact.toFixed(3)}
                </span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
};
