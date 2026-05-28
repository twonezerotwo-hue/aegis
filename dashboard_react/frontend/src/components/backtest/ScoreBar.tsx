/**
 * components/backtest/ScoreBar.tsx
 * AEGIS v7.3 — Reusable horizontal score bar for module scores
 * Shows 0–100 scale with animated fill and label
 */
import React from "react";

interface ScoreBarProps {
  value: number;       // 0.0 – 1.0
  label: string;
  color?: string;      // tailwind bg class or hex
  showPercent?: boolean;
}

export const ScoreBar: React.FC<ScoreBarProps> = ({
  value,
  label,
  color = "#3b82f6",
  showPercent = true,
}) => {
  const pct = Math.min(100, Math.max(0, value * 100));
  const isHex = color.startsWith("#");

  return (
    <div className="flex items-center gap-3 group" role="meter" aria-label={label} aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
      <span className="w-28 text-sm font-medium text-slate-300 truncate">{label}</span>
      <div className="flex-1 h-2.5 rounded-full bg-slate-700/60 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ease-out ${!isHex ? color : ""}`}
          style={{
            width: `${pct}%`,
            ...(isHex ? { backgroundColor: color } : {}),
          }}
        />
      </div>
      {showPercent && (
        <span className="w-12 text-right text-sm font-mono text-slate-400 tabular-nums">
          {pct.toFixed(0)}%
        </span>
      )}
    </div>
  );
};
