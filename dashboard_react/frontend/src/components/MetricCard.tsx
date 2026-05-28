import React, { useState } from "react";
import { Metric } from "../types";
import { DataStatusBadge } from "./ui/DataStatusBadge";

interface MetricCardProps {
  metric: Metric;
}

const getTooltipMessage = (metricName: string, score: number): string => {
  if (metricName.includes("Touche")) {
    if (score > 0.7) return "🟢 Teknik alım bölgesi (AL düşün)";
    if (score < 0.3) return "🔴 Teknik satım bölgesi (SAT düşün)";
    return "🟡 Kararsız bölge (BEKLE)";
  }
  if (metricName.includes("Fundamental")) {
    return score > 0.5
      ? "🟢 Blockchain ağı aktif, güvenli"
      : "⚠️ Blockchain ağı soğuk, dikkatli ol";
  }
  if (metricName.includes("Quantum")) {
    return score > 0.6
      ? "🟢 Likidite yüksek, işlem yapmak güvenli"
      : "⚠️ Likidite düşük, emirleri parçala";
  }
  if (metricName.includes("Sentinel")) {
    if (score > 0.7) return "🔴 Piyasa riskli (VIX yüksek) → BEKLE";
    if (score < 0.3) return "🟢 Piyasa sakin, işlem için uygun";
    return "🟡 Normal risk seviyesi, dikkatli kal";
  }
  if (metricName.includes("News")) {
    if (score > 0.6) return "🟢 Haberler olumlu, AL destek";
    if (score < 0.4) return "🔴 Haberler olumsuz, SAT destek";
    return "🟡 Haberler kararsız";
  }
  return "Metrik hakkında bilgi yok";
};

export const MetricCard: React.FC<MetricCardProps> = ({ metric }) => {
  const [showTooltip, setShowTooltip] = useState(false);

  const getStatusClass = (health: string) => {
    switch (health) {
      case "healthy": return "status-healthy";
      case "warning":  return "status-warning";
      case "down":     return "status-down";
      default:         return "status-warning";
    }
  };

  const getTrendIcon = (score: number) => {
    if (score > 0.7) return "↑";
    if (score < 0.4) return "↓";
    return "→";
  };

  const tooltipMessage = getTooltipMessage(metric.name, metric.score);

  return (
    <div className="metric-card" style={{ borderLeftColor: metric.color }}>
      <div className="border-l-4 pl-4" style={{ borderLeftColor: metric.color }}>
        {/* Header */}
        <div className="flex items-center justify-between">
          <p className="metric-label">{metric.name}</p>
          <div
            className="relative inline-block"
            onMouseEnter={() => setShowTooltip(true)}
            onMouseLeave={() => setShowTooltip(false)}
          >
            <button
              className="text-gray-400 hover:text-cyan-400 font-bold text-sm w-6 h-6 rounded-full border border-gray-600 hover:border-cyan-400 flex items-center justify-center transition-all"
              title="Rehber ve tavsiyeleri görmek için tıkla"
            >
              ?
            </button>
            {showTooltip && (
              <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 w-48 bg-gray-900 border border-cyan-500 rounded-lg p-3 text-xs text-gray-100 z-50 shadow-lg">
                <div className="text-cyan-300 font-semibold mb-1">Rehber:</div>
                <p>{tooltipMessage}</p>
                <div className="absolute top-full left-1/2 transform -translate-x-1/2 border-4 border-transparent border-t-cyan-500" />
              </div>
            )}
          </div>
        </div>

        {/* Data status */}
        <div className="mt-3">
          <DataStatusBadge data={metric} compact />
        </div>

        {/* Score + trend + health */}
        <div className="mt-4 flex items-end justify-between">
          <div>
            <p className="metric-value">{(metric.score * 100).toFixed(1)}%</p>
            <p className="text-lg font-semibold text-gray-300">{getTrendIcon(metric.score)}</p>
          </div>
          <span className={`status-badge ${getStatusClass(metric.health)}`}>
            {metric.health}
          </span>
        </div>

        {/* Summary from backend — data-driven explanation */}
        {metric.summary ? (
          <div className="mt-3 rounded-lg bg-slate-800/60 border border-slate-700/50 px-3 py-2 text-[11px] leading-relaxed text-slate-300">
            {metric.summary}
          </div>
        ) : (
          <div className="mt-3 text-xs text-gray-400 bg-gray-800 bg-opacity-50 rounded p-2">
            {tooltipMessage.substring(0, 25)}...
          </div>
        )}
      </div>
    </div>
  );
};
