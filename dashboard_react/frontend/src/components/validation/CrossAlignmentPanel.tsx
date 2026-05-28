import React from "react";
import type { ConsensusResponse, MacroViewModel } from "../../types/dashboardV2";
import type { Vade } from "../../context/VadeContext";

export interface AssetResult {
  label: string;
  consensus: ConsensusResponse | null;
}

interface Props {
  macro: MacroViewModel;
  assets: Record<string, AssetResult>;
  vade: Vade;
}

const getRegimeBias = (regime: string): string[] => {
  if (regime.includes("RISK_ON") || regime.includes("LIQUIDITY")) {
    return ["btc", "commodity", "gold"];
  }
  if (regime.includes("RISK_OFF")) {
    return ["gold", "bond", "cash"];
  }
  if (regime.includes("STAG")) {
    return ["gold", "commodity"];
  }
  return ["gold", "btc"];
};

const VADE_WARNINGS: Record<Vade, string | null> = {
  short: "Kisa vadede volatilite yuksek, stop-loss daha sik ve girisler kademeli olmali.",
  medium: null,
  long: "Uzun vadeli pozisyonlarda likidite suresi ve vade uyumsuzlugunu kontrol et.",
};

const BIAS_MODE: Record<Vade, { label: string; icon: string; description: string }> = {
  short: { label: "Momentum", icon: "M", description: "Yalnizca BUY uyumlu sayilir" },
  medium: { label: "Dengeli", icon: "D", description: "BUY uyumlu, HOLD notr" },
  long: { label: "Dongusel", icon: "C", description: "BUY ve HOLD uyumlu sayilir" },
};

interface AlignmentRow {
  key: string;
  label: string;
  action: string;
  inBias: boolean;
  aligned: boolean;
}

const computeAlignment = (
  assets: Record<string, AssetResult>,
  regimeBias: string[],
  vade: Vade
): { rows: AlignmentRow[]; matchCount: number } => {
  const rows: AlignmentRow[] = [];
  let matchCount = 0;

  for (const [key, { label, consensus }] of Object.entries(assets)) {
    if (!consensus) {
      continue;
    }

    const action = consensus.action;
    const inBias = regimeBias.includes(key);
    const aligned =
      vade === "long"
        ? inBias
          ? action === "BUY" || action === "HOLD"
          : action === "SELL"
        : inBias
          ? action === "BUY"
          : action === "HOLD" || action === "SELL";

    if (aligned) {
      matchCount += 1;
    }
    rows.push({ key, label, action, inBias, aligned });
  }

  return { rows, matchCount };
};

type ChecklistStatus = "ONAY" | "RISK" | "UNVERIFIED";

const statusColor = (status: ChecklistStatus): string =>
  status === "ONAY" ? "text-emerald-400" : status === "UNVERIFIED" ? "text-amber-300" : "text-rose-400";

const statusDot = (status: ChecklistStatus): string =>
  status === "ONAY" ? "bg-emerald-400" : status === "UNVERIFIED" ? "bg-amber-400" : "bg-rose-400";

