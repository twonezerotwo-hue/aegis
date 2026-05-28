import React from "react";

interface ExpertControlsProps {
  weights: Record<string, number>;
  onChange: (w: Record<string, number>) => void;
}

const MODULE_ORDER = ["touche", "fundamental", "news", "sentinel", "quantum"];

export const ExpertControls: React.FC<ExpertControlsProps> = ({ weights, onChange }) => {
  const total = Object.values(weights).reduce((a, b) => a + b, 0);

  return (
    <div className="rounded-xl border border-purple-500/30 bg-slate-900/80 p-5">
      <div className="flex justify-between items-center mb-3">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-purple-400">
          🛠️ Expert Overrides
        </h3>
        <span
          className={`px-2 py-0.5 rounded-full text-xs font-mono ${
            Math.abs(total - 1) < 0.01
              ? "bg-emerald-500/20 text-emerald-300"
              : "bg-amber-500/20 text-amber-300"
          }`}
        >
          Σ {(total * 100).toFixed(0)}%
        </span>
      </div>
      <div className="grid grid-cols-5 gap-3">
        {MODULE_ORDER.map((k) => {
          const v = weights[k] ?? 0;
          return (
            <div key={k} className="text-center">
              <label className="text-xs text-slate-400 capitalize block mb-1">
                {k}: <span className="text-white font-mono">{(v * 100).toFixed(0)}%</span>
              </label>
              <input
                type="range"
                min={0}
                max={0.6}
                step={0.05}
                value={v}
                onChange={(e) => onChange({ ...weights, [k]: +e.target.value })}
                className="w-full accent-purple-500"
              />
            </div>
          );
        })}
      </div>
    </div>
  );
};
