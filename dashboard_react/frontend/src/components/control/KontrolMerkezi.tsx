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

const MODULE_LABELS: Record<string, string> = {
  touche: "Touche",
  fundamental: "Fundamental",
  news: "News",
  sentinel: "Sentinel",
  quantum: "Quantum",
};

const MODULE_COLORS: Record<string, string> = {
  touche: "bg-violet-400",
  fundamental: "bg-sky-400",
  news: "bg-amber-400",
  sentinel: "bg-rose-400",
  quantum: "bg-emerald-400",
};

function pct(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "--";
  return `${Math.round(value * 100)}%`;
}

function scorePct(value: number | null | undefined): number {
  if (value == null || !Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, Math.round(value * 100)));
}

function formatSignedUsd(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "--";
  const sign = value >= 0 ? "+" : "";
  return `${sign}$${value.toFixed(2)}`;
}

function candidateTone(consensus: ConsensusResponse | null): { label: string; cls: string; dot: string } {
  if (!consensus) {
    return { label: "No candidate", cls: "text-slate-400 border-slate-700 bg-slate-800/70", dot: "bg-slate-500" };
  }
  if (consensus.action === "BUY") {
    return { label: "Positive candidate", cls: "text-emerald-300 border-emerald-500/30 bg-emerald-500/10", dot: "bg-emerald-400" };
  }
  if (consensus.action === "SELL") {
    return { label: "Negative candidate", cls: "text-rose-300 border-rose-500/30 bg-rose-500/10", dot: "bg-rose-400" };
  }
  return { label: "No candidate", cls: "text-slate-300 border-slate-700 bg-slate-800/70", dot: "bg-slate-500" };
}

function dataFreshnessLabel(consensus: ConsensusResponse | null, macro: MacroViewModel | null): string {
  const consensusAge = consensus ? formatDataAge(consensus.timestamp ?? consensus.last_updated ?? null) : "consensus yok";
  const macroAge = macro ? formatDataAge(macro.timestamp ?? macro.last_updated ?? null) : "macro yok";
  return `Consensus: ${consensusAge} | Macro: ${macroAge}`;
}

const ModuleBars: React.FC<{ consensus: ConsensusResponse | null }> = ({ consensus }) => {
  const scores = consensus?.module_scores ?? {};
  const weights = consensus?.module_weights ?? {};

  return (
    <div className="space-y-2">
      {Object.entries(MODULE_LABELS).map(([key, label]) => {
        const score = scorePct((scores as Record<string, number>)[key]);
        const weight = scorePct((weights as Record<string, number>)[key]);
        return (
          <div key={key} className="grid grid-cols-[92px_minmax(0,1fr)_64px] items-center gap-3">
            <span className="truncate text-[11px] font-semibold text-slate-400">{label}</span>
            <div className="h-2 rounded-full bg-slate-800">
              <div
                className={`h-2 rounded-full ${MODULE_COLORS[key] ?? "bg-slate-400"}`}
                style={{ width: `${score}%` }}
              />
            </div>
            <span className="text-right font-mono text-[10px] text-slate-500">
              {score} / {weight}
            </span>
          </div>
        );
      })}
    </div>
  );
};