export const CrossAlignmentPanel: React.FC<Props> = ({ macro, assets, vade }) => {
  const regimeBias = getRegimeBias(macro.regime);
  const { rows, matchCount } = computeAlignment(assets, regimeBias, vade);
  const total = rows.length;
  const alignmentPct = total > 0 ? Math.round((matchCount / total) * 100) : 0;
  const isAligned = alignmentPct >= 75;
  const vadeWarning = VADE_WARNINGS[vade];
  const biasMode = BIAS_MODE[vade];
  const liveVerifiedMacro =
    macro.data_status === "LIVE" &&
    macro.verified === true &&
    macro.live === true;
  const hedgeUnverified =
    !liveVerifiedMacro ||
    macro.hedge_unverified === true ||
    macro.hedge_source === "derived_from_unverified_macro" ||
    (macro.hedge && macro.live !== true);
  const vixUnverified = !liveVerifiedMacro || (macro.fallback_fields ?? []).includes("vix");

  const barCls =
    alignmentPct >= 75 ? "bg-emerald-500" : alignmentPct >= 50 ? "bg-amber-500" : "bg-rose-500";

  const statusBadgeCls = isAligned
    ? "border-emerald-500/30 bg-emerald-500/8 text-emerald-300"
    : "border-amber-500/30 bg-amber-500/8 text-amber-300";

  const actionClass: Record<string, string> = {
    BUY: "text-emerald-400",
    HOLD: "text-amber-400",
    SELL: "text-rose-400",
  };

  const eventRiskPct = macro.metrics.event_risk_score * 100;
  const eventRiskLevel =
    eventRiskPct >= 60 ? "YUKSEK" : eventRiskPct >= 30 ? "NORMAL" : "DUSUK";
  const hedgeNote = !liveVerifiedMacro
    ? "(macro data not fully verified)"
    : hedgeUnverified
      ? "(fallback macrodan turetilmis)"
      : macro.hedge
        ? "(hedge aktif)"
        : "(hedge kapali)";
  const vixNote = !liveVerifiedMacro
    ? "(macro data not fully verified)"
    : vixUnverified
      ? "(VIX fallback)"
      : macro.metrics.vix.toFixed(1);

  const checklistItems: Array<{ label: string; note?: string; status: ChecklistStatus }> = [
    {
      label: "Makro rejim uygun",
      note: !liveVerifiedMacro
        ? "(macro data not fully verified)"
        : macro.regime.includes("RISK_OFF") && !macro.hedge
          ? "(risk-off, hedge yok)"
          : undefined,
      status: !liveVerifiedMacro
        ? "UNVERIFIED"
        : !macro.regime.includes("RISK_OFF") || macro.hedge
          ? "ONAY"
          : "RISK",
    },
    {
      label: "Uyum skoru >= 75%",
      note: `${alignmentPct}%`,
      status: isAligned ? "ONAY" : "RISK",
    },
    {
      label: "Hedge durumu",
      note: hedgeNote,
      status: hedgeUnverified ? "UNVERIFIED" : !macro.hedge ? "ONAY" : "RISK",
    },
    {
      label: `EvRisk: ${eventRiskPct.toFixed(0)}% (${eventRiskLevel})`,
      status: !liveVerifiedMacro ? "UNVERIFIED" : macro.metrics.event_risk_score < 0.5 ? "ONAY" : "RISK",
    },
    {
      label: "VIX normal bolge",
      note: vixNote,
      status: vixUnverified ? "UNVERIFIED" : macro.metrics.vix < 25 ? "ONAY" : "RISK",
    },
  ];

  return (
    <div className="rounded-2xl border border-slate-700/60 bg-slate-800 p-5 shadow-md shadow-slate-950/20">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">
            Uyum ve Kross-Validasyon
          </p>
          <p className="mt-0.5 text-[10px] font-mono text-emerald-400/70">
            {biasMode.icon} {biasMode.label} · <span className="text-slate-500">{biasMode.description}</span>
          </p>
        </div>
        <span className={`inline-flex rounded-full border px-3 py-1 text-[11px] font-bold uppercase tracking-wider ${statusBadgeCls}`}>
          {isAligned ? "UYUMLU" : "SAPMA"}
        </span>
      </div>

      <div className="mb-5">
        <div className="mb-1.5 flex items-center justify-between">
          <span className="text-[11px] text-slate-400">Makro bias ve modul sinyali uyumu</span>
          <span className="font-mono text-sm font-bold text-white">{alignmentPct}%</span>
        </div>
        <div className="h-2 rounded-full bg-slate-700">
          <div className={`h-2 rounded-full ${barCls} transition-all duration-700`} style={{ width: `${alignmentPct}%` }} />
        </div>
        <p className="mt-1 text-[10px] text-slate-600">
          Bias: [{regimeBias.map((key) => key.toUpperCase()).join(", ")}] · {matchCount}/{total} sinyal uyumlu
        </p>
      </div>

      <div className="mb-5 grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-5">
        {rows.map(({ key, label, action, aligned }) => (
          <div
            key={key}
            className={`rounded-xl border p-2.5 text-center transition-colors ${
              aligned ? "border-emerald-500/20 bg-emerald-500/5" : "border-rose-500/20 bg-rose-500/5"
            }`}
          >
            <p className="truncate text-[9px] uppercase tracking-wider text-slate-500">{label}</p>
            <p className={`mt-0.5 font-mono text-[12px] font-bold ${actionClass[action] ?? "text-slate-300"}`}>
              {action}
            </p>
            <p className={`mt-0.5 text-[9px] ${aligned ? "text-emerald-600" : "text-rose-500"}`}>
              {aligned ? "uyumlu" : "sapma"}
            </p>
          </div>
        ))}
      </div>

      <div className="space-y-2 border-t border-slate-700/50 pt-4">
        <p className="mb-2.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          Final Onay Listesi
        </p>
        {checklistItems.map(({ label, note, status }) => (
          <div key={label} className="flex items-center gap-2">
            <span className={`h-2 w-2 shrink-0 rounded-full ${statusDot(status)}`} />
            <span className="text-[11px] text-slate-300">{label}</span>
            {note && <span className="text-[10px] text-slate-600">{note}</span>}
            <span className={`ml-auto text-[10px] font-semibold ${statusColor(status)}`}>{status}</span>
          </div>
        ))}
      </div>

      {vadeWarning && (
        <div className="mt-4 flex items-start gap-2 rounded-xl border border-amber-500/20 bg-amber-500/5 px-3 py-2.5">
          <span className="mt-0.5 shrink-0 text-amber-400">!</span>
          <p className="text-[10px] leading-4 text-amber-300">{vadeWarning}</p>
        </div>
      )}
    </div>
  );
};
