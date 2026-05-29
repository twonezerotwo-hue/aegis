import React from "react";
import { SystemHealth } from "../types";
import { DataStatusBadge } from "./ui/DataStatusBadge";

interface SystemStatusProps {
  health: SystemHealth;
  /** 0-1 sentinel score (inverted event risk). undefined = not yet loaded. */
  sentinelScore?: number;
  /** 0-1 quantum score. undefined = not yet loaded. */
  quantumScore?: number;
}

// ── Signal badges for background-only modules ─────────────────────────────────

interface SignalBadge {
  label: string;
  cls: string;
}

const sentinelBadge = (score: number | undefined): SignalBadge => {
  if (score === undefined) return { label: "—", cls: "text-slate-500" };
  if (score >= 0.55) return { label: "✓ Düşük Risk", cls: "text-emerald-400" };
  if (score >= 0.45) return { label: "~ Orta Risk",  cls: "text-amber-400"   };
  return              { label: "✗ Yüksek Risk",       cls: "text-rose-400"    };
};

const quantumBadge = (score: number | undefined): SignalBadge => {
  if (score === undefined)            return { label: "—",              cls: "text-slate-500"   };
  if (Math.abs(score - 0.5) < 0.01)  return { label: "~ Veri Yok",    cls: "text-slate-500"   };
  if (score >= 0.55)                  return { label: "✓ Likidite İyi", cls: "text-emerald-400" };
  if (score >= 0.45)                  return { label: "~ Nötr",         cls: "text-amber-400"   };
  return                                     { label: "✗ Düşük Likidite", cls: "text-rose-400"  };
};

const BACKGROUND_MODULES = new Set(["sentinel", "quantum"]);

export const SystemStatus: React.FC<SystemStatusProps> = ({
  health,
  sentinelScore,
  quantumScore,
}) => {
  const getStatusColor = (status: string) =>
    status === "UP"
      ? "bg-green-500 bg-opacity-20 text-green-300"
      : "bg-red-500 bg-opacity-20 text-red-300";

  const getOverallStatusColor = (status: string) =>
    status === "healthy" ? "text-green-400"
    : status === "degraded" ? "text-yellow-400"
    : status === "down" ? "text-red-400"
    : "text-gray-400";

  const sentinel = sentinelBadge(sentinelScore);
  const quantum  = quantumBadge(quantumScore);

  return (
    <div className="metric-card">
      <p className="metric-label">System Status</p>
      <div className="mt-3">
        <DataStatusBadge data={health} />
      </div>
      <div className="mt-4">
        <div className="flex items-center justify-between">
          <div>
            <p className={`text-2xl font-bold uppercase ${getOverallStatusColor(health.overall_status)}`}>
              {health.overall_status}
            </p>
            <p className="text-xs text-gray-500">
              {health.up_count}/{health.total_count} services online
            </p>
          </div>
          <div className="text-right">
            <p className="text-3xl font-bold text-cyan-400">{health.up_count}</p>
          </div>
        </div>

        <div className="mt-4 space-y-2 border-t border-gray-700 pt-4">
          {Object.entries(health.services).map(([service, status]) => {
            const isBackground = BACKGROUND_MODULES.has(service);
            const signal =
              service === "sentinel" ? sentinel
              : service === "quantum"  ? quantum
              : null;

            return (
              <div
                key={service}
                className="flex items-center justify-between rounded bg-gray-800 bg-opacity-50 p-2"
              >
                <div className="flex items-center gap-2">
                  <span className="capitalize text-gray-300">{service}</span>
                  {isBackground && (
                    <span className="text-[9px] uppercase tracking-wider text-slate-600">
                      arka plan
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {signal && (
                    <span className={`text-[10px] font-semibold ${signal.cls}`}>
                      {signal.label}
                    </span>
                  )}
                  <span className={`inline-block rounded px-2 py-1 text-xs font-medium ${getStatusColor(status)}`}>
                    {status}
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Explanation note */}
        <p className="mt-3 text-[9px] leading-4 text-slate-600">
          Sentinel (makro risk filtresi) ve Quantum (likidite kalitesi) consensus
          sinyaline girmez — arka planda çalışır, yalnız uyarı üretir.
        </p>
      </div>
    </div>
  );
};