export const KontrolMerkezi: React.FC<KontrolProps> = ({
  macro,
  btcConsensus,
  dailyPnl,
  loading,
}) => {
  const tone = candidateTone(btcConsensus);
  const score = btcConsensus?.weighted_score ?? btcConsensus?.five_module_score ?? null;
  const edge = score == null ? null : Math.abs(score - 0.5);
  const warnings = [
    ...(btcConsensus?.warnings ?? []),
    ...(macro?.warnings ?? []),
    dailyPnl?.kill_switch_active ? "Kill switch active; candidates should be blocked." : null,
  ].filter(Boolean) as string[];

  if (loading) {
    return (
      <section className="grid gap-4 lg:grid-cols-3">
        {[0, 1, 2].map((item) => (
          <div key={item} className="min-h-[220px] animate-pulse rounded-xl border border-slate-800 bg-slate-900 p-5">
            <div className="h-4 w-28 rounded bg-slate-800" />
            <div className="mt-5 h-12 rounded bg-slate-800" />
            <div className="mt-4 space-y-2">
              <div className="h-2 rounded bg-slate-800" />
              <div className="h-2 w-4/5 rounded bg-slate-800" />
              <div className="h-2 w-2/3 rounded bg-slate-800" />
            </div>
          </div>
        ))}
      </section>
    );
  }

  return (
    <section className="grid gap-4 lg:grid-cols-3">
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
              Agent evidence
            </p>
            <h3 className="mt-2 text-base font-semibold text-slate-100">Signal candidate</h3>
          </div>
          <span className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[11px] font-bold ${tone.cls}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${tone.dot}`} />
            {tone.label}
          </span>
        </div>

        <div className="mt-5 grid grid-cols-3 gap-2">
          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
            <p className="text-[9px] uppercase tracking-[0.14em] text-slate-600">Score</p>
            <p className="mt-1 font-mono text-xl font-bold text-slate-100">{pct(score)}</p>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
            <p className="text-[9px] uppercase tracking-[0.14em] text-slate-600">Confidence</p>
            <p className="mt-1 font-mono text-xl font-bold text-slate-100">{pct(btcConsensus?.confidence)}</p>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
            <p className="text-[9px] uppercase tracking-[0.14em] text-slate-600">Edge</p>
            <p className="mt-1 font-mono text-xl font-bold text-slate-100">{pct(edge)}</p>
          </div>
        </div>

        <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/35 px-3 py-2 text-[11px] leading-5 text-slate-400">
          {btcConsensus?.green_light_reason || "No verified candidate reason available."}
        </div>
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
              Module attribution
            </p>
            <h3 className="mt-2 text-base font-semibold text-slate-100">Score and weight</h3>
          </div>
          {btcConsensus && <DataStatusBadge data={btcConsensus} compact />}
        </div>

        <div className="mt-5">
          <ModuleBars consensus={btcConsensus} />
        </div>
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
              Safety state
            </p>
            <h3 className="mt-2 text-base font-semibold text-slate-100">Freshness and risk</h3>
          </div>
          {macro && <DataStatusBadge data={macro} compact />}
        </div>

        <div className="mt-5 space-y-3">
          <div className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2">
            <div className="flex items-center justify-between gap-3 text-[11px]">
              <span className="text-slate-500">Data freshness</span>
              <span className="text-right font-mono text-slate-300">{dataFreshnessLabel(btcConsensus, macro)}</span>
            </div>
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2">
            <div className="flex items-center justify-between gap-3 text-[11px]">
              <span className="text-slate-500">Daily PnL monitor</span>
              <span className={dailyPnl && dailyPnl.realized_pnl < 0 ? "font-mono text-rose-300" : "font-mono text-emerald-300"}>
                {formatSignedUsd(dailyPnl?.realized_pnl)}
              </span>
            </div>
          </div>

          <div className={`rounded-lg border px-3 py-2 text-[11px] ${
            dailyPnl?.kill_switch_active
              ? "border-rose-500/40 bg-rose-500/10 text-rose-200"
              : "border-emerald-500/25 bg-emerald-500/5 text-emerald-200"
          }`}>
            {dailyPnl?.kill_switch_active ? "Kill switch active" : "Kill switch clear"}
          </div>

          {warnings.length > 0 && (
            <div className="max-h-28 overflow-y-auto rounded-lg border border-amber-500/25 bg-amber-500/10 px-3 py-2">
              {warnings.slice(0, 4).map((warning, index) => (
                <p key={`${warning}-${index}`} className="text-[11px] leading-5 text-amber-100">
                  {warning}
                </p>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
};
