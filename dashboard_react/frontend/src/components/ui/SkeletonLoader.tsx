/**
 * components/ui/SkeletonLoader.tsx
 * AEGIS v7.0 — Reusable skeleton placeholder
 * Variants: "lines" (default), "card", "bar-chart", "stat"
 * All animate-pulse; width/height matches real card shapes.
 */

import React from "react";

type SkeletonVariant = "lines" | "card" | "bar-chart" | "stat";

interface SkeletonLoaderProps {
  lines?: number;
  className?: string;
  compact?: boolean;
  variant?: SkeletonVariant;
}

const Pulse: React.FC<{ className: string; style?: React.CSSProperties }> = ({ className, style }) => (
  <div className={`animate-pulse rounded-md bg-slate-700/50 ${className}`} style={style} />
);

const LinesVariant: React.FC<{ lines: number; compact: boolean }> = ({ lines, compact }) => (
  <div className={`rounded-2xl border border-slate-700/50 bg-slate-900/80 ${compact ? "p-3" : "p-4"}`}>
    <Pulse className={compact ? "h-2.5 w-16" : "h-3 w-24"} />
    <div className="mt-3 space-y-2">
      {Array.from({ length: lines }).map((_, i) => (
        <Pulse key={i} className={compact ? "h-2" : "h-2.5"} style={{ width: `${92 - i * 9}%` } as React.CSSProperties} />
      ))}
    </div>
  </div>
);

const BarChartVariant: React.FC<{ lines: number }> = ({ lines }) => (
  <div className="rounded-2xl border border-slate-700/50 bg-slate-900/80 p-4">
    <Pulse className="h-3 w-24 mb-4" />
    <div className="space-y-3">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="flex items-center gap-3">
          <Pulse className="h-2.5 w-14" />
          <div className="flex-1 h-2 rounded-full bg-slate-700/50 animate-pulse" style={{ opacity: 0.5 + i * 0.1 } as React.CSSProperties} />
          <Pulse className="h-2.5 w-8" />
        </div>
      ))}
    </div>
  </div>
);

const StatVariant: React.FC = () => (
  <div className="rounded-2xl border border-slate-700/50 bg-slate-900/80 p-4">
    <Pulse className="h-2.5 w-16 mb-3" />
    <Pulse className="h-8 w-24 mb-2" />
    <Pulse className="h-2 w-20" />
  </div>
);

const CardVariant: React.FC<{ lines: number }> = ({ lines }) => (
  <div className="rounded-2xl border border-slate-700/50 bg-slate-900/80 p-5">
    <div className="flex items-start justify-between mb-4">
      <div>
        <Pulse className="h-2.5 w-20 mb-2" />
        <Pulse className="h-6 w-32" />
      </div>
      <Pulse className="h-10 w-20 rounded-xl" />
    </div>
    <div className="grid gap-2 grid-cols-3 mb-4">
      {[0, 1, 2].map((i) => <Pulse key={i} className="h-14 rounded-xl" />)}
    </div>
    <div className="space-y-2">
      {Array.from({ length: lines }).map((_, i) => (
        <Pulse key={i} className="h-2.5" style={{ width: `${85 - i * 8}%` } as React.CSSProperties} />
      ))}
    </div>
  </div>
);

export const SkeletonLoader: React.FC<SkeletonLoaderProps> = ({
  lines = 3,
  className = "",
  compact = false,
  variant = "lines",
}) => {
  const inner =
    variant === "bar-chart" ? <BarChartVariant lines={lines} /> :
    variant === "stat"      ? <StatVariant /> :
    variant === "card"      ? <CardVariant lines={lines} /> :
    <LinesVariant lines={lines} compact={compact} />;

  return <div className={className}>{inner}</div>;
};
