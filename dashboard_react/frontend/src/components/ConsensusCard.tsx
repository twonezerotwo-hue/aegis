import React from "react";
import { ConsensusData } from "../types";
import { PieChart, Pie, Cell, ResponsiveContainer, Legend } from "recharts";
import { DataStatusBadge } from "./ui/DataStatusBadge";

interface ConsensusCardProps {
  data: ConsensusData;
}

export const ConsensusCard: React.FC<ConsensusCardProps> = ({ data }) => {
  const getActionColor = (action: string) => {
    switch (action) {
      case "BUY":
        return "text-green-400";
      case "SELL":
        return "text-red-400";
      case "HOLD":
        return "text-yellow-400";
      default:
        return "text-gray-400";
    }
  };

  const chartData = [
    { name: "Touche", value: data.weights.touche * 100 },
    { name: "Fundamental", value: data.weights.fundamental * 100 },
    { name: "News", value: data.weights.news * 100 },
  ];

  const COLORS = ["#3B82F6", "#10B981", "#EC4899"];

  return (
    <div className="metric-card col-span-full md:col-span-2 lg:col-span-3">
      <p className="metric-label">Consensus Signal</p>
      <div className="mt-3">
        <DataStatusBadge data={data} />
      </div>
      <div className="mt-4 grid gap-6 md:grid-cols-2">
        <div>
          <p className="mb-2 text-sm text-gray-400">3-Way Weighted Score</p>
          <p
            className="metric-value"
            style={{ color: data.weighted_score > 0.65 ? "#10B981" : data.weighted_score < 0.35 ? "#EF4444" : "#F59E0B" }}
          >
            {(data.weighted_score * 100).toFixed(2)}%
          </p>
          <p className={`mt-2 text-2xl font-bold ${getActionColor(data.action)}`}>
            {data.action}
          </p>
          <p className="text-xs text-gray-500">
            Confidence: {(data.confidence * 100).toFixed(1)}%
          </p>
        </div>
        <div>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie
                data={chartData}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={80}
                paddingAngle={2}
                dataKey="value"
              >
                {COLORS.map((color, index) => (
                  <Cell key={`cell-${index}`} fill={color} />
                ))}
              </Pie>
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2 border-t border-gray-700 pt-4">
        {Object.entries(data.components).map(([key, value]) => (
          <div key={key}>
            <p className="text-xs uppercase text-gray-500">{key}</p>
            <p className="font-semibold">{(value.score * 100).toFixed(1)}%</p>
            <p className="text-xs text-gray-400">{(value.weight * 100).toFixed(0)}% weight</p>
          </div>
        ))}
      </div>
    </div>
  );
};
