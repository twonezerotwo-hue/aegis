/**
 * src/components/ui/ConsensusGauge.tsx
 * SVG yarım daire gauge — 0-100 arası konsensüs skoru.
 * <48 kırmızı · 48-52 sarı · 52+ yeşil. Animasyonlu stroke-dasharray geçişi.
 */

import React from "react";

interface Props {
  /** 0–100 consensus score */
  score: number;
  /** Optional label below the score */
  label?: string;
  /** Diameter in px (default: 120) */
  size?: number;
  className?: string;
}

function scoreColor(score: number): { stroke: string; text: string } {
  if (score >= 52) return { stroke: "#34d399", text: "text-emerald-400" }; // emerald-400
  if (score >= 48) return { stroke: "#fbbf24", text: "text-amber-400" };   // amber-400
  return { stroke: "#fb7185", text: "text-rose-400" };                      // rose-400
}

export const ConsensusGauge: React.FC<Props> = ({
  score,
  label,
  size = 120,
  className = "",
}) => {
  const clamped = Math.min(100, Math.max(0, score));
  const { stroke, text } = scoreColor(clamped);

  // Half-circle geometry
  const strokeWidth = size * 0.085;
  const radius = (size - strokeWidth) / 2;
  const cx = size / 2;
  const cy = size / 2;

  // Semicircle arc: starts at 180° (left), sweeps clockwise to 0° (right)
  // circumference of a full circle; we use only the top half
  const fullArc = Math.PI * radius; // half circumference
  const fillArc = (clamped / 100) * fullArc;
  const emptyArc = fullArc - fillArc;

  // The SVG arc path for the top semicircle
  const trackD = `M ${strokeWidth / 2} ${cy} A ${radius} ${radius} 0 0 1 ${size - strokeWidth / 2} ${cy}`;

  return (
    <div
      className={`flex flex-col items-center gap-1 ${className}`}
      role="meter"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label ? `${label}: ${clamped}` : `Konsensüs skoru: ${clamped}`}
    >
      <svg
        width={size}
        height={size / 2 + strokeWidth}
        viewBox={`0 0 ${size} ${size / 2 + strokeWidth}`}
        overflow="visible"
        aria-hidden="true"
      >
        {/* Track (background arc) */}
        <path
          d={trackD}
          fill="none"
          stroke="rgba(100,116,139,0.25)"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
        />
        {/* Fill arc */}
        <path
          d={trackD}
          fill="none"
          stroke={stroke}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={`${fillArc} ${emptyArc + 1}`}
          style={{ transition: "stroke-dasharray 0.6s ease, stroke 0.4s ease" }}
        />
      </svg>

      {/* Score text */}
      <div className="flex flex-col items-center -mt-1">
        <span className={`font-mono text-2xl font-bold leading-none ${text}`}>
          {Math.round(clamped)}
        </span>
        {label && (
          <span className="mt-0.5 text-[9px] font-semibold uppercase tracking-wider text-slate-500">
            {label}
          </span>
        )}
      </div>
    </div>
  );
};
