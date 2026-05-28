import React, { useState, useEffect } from "react";

interface UnifiedOptimizerStatus {
  enabled: boolean;
  error?: string;
  weights?: Record<number, number>;
  phase_params?: Record<number, Record<string, number>>;
  stats?: Record<string, any>;
}

const phaseNames: Record<number, string> = {
  1: "Likidite",
  2: "Piyasa Yapısı",
  3: "Bölgeler",
  4: "Teyit",
  5: "Zamanlama",
  6: "Risk",
  7: "Makro",
};

export const OptimizerCard: React.FC = () => {
  const [status, setStatus] = useState<UnifiedOptimizerStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [optimizing, setOptimizing] = useState(false);
  const [tradeHistory, setTradeHistory] = useState<any[]>([]);

  useEffect(() => {
    fetchOptimizerStatus();
    const interval = setInterval(fetchOptimizerStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  const fetchOptimizerStatus = async () => {
    try {
      const response = await fetch("http://localhost:8502/api/optimizer/status");
      if (response.ok) {
        const data: UnifiedOptimizerStatus = await response.json();
        setStatus(data);
        setError(null);
      } else {
        setError("Failed to fetch optimizer status");
      }
    } catch (err) {
      setError(`Error: ${err}`);
    } finally {
      setLoading(false);
    }
  };

  const recordTrade = async () => {
    // Example trade recording - in real scenario this would come from trading system
    const mockTrade = {
      entry_price: 42500,
      exit_price: 42750,
      pnl: 250,
      winning_phases: [2, 3, 5],
      losing_phases: [],
      rsi_at_entry: 35,
      macd_at_entry: 0.0050,
      volatility: 2.1,
      fibonacci_level: 0.618,
    };

    try {
      const response = await fetch("http://localhost:8502/api/optimizer/record-trade", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(mockTrade),
      });

      if (response.ok) {
        alert("Trade recorded!");
        await fetchOptimizerStatus();
      } else {
        alert("Failed to record trade");
      }
    } catch (err) {
      alert(`Error: ${err}`);
    }
  };

  const triggerOptimization = async (type: "light" | "heavy") => {
    setOptimizing(true);
    try {
      const response = await fetch(
        `http://localhost:8502/api/optimizer/periodic-optimize?optimization_type=${type}`,
        { method: "POST" }
      );

      if (response.ok) {
        const result = await response.json();
        if (result.success) {
          alert(`Optimization complete! Best Score: ${result.best_score?.toFixed(2)}`);
          await fetchOptimizerStatus();
        } else {
          alert(result.message || "Optimization failed");
        }
      } else {
        alert("Optimization failed");
      }
    } catch (err) {
      alert(`Error: ${err}`);
    } finally {
      setOptimizing(false);
    }
  };

  const saveConfig = async () => {
    try {
      const response = await fetch(
        "http://localhost:8502/api/optimizer/save-config?filepath=unified_optimizer_config.yaml",
        { method: "POST" }
      );

      if (response.ok) {
        alert("Configuration saved!");
      } else {
        alert("Failed to save configuration");
      }
    } catch (err) {
      alert(`Error: ${err}`);
    }
  };

  if (loading) {
    return (
      <div className="rounded-lg border border-gray-700 bg-gray-900 p-6">
        <p className="text-gray-400">Loading unified optimizer status...</p>
      </div>
    );
  }

  if (!status?.enabled) {
    return (
      <div className="rounded-lg border border-yellow-700 border-opacity-30 bg-yellow-700 bg-opacity-10 p-6">
        <h3 className="mb-2 text-lg font-bold text-yellow-300">Unified Optimizer</h3>
        <p className="text-yellow-400">{status?.error || "Optimizer not available"}</p>
      </div>
    );
  }

  const stats = status?.stats || {};
  const weights = status?.weights || {};
  const phase_params = status?.phase_params || {};

  return (
    <div className="space-y-6">
      {/* Status Summary */}
      <div className="rounded-lg border border-cyan-700 border-opacity-30 bg-cyan-700 bg-opacity-10 p-6">
        <h3 className="mb-4 text-lg font-bold text-cyan-300">Unified Optimizer Status</h3>

        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <div>
            <p className="text-xs text-gray-500">Total Trades</p>
            <p className="text-2xl font-bold text-cyan-400">{stats?.total_trades || 0}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Win Rate</p>
            <p className="text-2xl font-bold text-green-400">
              {stats?.win_rate ? stats.win_rate.toFixed(1) : 0}%
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Total PnL</p>
            <p className={`text-2xl font-bold ${stats?.total_pnl > 0 ? "text-green-400" : "text-red-400"}`}>
              {stats?.total_pnl ? stats.total_pnl.toFixed(2) : 0}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Optimizations</p>
            <p className="text-2xl font-bold text-blue-400">{stats?.optimization_count || 0}</p>
          </div>
        </div>
      </div>

      {/* Phase Weights */}
      <div className="rounded-lg border border-gray-700 bg-gray-900 p-6">
        <h4 className="mb-4 text-base font-semibold text-gray-300">Phase Weights</h4>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-7">
          {Object.entries(weights)
            .sort(([a], [b]) => Number(a) - Number(b))
            .map(([phase, weight]) => (
              <div key={phase} className="rounded border border-gray-700 bg-gray-800 p-3 text-center">
                <p className="text-xs text-gray-500">{phaseNames[Number(phase)] || `Phase ${phase}`}</p>
                <p className="mt-1 text-lg font-bold text-cyan-400">{(weight * 100).toFixed(1)}%</p>
              </div>
            ))}
        </div>
      </div>

      {/* Phase Parameters */}
      <div className="rounded-lg border border-gray-700 bg-gray-900 p-6">
        <h4 className="mb-4 text-base font-semibold text-gray-300">Phase Parameters</h4>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
          {Object.entries(phase_params)
            .sort(([a], [b]) => Number(a) - Number(b))
            .map(([phase, params]) => (
              <div key={phase} className="rounded border border-gray-700 bg-gray-800 p-3">
                <p className="mb-2 font-semibold text-cyan-300">{phaseNames[Number(phase)] || `Phase ${phase}`}</p>
                <div className="space-y-1 text-xs text-gray-400">
                  {Object.entries(params).map(([key, value]) => (
                    <div key={key} className="flex justify-between">
                      <span>{key}:</span>
                      <span className="font-mono text-gray-300">
                        {typeof value === "number" ? value.toFixed(2) : value}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
        </div>
      </div>

      {/* Controls */}
      <div className="rounded-lg border border-purple-700 border-opacity-30 bg-purple-700 bg-opacity-10 p-6">
        <h4 className="mb-4 text-base font-semibold text-purple-300">Controls</h4>

        <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-3">
          <button
            onClick={recordTrade}
            disabled={optimizing}
            className={`rounded px-4 py-2 font-semibold transition-all text-sm ${
              optimizing ? "cursor-not-allowed bg-gray-700 text-gray-500" : "bg-green-700 text-green-100 hover:bg-green-600"
            }`}
          >
            Record Trade
          </button>

          <button
            onClick={() => triggerOptimization("light")}
            disabled={optimizing}
            className={`rounded px-4 py-2 font-semibold transition-all text-sm ${
              optimizing ? "cursor-not-allowed bg-gray-700 text-gray-500" : "bg-blue-700 text-blue-100 hover:bg-blue-600"
            }`}
          >
            {optimizing ? "Optimizing..." : "Light Optimize"}
          </button>

          <button
            onClick={() => triggerOptimization("heavy")}
            disabled={optimizing}
            className={`rounded px-4 py-2 font-semibold transition-all text-sm ${
              optimizing ? "cursor-not-allowed bg-gray-700 text-gray-500" : "bg-orange-700 text-orange-100 hover:bg-orange-600"
            }`}
          >
            {optimizing ? "Optimizing..." : "Heavy Optimize"}
          </button>

          <button
            onClick={saveConfig}
            disabled={optimizing}
            className={`rounded px-4 py-2 font-semibold transition-all text-sm md:col-span-2 ${
              optimizing ? "cursor-not-allowed bg-gray-700 text-gray-500" : "bg-yellow-700 text-yellow-100 hover:bg-yellow-600"
            }`}
          >
            Save Configuration
          </button>
        </div>

        <p className="text-xs text-gray-500">
          Light: Grid search optimization (comprehensive, slower)
          <br />
          Heavy: Bayesian optimization (adaptive, faster)
        </p>
      </div>

      {/* Statistics */}
      <div className="rounded-lg border border-gray-700 bg-gray-900 p-6">
        <h4 className="mb-4 text-base font-semibold text-gray-300">Trade Statistics</h4>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
          <div className="rounded bg-gray-800 p-3">
            <p className="text-xs text-gray-500">Winning Trades</p>
            <p className="text-xl font-bold text-green-400">{stats?.winning_trades || 0}</p>
          </div>
          <div className="rounded bg-gray-800 p-3">
            <p className="text-xs text-gray-500">Losing Trades</p>
            <p className="text-xl font-bold text-red-400">{stats?.losing_trades || 0}</p>
          </div>
          <div className="rounded bg-gray-800 p-3">
            <p className="text-xs text-gray-500">Average PnL</p>
            <p className={`text-xl font-bold ${stats?.avg_pnl > 0 ? "text-green-400" : "text-red-400"}`}>
              {stats?.avg_pnl ? stats.avg_pnl.toFixed(2) : 0}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

