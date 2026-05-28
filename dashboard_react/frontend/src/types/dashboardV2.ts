import type { DataStatus } from "../utils/dataFreshness";

export type TradingAction = "BUY" | "SELL" | "HOLD";
export type RebalanceActionType = "BUY" | "SELL";

export interface AllocationWeights {
  gold: number;
  btc: number;
  bond: number;
  commodity: number;
  cash: number;
}

export interface MacroMetrics {
  dxy: number;
  vix: number;
  us10y: number;
  brent: number;
  xau: number;
  btc_d: number;
  usdt_d: number;
  hg: number;
  event_risk_score: number;
  hours_to_event: number;
}

export interface RebalanceAction {
  asset: keyof AllocationWeights;
  action: RebalanceActionType;
  delta: number;
  current_weight: number;
  target_weight: number;
}

export interface MacroViewModel {
  status: string;
  source: string;
  timestamp: string | null;
  last_updated?: string | null;
  fallback_used?: boolean;
  data_status?: DataStatus;
  fallback: boolean;
  verified?: boolean;
  live?: boolean;
  warning?: string;
  fallback_fields?: string[];
  source_fields?: string[];
  field_sources?: Record<string, string>;
  regime: string;
  macro_score: number;
  hedge: boolean;
  hedge_unverified?: boolean;
  hedge_source?: "backend" | "derived" | "derived_from_unverified_macro";
  position_size_pct: number;
  stop_loss_pct: number;
  allocation_target: AllocationWeights;
  allocation_current: AllocationWeights;
  allocation_horizon?: "short" | "medium" | "long";
  allocation_profile?: "defensive" | "balanced" | "structural" | "fallback_illustrative" | string;
  allocation_basis?: string[];
  warnings?: string[];
  horizon_adjustments?: Partial<AllocationWeights>;
  rebalance_required: boolean;
  rebalance_actions: RebalanceAction[];
  metrics: MacroMetrics;
  error?: string;
}

export type MacroResponse = MacroViewModel;

export interface ConsensusComponent {
  score: number;
  weight: number;
}

export interface ConsensusCriteria {
  regime_suitable: boolean;
  dynamic_threshold_pass: boolean;
  modules_agree_3plus: boolean;
  multi_tf_aligned: boolean;
  cbr_edge_valid: boolean;
  liquidity_ok: boolean;
  risk_multiplier_ok: boolean;
  event_risk_ok: boolean;
  ci_guard_pass?: boolean;
  correlation_ok?: boolean;
}

export interface CorrelationPair {
  modules: [string, string];
  correlation: number;
  penalized: string;
}

export interface WeightsResponse {
  weights: ModuleWeights;
  drift_total: number;
  drift_limit: number;
  drift_frozen: boolean;
  backup_exists: boolean;
  week_start?: string;
}

export interface TradeAttributionResult {
  attribution_ref: string;
  winning_modules: string[];
  losing_modules: string[];
  contribution_pct: Record<string, number>;
  error?: string;
}

export interface ModuleScores {
  touche: number;
  fundamental: number;
  news: number;
  sentinel: number;
  quantum: number;
}

export interface ModuleWeights {
  touche: number;
  fundamental: number;
  news: number;
  sentinel: number;
  quantum: number;
}

export interface CBRSummary {
  sample_count: number;
  win_rate_pct: number;
  similarity_score: number;
  include_in_consensus: boolean;
  is_historical_weak: boolean;
  confidence_modifier: number;
  reason: string;
}

export interface MultiTfSummary {
  is_valid: boolean;
  final_signal: string;
  reason: string;
  holding_period_hours: number;
}

export interface SentinelSummary {
  risk_multiplier: number;
  regime_context: {
    event_risk_score: number;
    hours_to_event: number;
    is_low_risk: boolean;
    source: string;
  };
}

export interface ConsensusModuleSource {
  module: string;
  service: string;
  source: string;
  source_data: string;
  timestamp: string | null;
  timestamp_source: string;
  data_status: DataStatus;
  fallback_used: boolean;
  verified: boolean;
  asset_specific: boolean;
  shared_score: boolean;
  value: number;
  warnings: string[];
}

export interface ConsensusModuleSources {
  technical: ConsensusModuleSource;
  fundamental: ConsensusModuleSource;
  news: ConsensusModuleSource;
  sentinel: ConsensusModuleSource;
  quantum: ConsensusModuleSource;
}

export interface ConsensusResponse {
  asset?: string;
  action: TradingAction;
  confidence: number;
  weighted_score: number;
  source?: string;
  last_updated?: string | null;
  fallback_used?: boolean;
  verified?: boolean;
  data_status?: DataStatus;
  warnings?: string[];
  module_sources?: ConsensusModuleSources;
  green_light: boolean;
  green_light_reason: string;
  failed_criteria: string[];
  criteria: ConsensusCriteria;
  module_scores: ModuleScores;
  module_weights: ModuleWeights;
  components: {
    touche: ConsensusComponent;
    fundamental: ConsensusComponent;
    news: ConsensusComponent;
  };
  five_module_score: number;
  position_size: number;
  symbol: string;
  timeframe: string;
  timestamp: string | null;
  cbr: CBRSummary;
  multi_tf: MultiTfSummary;
  sentinel: SentinelSummary;
  // v7.0 fields
  confidence_interval?: [number, number];
  meta_score?: number;
  correlation_penalty?: number;
  correlation_penalized_pairs?: CorrelationPair[];
  attribution_ref?: string;
  adjusted_module_weights?: ModuleWeights;
}

export interface AttributionModule {
  total_trades: number;
  win_rate: number;
  attribution_score: number;
  role: string;
}

export interface AttributionModules {
  touche: AttributionModule;
  fundamental: AttributionModule;
  sentinel: AttributionModule;
  news: AttributionModule;
  quantum: AttributionModule;
}

export interface AttributionResponse {
  period: string;
  modules: AttributionModules;
}

export interface CBRMatch {
  id: string;
  label: string;
  similarity: number;
  outcome: "WIN" | "LOSS" | "NEUTRAL";
  regime: string;
  note: string;
}

export interface CBRResponse {
  symbol: string;
  similarity_score: number;
  sample_count: number;
  win_rate_pct: number;
  include_in_consensus: boolean;
  is_historical_weak: boolean;
  confidence_modifier: number;
  reason: string;
  matches: CBRMatch[];
}

export interface SystemSnapshot {
  macro: MacroViewModel;
  consensus: ConsensusResponse;
  attribution: AttributionResponse;
  cbr: CBRResponse;
}

export interface SystemState {
  macro: MacroViewModel | null;
  consensus: ConsensusResponse | null;
  attribution: AttributionResponse | null;
  cbr: CBRResponse | null;
  loading: boolean;
  error: string | null;
  lastUpdated: string | null;
  lastSuccessfulUpdate?: string | null;
  lastKnownState: SystemSnapshot | null;
}
