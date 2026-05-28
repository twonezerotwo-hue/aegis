/**
 * RegimeBadge — Shows current market regime with color coding + allocation pie.
 *
 * Data fed from SSE /api/live-feed → regime, regime_allocation fields.
 */
import React from "react";
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

export interface RegimeInfo {
  regime: string;
  event_risk_score: number;
  hours_to_event: number;
  allocation: Record<string, number>;
}

interface RegimeBadgeProps {
  regimeInfo: RegimeInfo;
}

const REGIME_STYLES: Record<
  string,
  { bg: string; border: string; text: string; label: string }
> = {
  LIQUIDITY_EXPANSION: {
    bg: "bg-green-900/40",
    border: "border-green-500",
    text: "text-green-300",
    label: "Liquidity Expansion",
  },
  NORMALIZATION: {
    bg: "bg-blue-900/40",
    border: "border-blue-500",
    text: "text-blue-300",
    label: "Normalization",
  },
  STAGFLATION: {
    bg: "bg-yellow-900/40",
    border: "border-yellow-500",
    text: "text-yellow-300",
    label: "Stagflation",
  },
  RISK_OFF: {
    bg: "bg-red-900/40",
    border: "border-red-500",
    text: "text-red-300",
    label: "Risk Off",
  },
};

const PIE_COLORS = ["#F59E0B", "#3B82F6", "#10B981", "#6B7280"];

export const RegimeBadge: React.FC<RegimeBadgeProps> = ({ regimeInfo }) => {
  const style =
    REGIME_STYLES[regimeInfo.regime] ?? REGIME_STYLES["NORMALIZATION"];
  const riskPct = Math.round(regimeInfo.event_risk_score * 100);

  const pieData = Object.entries(regimeInfo.allocation).map(([k, v]) => ({
    name: k,
    value: v,
  }));

  return (
    <div
      className={`rounded-xl border ${style.border} ${style.bg} p-4 flex flex-col gap-3`}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-widest text-gray-400">
            Market Regime
          </p>
          <p className={`text-2xl font-bold mt-1 ${style.text}`}>
            {style.label}
          </p>
        </div>
        <div className="text-right">
          <p className="text-xs text-gray-400">Event Risk</p>
          <p
            className={`text-xl font-bold ${
              riskPct > 40 ? "text-red-400" : "text-green-400"
            }`}
          >
            {riskPct}%
          </p>
          <p className="text-xs text-gray-500">
            {regimeInfo.hours_to_event}h to event
          </p>
        </div>
      </div>

      {/* Allocation Pie */}
      <div className="h-40">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={pieData}
              cx="50%"
              cy="50%"
              innerRadius={35}
              outerRadius={55}
              paddingAngle={2}
              dataKey="value"
            >
              {pieData.map((_, i) => (
                <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
              ))}
            </Pie>
            <Tooltip
              formatter={(v: number) => `${v}%`}
              contentStyle={{
                background: "#1F2937",
                border: "1px solid #374151",
                borderRadius: "8px",
              }}
            />
            <Legend
              formatter={(v) => (
                <span className="text-xs text-gray-300">{v}</span>
              )}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
