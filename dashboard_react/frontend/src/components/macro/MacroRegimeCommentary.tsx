/**
 * src/components/macro/MacroRegimeCommentary.tsx
 * Rejim badge + makro metriklerden türetilen 1-2 cümlelik AI yorum paneli.
 */

import React from "react";
import type { MacroViewModel } from "../../types/dashboardV2";
import { DataStatusBadge } from "../ui/DataStatusBadge";

interface Props {
  macro: MacroViewModel;
}

const REGIME_STYLE: Record<string, string> = {
  RISK_ON:      "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  LIQUIDITY:    "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  RISK_OFF:     "border-rose-500/40 bg-rose-500/10 text-rose-300",
  STAGFLATION:  "border-amber-500/40 bg-amber-500/10 text-amber-300",
  NORMALIZATION:"border-sky-500/40 bg-sky-500/10 text-sky-300",
};

const getRegimeStyle = (regime: string): string => {
  for (const key of Object.keys(REGIME_STYLE)) {
    if (regime.includes(key)) return REGIME_STYLE[key];
  }
  return "border-slate-500/40 bg-slate-500/10 text-slate-300";
};

const deriveCommentary = (macro: MacroViewModel): string => {
  const { metrics, regime, hedge, macro_score } = macro;
  const sentences: string[] = [];

  // DXY signal
  if (metrics.dxy >= 105) {
    sentences.push(
      `DXY ${metrics.dxy.toFixed(1)} ile güçlü dolar ortamı; risk varlıklarında satış baskısı gözleniyor.`
    );
  } else if (metrics.dxy < 100) {
    sentences.push(
      `DXY ${metrics.dxy.toFixed(1)} ile zayıf dolar; BTC ve emtia için destekleyici ortam oluşuyor.`
    );
  } else {
    sentences.push(`DXY ${metrics.dxy.toFixed(1)} nötr bölgede seyrediyor.`);
  }

  // VIX + Brent + XAU narrative
  if (metrics.vix >= 25) {
    sentences.push(
      `VIX ${metrics.vix.toFixed(1)} ile volatilite yüksek — pozisyon büyüklükleri kısıtlanmalı.`
    );
  } else if (regime.includes("STAG") && metrics.brent >= 85) {
    sentences.push(
      `Brent ${metrics.brent.toFixed(1)}$ stagflasyon baskısını teyit ediyor; emtia varlıkları öne çıkıyor.`
    );
  } else if (metrics.xau >= 2400) {
    sentences.push(
      `Altın ${Math.round(metrics.xau).toLocaleString()}$ ile jeopolitik risk primini fiyatlıyor.`
    );
  } else if (macro_score > 0.25) {
    sentences.push(
      `Makro kompozit skor pozitif (${macro_score >= 0 ? "+" : ""}${macro_score.toFixed(3)}); orta vadeli risk-on giriş koşulları uygun.`
    );
  } else if (macro_score < -0.15) {
    sentences.push(
      `Makro skor negatif bölgede (${macro_score.toFixed(3)}); savunmacı dağılım ve hedge önceliklendiriliyor.`
    );
  } else {
    sentences.push(
      `Makro skor dengede (${macro_score >= 0 ? "+" : ""}${macro_score.toFixed(3)}); bekleme modu devam ediyor.`
    );
  }

  if (hedge) {
    sentences.push("Hedge aktif: altın ve tahvil ağırlığı artırılmış, BTC pozisyonu daraltılmış.");
  }

  return sentences.slice(0, 2).join(" ");
};

const METRIC_ROWS = [
  { key: "dxy",               label: "DXY",    fmt: (v: number) => v.toFixed(1) },
  { key: "vix",               label: "VIX",    fmt: (v: number) => v.toFixed(1) },
  { key: "us10y",             label: "US10Y",  fmt: (v: number) => `${v.toFixed(2)}%` },
  { key: "brent",             label: "Brent",  fmt: (v: number) => `$${v.toFixed(1)}` },
  { key: "xau",               label: "XAU",    fmt: (v: number) => `$${Math.round(v).toLocaleString()}` },
  { key: "btc_d",             label: "BTC.D",  fmt: (v: number) => `${v.toFixed(1)}%` },
  { key: "usdt_d",            label: "USDT.D", fmt: (v: number) => `${v.toFixed(1)}%` },
  { key: "event_risk_score",  label: "EvRisk", fmt: (v: number) => `${(v * 100).toFixed(0)}%` },
] as const;

