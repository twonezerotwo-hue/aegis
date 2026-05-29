import React, { useState } from "react";
import type { RealEstateDecision, RealEstateSignal } from "../../types/dashboardV2";

interface Props {
  decision: RealEstateDecision | undefined;
}

const SIGNAL_CONFIG: Record<RealEstateSignal, { label: string; color: string; ring: string; badge: string }> = {
  BUY_ZONE:   { label: "BUY ZONE",   color: "text-emerald-300", ring: "ring-emerald-400/40", badge: "bg-emerald-500/15 text-emerald-300 border-emerald-400/30" },
  BUILD_ZONE: { label: "BUILD ZONE", color: "text-sky-300",     ring: "ring-sky-400/40",     badge: "bg-sky-500/15 text-sky-300 border-sky-400/30" },
  RESEARCH:   { label: "RESEARCH",   color: "text-amber-300",   ring: "ring-amber-400/40",   badge: "bg-amber-500/15 text-amber-300 border-amber-400/30" },
  WAIT:       { label: "WAIT",       color: "text-slate-300",   ring: "ring-slate-400/40",   badge: "bg-slate-500/15 text-slate-300 border-slate-400/30" },
  AVOID:      { label: "AVOID",      color: "text-rose-300",    ring: "ring-rose-400/40",    badge: "bg-rose-500/15 text-rose-300 border-rose-400/30" },
};

const ChecklistSection: React.FC<{ title: string; items: string[]; icon: string }> = ({ title, items, icon }) => {
  if (items.length === 0) return null;
  return (
    <div className="space-y-1.5">
      <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">{icon} {title}</p>
      <ul className="space-y-1">
        {items.map((item, i) => (
          <li key={i} className="flex items-start gap-1.5 text-[11px] text-slate-300">
            <span className="mt-0.5 shrink-0 text-slate-500">·</span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
};

export const RealEstateDecisionPanel: React.FC<Props> = ({ decision }) => {
  const [expanded, setExpanded] = useState(false);

  if (!decision) {
    return (
      <div className="rounded-2xl border border-slate-700/60 bg-slate-900 p-5">
        <p className="text-xs text-slate-500">Gayrimenkul karar verisi alınamadı.</p>
      </div>
    );
  }

  const cfg = SIGNAL_CONFIG[decision.signal] ?? SIGNAL_CONFIG.WAIT;

  return (
    <div className="rounded-2xl border border-slate-700/60 bg-slate-900 p-5 shadow-md shadow-slate-950/20 transition-all duration-300 hover:border-slate-600">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">
            Real Estate Decision Layer
          </p>
          <h2 className="mt-1 text-sm font-semibold text-slate-300">
            Ev / Arsa / İnşaat Karar Paneli
          </h2>
          <p className="mt-0.5 text-[10px] text-slate-500 italic">
            Likit portföy yüzdesi değildir · Yatırım tavsiyesi değildir
          </p>
        </div>
        <span className={`shrink-0 rounded-full border px-3 py-1 text-xs font-bold tracking-wider ${cfg.badge}`}>
          {cfg.label}
        </span>
      </div>

      {/* Confidence bar */}
      <div className="mt-4">
        <div className="mb-1 flex justify-between text-[10px] uppercase tracking-wider text-slate-500">
          <span>Macro Confidence</span>
          <span className={`font-mono font-semibold ${cfg.color}`}>{decision.confidence}%</span>
        </div>
        <div className="h-1.5 rounded-full bg-slate-700/50">
          <div
            className={`h-1.5 rounded-full transition-all duration-700 ${
              decision.signal === "AVOID" ? "bg-rose-500" :
              decision.signal === "BUY_ZONE" ? "bg-emerald-500" :
              decision.signal === "BUILD_ZONE" ? "bg-sky-500" :
              decision.signal === "RESEARCH" ? "bg-amber-500" : "bg-slate-500"
            }`}
            style={{ width: `${Math.min(100, decision.confidence)}%` }}
          />
        </div>
      </div>

      {/* Data status */}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className={`rounded-full border px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wider ${
          decision.verified ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-300" : "border-amber-400/30 bg-amber-500/10 text-amber-300"
        }`}>
          {decision.verified ? "Verified" : "Unverified"} · {decision.data_status}
        </span>
        {!decision.verified && (
          <span className="text-[9px] text-amber-400/70">Yerel veri zorunlu</span>
        )}
      </div>

      {/* Rationale */}
      {decision.rationale.length > 0 && (
        <div className="mt-4 rounded-xl border border-slate-700/60 bg-slate-800/60 p-3">
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">Makro Gerekçe</p>
          <ul className="space-y-1">
            {decision.rationale.map((r, i) => (
              <li key={i} className="flex items-start gap-1.5 text-[11px] text-slate-300">
                <span className="mt-0.5 shrink-0 text-slate-500">·</span>
                <span>{r}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Warning */}
      {decision.warning && (
        <div className="mt-3 rounded-xl border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-[10px] text-amber-200/80">
          {decision.warning}
        </div>
      )}

      {/* Expand toggle */}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="mt-4 w-full rounded-xl border border-slate-700 bg-slate-800/40 px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400 transition-colors hover:border-slate-500 hover:text-slate-200"
      >
        {expanded ? "▲ Gizle" : "▼ Detaylı Kontrol Listesi"}
      </button>

      {expanded && (
        <div className="mt-4 space-y-4">

          {/* Positive signals */}
          <ChecklistSection title="Alım / Giriş Destekleyen Koşullar" items={decision.buy_conditions} icon="✓" />

          {/* Construction */}
          <ChecklistSection title="İnşaat / Proje Koşulları" items={decision.construction_conditions} icon="🏗" />

          {/* Avoid conditions */}
          <ChecklistSection title="Kaçınma Koşulları" items={decision.avoid_conditions} icon="✗" />

          {/* Required checks */}
          <div className="space-y-1.5">
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">
              ☑ Zorunlu Yerel Kontroller
            </p>
            <ul className="space-y-1">
              {decision.required_checks.map((item, i) => (
                <li key={i} className="flex items-start gap-1.5 text-[11px] text-slate-400">
                  <span className="mt-0.5 shrink-0 text-slate-600">□</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Disclaimer */}
          <div className="rounded-xl border border-slate-700/40 bg-slate-800/30 px-3 py-2 text-[9px] text-slate-500 italic">
            {decision.disclaimer}
          </div>
        </div>
      )}
    </div>
  );
};
