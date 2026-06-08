/**
 * MacroRegimeCommentary — kompakt makro bağlam paneli.
 *
 * Gösterir: Rejim badge | Skor | Veri durumu | AI yorumu (1-2 cümle)
 * Göstermez: Ham metrik tablosu (DXY/VIX/XAU/… Kontrol Merkezi'nde zaten var)
 */

import React from "react";
import type { MacroViewModel } from "../../types/dashboardV2";
import { DataStatusBadge } from "../ui/DataStatusBadge";

interface Props {
  macro: MacroViewModel;
}

// ── Rejim renk eşlemesi ───────────────────────────────────────────────────────
const REGIME_CLS: Record<string, string> = {
  RISK_ON:       "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  LIQUIDITY:     "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  RISK_OFF:      "border-rose-500/40    bg-rose-500/10    text-rose-300",
  STAGFLATION:   "border-amber-500/40   bg-amber-500/10   text-amber-300",
  NORMALIZATION: "border-sky-500/40     bg-sky-500/10     text-sky-300",
  ACCUMULATION:  "border-violet-500/40  bg-violet-500/10  text-violet-300",
};

const regimeCls = (regime: string): string => {
  for (const key of Object.keys(REGIME_CLS)) {
    if (regime.toUpperCase().includes(key)) return REGIME_CLS[key];
  }
  return "border-slate-500/40 bg-slate-500/10 text-slate-300";
};

// ── Türkçe yorumu türet ───────────────────────────────────────────────────────
const deriveCommentary = (macro: MacroViewModel): string => {
  const { metrics, regime, hedge, macro_score } = macro;
  const lines: string[] = [];

  // Cümle 1: Dolar + risk varlığı
  if (metrics.dxy >= 105) {
    lines.push(`DXY ${metrics.dxy.toFixed(1)} ile güçlü dolar; risk varlıklarında satış baskısı.`);
  } else if (metrics.dxy < 100) {
    lines.push(`DXY ${metrics.dxy.toFixed(1)} ile zayıf dolar; BTC ve emtia için destekleyici ortam.`);
  } else {
    lines.push(`DXY ${metrics.dxy.toFixed(1)} nötr bölgede seyrediyor.`);
  }

  // Cümle 2: VIX / Altın / Brent / Makro skor
  if (metrics.vix >= 25) {
    lines.push(`VIX ${metrics.vix.toFixed(1)} — volatilite yüksek, pozisyon büyüklükleri kısıtlanmalı.`);
  } else if (regime.toUpperCase().includes("STAG") && metrics.brent >= 85) {
    lines.push(`Brent ${metrics.brent.toFixed(1)}$ stagflasyon baskısını teyit ediyor.`);
  } else if (metrics.xau >= 2400) {
    lines.push(`Altın ${Math.round(metrics.xau).toLocaleString()}$ — jeopolitik risk primi fiyatlanıyor.`);
  } else if (macro_score > 0.25) {
    lines.push(`Makro kompozit skor pozitif (+${macro_score.toFixed(3)}); orta vadeli giriş koşulları uygun.`);
  } else if (macro_score < -0.15) {
    lines.push(`Makro skor negatif (${macro_score.toFixed(3)}); savunmacı pozisyon öneriliyor.`);
  } else {
    lines.push(`Makro skor dengede (${macro_score >= 0 ? "+" : ""}${macro_score.toFixed(3)}); bekleme modu devam ediyor.`);
  }

  if (hedge) {
    lines.push("Hedge aktif — altın ve tahvil ağırlığı artırılmış, BTC daraltılmış.");
  }

  return lines.slice(0, 2).join(" ");
};

// ── Bileşen ───────────────────────────────────────────────────────────────────
export const MacroRegimeCommentary: React.FC<Props> = ({ macro }) => {
  const liveVerifiedMacro =
    macro.data_status === "LIVE" && macro.verified === true && macro.live === true;
  const isLive = liveVerifiedMacro;
  const isPartial = macro.data_status === "PARTIAL_FALLBACK";
  // live macro commentary is intentionally disabled unless macro data is verified.

  const commentary = isLive
    ? deriveCommentary(macro)
    : isPartial
      ? "Bazı makro alanlar fallback veriye dayanıyor — yorum kısmi doğrulukta."
      : "Makro veri henüz doğrulanmadı — portföy tahminlere dayalı.";

  return (
    <div className="rounded-2xl border border-slate-700/60 bg-slate-900 px-5 py-4 shadow-md transition-all duration-300 hover:border-slate-600">
      {/* Tek satır: rejim + skor + durum */}
      <div className="flex flex-wrap items-center gap-2.5">
        <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">
          Makro Rejim
        </p>

        {/* Rejim badge */}
        <span className={`inline-flex rounded-full border px-3 py-1 text-[11px] font-bold uppercase tracking-widest ${regimeCls(macro.regime)}`}>
          {macro.regime}
        </span>

        {/* Skor */}
        <span className="font-mono text-[11px] text-slate-500">
          {macro.macro_score >= 0 ? "+" : ""}{macro.macro_score.toFixed(3)}
        </span>

        {/* Veri durumu */}
        <DataStatusBadge data={macro} compact showDetails={false} />

        {!liveVerifiedMacro && (
          <span className="inline-flex rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[9px] font-semibold text-amber-300">
            NOT FULLY VERIFIED
          </span>
        )}

        {/* Hedge badge — sadece aktifse */}
        {macro.hedge && isLive && !macro.hedge_unverified && (
          <span className="inline-flex rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[9px] font-semibold text-amber-300">
            HEDGE ON
          </span>
        )}
      </div>

      {/* Makro uyarısı (gerekliyse) */}
      {macro.warning && !isLive && (
        <p className="mt-2 text-[10px] text-amber-400/80">{macro.warning}</p>
      )}

      {/* AI yorumu */}
      <p className="mt-3 text-xs italic leading-5 text-slate-400">
        {commentary}
      </p>
    </div>
  );
};
