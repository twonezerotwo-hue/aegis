/**
 * src/components/ui/ExitSignalPanel.tsx
 * touche/exit_signal yanıtını gösterir.
 * FULL_CLOSE → kırmızı · PARTIAL_CLOSE → sarı · NONE → gri
 */

import React from "react";

export interface ExitSignal {
  signal: "FULL_CLOSE" | "PARTIAL_CLOSE" | "NONE";
  /** 0–100, kapatılacak pozisyon yüzdesi */
  percentage?: number;
  reason?: string;
  timestamp?: string;
}

interface Props {
  exitSignal: ExitSignal | null;
  /** If true renders a compact single-line chip instead of the full panel */
  compact?: boolean;
  className?: string;
}

type SignalStyle = {
  border: string;
  bg: string;
  header: string;
  badge: string;
  icon: string;
};

const SIGNAL_STYLES: Record<ExitSignal["signal"], SignalStyle> = {
  FULL_CLOSE: {
    border: "border-rose-500/50",
    bg: "bg-rose-500/10",
    header: "text-rose-300",
    badge: "border-rose-500/40 bg-rose-500/20 text-rose-300",
    icon: "🔴",
  },
  PARTIAL_CLOSE: {
    border: "border-amber-500/50",
    bg: "bg-amber-500/10",
    header: "text-amber-300",
    badge: "border-amber-500/40 bg-amber-500/20 text-amber-300",
    icon: "🟡",
  },
  NONE: {
    border: "border-slate-700/60",
    bg: "bg-slate-800/40",
    header: "text-slate-400",
    badge: "border-slate-600/50 bg-slate-700/30 text-slate-400",
    icon: "⚪",
  },
};

export const ExitSignalPanel: React.FC<Props> = ({
  exitSignal,
  compact = false,
  className = "",
}) => {
  if (!exitSignal) {
    return (
      <div
        className={`rounded-xl border border-slate-700/40 bg-slate-800/30 px-3 py-2
          text-[10px] text-slate-600 ${className}`}
      >
        Çıkış sinyali bekleniyor…
      </div>
    );
  }

  const s = SIGNAL_STYLES[exitSignal.signal];

  if (compact) {
    return (
      <span
        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5
          text-[10px] font-bold uppercase tracking-wider ${s.badge} ${className}`}
        aria-label={`Çıkış: ${exitSignal.signal}`}
      >
        <span aria-hidden="true">{s.icon}</span>
        {exitSignal.signal.replace("_", " ")}
        {exitSignal.percentage !== undefined && exitSignal.signal !== "NONE" && (
          <span className="font-mono">{exitSignal.percentage}%</span>
        )}
      </span>
    );
  }

  return (
    <section
      className={`rounded-2xl border ${s.border} ${s.bg} p-4 ${className}`}
      aria-label="Çıkış sinyali paneli"
    >
      {/* Header row */}
      <div className="flex items-center justify-between mb-3">
        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
          Çıkış Sinyali
        </p>
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5
            text-[10px] font-bold uppercase tracking-wider ${s.badge}`}
        >
          <span aria-hidden="true">{s.icon}</span>
          {exitSignal.signal.replace("_", " ")}
        </span>
      </div>

      {/* Percentage bar */}
      {exitSignal.percentage !== undefined && exitSignal.signal !== "NONE" && (
        <div className="mb-3">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[9px] uppercase tracking-wider text-slate-500">
              Kapatılacak Pozisyon
            </span>
            <span className={`font-mono text-sm font-bold ${s.header}`}>
              {exitSignal.percentage}%
            </span>
          </div>
          <div className="h-1.5 rounded-full bg-slate-700/60">
            <div
              className={`h-1.5 rounded-full transition-all duration-500 ${
                exitSignal.signal === "FULL_CLOSE" ? "bg-rose-400" : "bg-amber-400"
              }`}
              style={{ width: `${Math.min(100, exitSignal.percentage)}%` }}
              role="presentation"
            />
          </div>
        </div>
      )}

      {/* Reason */}
      {exitSignal.reason && (
        <p className="text-[10px] leading-4 text-slate-400 mt-1">
          <span className="font-semibold text-slate-300">Gerekçe:</span>{" "}
          {exitSignal.reason}
        </p>
      )}

      {/* Timestamp */}
      {exitSignal.timestamp && (
        <p className="mt-2 font-mono text-[9px] text-slate-600">
          {exitSignal.timestamp}
        </p>
      )}
    </section>
  );
};
