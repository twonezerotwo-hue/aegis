/**
 * KontrolMerkezi — AEGIS ana kontrol paneli.
 * 3 zone: Karar | Performans | Risk
 * Tek bakışta: "Şu an ne durumdasın?"
 */

import React from "react";
import type { ConsensusResponse, MacroViewModel } from "../../types/dashboardV2";
import { DataStatusBadge } from "../ui/DataStatusBadge";
import { formatDataAge } from "../../utils/dataFreshness";

interface DailyPnL {
  date: string;
  realized_pnl: number;
  trade_count: number;
  kill_switch_threshold: number;
  kill_switch_active: boolean;
  message: string;
}

interface KontrolProps {
  macro: MacroViewModel | null;
  btcConsensus: ConsensusResponse | null;
  dailyPnl: DailyPnL | null;
  loading: boolean;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

const ACTION_CLS: Record<string, string> = {
  BUY:  "text-emerald-400 border-emerald-500/40 bg-emerald-500/10",
  HOLD: "text-amber-400  border-amber-500/40  bg-amber-500/10",
  SELL: "text-rose-400   border-rose-500/40   bg-rose-500/10",
};

const ACTION_TR: Record<string, string> = {
  BUY: "AL", HOLD: "TUT", SELL: "SAT",
};

const riskColor = (score: number) =>
  score < 0.35 ? "text-emerald-400"
  : score < 0.55 ? "text-amber-400"
  : "text-rose-400";

const riskLabel = (score: number) =>
  score < 0.35 ? "Düşük" : score < 0.55 ? "Orta" : "Yüksek";

const pnlColor = (v: number) => v >= 0 ? "text-emerald-400" : "text-rose-400";

const MODULE_COLORS: Record<string, string> = {
  touche: "bg-violet-400", fundamental: "bg-sky-400",
  news: "bg-amber-400", sentinel: "bg-rose-400", quantum: "bg-emerald-400",
};

// ── Zone 1: Karar Paneli ─────────────────────────────────────────────────────

const KararPaneli: React.FC<{ consensus: ConsensusResponse | null; loading: boolean }> = ({
  consensus, loading,
}) => {
  if (loading) return (
    <div className="animate-pulse space-y-3">
      <div className="h-16 rounded-xl bg-slate-700/50" />
      <div className="h-4 w-3/4 rounded bg-slate-700/50" />
      <div className="space-y-2">
        {[1,2,3,4,5].map(i => <div key={i} className="h-2 rounded-full bg-slate-700/40" />)}
      </div>
    </div>
  );

  if (!consensus) return (
    <div className="flex flex-col items-center justify-center py-6 text-slate-600">
      <p className="text-xs">BTC sinyali bekleniyor…</p>
    </div>
  );

  const action = consensus.action;
  const cls = ACTION_CLS[action] ?? ACTION_CLS.HOLD;
  const confidencePct = Math.round(consensus.confidence * 100);
  const fiveModScore = (consensus.five_module_score * 100).toFixed(1);
  const scores = consensus.module_scores;

  return (
    <div className="space-y-4">
      {/* Sinyal */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">BTC Sinyali</p>
          <p className={`mt-0.5 text-3xl font-extrabold leading-none ${cls.split(" ")[0]}`}>
            {ACTION_TR[action] ?? action}
          </p>
        </div>
        <div className="text-right">
          <p className="text-[9px] uppercase tracking-wider text-slate-600">Güven</p>
          <p className="font-mono text-2xl font-bold text-white">{confidencePct}<span className="text-sm text-slate-500">%</span></p>
          <p className="text-[9px] text-slate-600">5-Mod: {fiveModScore}</p>
        </div>
      </div>

      {/* Green light */}
      {consensus.green_light && consensus.verified && (
        <div className="flex items-center gap-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-2.5 py-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-[10px] font-semibold text-emerald-400">ONAY — Tüm filtreler geçildi</span>
        </div>
      )}

      {/* Modül skorları */}
      <div className="space-y-1.5">
        {Object.entries(scores).map(([mod, val]) => {
          const pct = Math.min(100, Math.max(0, Math.round((val as number) * 100)));
          return (
            <div key={mod} className="flex items-center gap-2">
              <span className="w-3 shrink-0 font-mono text-[9px] font-bold uppercase text-slate-500">
                {mod[0].toUpperCase()}
              </span>
              <div className="h-1.5 flex-1 rounded-full bg-slate-700/60">
                <div
                  className={`h-1.5 rounded-full ${MODULE_COLORS[mod] ?? "bg-slate-400"} transition-all duration-500`}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="w-6 shrink-0 text-right font-mono text-[9px] text-slate-500">{pct}</span>
            </div>
          );
        })}
      </div>

      {/* Data status */}
      <DataStatusBadge data={consensus} compact className="mt-1" />
    </div>
  );
};

// ── Zone 2: Performans ────────────────────────────────────────────────────────

const PerformansPaneli: React.FC<{ pnl: DailyPnL | null }> = ({ pnl }) => (
  <div className="space-y-4">
    <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">
      Günlük Performans
    </p>

    {pnl ? (
      <>
        {/* Günlük P&L büyük sayı */}
        <div className="flex items-end justify-between">
          <div>
            <p className="text-[9px] uppercase tracking-wider text-slate-600">Gerçekleşen P&L</p>
            <p className={`font-mono text-3xl font-extrabold leading-none ${pnlColor(pnl.realized_pnl)}`}>
              {pnl.realized_pnl >= 0 ? "+" : ""}${pnl.realized_pnl.toFixed(2)}
            </p>
          </div>
          <div className="text-right">
            <p className="text-[9px] uppercase tracking-wider text-slate-600">İşlem</p>
            <p className="font-mono text-xl font-bold text-white">{pnl.trade_count}</p>
          </div>
        </div>

        {/* Kill switch progress bar */}
        <div>
          <div className="mb-1.5 flex items-center justify-between text-[9px]">
            <span className="text-slate-600">Günlük limit</span>
            <span className={pnl.kill_switch_active ? "font-semibold text-rose-400" : "text-slate-500"}>
              {pnl.kill_switch_active
                ? "⚠ LİMİT AŞILDI"
                : `${Math.abs(pnl.realized_pnl).toFixed(2)} / $${(pnl.kill_switch_threshold * 10000).toFixed(0)}`
              }
            </span>
          </div>
          <div className="h-1.5 rounded-full bg-slate-700/60">
            <div
              className={`h-1.5 rounded-full transition-all duration-500 ${
                pnl.kill_switch_active ? "bg-rose-500" : "bg-amber-500"
              }`}
              style={{
                width: `${Math.min(100, (Math.abs(pnl.realized_pnl) / (pnl.kill_switch_threshold * 10000)) * 100)}%`,
              }}
            />
          </div>
        </div>

        <p className="text-[9px] italic text-slate-700">
          {pnl.message}
        </p>
      </>
    ) : (
      <div className="space-y-2 py-2">
        <div className="text-center">
          <p className="font-mono text-2xl font-bold text-slate-600">—</p>
          <p className="text-[9px] text-slate-700">P&L verisi yükleniyor</p>
        </div>
        <p className="text-[9px] text-slate-700 text-center">
          /api/pnl/daily endpoint'ine bağlanılıyor…
        </p>
      </div>
    )}
  </div>
);

// ── Zone 3: Risk Göstergesi ────────────────────────────────────────────────────

const RiskPaneli: React.FC<{ macro: MacroViewModel | null; pnl: DailyPnL | null }> = ({ macro, pnl }) => {
  const eventRisk = macro?.metrics?.event_risk_score ?? null;
  const vix       = macro?.metrics?.vix ?? null;
  const hyg       = (macro?.metrics as Record<string, number> | undefined)?.hyg ?? null;
  const funding   = (macro?.metrics as Record<string, number> | undefined)?.funding_rate ?? null;

  const killActive = pnl?.kill_switch_active ?? false;

  return (
    <div className="space-y-3">
      <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">
        Risk Monitörü
      </p>

      {/* Kill Switch */}
      <div className={`flex items-center justify-between rounded-lg border px-3 py-2 ${
        killActive
          ? "border-rose-500/50 bg-rose-500/10"
          : "border-emerald-500/20 bg-emerald-500/5"
      }`}>
        <span className="text-[11px] font-semibold text-slate-300">Kill Switch</span>
        <span className={`text-[11px] font-bold ${killActive ? "text-rose-400" : "text-emerald-400"}`}>
          {killActive ? "⚠ AKTİF" : "● KAPALI"}
        </span>
      </div>

      {/* Makro risk göstergeleri */}
      <div className="space-y-2 rounded-xl border border-slate-800 bg-slate-950/40 p-3">
        {[
          { label: "Olay Riski",  value: eventRisk !== null ? `${(eventRisk * 100).toFixed(0)}%` : "—", color: eventRisk !== null ? riskColor(eventRisk) : "text-slate-600", sub: eventRisk !== null ? riskLabel(eventRisk) : "" },
          { label: "VIX",         value: vix !== null ? vix.toFixed(1) : "—",  color: vix !== null ? (vix < 18 ? "text-emerald-400" : vix < 28 ? "text-amber-400" : "text-rose-400") : "text-slate-600", sub: vix !== null ? (vix < 18 ? "Sakin" : vix < 28 ? "Normal" : "Yüksek") : "" },
          { label: "HYG",         value: hyg !== null ? hyg.toFixed(1) : "—",  color: hyg !== null ? (hyg > 77 ? "text-emerald-400" : hyg > 74 ? "text-amber-400" : "text-rose-400") : "text-slate-600", sub: hyg !== null ? (hyg > 77 ? "Güçlü" : hyg > 74 ? "Zayıflıyor" : "Bozulmuş") : "" },
          { label: "Funding",     value: funding !== null ? `${(funding * 100).toFixed(3)}%` : "—", color: funding !== null ? (Math.abs(funding) < 0.02 ? "text-emerald-400" : Math.abs(funding) < 0.05 ? "text-amber-400" : "text-rose-400") : "text-slate-600", sub: funding !== null ? (funding > 0.05 ? "Uzun Kalabalık" : funding < -0.05 ? "Kısa Kalabalık" : "Normal") : "" },
        ].map(({ label, value, color, sub }) => (
          <div key={label} className="flex items-center justify-between">
            <span className="text-[10px] text-slate-500">{label}</span>
            <div className="text-right">
              <span className={`font-mono text-[11px] font-semibold ${color}`}>{value}</span>
              {sub && <span className="ml-1.5 text-[9px] text-slate-600">{sub}</span>}
            </div>
          </div>
        ))}
      </div>

      {/* Makro rejim */}
      {macro && (
        <div className="rounded-lg border border-slate-800 bg-slate-950/30 px-3 py-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-slate-500">Rejim</span>
            <span className="font-mono text-[11px] font-semibold text-sky-300">{macro.regime}</span>
          </div>
          <div className="flex items-center justify-between mt-1">
            <span className="text-[10px] text-slate-500">Makro Durum</span>
            <DataStatusBadge data={macro} compact />
          </div>
        </div>
      )}
    </div>
  );
};

// ── Ana Bileşen ───────────────────────────────────────────────────────────────

export const KontrolMerkezi: React.FC<KontrolProps> = ({
  macro, btcConsensus, dailyPnl, loading,
}) => {
  return (
    <div className="grid gap-4 lg:grid-cols-3">

      {/* Zone 1: Karar */}
      <div className="rounded-2xl border border-slate-700/60 bg-slate-900 p-5 shadow-md">
        <p className="mb-4 text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">
          Karar Paneli
        </p>
        <KararPaneli consensus={btcConsensus} loading={loading} />
      </div>

      {/* Zone 2: Performans */}
      <div className="rounded-2xl border border-slate-700/60 bg-slate-900 p-5 shadow-md">
        <PerformansPaneli pnl={dailyPnl} />
      </div>

      {/* Zone 3: Risk */}
      <div className="rounded-2xl border border-slate-700/60 bg-slate-900 p-5 shadow-md">
        <RiskPaneli macro={macro} pnl={dailyPnl} />
      </div>

    </div>
  );
};
