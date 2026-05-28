import React, { useState } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8502";

interface MacroSliders {
  dxy: number;
  vix: number;
  us10y: number;
  m2sl: number;
  xau: number;
}

interface SimResult {
  regime_probability_distribution: Record<string, number>;
  liquidity_composite: { liquidity_composite_score: number; interpretation: string };
  volatility_composite: { volatility_composite: number; regime_signal: string };
}

const SLIDERS: { key: keyof MacroSliders; label: string; min: number; max: number; step: number }[] = [
  { key: "dxy", label: "DXY", min: 90, max: 115, step: 0.5 },
  { key: "vix", label: "VIX", min: 10, max: 40, step: 0.5 },
  { key: "us10y", label: "US10Y %", min: 2, max: 6, step: 0.05 },
  { key: "m2sl", label: "M2SL (T)", min: 15, max: 30, step: 0.5 },
  { key: "xau", label: "XAU ($)", min: 3000, max: 6000, step: 50 },
];

export const ScenarioSimulator: React.FC = () => {
  const [macro, setMacro] = useState<MacroSliders>({ dxy: 98, vix: 19, us10y: 4.25, m2sl: 22, xau: 4800 });
  const [result, setResult] = useState<SimResult | null>(null);
  const [loading, setLoading] = useState(false);

  const run = async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE}/api/simulator`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(macro),
      });
      setResult(await r.json());
    } catch (e) {
      console.error("[ScenarioSimulator] error:", e);
    }
    setLoading(false);
  };

  const dominantRegime = result
    ? Object.entries(result.regime_probability_distribution).sort(([, a], [, b]) => b - a)[0]
    : null;

  return (
    <div className="rounded-xl border border-slate-700/50 bg-slate-900/80 p-5">
      <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500 mb-3">
        🔮 Scenario Simulator (What-If)
      </h3>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-4">
        {SLIDERS.map((s) => (
          <div key={s.key} className="flex flex-col">
            <label className="text-xs text-slate-400 mb-1">
              {s.label}: <span className="text-white font-mono">{macro[s.key]}</span>
            </label>
            <input
              type="range"
              min={s.min}
              max={s.max}
              step={s.step}
              value={macro[s.key]}
              onChange={(e) => setMacro((p) => ({ ...p, [s.key]: +e.target.value }))}
              className="w-full accent-blue-500"
            />
          </div>
        ))}
      </div>
      <button
        onClick={run}
        disabled={loading}
        className="w-full py-2 rounded-lg font-semibold text-sm transition-all bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:text-slate-500"
      >
        {loading ? "Hesaplanıyor..." : "▶ Run Simulation"}
      </button>
      {result && dominantRegime && (
        <div className="mt-3 grid grid-cols-3 gap-3 text-xs">
          <div className="bg-slate-800/60 rounded-lg p-2 text-center">
            <div className="text-slate-500 mb-1">Dominant Regime</div>
            <div className="text-white font-semibold capitalize">{dominantRegime[0]}</div>
            <div className="text-blue-400 font-mono">{(dominantRegime[1] * 100).toFixed(0)}%</div>
          </div>
          <div className="bg-slate-800/60 rounded-lg p-2 text-center">
            <div className="text-slate-500 mb-1">Liquidity</div>
            <div className="text-white font-mono">{result.liquidity_composite.liquidity_composite_score}/100</div>
            <div className="text-slate-400">{result.liquidity_composite.interpretation}</div>
          </div>
          <div className="bg-slate-800/60 rounded-lg p-2 text-center">
            <div className="text-slate-500 mb-1">Volatility</div>
            <div className="text-white font-mono">{result.volatility_composite.volatility_composite}/100</div>
            <div className="text-slate-400">{result.volatility_composite.regime_signal}</div>
          </div>
        </div>
      )}
    </div>
  );
};
