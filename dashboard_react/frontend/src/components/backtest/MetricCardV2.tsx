/**
 * components/backtest/MetricCardV2.tsx
 * AEGIS v7.3 — Metric display card with trend indicator and color coding
 * PnL+ → emerald, PnL- → red, neutral → slate
 */
import React from "react";
import type { MetricTrend } from "../../types/backtestV2";

interface MetricCardV2Props {
  title: string;
  value: string;
  trend?: MetricTrend;
  subtitle?: string;
  icon?: string;
}

const TREND_STYLES: Record<MetricTrend, { text: string; bg: string; arrow: string }> = {
  up:      { text: "text-emerald-400", bg: "border-emerald-500/30", arrow: "↑" },
  down:    { text: "text-red-400",     bg: "border-red-500/30",     arrow: "↓" },
  neutral: { text: "text-slate-400",   bg: "border-slate-600/30",   arrow: "—" },
};

export const MetricCardV2: React.FC<MetricCardV2Props> = ({
  title,
  value,
  trend = "neutral",
  subtitle,
  icon,
}) => {
  const style = TREND_STYLES[trend];

  return (
    <div
      className={`rounded-xl border ${style.bg} bg-slate-900/80 p-4 backdrop-blur-sm
        transition-all duration-300 hover:shadow-lg hover:shadow-slate-900/50
        animate-[fadeSlideUp_0.4s_ease-out_forwards]`}
      role="group"
      aria-label={title}
    >
      <div className="flex items-center justify-between mb-1">
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
          {icon && <span className="mr-1">{icon}</span>}
          {title}
        </p>
        <span className={`text-xs font-bold ${style.text}`}>{style.arrow}</span>
      </div>
      <p className={`text-2xl font-bold font-mono tabular-nums ${style.text}`}>
        {value}
      </p>
      {subtitle && (
        <p className="mt-1 text-xs text-slate-500">{subtitle}</p>
      )}
    </div>
  );
};
