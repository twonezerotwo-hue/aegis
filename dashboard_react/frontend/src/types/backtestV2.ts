/**
 * AEGIS v7.3 — Type-safe Backtest API Response Interfaces
 * Matches the exact backend /backtest/run response schema
 */

export interface BacktestPnL {
  total_pnl: number;
  total_pnl_pct: number;
  num_trades: number;
}

export interface BacktestWinLoss {
  win_rate: number;
  win_count: number;
  loss_count: number;
  avg_win: number;
  avg_loss: number;
  profit_factor: number;
}

export interface BacktestDrawdown {
  max_drawdown: number;
  max_drawdown_pct: number;
}

export interface BacktestMetricsV2 {
  pnl: BacktestPnL;
  win_loss: BacktestWinLoss;
  drawdown: BacktestDrawdown;
  sharpe_ratio: number;
  sortino_ratio: number;
  initial_capital: number;
  final_capital: number;
}

export interface BacktestModuleScores {
  touche: number;
  fundamental: number;
  quantum: number;
  sentinel: number;
  news: number;
}

export interface BacktestTrade {
  entry_time: string;
  exit_time: string;
  entry_price: number;
  exit_price: number;
  position: "LONG" | "SHORT";
  pnl: number;
  pnl_pct: number;
  z_score?: number;
  regime?: string;
  corr_regime?: string;
}

export interface BacktestDateRange {
  start: string;
  end: string;
}

export interface PortfolioAllocationEntry {
  allocation_pct: number;
  rationale: string;
}

export interface BacktestResultV2 {
  success: boolean;
  backtest_id: string;
  symbol: string;
  timeframe: string;
  horizon?: string;
  date_range: BacktestDateRange;
  data_source?: string;
  metrics: BacktestMetricsV2;
  module_scores: BacktestModuleScores;
  score_attribution?: Record<string, { feature: string; value: string | number; impact: number }[]>;
  portfolio_allocation?: Record<string, PortfolioAllocationEntry>;
  regime?: string;
  total_trades: number;
  trades: BacktestTrade[];
  data_points: number;
  generated_at?: string;
}

export interface BacktestParamsV2 {
  symbol: string;
  timeframe: string;
  horizon?: string;
  start_date: string;
  end_date: string;
  initial_capital?: number;
  risk_per_trade?: number;
  use_live_data?: boolean;
  include_fees?: boolean;
}

/** Metric trend direction for UI display */
export type MetricTrend = "up" | "down" | "neutral";

/** Module score entry for ScoreBar */
export interface ModuleScoreEntry {
  key: keyof BacktestModuleScores;
  label: string;
  value: number;
  color: string;
}

/** Default module color map */
export const MODULE_COLORS: Record<keyof BacktestModuleScores, string> = {
  touche: "#3b82f6",      // blue
  fundamental: "#10b981", // emerald
  quantum: "#8b5cf6",     // violet
  sentinel: "#f59e0b",    // amber
  news: "#ec4899",        // pink
};

/** Validate a BacktestResultV2 has all required fields */
export function validateBacktestResult(data: unknown): data is BacktestResultV2 {
  if (!data || typeof data !== "object") return false;
  const d = data as Record<string, unknown>;
  const required = ["success", "backtest_id", "metrics", "module_scores", "trades"];
  return required.every((key) => key in d);
}