export const MacroRegimeCommentary: React.FC<Props> = ({ macro }) => {
  const fallbackFieldSet = new Set(macro.fallback_fields ?? []);
  const liveVerifiedMacro =
    macro.data_status === "LIVE" &&
    macro.verified === true &&
    macro.live === true;
  const partialFallback = macro.data_status === "PARTIAL_FALLBACK";
  const fallbackLike = macro.data_status === "FALLBACK";
  const commentary = liveVerifiedMacro
    ? deriveCommentary(macro)
    : partialFallback
      ? "NOT FULLY VERIFIED. Some macro fields are fallback values, so live macro commentary is intentionally disabled."
      : fallbackLike
        ? "FALLBACK DATA. Live macro commentary is intentionally disabled because the macro payload is not verified."
        : "NOT VERIFIED. Live macro commentary is intentionally disabled until macro data is fully verified.";
  const commentaryTitle = liveVerifiedMacro
    ? "AI Makro Yorumu"
    : partialFallback
      ? "NOT FULLY VERIFIED"
      : fallbackLike
        ? "FALLBACK"
        : "NOT VERIFIED";
  const sourceLabel = macro.source?.trim() || "unknown";

  return (
    <div className="rounded-2xl border border-slate-700/60 bg-slate-900 p-5 shadow-md shadow-slate-950/20
      transition-all duration-300 hover:border-slate-600">
      {/* Header row */}
      <div className="flex flex-wrap items-center gap-2.5 mb-3">
        <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">
          Makro Rejim
        </p>
        <span
          className={`inline-flex rounded-full border px-3 py-1 text-[11px] font-bold uppercase tracking-widest ${getRegimeStyle(macro.regime)}`}
        >
          {macro.regime}
        </span>
        <span className="font-mono text-[11px] text-slate-500">
          Skor: {macro.macro_score >= 0 ? "+" : ""}{macro.macro_score.toFixed(3)}
        </span>
        {macro.hedge && !liveVerifiedMacro && (
          <span className="inline-flex rounded-full border border-amber-500/40 bg-amber-500/10 px-2.5 py-0.5 text-[10px] font-semibold text-amber-200">
            HEDGE UNVERIFIED
          </span>
        )}
        {macro.hedge && liveVerifiedMacro && macro.hedge_unverified && (
          <span className="inline-flex rounded-full border border-amber-500/40 bg-amber-500/10 px-2.5 py-0.5 text-[10px] font-semibold text-amber-200">
            HEDGE UNVERIFIED
          </span>
        )}
        {macro.hedge && liveVerifiedMacro && !macro.hedge_unverified && (
          <span className="inline-flex rounded-full border border-amber-500/40 bg-amber-500/10 px-2.5 py-0.5 text-[10px] font-semibold text-amber-300">
            HEDGE ON
          </span>
        )}
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <DataStatusBadge data={macro} compact showDetails={false} />
        {partialFallback && (
          <span className="inline-flex rounded-full border border-amber-500/40 bg-amber-500/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-amber-100">
            PARTIAL FALLBACK DATA
          </span>
        )}
        {!liveVerifiedMacro && (
          <span className="inline-flex rounded-full border border-rose-500/30 bg-rose-500/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-rose-100">
            {partialFallback ? "NOT FULLY VERIFIED" : fallbackLike ? "FALLBACK" : "NOT VERIFIED"}
          </span>
        )}
        <span className="inline-flex rounded-full border border-slate-600 bg-slate-800 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-300">
          SOURCE: {sourceLabel}
        </span>
      </div>

      {macro.warning && (
        <div className="mb-4 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-100">
          {macro.warning}
        </div>
      )}

      {fallbackFieldSet.size > 0 && (
        <div className="mb-4">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-amber-300">
            Field-Level Fallback
          </p>
          <div className="flex flex-wrap gap-2">
            {METRIC_ROWS.filter(({ key }) => fallbackFieldSet.has(key)).map(({ key, label }) => (
              <span
                key={key}
                className="inline-flex rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-amber-100"
              >
                {label} fallback
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Commentary block */}
      <div className="bg-slate-800/50 border-l-4 border-blue-400 rounded-r-lg px-4 py-3 mb-4">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-blue-400 mb-1">
          {commentaryTitle}
        </p>
        <p className="text-xs italic leading-5 text-slate-300">{commentary}</p>
      </div>

      {/* Metric chips */}
      <div className="grid grid-cols-4 gap-2 sm:grid-cols-8">
        {METRIC_ROWS.map(({ key, label, fmt }) => (
          <div key={key} className="text-center rounded-lg bg-slate-800/40 px-2 py-1.5">
            <p className="text-[9px] uppercase tracking-widest text-slate-600">{label}</p>
            <p className="font-mono text-[11px] font-semibold text-slate-200">
              {fmt(macro.metrics[key as keyof typeof macro.metrics])}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
};
