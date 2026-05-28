import React from "react";
import { SymbolSelector } from "./SymbolSelector";
import { TimeframeSelector } from "./TimeframeSelector";
import { DataStatusBadge } from "./ui/DataStatusBadge";
import type { DashboardData } from "../types";

interface HeaderProps {
  currentSymbol?: string;
  onSymbolChange?: (symbol: string) => void;
  currentTimeframe?: string;
  onTimeframeChange?: (timeframe: string) => void;
  dashboardData?: DashboardData | null;
}

export const Header: React.FC<HeaderProps> = ({
  currentSymbol = "BTC/USDT",
  onSymbolChange = () => {},
  currentTimeframe = "1h",
  onTimeframeChange = () => {},
  dashboardData = null,
}) => {
  const time = new Date().toLocaleTimeString();

  return (
    <header className="border-b border-gray-700 bg-gray-900 bg-opacity-50 backdrop-blur-sm">
      <div className="mx-auto max-w-7xl px-6 py-6">
        <div className="flex flex-col items-start justify-between gap-4 md:flex-row md:items-center">
          <div className="flex items-center gap-4">
            <div className="text-3xl font-bold">
              <span className="bg-gradient-to-r from-cyan-400 to-blue-400 bg-clip-text text-transparent">
                AEGIS
              </span>
            </div>
            <div className="hidden md:block">
              <h1 className="text-2xl font-bold">Holding Dashboard</h1>
              <p className="text-sm text-gray-400">
                Real-time AI Consensus Engine
              </p>
            </div>
          </div>

          <div className="flex flex-col items-start justify-between gap-4 md:flex-row md:items-center md:gap-6">
            <div>
              <p className="mb-2 text-xs uppercase text-gray-500">Trading Pair</p>
              <SymbolSelector
                currentSymbol={currentSymbol}
                onSymbolChange={onSymbolChange}
              />
            </div>

            <div>
              <TimeframeSelector
                currentTimeframe={currentTimeframe}
                onTimeframeChange={onTimeframeChange}
              />
            </div>

            <div className="text-right">
              <p className="font-mono text-sm text-gray-400">Browser time</p>
              <p className="font-mono text-lg text-cyan-400">{time}</p>
            </div>

            <div className="min-w-[180px]">
              <DataStatusBadge
                data={dashboardData}
                showDetails
                compact
                className="items-start md:items-end"
              />
            </div>
          </div>
        </div>
      </div>
    </header>
  );
};
