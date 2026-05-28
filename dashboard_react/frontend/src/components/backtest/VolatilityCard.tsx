import React from "react";

interface VolatilityCardProps {
  volatility: {
    volatility_composite: number;
    regime_signal: string;
    components?: {
      vix?: number;
      move?: number;
      cvix?: number;
    };
  };
}

export const VolatilityCard: React.FC<VolatilityCardProps> = ({
  volatility,
}) => {
  const composite = volatility?.volatility_composite ?? 0;
  const signal = volatility?.regime_signal || "N/A";
  const vix = volatility?.components?.vix;
  const move = volatility?.components?.move;
  const cvix = volatility?.components?.cvix;

  const signalColor: Record<string, string> = {
    low_vol: "text-emerald-300 bg-emerald-500/20 border-emerald-500/30",
    moderate_vol: "text-amber-300 bg-amber-500/20 border-amber-500/30",
    high_vol: "text-red-300 bg-red-500/20 border-red-500/30",
    extreme_vol: "text-fuchsia-300 bg-fuchsia-500/20 border-fuchsia-500/30",
  };

  const barColor =
    composite > 70
      ? "bg-red-500"
      : composite > 40
        ? "bg-amber-500"
        : "bg-emerald-500";

  return (
    <div className="rounded-xl border border-slate-700/50 bg-slate-900/80 p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
          Volatility Composite
        </h3>
        <span
          className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${signalColor[signal] || signalColor.moderate_vol}`}
        >
          {signal.replace(/_/g, " ")}
        </span>
      </div>

      {/* Composite gauge */}
      <div className="mb-4">
        <div className="flex justify-between text-xs mb-1.5">
          <span className="text-slate-500">Composite</span>
          <span
            className={`font-mono font-semibold ${composite > 70 ? "text-red-400" : composite > 40 ? "text-amber-400" : "text-emerald-400"}`}
          >
            {composite.toFixed(1)}
          </span>
        </div>
        <div className="h-2.5 bg-slate-700/60 rounded-full overflow-hidden">
          <div
            className={`h-full ${barColor} rounded-full transition-all duration-700`}
            style={{ width: `${Math.min(composite, 100)}%` }}
          />
        </div>
      </div>

      {/* Source gauges */}
      <div className="space-y-2">
        {[
          { label: "VIX (Equity)", value: vix, max: 80 },
          { label: "MOVE (Bond)", value: move, max: 200 },
          { label: "CVIX (Crypto)", value: cvix, max: 120 },
        ].map((item) => (
          <div key={item.label}>
            <div className="flex justify-between text-xs mb-1">
              <span className="text-slate-500">{item.label}</span>
              <span className="font-mono text-slate-300">
                {item.value?.toFixed(1) ?? "—"}
              </span>
            </div>
            <div className="h-1.5 bg-slate-700/40 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-500/60 rounded-full transition-all duration-500"
                style={{
                  width: `${item.value != null ? Math.min((item.value / item.max) * 100, 100) : 0}%`,
                }}
              />
            </div>
          </div>
        ))}
      </div>

      <div className="mt-3 text-xs text-slate-600">
        Sources: CBOE VIX + ICE MOVE + Deribit DVOL
      </div>
    </div>
  );
};
