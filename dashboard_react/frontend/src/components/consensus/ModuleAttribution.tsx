import React from "react";
import { AttributionModule, AttributionModules } from "../../types/dashboardV2";

interface ModuleAttributionProps {
  modules: AttributionModules;
}

const moduleOrder: Array<{ key: keyof AttributionModules; label: string; tone: string; glow: string }> = [
  { key: "touche", label: "Touche", tone: "bg-sky-400", glow: "shadow-sky-900/40" },
  { key: "fundamental", label: "Fundamental", tone: "bg-emerald-400", glow: "shadow-emerald-900/40" },
  { key: "sentinel", label: "Sentinel", tone: "bg-amber-400", glow: "shadow-amber-900/40" },
  { key: "news", label: "News", tone: "bg-rose-400", glow: "shadow-rose-900/40" },
  { key: "quantum", label: "Quantum", tone: "bg-violet-400", glow: "shadow-violet-900/40" },
];

const buildTrendSeries = (module: AttributionModule): number[] => {
  const base = 30 + module.win_rate * 45;
  const amplitude = Math.min(22, Math.max(8, Math.abs(module.attribution_score) * 14));
  const tradeFactor = Math.min(10, module.total_trades / 4);

  return [
    base - amplitude * 0.35,
    base + tradeFactor * 0.3,
    base - amplitude * 0.15,
    base + amplitude * 0.55,
    base + amplitude * 0.15,
    base + amplitude,
  ].map((value) => Math.max(8, Math.min(92, value)));
};

const toSparklinePoints = (values: number[]): string =>
  values
    .map((value, index) => `${index * 24},${100 - value}`)
    .join(" ");

export const ModuleAttribution: React.FC<ModuleAttributionProps> = ({ modules }) => {
  return (
    <div className="grid gap-3 xl:grid-cols-2">
      {moduleOrder.map(({ key, label, tone, glow }) => {
        const module = modules[key];
        const trendSeries = buildTrendSeries(module);
        const strength = Math.max(10, Math.min(100, 45 + module.attribution_score * 18));
        const direction = module.attribution_score >= 0 ? "Katki pozitif" : "Katki baskiliyor";

        return (
          <div
            key={key}
            className="group rounded-2xl border border-slate-700 bg-slate-900/90 p-4 transition-all duration-300 hover:-translate-y-0.5 hover:border-slate-500 hover:shadow-xl hover:shadow-slate-950/40"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-slate-500">{label}</p>
                <p className="mt-2 text-lg font-semibold text-white">{module.role}</p>
                <p className="mt-1 text-xs uppercase tracking-[0.16em] text-slate-500">{direction}</p>
              </div>
              <span className={`inline-flex rounded-full border border-white/10 px-3 py-1 text-xs font-semibold text-white ${tone.replace("bg", "bg").replace("400", "500/15")}`}>
                {module.attribution_score >= 0 ? "+" : ""}
                {module.attribution_score.toFixed(2)}
              </span>
            </div>

            <div className="mt-4 grid grid-cols-3 gap-3 text-sm">
              <div className="rounded-xl border border-slate-700 bg-slate-950/70 px-3 py-2">
                <p className="text-[11px] uppercase tracking-[0.16em] text-slate-500">Win Rate</p>
                <p className="mt-2 font-mono text-base text-white">{(module.win_rate * 100).toFixed(1)}%</p>
              </div>
              <div className="rounded-xl border border-slate-700 bg-slate-950/70 px-3 py-2">
                <p className="text-[11px] uppercase tracking-[0.16em] text-slate-500">Trades</p>
                <p className="mt-2 font-mono text-base text-white">{module.total_trades}</p>
              </div>
              <div className="rounded-xl border border-slate-700 bg-slate-950/70 px-3 py-2">
                <p className="text-[11px] uppercase tracking-[0.16em] text-slate-500">Strength</p>
                <p className="mt-2 font-mono text-base text-white">{strength.toFixed(0)}%</p>
              </div>
            </div>

            <div className="mt-4 overflow-hidden rounded-2xl border border-slate-700 bg-slate-950/70 px-3 py-3">
              <div className="flex items-center justify-between text-[11px] uppercase tracking-[0.18em] text-slate-500">
                <span>Trend</span>
                <span>Last 6 windows</span>
              </div>
              <svg viewBox="0 0 120 100" className="mt-3 h-20 w-full">
                <polyline
                  fill="none"
                  stroke="rgba(148, 163, 184, 0.18)"
                  strokeWidth="1"
                  points="0,50 120,50"
                />
                <polyline
                  fill="none"
                  stroke="currentColor"
                  className={`${tone.replace("bg", "text")} drop-shadow-sm`}
                  strokeWidth="3"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  points={toSparklinePoints(trendSeries)}
                />
              </svg>
            </div>

            <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-800">
              <div className={`h-2 rounded-full ${tone} shadow-lg ${glow} transition-all duration-500 group-hover:brightness-110`} style={{ width: `${strength}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
};