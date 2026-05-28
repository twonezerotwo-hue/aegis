/**
 * src/components/ui/RegimeBadge.tsx
 * Makro rejim etiketi — renk kodu + 12h tampon süresi tooltip.
 */

import React from "react";

interface Props {
  regime: string;
  /** Show 12-hour buffer time tooltip on hover (default: true) */
  showBufferTooltip?: boolean;
  className?: string;
}

type RegimeStyle = { bg: string; border: string; text: string; dot: string };

const REGIME_STYLES: Record<string, RegimeStyle> = {
  STAGFLATION: {
    bg: "bg-amber-500/15",
    border: "border-amber-500/40",
    text: "text-amber-300",
    dot: "bg-amber-400",
  },
  RISK_OFF: {
    bg: "bg-rose-500/15",
    border: "border-rose-500/40",
    text: "text-rose-300",
    dot: "bg-rose-400",
  },
  "LIQ.EXP": {
    bg: "bg-emerald-500/15",
    border: "border-emerald-500/40",
    text: "text-emerald-300",
    dot: "bg-emerald-400",
  },
  NORMAL: {
    bg: "bg-slate-500/15",
    border: "border-slate-500/40",
    text: "text-slate-300",
    dot: "bg-slate-400",
  },
};

const DEFAULT_STYLE: RegimeStyle = {
  bg: "bg-slate-700/20",
  border: "border-slate-600/40",
  text: "text-slate-400",
  dot: "bg-slate-500",
};

function resolveStyle(regime: string): RegimeStyle {
  // Exact match first, then prefix match
  if (REGIME_STYLES[regime]) return REGIME_STYLES[regime];
  for (const key of Object.keys(REGIME_STYLES)) {
    if (regime.startsWith(key)) return REGIME_STYLES[key];
  }
  return DEFAULT_STYLE;
}

export const RegimeBadge: React.FC<Props> = ({
  regime,
  showBufferTooltip = true,
  className = "",
}) => {
  const [tooltipVisible, setTooltipVisible] = React.useState(false);
  const s = resolveStyle(regime.toUpperCase());

  return (
    <div
      className={`relative inline-flex items-center gap-1.5 ${className}`}
      onMouseEnter={() => showBufferTooltip && setTooltipVisible(true)}
      onMouseLeave={() => setTooltipVisible(false)}
    >
      <span
        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5
          text-[10px] font-bold uppercase tracking-wider select-none
          ${s.bg} ${s.border} ${s.text}`}
        aria-label={`Rejim: ${regime}`}
      >
        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${s.dot}`} aria-hidden="true" />
        {regime}
      </span>

      {/* 12h buffer tooltip */}
      {tooltipVisible && (
        <div
          role="tooltip"
          className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50
            whitespace-nowrap rounded-lg border border-slate-700/80 bg-slate-900
            px-2.5 py-1.5 text-[10px] text-slate-300 shadow-xl shadow-slate-950/60
            pointer-events-none"
        >
          <span className="font-semibold text-slate-200">12h tampon süresi</span>
          <br />
          Rejim değişimi onaylanmadan işlem yapılmaz.
          {/* Arrow */}
          <span
            className="absolute top-full left-1/2 -translate-x-1/2 -mt-px
              border-4 border-transparent border-t-slate-700/80"
            aria-hidden="true"
          />
        </div>
      )}
    </div>
  );
};
