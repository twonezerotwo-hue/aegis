import { useState, useEffect } from "react";
import { DashboardData } from "../types";
import apiService from "../services/api";

export const useMetrics = (
  symbol: string = "BTC/USDT",
  timeframe: string = "1h",
  intervalMs: number = 10000
) => {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const response = await apiService.getDashboard(symbol, timeframe);
        setData(response);
        setError(null);
      } catch (err) {
        console.error("Error fetching metrics:", err);
        setError(err instanceof Error ? err.message : "Failed to fetch metrics");
      } finally {
        setLoading(false);
      }
    };

    // Initial fetch
    fetchData();

    // Set up interval for auto-refresh
    const interval = setInterval(fetchData, intervalMs);

    return () => clearInterval(interval);
  }, [symbol, timeframe, intervalMs]);

  return { data, loading, error };
};
