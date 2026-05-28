/**
 * ConsensusGauge — Premium consensus display with:
 *  - 5-module contribution bars
 *  - Final score arc gauge
 *  - Green Light 8-criteria checklist
 *  - Attribution breakdown
 *
 * Data: SSE /api/live-feed → consensus field.
 */
import React from "react";
import {
  RadialBarChart,
  RadialBar,
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
} from "recharts";

export interface ConsensusPayload {
  action: "BUY" | "SELL" | "HOLD";
  green_light: boolean;
  confidence: number;
  five_module_score: number;
  module_scores: Record<string, number>;
  module_weights: Record<string, number>;
  criteria: Record<string, boolean>;
  failed_criteria: string[];
  cbr: {
    is_historical_weak?: boolean;
    sample_count?: number;
    win_rate_pct?: number;
    reason?: string;
  };
  multi_tf?: { is_valid: boolean; final_signal: string; reason: string };
  sentinel?: { risk_multiplier: number };
  position_size: number;
}

interface ConsensusGaugeProps {
  data: ConsensusPayload;
}

const MODULE_COLORS: Record<string, string> = {
  touche: "#3B82F6",
  fundamental: "#10B981",
  news: "#EC4899",
  sentinel: "#F59E0B",
  quantum: "#8B5CF6",
};

const CRITERIA_LABELS: Record<string, string> = {
  regime_suitable: "Regime Suitable",
  dynamic_threshold_pass: "Dynamic Threshold",
  modules_agree_3plus: "3+ Modules Agree",
  multi_tf_aligned: "Multi-TF Aligned",
  cbr_edge_valid: "CBR Edge Valid",
  liquidity_ok: "Liquidity OK",
  risk_multiplier_ok: "Risk Multiplier OK",
  event_risk_ok: "Event Risk OK",
};

export const ConsensusGauge: React.FC<ConsensusGaugeProps> = ({ data }) => {
  const score = Math.round((data.five_module_score ?? 0.5) * 100);
  const actionColor =
    data.action === "BUY"
      ? "#10B981"
      : data.action === "SELL"
      ? "#EF4444"
      : "#F59E0B";

  // Attribution bars
  const attributionData = Object.entries(data.module_scores ?? {}).map(
    ([module, score]) => ({
      module: module.charAt(0).toUpperCase() + module.slice(1),
      contribution: Math.round(
        score * (data.module_weights?.[module] ?? 0) * 100
      ),
      score: Math.round(score * 100),
    })
  );

  // Radial gauge data
  const gaugeData = [{ value: score, fill: actionColor }];

  return (
    <div className="rounded-xl border border-gray-700 bg-gray-900/60 p-4 flex flex-col gap-4">
      <p className="text-xs uppercase tracking-widest text-gray-400">
        Consensus Signal
      </p>

      {/* Top row: gauge + action */}
      <div className="flex items-center gap-4">
        <div className="relative w-32 h-32 flex-shrink-0">
          <ResponsiveContainer width="100%" height="100%">
            <RadialBarChart
              cx="50%"
              cy="50%"
              innerRadius="60%"
              outerRadius="90%"
              startAngle={180}
              endAngle={0}
              data={gaugeData}
            >
              <RadialBar
                dataKey="value"
                cornerRadius={6}
                background={{ fill: "#374151" }}
              />
            </RadialBarChart>
          </ResponsiveContainer>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-2xl font-bold" style={{ color: actionColor }}>
              {score}
            </span>
            <span className="text-xs text-gray-400">/ 100</span>
          </div>
        </div>

        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span
              className="text-3xl font-extrabold"
              style={{ color: actionColor }}
            >
              {data.action}
            </span>
            {data.green_light ? (
              <span className="text-xs bg-green-800 text-green-300 px-2 py-0.5 rounded-full">
                🟢 GREEN LIGHT
              </span>
            ) : (
              <span className="text-xs bg-red-900/50 text-red-400 px-2 py-0.5 rounded-full">
                🔴 GATED
              </span>
            )}
          </div>
          <p className="text-sm text-gray-400 mt-1">
            Confidence:{" "}
            <span className="text-white font-semibold">
              {Math.round(data.confidence * 100)}%
            </span>
          </p>
          <p className="text-sm text-gray-400">
            Position:{" "}
            <span className="text-white font-semibold">
              {((data.position_size ?? 0) * 100).toFixed(1)}%
            </span>
            {data.cbr?.is_historical_weak && (
              <span className="ml-2 text-xs text-yellow-400">
                ⚠ CBR Weak (−20%)
              </span>
            )}
          </p>
        </div>
      </div>

      {/* Attribution bars */}
      <div>
        <p className="text-xs text-gray-500 mb-2">Module Contribution</p>
        <div className="h-32">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={attributionData}
              layout="vertical"
              margin={{ left: 0, right: 10, top: 0, bottom: 0 }}
            >
              <XAxis type="number" domain={[0, 50]} hide />
              <YAxis
                dataKey="module"
                type="category"
                width={70}
                tick={{ fontSize: 11, fill: "#9CA3AF" }}
              />
              <Tooltip
                formatter={(v: number) => [`${v}pt`, "Contribution"]}
                contentStyle={{
                  background: "#1F2937",
                  border: "1px solid #374151",
                  borderRadius: "8px",
                }}
              />
              <Bar dataKey="contribution" radius={[0, 4, 4, 0]}>
                {attributionData.map((entry, i) => (
                  <Cell
                    key={i}
                    fill={
                      MODULE_COLORS[entry.module.toLowerCase()] ?? "#6B7280"
                    }
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Green Light checklist */}
      <div>
        <p className="text-xs text-gray-500 mb-2">Green Light Criteria</p>
        <div className="grid grid-cols-2 gap-1">
          {Object.entries(CRITERIA_LABELS).map(([key, label]) => {
            const pass = data.criteria?.[key] ?? false;
            return (
              <div key={key} className="flex items-center gap-1.5">
                <span
                  className={`text-sm ${pass ? "text-green-400" : "text-red-400"}`}
                >
                  {pass ? "✓" : "✗"}
                </span>
                <span
                  className={`text-xs ${pass ? "text-gray-300" : "text-gray-500"}`}
                >
                  {label}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* CBR context */}
      {data.cbr && (
        <div className="border-t border-gray-700 pt-2 text-xs text-gray-500 flex gap-4">
          <span>
            CBR Samples:{" "}
            <span className="text-gray-300">{data.cbr.sample_count ?? 0}</span>
          </span>
          <span>
            Win Rate:{" "}
            <span className="text-gray-300">
              {(data.cbr.win_rate_pct ?? 0).toFixed(1)}%
            </span>
          </span>
          {data.cbr.is_historical_weak && (
            <span className="text-yellow-400">Historical Weak Mode</span>
          )}
        </div>
      )}
    </div>
  );
};
