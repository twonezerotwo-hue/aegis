/**
 * components/consensus/DecisionCard.tsx
 * AEGIS v7.0 — Premium decision card
 * Score hierarchy, expandable "Neden?" section, v7 CI / meta / correlation fields,
 * criteria grid with pass/fail color coding, responsive layout.
 */

import React, { useState } from "react";
import { ConsensusResponse } from "../../types/dashboardV2";
import { AnimatedNumber } from "../ui/AnimatedNumber";
import { SkeletonLoader } from "../ui/SkeletonLoader";

interface DecisionCardProps {
  consensus: ConsensusResponse | null;
  loading: boolean;
}

const criteriaLabels: Record<string, string> = {
  regime_suitable:       "Rejim",
  dynamic_threshold_pass:"Threshold",
  modules_agree_3plus:   "3+ Modül",
  multi_tf_aligned:      "Multi-TF",
  cbr_edge_valid:        "CBR",
  liquidity_ok:          "Likidite",
  risk_multiplier_ok:    "Risk",
  event_risk_ok:         "Event",
  ci_guard_pass:         "CI Guard",
  correlation_ok:        "Corr",
};

const getActionCls = (action: string) => {
  if (action === "BUY")  return { text: "text-emerald-400", fill: "bg-emerald-500", glow: "shadow-emerald-500/20" };
  if (action === "SELL") return { text: "text-rose-400",    fill: "bg-rose-500",    glow: "shadow-rose-500/20" };
  return                        { text: "text-amber-400",   fill: "bg-amber-500",   glow: "shadow-amber-500/20" };
};

