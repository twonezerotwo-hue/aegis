/**
 * Backtest API Service - AI-Driven Backtesting
 * Uses Consensus Engine decisions (Touche 50% + Fundamental 35% + News 15%)
 */

export interface AIBacktestParams {
  symbol: string;
  timeframe: string;
  start_date: string;  // YYYY-MM-DD
  end_date: string;    // YYYY-MM-DD
}

export interface BacktestMetrics {
  pnl: {
    total_pnl: number;
    total_pnl_pct: number;
    num_trades: number;
  };
  win_loss: {
    win_rate: number;
    win_count: number;
    loss_count: number;
    avg_win: number;
    avg_loss: number;
    profit_factor: number;
  };
  drawdown: {
    max_drawdown: number;
    max_drawdown_pct: number;
  };
  sharpe_ratio: number;
  sortino_ratio: number;
  initial_capital: number;
  final_capital: number;
}

export interface Trade {
  entry_time: string;
  exit_time: string;
  entry_price: number;
  exit_price: number;
  position: string;
  pnl: number;
  pnl_pct: number;
}

export interface BacktestResult {
  success: boolean;
  symbol: string;
  timeframe: string;
  strategy: string;
  date_range: {
    start: string;
    end: string;
  };
  metrics: BacktestMetrics;
  total_trades: number;
  trades?: Trade[];
  generated_at: string;
  data_points: number;
}

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8502';

export const backtestApi = {
  async runBacktest(params: AIBacktestParams): Promise<BacktestResult> {
    const response = await fetch(
      `${API_BASE_URL}/backtest/run`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(params),
      }
    );

    if (!response.ok) {
      throw new Error(`Backtest failed: ${response.statusText}`);
    }

    return response.json();
  },

  async getResults(symbol: string, timeframe: string): Promise<BacktestResult> {
    const response = await fetch(
      `${API_BASE_URL}/backtest/results?symbol=${symbol}&timeframe=${timeframe}`
    );

    if (!response.ok) {
      throw new Error(`Failed to fetch results: ${response.statusText}`);
    }

    return response.json();
  },

  async getSupportedTimeframes(): Promise<{
    timeframes: string[];
    strategy: string;
    ai_modules: string[];
  }> {
    const response = await fetch(
      `${API_BASE_URL}/backtest/supported-timeframes`
    );

    if (!response.ok) {
      throw new Error(`Failed to fetch timeframes: ${response.statusText}`);
    }

    return response.json();
  },

  async exportCSV(symbol: string, timeframe: string): Promise<Blob> {
    const response = await fetch(
      `${API_BASE_URL}/backtest/export/csv?symbol=${symbol}&timeframe=${timeframe}`
    );

    if (!response.ok) {
      throw new Error(`CSV export failed: ${response.statusText}`);
    }

    return response.blob();
  },

  async exportHTML(symbol: string, timeframe: string): Promise<Blob> {
    const response = await fetch(
      `${API_BASE_URL}/backtest/export/html?symbol=${symbol}&timeframe=${timeframe}`
    );

    if (!response.ok) {
      throw new Error(`HTML export failed: ${response.statusText}`);
    }

    return response.blob();
  },

  async clearCache(): Promise<{ message: string }> {
    const response = await fetch(
      `${API_BASE_URL}/backtest/cache`,
      { method: 'DELETE' }
    );

    if (!response.ok) {
      throw new Error(`Cache clear failed: ${response.statusText}`);
    }

    return response.json();
  },
};
