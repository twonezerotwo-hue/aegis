/**
 * ConsensusCard — V2 yeniden yazımı.
 * Pie chart kaldırıldı (50/35/15 sabiti göstermek anlamsız).
 * BUY/SELL/HOLD büyük + güven + ağırlıklı skor + modül çubuklar.
 */

import React from "react";
import type { ConsensusData } from "../types";
import { DataStatusBadge } from "./ui/DataStatusBadge";

interface ConsensusCardProps {
  data: ConsensusData;
}

const ACTION_CFG = {
  BUY:  { label: "AL",  cls: "text-emerald-400 border-emerald-500/40 bg-emerald-500/10" },
  SELL: { label: "SAT", cls: "text-rose-400    border-rose-500/40    bg-rose-500/10"    },
  HOLD: { label: "TUT", cls: "text-amber-400   border-amber-500/40   bg-amber-500/10"   },
} as const;

const MOD_COLORS: Record<string, string> = {
  touche:      "bg-violet-400",
  fundamental: "bg-sky-400",
  news:        "bg-amber-400",
};
const MOD_TR: Record<string, string> = {
  touche: "Touche", fundamental: "Temel", news: "Haber",
};

export const ConsensusCard: React.FC<ConsensusCardProps> = ({ data }) => {
  const action = (data.action ?? "HOLD") as keyof typeof ACTION_CFG;
  const cfg    = ACTION_CFG[action] ?? ACTION_CFG.HOLD;
  const score  = data.weighted_score ?? 0;
  const confPct = ((data.confidence ?? 0) * 100).toFixed(1);

  return (
    <div className="rounded-2xl border border-slate-700/60 bg-slate-900 p-5 shadow-md transition-all duration-300 hover:border-slate-600">

      {/* Header */}
      <div className="mb-4 flex items-center justify-between gap-2">
        <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">
          Consensus Sinyali
        </p>
        <DataStatusBadge data={data} compact />
      </div>

      {/* Eylem + güven */}
      <div className="mb-5 flex items-center gap-4">
        <span className={`inline-flex rounded-2xl border px-5 py-2 text-2xl font-extrabold tracking-wide ${cfg.cls}`}>
          {cfg.label}
        </span>
        <div>
          <p className="text-[9px] uppercase tracking-wider text-slate-600">Ağırlıklı Skor</p>
          <p className="font-mono text-xl font-bold text-white">
            {(score * 100).toFixed(1)}<span className="text-sm text-slate-500">%</span>
          </p>
          <p className="text-[9px] text-slate-600">Güven: {confPct}%</p>
        </div>
      </div>

      {/* Modül çubukları */}
      <div className="space-y-2">
        {Object.entries(data.components ?? {}).map(([key, val]) => {
          const pct  = Math.round((val.score ?? 0) * 100);
          const wPct = Math.round((val.weight ?? 0) * 100);
          return (
            <div key={key} className="flex items-center gap-2">
              <span className="w-12 shrink-0 text-[9px] text-slate-500">{MOD_TR[key] ?? key}</span>
              <div className="h-1.5 flex-1 rounded-full bg-slate-700/60">
                <div
                  className={`h-1.5 rounded-full ${MOD_COLORS[key] ?? "bg-slate-400"} transition-all duration-500`}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="w-8 shrink-0 text-right font-mono text-[9px] text-slate-400">{pct}</span>
              <span className="w-10 shrink-0 text-right text-[8px] text-slate-700">%{wPct}w</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};
