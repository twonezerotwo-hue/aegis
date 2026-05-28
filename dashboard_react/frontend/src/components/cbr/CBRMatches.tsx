import React from "react";
import { CBRMatch } from "../../types/dashboardV2";

interface CBRMatchesProps {
  matches: CBRMatch[];
  sampleCount: number;
  winRatePct: number;
  similarityScore: number;
  reason: string;
}

const outcomeClasses: Record<CBRMatch["outcome"], string> = {
  WIN: "border-emerald-500/20 bg-emerald-500/10 text-emerald-300",
  LOSS: "border-rose-500/20 bg-rose-500/10 text-rose-300",
  NEUTRAL: "border-slate-600 bg-slate-700/60 text-slate-300",
};

const outcomeGlyph: Record<CBRMatch["outcome"], string> = {
  WIN: "✓",
  LOSS: "✕",
  NEUTRAL: "•",
};

export const CBRMatches: React.FC<CBRMatchesProps> = ({
  matches,
  sampleCount,
  winRatePct,
  similarityScore,
  reason,
}) => {
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-2xl border border-slate-700 bg-slate-900/90 px-4 py-3">
          <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Sample Count</p>
          <p className="mt-2 font-mono text-xl text-white">{sampleCount}</p>
        </div>
        <div className="rounded-2xl border border-slate-700 bg-slate-900/90 px-4 py-3">
          <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Win Rate</p>
          <p className="mt-2 font-mono text-xl text-white">{winRatePct.toFixed(1)}%</p>
        </div>
        <div className="rounded-2xl border border-slate-700 bg-slate-900/90 px-4 py-3">
          <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Edge Similarity</p>
          <p className="mt-2 font-mono text-xl text-white">{(similarityScore * 100).toFixed(1)}%</p>
        </div>
      </div>

      {matches.length === 0 ? (
        <div className="rounded-2xl border border-slate-700 bg-slate-900/90 p-4 text-sm leading-6 text-slate-300">
          Endpoint benzer vaka listesi donmedi. Historical edge ozeti gosteriliyor: <span className="text-slate-100">{reason}</span>
        </div>
      ) : (
        <div className="space-y-3">
          {matches.map((match) => {
            const similarityPct = Math.max(6, Math.min(100, match.similarity * 100));

            return (
              <div
                key={match.id}
                className="group rounded-2xl border border-slate-700 bg-slate-900/90 p-4 transition-all duration-300 hover:-translate-y-0.5 hover:border-slate-500 hover:shadow-xl hover:shadow-slate-950/40"
              >
                <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-semibold text-white">{match.label}</p>
                      <span className={`inline-flex items-center gap-2 rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] ${outcomeClasses[match.outcome]}`}>
                        <span>{outcomeGlyph[match.outcome]}</span>
                        <span>{match.outcome}</span>
                      </span>
                    </div>
                    <p className="mt-2 text-xs uppercase tracking-[0.18em] text-slate-500">{match.regime}</p>
                    <p className="mt-2 text-sm leading-6 text-slate-300">{match.note}</p>
                  </div>

                  <div className="w-full max-w-sm">
                    <div className="flex items-center justify-between text-[11px] uppercase tracking-[0.18em] text-slate-500">
                      <span>Similarity</span>
                      <span className="font-mono text-slate-200">{similarityPct.toFixed(1)}%</span>
                    </div>
                    <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-800">
                      <div className="h-2 rounded-full bg-cyan-400 shadow-lg shadow-cyan-950/40 transition-all duration-500 group-hover:brightness-110" style={{ width: `${similarityPct}%` }} />
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};