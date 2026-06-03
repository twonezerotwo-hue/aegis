import type { DataStatus } from "../utils/dataFreshness";

export interface Metric {
  name: string;
  score: number;
  health: "healthy" | "warning" | "down";
  color: string;
  summary?: string;
  timestamp?: string | null;
  last_updated?: string | null;
  source?: string;
  fallback_used?: boolean;
  data_status?: DataStatus;
}

export interface ConsensusData {
  weighted_score: number;
  action: "BUY" | "SELL" | "HOLD";
  confidence: number;
  weights: {
    touche: number;
    fundamental: number;
    news: number;
  };
  components: {
    touche: { score: number; weight: number };
    fundamental: { score: number; weight: number };
    news: { score: number; weight: number };
  };
  timestamp?: string | null;
  last_updated?: string | null;
  source?: string;
  fallback_used?: boolean;
  data_status?: DataStatus;
}

export interface SystemHealth {
  overall_status: "healthy" | "degraded" | "down";
  services: Record<string, "UP" | "DOWN">;
  up_count: number;
  total_count: number;
  timestamp?: string | null;
  last_updated?: string | null;
  source?: string;
  fallback_used?: boolean;
  data_status?: DataStatus;
}

export interface DashboardData {
  timestamp: string | null;
  last_updated?: string | null;
  source?: string;
  fallback_used?: boolean;
  data_status?: DataStatus;
  metrics: {
    touche: Metric;
    fundamental: Metric;
    quantum: Metric;
    sentinel: Metric;
    news: Metric;
    ml?: Metric & {
      ml_detail?: {
        trained: boolean;
        signal?: string;
        buy_prob?: number;
        sell_prob?: number;
        confidence?: number;
        accuracy?: number;
        top_features?: [string, number][];
      };
    };
  };
  consensus: ConsensusData;
  health: SystemHealth;
}

// ─── AEGIS v6 Live Feed Types ─────────────────────────────────────────────────

export interface LiveConsensus {
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
    include_in_consensus?: boolean;
  };
  multi_tf?: {
    is_valid: boolean;
    final_signal: string;
    reason: string;
    holding_period_hours?: number;
  };
  sentinel?: { risk_multiplier: number; regime_context?: Record<string, unknown> };
  position_size: number;
}

export interface CBRMatch {
  case_id: string;
  similarity: number;
  outcome: "WIN" | "LOSS";
  regime: string;
  pnl_pct: number;
  days_ago: number;
  signal: "BUY" | "SELL";
}

export interface ExitSignal {
  exit: boolean;
  reason: string;
  partial_close?: boolean;
  close_pct?: number;
  trailing_stop?: number;
  structure_level?: number;
}

export interface EquityPoint {
  ts: number;
  equity: number;
}

export interface PaperTrade {
  balance_usdt: number;
  initial_capital: number;
  pnl: number;
  pnl_pct: number;
  equity_curve: EquityPoint[];
  open_positions: Array<{
    symbol: string;
    side: string;
    entry_price: number;
    quantity: number;
    unrealized_pnl: number;
  }>;
  trade_count: number;
  win_rate: number;
}

export interface LiveFeedPayload {
  type: "full_update" | "error";
  message?: string;
  tick?: number;
  timestamp: string | null;
  last_updated?: string | null;
  source?: string;
  fallback_used?: boolean;
  data_status?: DataStatus;
  symbol: string;
  regime: string;
  regime_allocation: Record<string, number>;
  event_risk_score: number;
  hours_to_event: number;
  consensus: LiveConsensus;
  cbr_matches: CBRMatch[];
  exit_signal: ExitSignal;
  paper_trade: PaperTrade;
}
