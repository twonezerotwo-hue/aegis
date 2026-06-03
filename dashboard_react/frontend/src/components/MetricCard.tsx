/**
 * MetricCard — V2 yeniden yazımı.
 * Slate-950 dark theme, Tailwind only, V1 legacy CSS sınıfı yok.
 */

import React from "react";
import type { Metric } from "../types";
import { DataStatusBadge } from "./ui/DataStatusBadge";

interface MetricCardProps {
  metric: Metric;
}

// ── Modül renk ve kimlik ──────────────────────────────────────────────────────
const MODULE_CFG: Record<string, { bar: string; ring: string; tfTag?: boolean }> = {
  "Touche EQS":        { bar: "bg-violet-400",  ring: "ring-violet-500/20" },
  "Fundamental Score": { bar: "bg-sky-400",     ring: "ring-sky-500/20",   tfTag: true },
  "Quantum Score":     { bar: "bg-emerald-400", ring: "ring-emerald-500/20",tfTag: true },
  "Sentinel Score":    { bar: "bg-rose-400",    ring: "ring-rose-500/20",  tfTag: true },
  "News Sentiment":    { bar: "bg-amber-400",   ring: "ring-amber-500/20", tfTag: true },
};

const getCfg = (name: string) =>
  Object.entries(MODULE_CFG).find(([k]) => name.includes(k.split(" ")[0]))?.[1]
  ?? { bar: "bg-slate-400", ring: "" };

// ── Skor rengi ────────────────────────────────────────────────────────────────
const scoreColor = (score: number) =>
  score > 0.65 ? "text-emerald-400"
  : score < 0.35 ? "text-rose-400"
  : "text-amber-400";

const scoreTrend = (score: number) =>
  score > 0.65 ? "↑" : score < 0.35 ? "↓" : "→";

// ── Sağlık durumu ─────────────────────────────────────────────────────────────
const healthLabel: Record<string, { label: string; cls: string }> = {
  healthy: { label: "Sağlıklı",  cls: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30" },
  warning: { label: "Uyarı",     cls: "text-amber-400   bg-amber-500/10   border-amber-500/30"   },
  down:    { label: "Kapalı",    cls: "text-rose-400    bg-rose-500/10    border-rose-500/30"     },
};

export const MetricCard: React.FC<MetricCardProps> = ({ metric }) => {
  const pct = (metric.score * 100).toFixed(1);
  const cfg = getCfg(metric.name);
  const hl  = healthLabel[metric.health] ?? healthLabel.warning;
  const sc  = scoreColor(metric.score);

  return (
    <div className={`rounded-2xl border border-slate-700/60 bg-slate-900 p-4 shadow-md ring-1 ${cfg.ring} transition-all duration-300 hover:border-slate-600`}>

      {/* Header */}
      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
            {metric.name}
          </p>
          {cfg.tfTag && (
            <span className="mt-0.5 inline-block text-[8px] text-slate-700 font-mono">
              TF BAĞIMSIZ
            </span>
          )}
        </div>
        <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[9px] font-semibold ${hl.cls}`}>
          {hl.label}
        </span>
      </div>

      {/* Skor + trend */}
      <div className="mb-3 flex items-end gap-2">
        <p className={`font-mono text-3xl font-extrabold leading-none ${sc}`}>
          {pct}<span className="text-sm text-slate-600">%</span>
        </p>
        <span className={`mb-0.5 text-lg font-bold ${sc}`}>{scoreTrend(metric.score)}</span>
        <div className="ml-auto">
          <DataStatusBadge data={metric} compact />
        </div>
      </div>

      {/* Skor bar */}
      <div className="mb-3 h-1.5 rounded-full bg-slate-700/60">
        <div
          className={`h-1.5 rounded-full ${cfg.bar} transition-all duration-500`}
          style={{ width: `${Math.min(100, metric.score * 100)}%` }}
        />
      </div>

      {/* Summary */}
      {metric.summary ? (
        <p className="text-[10px] leading-4 text-slate-500">{metric.summary}</p>
      ) : (
        <p className="text-[10px] italic text-slate-700">Özet bekleniyor…</p>
      )}

      {/* Zaman */}
      {metric.last_updated && (
        <p className="mt-2 text-right font-mono text-[9px] text-slate-700">
          {new Date(metric.last_updated).toLocaleTimeString("tr-TR")}
        </p>
      )}
    </div>
  );
};