export const DecisionCard: React.FC<DecisionCardProps> = ({ consensus, loading }) => {
  const [whyOpen, setWhyOpen] = useState(false);
  const whyId = React.useId();

  if (loading && !consensus) {
    return <SkeletonLoader variant="card" lines={3} />;
  }

  if (!consensus) {
    return (
      <div className="rounded-2xl border border-slate-700/60 bg-slate-900 p-5 text-sm text-slate-500">
        Consensus verisi alınamadı.
      </div>
    );
  }

  const cls = getActionCls(consensus.action);

  return (
    <div
      className="rounded-2xl border border-slate-700/60 bg-slate-900 shadow-md shadow-slate-950/30
        transition-all duration-300 hover:border-slate-600 hover:shadow-lg hover:shadow-slate-950/40"
    >
      {/* ── Top bar ─────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4 p-5 pb-4">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">
            Decision Card
          </p>
          <p className="mt-0.5 text-sm font-semibold text-white">Consensus Control</p>
        </div>
        {/* Action chip */}
        <div
          className={`shrink-0 rounded-xl border px-4 py-2 text-center shadow-lg ${cls.glow}
            ${consensus.action === "BUY"  ? "border-emerald-500/30 bg-emerald-500/10" :
              consensus.action === "SELL" ? "border-rose-500/30 bg-rose-500/10" :
                                            "border-amber-500/30 bg-amber-500/10"}`}
        >
          <p className="text-[10px] uppercase tracking-widest text-slate-500">Action</p>
          <p className={`mt-1 text-2xl font-semibold leading-none tracking-tight ${cls.text}`}>
            {consensus.action}
          </p>
          <span
            className={`mt-1.5 inline-flex rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase ${
              consensus.green_light
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                : "border-amber-500/30 bg-amber-500/10 text-amber-300"
            }`}
          >
            {consensus.green_light ? "Green Light" : "Gate Active"}
          </span>
        </div>
      </div>

      {/* ── Stat trio ───────────────────────────────────────────────── */}
      <div className="grid grid-cols-3 gap-2 px-5 pb-4">
        {[
          { label: "Confidence",    value: consensus.confidence * 100,    suffix: "%" },
          { label: "Weighted Scr",  value: consensus.weighted_score * 100, suffix: "%" },
          { label: "Position Size", value: consensus.position_size * 100,  suffix: "%" },
        ].map(({ label, value, suffix }) => (
          <div key={label} className="rounded-xl border border-slate-700/50 bg-slate-800/60 px-3 py-2.5">
            <p className="text-[10px] uppercase tracking-[0.14em] text-slate-500">{label}</p>
            <p className="mt-1.5 font-mono text-base font-medium text-white">
              <AnimatedNumber
                value={value}
                formatter={(v) => `${v.toFixed(1)}${suffix}`}
                className="font-mono"
              />
            </p>
          </div>
        ))}
      </div>

      {/* ── Five-module score bar ────────────────────────────────────── */}
      <div className="mx-5 mb-4 rounded-xl border border-slate-700/50 bg-slate-800/60 p-4">
        <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.14em] text-slate-500">
          <span>Five Module Score</span>
          <span className="font-mono text-slate-300">
            {(consensus.five_module_score * 100).toFixed(1)} / 100
          </span>
        </div>
        <div className="mt-3 flex items-end gap-4">
          <p className={`font-mono text-4xl font-semibold leading-none ${cls.text}`}>
            <AnimatedNumber
              value={consensus.five_module_score * 100}
              formatter={(v) => v.toFixed(1)}
              className="font-mono"
              neutralClassName={cls.text}
              positiveClassName="text-emerald-300"
              negativeClassName="text-rose-300"
            />
          </p>
          <div className="flex-1 pb-1">
            <div className="h-2 overflow-hidden rounded-full bg-slate-700/70">
              <div
                className={`h-2 rounded-full transition-all duration-500 ${cls.fill}`}
                style={{ width: `${Math.max(0, Math.min(100, consensus.five_module_score * 100))}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* ── Module score tiles ───────────────────────────────────────── */}
      <div className="grid grid-cols-5 gap-1.5 px-5 pb-4">
        {Object.entries(consensus.module_scores).map(([name, value]) => (
          <div key={name} className="rounded-xl border border-slate-700/50 bg-slate-800/50 px-2 py-2.5 text-center">
            <p className="text-[9px] uppercase tracking-[0.1em] text-slate-500">{name}</p>
            <p className="mt-1.5 font-mono text-sm font-medium text-white">
              {(value * 100).toFixed(0)}
            </p>
          </div>
        ))}
      </div>

      {/* ── Criteria grid ────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-1.5 px-5 pb-4 sm:grid-cols-4 lg:grid-cols-5">
        {Object.entries(consensus.criteria).map(([key, value]) => (
          <div
            key={key}
            className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 transition-colors duration-200 ${
              value
                ? "border-emerald-500/20 bg-emerald-500/5 hover:border-emerald-500/30"
                : "border-rose-500/20 bg-rose-500/5 hover:border-rose-500/30"
            }`}
          >
            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${value ? "bg-emerald-400" : "bg-rose-400"}`} />
            <span className="text-[10px] text-slate-300 truncate">{criteriaLabels[key] ?? key}</span>
          </div>
        ))}
      </div>

      {/* ── Failed criteria ──────────────────────────────────────────── */}
      <div className="mx-5 mb-4 rounded-xl border border-slate-700/50 bg-slate-800/40 p-3">
        <p className="text-[10px] uppercase tracking-[0.14em] text-slate-500">Failed Criteria</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {consensus.failed_criteria.length > 0 ? (
            consensus.failed_criteria.map((item) => (
              <span key={item} className="rounded-full border border-rose-500/25 bg-rose-500/10 px-2.5 py-0.5 text-[10px] text-rose-300">
                {item}
              </span>
            ))
          ) : (
            <span className="rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2.5 py-0.5 text-[10px] text-emerald-300">
              all_criteria_pass
            </span>
          )}
        </div>
      </div>

      {/* ── v7.0 signals (inline, no expand needed) ──────────────────── */}
      {(consensus.meta_score !== undefined ||
        consensus.confidence_interval !== undefined ||
        consensus.correlation_penalty !== undefined) && (
        <div className="mx-5 mb-4 rounded-xl border border-sky-500/20 bg-sky-500/5 p-3">
          <p className="text-[10px] uppercase tracking-[0.14em] text-sky-500 mb-2">v7.0 Signals</p>
          <div className="grid grid-cols-3 gap-2">
            {consensus.meta_score !== undefined && (
              <div>
                <p className="text-[9px] uppercase tracking-widest text-slate-500">Meta Score</p>
                <p className="mt-1 font-mono text-sm font-medium text-white">{consensus.meta_score.toFixed(1)}</p>
              </div>
            )}
            {consensus.confidence_interval !== undefined && (
              <div>
                <p className="text-[9px] uppercase tracking-widest text-slate-500">CI ±1σ</p>
                <p className="mt-1 font-mono text-[11px] font-medium text-white">
                  [{consensus.confidence_interval[0].toFixed(1)}, {consensus.confidence_interval[1].toFixed(1)}]
                </p>
              </div>
            )}
            {consensus.correlation_penalty !== undefined && (
              <div>
                <p className="text-[9px] uppercase tracking-widest text-slate-500">Corr ×</p>
                <p className={`mt-1 font-mono text-sm font-medium ${consensus.correlation_penalty < 1 ? "text-amber-400" : "text-emerald-400"}`}>
                  {consensus.correlation_penalty.toFixed(3)}
                </p>
              </div>
            )}
          </div>
          {consensus.correlation_penalized_pairs && consensus.correlation_penalized_pairs.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {consensus.correlation_penalized_pairs.map((pair, i) => (
                <span key={i} className="rounded-full border border-amber-500/25 bg-amber-500/10 px-2 py-0.5 text-[9px] text-amber-300">
                  {pair.penalized} penalized ({(pair.correlation * 100).toFixed(0)}% corr)
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── "Neden?" expandable ─────────────────────────────────────── */}
      <button
        type="button"
        onClick={() => setWhyOpen((v) => !v)}
        aria-expanded={whyOpen}
        aria-controls={whyId}
        className="flex w-full items-center justify-between border-t border-slate-700/50 px-5 py-3 text-left
          transition-colors duration-200 hover:bg-slate-800/40"
      >
        <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
          Neden bu karar?
        </span>
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
          className={`h-3.5 w-3.5 text-slate-500 transition-transform duration-200 ${whyOpen ? "rotate-180" : "rotate-0"}`}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
      <div
        id={whyId}
        role="region"
        className={`overflow-hidden transition-all duration-250 ease-in-out ${whyOpen ? "max-h-[400px]" : "max-h-0"}`}
      >
        <div className="px-5 pb-5 pt-3 space-y-3">
          <div className="rounded-xl border border-slate-700/50 bg-slate-800/40 p-3 text-xs leading-6 text-slate-400">
            <span className="font-semibold text-slate-300">Green Light:</span>{" "}
            {consensus.green_light_reason}
          </div>
          <div className="rounded-xl border border-slate-700/50 bg-slate-800/40 p-3 text-xs leading-6 text-slate-400">
            <span className="font-semibold text-slate-300">Multi-TF:</span>{" "}
            {consensus.multi_tf.reason} — {consensus.multi_tf.final_signal}
          </div>
          {consensus.cbr.reason && (
            <div className="rounded-xl border border-slate-700/50 bg-slate-800/40 p-3 text-xs leading-6 text-slate-400">
              <span className="font-semibold text-slate-300">CBR:</span>{" "}
              {consensus.cbr.reason} (win rate {consensus.cbr.win_rate_pct.toFixed(1)}%)
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
