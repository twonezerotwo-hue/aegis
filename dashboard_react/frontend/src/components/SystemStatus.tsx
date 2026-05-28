import React from "react";
import { SystemHealth } from "../types";
import { DataStatusBadge } from "./ui/DataStatusBadge";

interface SystemStatusProps {
  health: SystemHealth;
}

export const SystemStatus: React.FC<SystemStatusProps> = ({ health }) => {
  const getStatusColor = (status: string) => {
    if (status === "UP") return "bg-green-500 bg-opacity-20 text-green-300";
    return "bg-red-500 bg-opacity-20 text-red-300";
  };

  const getOverallStatusColor = (status: string) => {
    switch (status) {
      case "healthy":
        return "text-green-400";
      case "degraded":
        return "text-yellow-400";
      case "down":
        return "text-red-400";
      default:
        return "text-gray-400";
    }
  };

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
            <p className="text-3xl font-bold text-cyan-400">
              {health.up_count}
            </p>
          </div>
        </div>

        <div className="mt-4 space-y-2 border-t border-gray-700 pt-4">
          {Object.entries(health.services).map(([service, status]) => (
            <div
              key={service}
              className="flex items-center justify-between rounded bg-gray-800 bg-opacity-50 p-2"
            >
              <span className="capitalize text-gray-300">{service}</span>
              <span className={`inline-block rounded px-2 py-1 text-xs font-medium ${getStatusColor(status)}`}>
                {status}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
