import axios, { AxiosInstance } from "axios";
import { DashboardData, Metric, ConsensusData } from "../types";

// Priority: environment variable → localhost:8502 (for browser access)
const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8502";

class ApiService {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: API_URL,
      timeout: 30000,
      headers: {
        "Content-Type": "application/json",
      },
    });
  }

  async getHealth(): Promise<{ status: string }> {
    const response = await this.client.get("/health");
    return response.data;
  }

  async getMetrics(
    symbol: string = "BTC/USDT",
    timeframe: string = "1h"
  ): Promise<{
    touche: Metric;
    fundamental: Metric;
    quantum: Metric;
    sentinel: Metric;
    news: Metric;
  }> {
    try {
      const [touche, fundamental, quantum, sentinel, news] = await Promise.all([
        this.client.get<Metric>("/api/metrics/touche", { params: { symbol, timeframe } }),
        this.client.get<Metric>("/api/metrics/fundamental", {
          params: { symbol, timeframe },
        }),
        this.client.get<Metric>("/api/metrics/quantum", { params: { symbol, timeframe } }),
        this.client.get<Metric>("/api/metrics/sentinel", {
          params: { symbol, timeframe },
        }),
        this.client.get<Metric>("/api/metrics/news", { params: { timeframe } }),
      ]);

      return {
        touche: touche.data,
        fundamental: fundamental.data,
        quantum: quantum.data,
        sentinel: sentinel.data,
        news: news.data,
      };
    } catch (error) {
      console.error("Error fetching metrics:", error);
      throw error;
    }
  }

  async getConsensus(symbol: string = "BTC/USDT", timeframe: string = "1h"): Promise<ConsensusData> {
    const response = await this.client.get("/api/consensus", {
      params: { symbol, timeframe },
    });
    return response.data;
  }

  async getSystemHealth(): Promise<any> {
    const response = await this.client.get("/api/health");
    return response.data;
  }

  async getDashboard(symbol: string = "BTC/USDT", timeframe: string = "1h"): Promise<DashboardData> {
    const response = await this.client.get("/api/dashboard", {
      params: { symbol, timeframe },
    });
    return response.data;
  }

  async getConfig(): Promise<{
    symbols: string[];
    default_symbol: string;
  }> {
    const response = await this.client.get("/api/config");
    return response.data;
  }

  // ── ANALYZER AI ──
  async getAnalysis(symbol: string = "BTC/USDT", timeframe: string = "4h"): Promise<any> {
    try {
      const response = await this.client.get("/api/analysis", {
        params: { symbol, timeframe },
      });
      return response.data;
    } catch (error) {
      console.error("Error fetching analysis:", error);
      throw error;
    }
  }
}

export default new ApiService();
