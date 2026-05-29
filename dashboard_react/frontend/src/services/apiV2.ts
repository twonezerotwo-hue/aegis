import axios from "axios";
import {
  AllocationWeights,
  AssetMetadataItem,
  AttributionModule,
  AttributionResponse,
  CBRMatch,
  CBRResponse,
  CBRSummary,
  ConsensusCriteria,
  ConsensusModuleSource,
  ConsensusModuleSources,
  ConsensusResponse,
  CorrelationPair,
  MacroMetrics,
  MacroViewModel,
  ModuleScores,
  ModuleWeights,
  MultiTfSummary,
  RebalanceAction,
  RealEstateDecision,
  SentinelSummary,
  TradeAttributionResult,
  WeightsResponse,
} from "../types/dashboardV2";

interface RequestOptions {
  signal?: AbortSignal;
}

interface RawMacroMetrics {
  dxy?: number;
  vix?: number;
  us10y?: number;
  brent?: number;
  xau?: number;
  btc_d?: number;
  usdt_d?: number;
  hg?: number;
  event_risk_score?: number;
  hours_to_event?: number;
  regime?: string;
  market_regime?: string;
  current_regime?: string;
}

interface RawMacroAction {
  asset?: string;
  action?: string;
  delta?: number;
  deviation?: number;
  current_weight?: number;
  target_weight?: number;
}

interface RawMacroResponse {
  status?: string;
  source?: string;
  timestamp?: string;
  last_updated?: string;
  fallback?: boolean;
  fallback_used?: boolean;
  data_status?: string;
  verified?: boolean;
  live?: boolean;
  warning?: string;
  fallback_fields?: string[];
  source_fields?: string[];
  field_sources?: Record<string, string>;
  error?: string;
  regime?: string;
  macro_score?: number;
  hedge?: boolean;
  position_size_pct?: number;
  stop_loss_pct?: number;
  allocation_target?: Partial<AllocationWeights>;
  allocation_current?: Partial<AllocationWeights>;
  allocation_horizon?: string;
  allocation_profile?: string;
  allocation_basis?: string[];
  warnings?: string[];
  horizon_adjustments?: Partial<Record<keyof AllocationWeights, number>>;
  rebalance_required?: boolean;
  rebalance_actions?: RawMacroAction[];
  rebalance_signal?: {
    rebalance_required?: boolean;
    actions?: RawMacroAction[];
  };
  metrics?: RawMacroMetrics;
  asset_metadata?: Record<string, AssetMetadataItem>;
  real_estate_decision?: RealEstateDecision;
}

interface RawConsensusGatewayResponse {
  asset?: string;
  weighted_score?: number;
  action?: "BUY" | "SELL" | "HOLD";
  confidence?: number;
  weights?: Partial<Record<"touche" | "fundamental" | "news", number>>;
  components?: {
    touche?: { score?: number; weight?: number };
    fundamental?: { score?: number; weight?: number };
    news?: { score?: number; weight?: number };
  };
  symbol?: string;
  timeframe?: string;
  timestamp?: string;
  last_updated?: string;
  source?: string;
  fallback_used?: boolean;
  verified?: boolean;
  data_status?: string;
  warnings?: string[];
  module_sources?: RawConsensusModuleSources;
}

interface RawConsensusProcessResponse {
  asset?: string;
  symbol?: string;
  timeframe?: string;
  action?: "BUY" | "SELL" | "HOLD";
  confidence?: number;
  position_size?: number;
  green_light?: boolean;
  failed_criteria?: string[];
  criteria?: Partial<ConsensusCriteria>;
  module_weights?: Partial<ModuleWeights>;
  five_module_score?: number;
  module_scores?: Partial<ModuleScores>;
  cbr?: Partial<CBRSummary>;
  multi_tf?: Partial<MultiTfSummary>;
  sentinel?: {
    risk_multiplier?: number;
    regime_context?: {
      event_risk_score?: number;
      hours_to_event?: number;
      is_low_risk?: boolean;
      source?: string;
    };
  };
  timestamp?: string;
  last_updated?: string;
  source?: string;
  fallback_used?: boolean;
  verified?: boolean;
  data_status?: string;
  warnings?: string[];
  module_sources?: RawConsensusModuleSources;
  // v7.0 fields
  confidence_interval?: [number, number];
  meta_score?: number;
  correlation_penalty?: number;
  correlation_penalized_pairs?: CorrelationPair[];
  attribution_ref?: string;
  adjusted_module_weights?: Partial<ModuleWeights>;
}

interface RawConsensusModuleSource {
  module?: string;
  service?: string;
  source?: string;
  source_data?: string;
  timestamp?: string;
  timestamp_source?: string;
  data_status?: string;
  fallback_used?: boolean;
  verified?: boolean;
  asset_specific?: boolean;
  shared_score?: boolean;
  value?: number;
  warnings?: string[];
}

interface RawConsensusModuleSources {
  technical?: RawConsensusModuleSource;
  fundamental?: RawConsensusModuleSource;
  news?: RawConsensusModuleSource;
  sentinel?: RawConsensusModuleSource;
  quantum?: RawConsensusModuleSource;
}

interface RawAttributionModule {
  total_trades?: number;
  win_rate?: number;
  attribution_score?: number;
  role?: string;
}

interface RawAttributionResponse {
  period?: string;
  modules?: Record<string, RawAttributionModule>;
}

interface RawHistoricalEdgeMatch {
  id?: string;
  label?: string;
  similarity?: number;
  outcome?: "WIN" | "LOSS" | "NEUTRAL";
  regime?: string;
  note?: string;
}

interface RawHistoricalEdgeResponse {
  symbol?: string;
  similarity_score?: number;
  sample_count?: number;
  win_rate_pct?: number;
  include_in_consensus?: boolean;
  is_historical_weak?: boolean;
  confidence_modifier?: number;
  reason?: string;
  matches?: RawHistoricalEdgeMatch[];
}

const GATEWAY_URL = import.meta.env.VITE_API_URL || "http://localhost:8502";
const ANALYZER_URL = import.meta.env.VITE_ANALYZER_API_URL || "http://localhost:8007";
const CONSENSUS_URL = import.meta.env.VITE_CONSENSUS_API_URL || "http://localhost:8005";

const gatewayClient = axios.create({
  baseURL: GATEWAY_URL,
  timeout: 10000,
  headers: { "Content-Type": "application/json" },
});

const analyzerClient = axios.create({
  baseURL: ANALYZER_URL,
  timeout: 10000,
  headers: { "Content-Type": "application/json" },
});

const consensusClient = axios.create({
  baseURL: CONSENSUS_URL,
  timeout: 10000,
  headers: { "Content-Type": "application/json" },
});

const allocationKeys: Array<keyof AllocationWeights> = ["gold", "btc", "bond", "commodity", "cash"];

const getNumber = (value: number | undefined, fallback: number): number => {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }

  return fallback;
};

const getString = (value: string | undefined, fallback: string): string => {
  if (typeof value === "string" && value.trim().length > 0) {
    return value;
  }

  return fallback;
};

const getOptionalString = (value: unknown): string | null => {
  if (typeof value !== "string") {
    return null;
  }

  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
};

const getStringArray = (value: unknown): string[] | undefined => {
  if (!Array.isArray(value)) {
    return undefined;
  }

  const filtered = value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
  return filtered.length > 0 ? filtered : undefined;
};

const pickTimestamp = (...values: unknown[]): string | null => {
  for (const value of values) {
    const candidate = getOptionalString(value);
    if (candidate) {
      return candidate;
    }
  }

  return null;
};

const getDataStatus = (value: unknown): MacroViewModel["data_status"] | undefined => {
  if (typeof value !== "string") {
    return undefined;
  }

  const normalized = value.trim().toUpperCase();
  switch (normalized) {
    case "LIVE":
    case "RECENT":
    case "STALE":
    case "PARTIAL_FALLBACK":
    case "FALLBACK":
    case "MOCK":
    case "MISSING":
    case "UNKNOWN":
      return normalized as MacroViewModel["data_status"];
    default:
      return undefined;
  }
};

const hasFallbackSourceHint = (value: string | null): boolean => {
  if (!value) {
    return false;
  }

  const normalized = value.toLowerCase();
  return normalized.includes("fallback") || normalized.includes("cache");
};

const isPartialFallbackSource = (value: string | null): boolean => {
  if (!value) {
    return false;
  }

  return value.toLowerCase().includes("partial_plus_fallback");
};

const clamp = (value: number, min: number, max: number): number => Math.min(max, Math.max(min, value));

const isUnverifiedMacroStatus = (status: MacroViewModel["data_status"] | undefined): boolean =>
  status === "FALLBACK" ||
  status === "PARTIAL_FALLBACK" ||
  status === "MOCK" ||
  status === "MISSING" ||
  status === "UNKNOWN";

const MACRO_FALLBACK_CLUSTER = {
  dxy: 98.5,
  vix: 22.0,
  us10y: 4.25,
  brent: 92.0,
} as const;

const MACRO_FALLBACK_CLUSTER_FIELDS = ["dxy", "vix", "us10y", "brent"] as const;

const mergeMacroWarnings = (...warningLists: Array<string[] | undefined>): string[] | undefined => {
  const merged: string[] = [];
  for (const warningList of warningLists) {
    if (!warningList) {
      continue;
    }
    for (const warning of warningList) {
      if (warning && !merged.includes(warning)) {
        merged.push(warning);
      }
    }
  }

  return merged.length > 0 ? merged : undefined;
};

const isHardcodedFallbackCluster = (metrics: MacroMetrics): boolean =>
  metrics.dxy === MACRO_FALLBACK_CLUSTER.dxy &&
  metrics.vix === MACRO_FALLBACK_CLUSTER.vix &&
  metrics.us10y === MACRO_FALLBACK_CLUSTER.us10y &&
  metrics.brent === MACRO_FALLBACK_CLUSTER.brent;

const normalizeAdjustmentWeights = (value: unknown): Partial<AllocationWeights> | undefined => {
  if (!value || typeof value !== "object") {
    return undefined;
  }

  const source = value as Partial<Record<keyof AllocationWeights, unknown>>;
  const normalized: Partial<AllocationWeights> = {};
  for (const key of allocationKeys) {
    if (typeof source[key] === "number" && Number.isFinite(source[key])) {
      normalized[key] = Number((source[key] as number).toFixed(4));
    }
  }

  return Object.keys(normalized).length > 0 ? normalized : undefined;
};

const createWeights = (weights?: Partial<AllocationWeights>): AllocationWeights => ({
  gold: getNumber(weights?.gold, 0),
  btc: getNumber(weights?.btc, 0),
  bond: getNumber(weights?.bond, 0),
  commodity: getNumber(weights?.commodity, 0),
  cash: getNumber(weights?.cash, 0),
});

const hasCustomWeights = (weights?: Partial<AllocationWeights>): boolean => {
  if (!weights) {
    return false;
  }

  return allocationKeys.some((key) => typeof weights[key] === "number");
};

const normalizeWeights = (weights: AllocationWeights): AllocationWeights => {
  const total = allocationKeys.reduce((sum, key) => sum + weights[key], 0);

  if (total <= 0) {
    return { gold: 0.2, btc: 0.2, bond: 0.25, commodity: 0.15, cash: 0.2 };
  }

  const normalized: AllocationWeights = {
    gold: Number((weights.gold / total).toFixed(4)),
    btc: Number((weights.btc / total).toFixed(4)),
    bond: Number((weights.bond / total).toFixed(4)),
    commodity: Number((weights.commodity / total).toFixed(4)),
    cash: Number((weights.cash / total).toFixed(4)),
  };

  const diff = Number((1 - allocationKeys.reduce((sum, key) => sum + normalized[key], 0)).toFixed(4));
  normalized.cash = Number((normalized.cash + diff).toFixed(4));
  return normalized;
};

const normalizeMacroMetrics = (metrics?: RawMacroMetrics): MacroMetrics => ({
  dxy: getNumber(metrics?.dxy, 98.5),
  vix: getNumber(metrics?.vix, 22.0),
  us10y: getNumber(metrics?.us10y, 4.25),
  brent: getNumber(metrics?.brent, 92.0),
  xau: getNumber(metrics?.xau, 4800),
  btc_d: getNumber(metrics?.btc_d, 59.8),
  usdt_d: getNumber(metrics?.usdt_d, 7.5),
  hg: getNumber(metrics?.hg, 4.5),
  event_risk_score: getNumber(metrics?.event_risk_score, 0.25),
  hours_to_event: getNumber(metrics?.hours_to_event, 48),
});

const deriveRegime = (response: RawMacroResponse): string =>
  getString(
    response.regime || response.metrics?.regime || response.metrics?.market_regime || response.metrics?.current_regime,
    "NORMALIZATION"
  ).toUpperCase();

const deriveMacroScore = (metrics: MacroMetrics): number => {
  const score =
    ((103 - metrics.dxy) * 0.06) +
    ((22 - metrics.vix) * 0.04) +
    ((4.6 - metrics.us10y) * 0.12) +
    ((90 - metrics.brent) * 0.01);

  return Number(clamp(score, -1, 1).toFixed(4));
};

const BASE_ALLOCATION_BY_HORIZON: Record<string, AllocationWeights> = {
  short: { gold: 0.18, btc: 0.12, bond: 0.25, commodity: 0.10, cash: 0.35 },
  medium: { gold: 0.22, btc: 0.20, bond: 0.25, commodity: 0.13, cash: 0.20 },
  long: { gold: 0.25, btc: 0.28, bond: 0.18, commodity: 0.17, cash: 0.12 },
};

const deriveAllocationTarget = (regime: string, macroScore: number, hedge: boolean, horizon: string = "medium"): AllocationWeights => {
  const base = { ...(BASE_ALLOCATION_BY_HORIZON[horizon] ?? BASE_ALLOCATION_BY_HORIZON.medium) };

  if (regime.includes("RISK_OFF")) {
    base.gold += 0.05;
    base.bond += 0.08;
    base.cash += 0.05;
    base.btc -= 0.10;
    base.commodity -= 0.08;
  } else if (regime.includes("LIQUIDITY") || regime.includes("RISK_ON")) {
    base.btc += 0.08;
    base.commodity += 0.05;
    base.cash -= 0.07;
    base.bond -= 0.04;
    base.gold -= 0.02;
  } else if (regime.includes("ACCUMULATION")) {
    base.gold += 0.02;
    base.btc += 0.03;
    base.bond += 0.02;
    base.cash -= 0.04;
  }

  const adjusted: AllocationWeights = {
    gold: base.gold - (0.02 * macroScore),
    btc: base.btc + (0.10 * macroScore),
    bond: base.bond - (0.05 * macroScore),
    commodity: base.commodity + (0.03 * macroScore),
    cash: base.cash - (0.06 * macroScore),
  };

  if (hedge) {
    adjusted.gold += 0.03;
    adjusted.bond += 0.03;
    adjusted.cash += 0.02;
    adjusted.btc -= horizon === "short" ? 0.05 : 0.04;
    adjusted.commodity -= horizon === "short" ? 0.04 : 0.03;
  }

  return normalizeWeights(adjusted);
};

const deriveCurrentAllocation = (target: AllocationWeights, supplied?: Partial<AllocationWeights>): AllocationWeights => {
  if (hasCustomWeights(supplied)) {
    return normalizeWeights(createWeights(supplied));
  }

  return target;
};

const normalizeFieldSources = (value: unknown): Record<string, string> | undefined => {
  if (!value || typeof value !== "object") {
    return undefined;
  }

  const normalized = Object.entries(value as Record<string, unknown>).reduce<Record<string, string>>((acc, [key, sourceValue]) => {
    if (typeof sourceValue === "string" && sourceValue.trim().length > 0) {
      acc[key] = sourceValue.trim();
    }
    return acc;
  }, {});

  return Object.keys(normalized).length > 0 ? normalized : undefined;
};

const toAssetKey = (value: string | undefined): keyof AllocationWeights | null => {
  const normalized = getString(value, "").toLowerCase();
  if (normalized === "gold" || normalized === "btc" || normalized === "bond" || normalized === "commodity" || normalized === "cash") {
    return normalized;
  }

  return null;
};

const deriveRebalanceActions = (
  target: AllocationWeights,
  current: AllocationWeights,
  directActions?: RawMacroAction[],
  nestedActions?: RawMacroAction[]
): RebalanceAction[] => {
  const source = directActions ?? nestedActions;
  if (source && source.length > 0) {
    return source
      .map((item) => {
        const asset = toAssetKey(item.asset);
        if (!asset) {
          return null;
        }

        return {
          asset,
          action: item.action === "SELL" ? "SELL" : "BUY",
          delta: getNumber(item.delta ?? item.deviation, 0),
          current_weight: getNumber(item.current_weight, current[asset]),
          target_weight: getNumber(item.target_weight, target[asset]),
        };
      })
      .filter((item): item is RebalanceAction => item !== null);
  }

  return allocationKeys
    .map((asset) => {
      const delta = Number((target[asset] - current[asset]).toFixed(4));
      return {
        asset,
        action: (delta > 0 ? "BUY" : "SELL") as RebalanceAction["action"],
        delta,
        current_weight: current[asset],
        target_weight: target[asset],
      };
    })
    .filter((item) => Math.abs(item.delta) > 0.05);
};

export const normalizeMacroViewModel = (
  response: RawMacroResponse,
  horizon: string = "medium"
): MacroViewModel => {
  const metrics = normalizeMacroMetrics(response.metrics);
  const regime = deriveRegime(response);
  const macroScore = getNumber(response.macro_score, deriveMacroScore(metrics));
  const timestamp = pickTimestamp(response.last_updated, response.timestamp);
  const source = getOptionalString(response.source);
  const explicitStatus = getDataStatus(response.data_status);
  const fallbackFields = Array.isArray(response.fallback_fields)
    ? response.fallback_fields.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    : undefined;
  const sourceFields = Array.isArray(response.source_fields)
    ? response.source_fields.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    : undefined;
  const normalizedFieldSources = normalizeFieldSources(response.field_sources);
  const fallbackClusterDetected = isHardcodedFallbackCluster(metrics);
  const fallbackFieldSet = new Set<string>(fallbackFields ?? []);
  for (const [fieldName, fieldSource] of Object.entries(normalizedFieldSources ?? {})) {
    if (fieldSource.toLowerCase().includes("fallback")) {
      fallbackFieldSet.add(fieldName);
    }
  }
  if (fallbackClusterDetected) {
    for (const fieldName of MACRO_FALLBACK_CLUSTER_FIELDS) {
      fallbackFieldSet.add(fieldName);
    }
  }
  const forcedFieldSources = normalizedFieldSources
    ? { ...normalizedFieldSources }
    : fallbackClusterDetected
      ? Object.fromEntries(
          MACRO_FALLBACK_CLUSTER_FIELDS.map((fieldName) => [fieldName, "hardcoded_fallback_exact_match"])
        )
      : undefined;
  if (fallbackClusterDetected && forcedFieldSources) {
    for (const fieldName of MACRO_FALLBACK_CLUSTER_FIELDS) {
      forcedFieldSources[fieldName] = "hardcoded_fallback_exact_match";
    }
  }
  const normalizedFallbackFields = Array.from(fallbackFieldSet).sort();
  const hasFieldLevelFallback = normalizedFallbackFields.length > 0;
  const sourceIndicatesPartialFallback = isPartialFallbackSource(source);
  const sourceIndicatesFallback = hasFallbackSourceHint(source);
  const fallbackUsed =
    response.fallback_used === true ||
    response.fallback === true ||
    hasFieldLevelFallback ||
    explicitStatus === "FALLBACK" ||
    explicitStatus === "PARTIAL_FALLBACK" ||
    sourceIndicatesFallback;
  const dataStatus =
    hasFieldLevelFallback || explicitStatus === "PARTIAL_FALLBACK" || sourceIndicatesPartialFallback
      ? "PARTIAL_FALLBACK"
      : fallbackUsed
        ? "FALLBACK"
        : explicitStatus === "LIVE" || explicitStatus === "RECENT"
          ? timestamp
            ? explicitStatus
            : "UNKNOWN"
          : explicitStatus ?? (timestamp ? undefined : "UNKNOWN");
  const viewModelStatus =
    normalizedFallbackFields.length > 0 ? "PARTIAL_FALLBACK" : dataStatus;
  const unverifiedMacro = isUnverifiedMacroStatus(viewModelStatus);
  const derivedHedge = metrics.vix >= 22 || metrics.dxy >= 103 || metrics.us10y >= 4.6;
  const hedgeFromBackend = typeof response.hedge === "boolean";
  const hedgeSignal = hedgeFromBackend ? Boolean(response.hedge) : derivedHedge;
  const hedgeUnverified = unverifiedMacro && hedgeSignal;
  const hedge = unverifiedMacro
    ? hedgeSignal
    : hedgeFromBackend
      ? Boolean(response.hedge)
      : derivedHedge;
  const allocationHedge = unverifiedMacro ? false : hedgeFromBackend ? Boolean(response.hedge) : derivedHedge;
  const allocationHorizon =
    response.allocation_horizon === "short" || response.allocation_horizon === "medium" || response.allocation_horizon === "long"
      ? response.allocation_horizon
      : (horizon as MacroViewModel["allocation_horizon"]);
  const allocationProfile =
    getOptionalString(response.allocation_profile) ??
    (unverifiedMacro
      ? "fallback_illustrative"
      : allocationHorizon === "short"
        ? "defensive"
        : allocationHorizon === "long"
          ? "structural"
          : "balanced");
  const allocationBasis = getStringArray(response.allocation_basis);
  const warnings = mergeMacroWarnings(
    getStringArray(response.warnings),
    getOptionalString(response.warning) ? [getOptionalString(response.warning) as string] : undefined,
    unverifiedMacro ? ["Illustrative allocation based on incomplete/fallback macro data."] : undefined
  );
  const horizonAdjustments = normalizeAdjustmentWeights(response.horizon_adjustments);
  const target = hasCustomWeights(response.allocation_target)
    ? normalizeWeights(createWeights(response.allocation_target))
    : deriveAllocationTarget(regime, macroScore, allocationHedge, allocationHorizon ?? horizon);
  const current = deriveCurrentAllocation(target, response.allocation_current);
  const rebalanceActions = deriveRebalanceActions(target, current, response.rebalance_actions, response.rebalance_signal?.actions);
  let verified = response.verified ?? (viewModelStatus === "LIVE" || viewModelStatus === "RECENT");
  let live = response.live ?? (viewModelStatus === "LIVE");
  if (viewModelStatus !== "LIVE") {
    live = false;
  }
  if (viewModelStatus !== "LIVE" && viewModelStatus !== "RECENT") {
    verified = false;
  }
  if (normalizedFallbackFields.length > 0) {
    verified = false;
    live = false;
  }
  const warning =
    getOptionalString(response.warning) ??
    (viewModelStatus === "PARTIAL_FALLBACK"
      ? "Macro data is partially sourced from fallback values and is not fully verified."
      : viewModelStatus === "FALLBACK"
        ? "Macro data is fallback/hardcoded and not verified live market data."
        : viewModelStatus !== "LIVE" || verified !== true
          ? "Macro data is not fully verified."
          : undefined);

  return {
    status: getString(response.status, "ok"),
    source: getString(response.source, fallbackUsed ? "hardcoded_fallback" : "dashboard-gateway"),
    timestamp,
    last_updated: timestamp,
    fallback_used: fallbackUsed,
    data_status: viewModelStatus,
    fallback: fallbackUsed,
    verified,
    live,
    warning,
    fallback_fields: normalizedFallbackFields,
    source_fields: sourceFields,
    field_sources: forcedFieldSources,
    regime,
    macro_score: macroScore,
    hedge,
    hedge_unverified: hedgeUnverified,
    hedge_source: hedgeFromBackend
      ? "backend"
      : hedgeUnverified
        ? "derived_from_unverified_macro"
        : "derived",
    position_size_pct: getNumber(response.position_size_pct, regime.includes("RISK_OFF") ? 0.1 : regime.includes("LIQUIDITY") ? 0.25 : 0.15),
    stop_loss_pct: getNumber(response.stop_loss_pct, regime.includes("RISK_OFF") ? 0.06 : regime.includes("LIQUIDITY") ? 0.12 : 0.08),
    allocation_target: target,
    allocation_current: current,
    allocation_horizon: allocationHorizon,
    allocation_profile: allocationProfile,
    allocation_basis: allocationBasis,
    warnings,
    horizon_adjustments: horizonAdjustments,
    rebalance_required: unverifiedMacro ? false : response.rebalance_required ?? response.rebalance_signal?.rebalance_required ?? rebalanceActions.length > 0,
    rebalance_actions: unverifiedMacro ? [] : rebalanceActions,
    metrics,
    error: response.error,
    asset_metadata: response.asset_metadata,
    real_estate_decision: response.real_estate_decision,
  };
};

const normalizeCriteria = (criteria?: Partial<ConsensusCriteria>, greenLight?: boolean): ConsensusCriteria => ({
  regime_suitable: criteria?.regime_suitable ?? Boolean(greenLight),
  dynamic_threshold_pass: criteria?.dynamic_threshold_pass ?? Boolean(greenLight),
  modules_agree_3plus: criteria?.modules_agree_3plus ?? Boolean(greenLight),
  multi_tf_aligned: criteria?.multi_tf_aligned ?? Boolean(greenLight),
  cbr_edge_valid: criteria?.cbr_edge_valid ?? true,
  liquidity_ok: criteria?.liquidity_ok ?? true,
  risk_multiplier_ok: criteria?.risk_multiplier_ok ?? true,
  event_risk_ok: criteria?.event_risk_ok ?? true,
});

const normalizeComponents = (gateway: RawConsensusGatewayResponse): ConsensusResponse["components"] => ({
  touche: {
    score: getNumber(gateway.components?.touche?.score, 0.5),
    weight: getNumber(gateway.components?.touche?.weight, getNumber(gateway.weights?.touche, 0.5)),
  },
  fundamental: {
    score: getNumber(gateway.components?.fundamental?.score, 0.5),
    weight: getNumber(gateway.components?.fundamental?.weight, getNumber(gateway.weights?.fundamental, 0.35)),
  },
  news: {
    score: getNumber(gateway.components?.news?.score, 0.5),
    weight: getNumber(gateway.components?.news?.weight, getNumber(gateway.weights?.news, 0.15)),
  },
});

const normalizeModuleScores = (gateway: RawConsensusGatewayResponse, process: RawConsensusProcessResponse | null): ModuleScores => ({
  touche: getNumber(process?.module_scores?.touche, getNumber(gateway.components?.touche?.score, 0.5)),
  fundamental: getNumber(process?.module_scores?.fundamental, getNumber(gateway.components?.fundamental?.score, 0.5)),
  news: getNumber(process?.module_scores?.news, getNumber(gateway.components?.news?.score, 0.5)),
  sentinel: getNumber(process?.module_scores?.sentinel, 0.5),
  quantum: getNumber(process?.module_scores?.quantum, 0.5),
});

const normalizeModuleWeights = (process: RawConsensusProcessResponse | null): ModuleWeights => ({
  touche: getNumber(process?.module_weights?.touche, 0.4),
  fundamental: getNumber(process?.module_weights?.fundamental, 0.3),
  news: getNumber(process?.module_weights?.news, 0.15),
  sentinel: getNumber(process?.module_weights?.sentinel, 0.1),
  quantum: getNumber(process?.module_weights?.quantum, 0.05),
});

const normalizeCbrSummary = (process: RawConsensusProcessResponse | null): CBRSummary => ({
  sample_count: Math.max(0, Math.round(getNumber(process?.cbr?.sample_count, 20))),
  win_rate_pct: getNumber(process?.cbr?.win_rate_pct, 60),
  similarity_score: getNumber(process?.cbr?.similarity_score, 0.7),
  include_in_consensus: process?.cbr?.include_in_consensus ?? true,
  is_historical_weak: process?.cbr?.is_historical_weak ?? false,
  confidence_modifier: getNumber(process?.cbr?.confidence_modifier, 1),
  reason: getString(process?.cbr?.reason, "cbr_edge_valid"),
});

const normalizeMultiTf = (process: RawConsensusProcessResponse | null, action: string): MultiTfSummary => ({
  is_valid: process?.multi_tf?.is_valid ?? true,
  final_signal: getString(process?.multi_tf?.final_signal, action),
  reason: getString(process?.multi_tf?.reason, "aligned"),
  holding_period_hours: getNumber(process?.multi_tf?.holding_period_hours, 24),
});

const normalizeSentinel = (process: RawConsensusProcessResponse | null): SentinelSummary => ({
  risk_multiplier: getNumber(process?.sentinel?.risk_multiplier, 0.8),
  regime_context: {
    event_risk_score: getNumber(process?.sentinel?.regime_context?.event_risk_score, 0.18),
    hours_to_event: getNumber(process?.sentinel?.regime_context?.hours_to_event, 72),
    is_low_risk: process?.sentinel?.regime_context?.is_low_risk ?? true,
    source: getString(process?.sentinel?.regime_context?.source, "derived"),
  },
});

const CONSENSUS_STATUS_PRIORITY: Array<NonNullable<ConsensusResponse["data_status"]>> = [
  "FALLBACK",
  "MOCK",
  "MISSING",
  "STALE",
  "UNKNOWN",
  "PARTIAL_FALLBACK",
  "RECENT",
  "LIVE",
];

const aggregateConsensusStatus = (
  statuses: Array<ConsensusResponse["data_status"] | undefined>
): ConsensusResponse["data_status"] => {
  const normalized = statuses.filter((status): status is NonNullable<ConsensusResponse["data_status"]> => Boolean(status));
  return CONSENSUS_STATUS_PRIORITY.find((status) => normalized.includes(status)) ?? "UNKNOWN";
};

const mergeWarnings = (...warningLists: Array<string[] | undefined>): string[] | undefined => {
  const merged: string[] = [];
  for (const warningList of warningLists) {
    for (const warning of warningList ?? []) {
      if (warning && !merged.includes(warning)) {
        merged.push(warning);
      }
    }
  }

  return merged.length > 0 ? merged : undefined;
};

const normalizeConsensusModuleSource = (
  raw: RawConsensusModuleSource | undefined,
  defaults: {
    module: keyof ConsensusModuleSources;
    service: string;
    source: string;
    sourceData: string;
    value: number;
  }
): ConsensusModuleSource => {
  const missingSource = raw === undefined;
  const timestamp = pickTimestamp(raw?.timestamp);
  const fallbackUsed = raw?.fallback_used === true || missingSource;
  const dataStatus =
    getDataStatus(raw?.data_status) ??
    (missingSource ? "FALLBACK" : fallbackUsed ? "FALLBACK" : timestamp ? "LIVE" : "UNKNOWN");
  const assetSpecific = raw?.asset_specific ?? false;
  const sharedScore = raw?.shared_score ?? false;
  const warnings = mergeWarnings(
    getStringArray(raw?.warnings),
    missingSource ? ["Default neutral module score; module provenance unavailable."] : undefined
  );

  return {
    module: getString(raw?.module, defaults.module),
    service: getString(raw?.service, defaults.service),
    source: getString(raw?.source, defaults.source),
    source_data: getString(raw?.source_data, defaults.sourceData),
    timestamp,
    timestamp_source: getString(raw?.timestamp_source, timestamp ? "source_timestamp" : "none"),
    data_status: dataStatus ?? "UNKNOWN",
    fallback_used: fallbackUsed,
    verified: raw?.verified ?? (((dataStatus === "LIVE" || dataStatus === "RECENT") && !fallbackUsed && assetSpecific && !sharedScore)),
    asset_specific: assetSpecific,
    shared_score: sharedScore,
    value: getNumber(raw?.value, defaults.value),
    warnings: warnings ?? [],
  };
};

const normalizeConsensusModuleSources = (
  gateway: RawConsensusGatewayResponse,
  process: RawConsensusProcessResponse | null,
  moduleScores: ModuleScores,
  gatewayOnly: boolean
): ConsensusModuleSources => {
  const gatewaySources = gateway.module_sources ?? {};
  const processSources = process?.module_sources ?? {};

  const pickSource = (
    processKey: keyof ConsensusModuleSources,
    gatewayKey: keyof RawConsensusModuleSources | null,
    defaults: { service: string; source: string; sourceData: string; value: number }
  ): ConsensusModuleSource =>
    normalizeConsensusModuleSource(
      processSources[processKey] ?? (gatewayKey ? gatewaySources[gatewayKey] : undefined),
      {
        module: processKey,
        service: defaults.service,
        source: defaults.source,
        sourceData: defaults.sourceData,
        value: defaults.value,
      }
    );

  return {
    technical: pickSource("technical", "technical", {
      service: "dashboard-gateway",
      source: gatewayOnly ? "gateway_only_missing_module" : "missing_module_source",
      sourceData: "technical",
      value: moduleScores.touche,
    }),
    fundamental: pickSource("fundamental", "fundamental", {
      service: "dashboard-gateway",
      source: gatewayOnly ? "gateway_only_missing_module" : "missing_module_source",
      sourceData: "fundamental",
      value: moduleScores.fundamental,
    }),
    news: pickSource("news", "news", {
      service: "dashboard-gateway",
      source: gatewayOnly ? "gateway_only_missing_module" : "missing_module_source",
      sourceData: "news",
      value: moduleScores.news,
    }),
    sentinel: pickSource("sentinel", null, {
      service: "consensus-engine",
      source: gatewayOnly ? "gateway_only_missing_module" : "missing_module_source",
      sourceData: "sentinel",
      value: moduleScores.sentinel,
    }),
    quantum: pickSource("quantum", null, {
      service: "consensus-engine",
      source: gatewayOnly ? "gateway_only_missing_module" : "missing_module_source",
      sourceData: "quantum",
      value: moduleScores.quantum,
    }),
  };
};

const normalizeConsensus = (
  gateway: RawConsensusGatewayResponse,
  process: RawConsensusProcessResponse | null,
  gatewayOnly: boolean = false
): ConsensusResponse => {
  const action = process?.action ?? gateway.action ?? "HOLD";
  const moduleScores = normalizeModuleScores(gateway, process);
  const moduleWeights = normalizeModuleWeights(process);
  const failedCriteria = process?.failed_criteria ?? [];
  const moduleSources = normalizeConsensusModuleSources(gateway, process, moduleScores, gatewayOnly);
  const timestamp = pickTimestamp(
    process?.last_updated,
    process?.timestamp,
    gateway.last_updated,
    gateway.timestamp,
    moduleSources.technical.timestamp,
    moduleSources.fundamental.timestamp,
    moduleSources.news.timestamp,
    moduleSources.sentinel.timestamp,
    moduleSources.quantum.timestamp
  );
  const fallbackUsed =
    gateway.fallback_used === true ||
    process?.fallback_used === true ||
    gatewayOnly ||
    Object.values(moduleSources).some((moduleSource) => moduleSource.fallback_used);
  const source = getString(
    process?.source ?? gateway.source,
    gatewayOnly ? "gateway_only" : "dashboard-gateway"
  );
  const dataStatus = aggregateConsensusStatus([
    getDataStatus(process?.data_status),
    getDataStatus(gateway.data_status),
    moduleSources.technical.data_status,
    moduleSources.fundamental.data_status,
    moduleSources.news.data_status,
    moduleSources.sentinel.data_status,
    moduleSources.quantum.data_status,
    fallbackUsed ? "FALLBACK" : undefined,
    timestamp ? undefined : "UNKNOWN",
  ]);
  const warnings = mergeWarnings(
    getStringArray(gateway.warnings),
    getStringArray(process?.warnings),
    moduleSources.technical.warnings,
    moduleSources.fundamental.warnings,
    moduleSources.news.warnings,
    moduleSources.sentinel.warnings,
    moduleSources.quantum.warnings,
    dataStatus && ["STALE", "FALLBACK", "MOCK", "MISSING", "UNKNOWN"].includes(dataStatus)
      ? ["Signal is not verified because source data is stale/fallback/mock."]
      : undefined
  );
  const verified =
    dataStatus !== undefined &&
    ["LIVE", "RECENT"].includes(dataStatus) &&
    gateway.verified !== false &&
    process?.verified !== false &&
    Object.values(moduleSources).every((moduleSource) => moduleSource.verified);
  const fiveModuleScore = getNumber(
    process?.five_module_score,
    Number((
      (moduleScores.touche * moduleWeights.touche) +
      (moduleScores.fundamental * moduleWeights.fundamental) +
      (moduleScores.news * moduleWeights.news) +
      (moduleScores.sentinel * moduleWeights.sentinel) +
      (moduleScores.quantum * moduleWeights.quantum)
    ).toFixed(4))
  );

  return {
    asset: getString(
      process?.asset ?? gateway.asset,
      getString(gateway.symbol, "BTC/USDT").replace("/USDT", "").replace("/", "")
    ),
    action,
    confidence: getNumber(process?.confidence, getNumber(gateway.confidence, 0.5)),
    weighted_score: getNumber(gateway.weighted_score, fiveModuleScore),
    green_light: process?.green_light ?? false,
    green_light_reason: failedCriteria.length > 0 ? failedCriteria.join(", ") : "all_criteria_pass",
    failed_criteria: failedCriteria,
    criteria: normalizeCriteria(process?.criteria, process?.green_light),
    module_scores: moduleScores,
    module_weights: moduleWeights,
    components: normalizeComponents(gateway),
    five_module_score: fiveModuleScore,
    position_size: getNumber(process?.position_size, 0),
    symbol: getString(process?.symbol ?? gateway.symbol, "BTC/USDT"),
    timeframe: getString(process?.timeframe ?? gateway.timeframe, "1h"),
    source,
    last_updated: timestamp,
    fallback_used: fallbackUsed,
    data_status: dataStatus,
    verified,
    warnings,
    module_sources: moduleSources,
    timestamp,
    cbr: normalizeCbrSummary(process),
    multi_tf: normalizeMultiTf(process, action),
    sentinel: normalizeSentinel(process),
    // v7.0 pass-through
    confidence_interval: process?.confidence_interval,
    meta_score: process?.meta_score,
    correlation_penalty: process?.correlation_penalty,
    correlation_penalized_pairs: process?.correlation_penalized_pairs,
    attribution_ref: process?.attribution_ref,
    adjusted_module_weights: process?.adjusted_module_weights
      ? {
          touche: getNumber(process.adjusted_module_weights.touche, moduleWeights.touche),
          fundamental: getNumber(process.adjusted_module_weights.fundamental, moduleWeights.fundamental),
          news: getNumber(process.adjusted_module_weights.news, moduleWeights.news),
          sentinel: getNumber(process.adjusted_module_weights.sentinel, moduleWeights.sentinel),
          quantum: getNumber(process.adjusted_module_weights.quantum, moduleWeights.quantum),
        }
      : undefined,
  };
};

const getAttributionModule = (
  modules: Record<string, RawAttributionModule> | undefined,
  aliases: string[]
): AttributionModule => {
  const found = aliases.map((alias) => modules?.[alias]).find((item) => item !== undefined);

  return {
    total_trades: Math.max(0, Math.round(getNumber(found?.total_trades, 0))),
    win_rate: getNumber(found?.win_rate, 0),
    attribution_score: getNumber(found?.attribution_score, 0),
    role: getString(found?.role, "Neutral"),
  };
};

const normalizeAttribution = (response: RawAttributionResponse): AttributionResponse => ({
  period: getString(response.period, "7d"),
  modules: {
    touche: getAttributionModule(response.modules, ["touche", "touche_ai"]),
    fundamental: getAttributionModule(response.modules, ["fundamental", "fundamental_ai"]),
    sentinel: getAttributionModule(response.modules, ["sentinel", "sentinel_ai"]),
    news: getAttributionModule(response.modules, ["news", "news_ai"]),
    quantum: getAttributionModule(response.modules, ["quantum", "quantum_ai"]),
  },
});

const normalizeCbr = (response: RawHistoricalEdgeResponse): CBRResponse => {
  const matches: CBRMatch[] = (response.matches ?? []).map((match, index) => ({
    id: getString(match.id, `match-${index + 1}`),
    label: getString(match.label, `Edge sample ${index + 1}`),
    similarity: getNumber(match.similarity, getNumber(response.similarity_score, 0.7)),
    outcome: match.outcome ?? "NEUTRAL",
    regime: getString(match.regime, "historical_edge"),
    note: getString(match.note, getString(response.reason, "historical_edge_context")),
  }));

  return {
    symbol: getString(response.symbol, "BTC"),
    similarity_score: getNumber(response.similarity_score, 0.7),
    sample_count: Math.max(0, Math.round(getNumber(response.sample_count, 20))),
    win_rate_pct: getNumber(response.win_rate_pct, 60),
    include_in_consensus: response.include_in_consensus ?? true,
    is_historical_weak: response.is_historical_weak ?? false,
    confidence_modifier: getNumber(response.confidence_modifier, 1),
    reason: getString(response.reason, "cbr_edge_valid"),
    matches,
  };
};

export const fetchMacro = async (
  horizon: string = "medium",
  options: RequestOptions = {}
): Promise<MacroViewModel> => {
  const response = await gatewayClient.get<RawMacroResponse>("/api/macro", {
    params: { horizon },
    signal: options.signal,
    timeout: 5000,
  });
  return normalizeMacroViewModel(response.data, horizon);
};

export const fetchConsensus = async (
  symbol: string = "BTC/USDT",
  timeframe: string = "1h",
  options: RequestOptions = {},
  horizon: string = "medium"
): Promise<ConsensusResponse> => {
  const compactSymbol = symbol.replace("/USDT", "").replace("/", "");

  console.log("[apiV2] Fetching", compactSymbol, horizon);

  const [gatewaySettled, processSettled] = await Promise.allSettled([
    gatewayClient.get<RawConsensusGatewayResponse>("/api/consensus", {
      params: { symbol, timeframe, horizon },
      signal: options.signal,
    }),
    consensusClient.post<RawConsensusProcessResponse>(
      "/process",
      { symbol: compactSymbol, timeframe, horizon },
      { signal: options.signal }
    ),
  ]);

  if (gatewaySettled.status === "rejected") {
    const err =
      gatewaySettled.reason instanceof Error
        ? gatewaySettled.reason
        : new Error(String(gatewaySettled.reason));
    console.warn(`[apiV2] Gateway failed for ${symbol}:`, err.message);
    throw err;
  }

  if (processSettled.status === "rejected") {
    console.warn(
      `[apiV2] /process failed for ${symbol} (gateway-only fallback):`,
      processSettled.reason instanceof Error
        ? processSettled.reason.message
        : processSettled.reason
    );
  }

  return normalizeConsensus(
    gatewaySettled.value.data,
    processSettled.status === "fulfilled" ? processSettled.value.data : null,
    processSettled.status === "rejected"
  );
};

export const fetchExitAttribution = async (
  period: string = "7d",
  options: RequestOptions = {}
): Promise<AttributionResponse> => {
  const response = await analyzerClient.get<RawAttributionResponse>("/dashboard/exit_attribution", {
    params: { period },
    signal: options.signal,
  });

  return normalizeAttribution(response.data);
};

export const fetchHistoricalEdge = async (
  symbol: string = "BTC",
  sampleCount: number = 20,
  winRatePct: number = 60,
  similarityScore: number = 0.7,
  options: RequestOptions = {}
): Promise<CBRResponse> => {
  const response = await consensusClient.get<RawHistoricalEdgeResponse>("/consensus/historical_edge", {
    params: {
      symbol,
      sample_count: sampleCount,
      win_rate_pct: winRatePct,
      similarity_score: similarityScore,
    },
    signal: options.signal,
  });

  return normalizeCbr(response.data);
};

export const fetchWeights = async (options: RequestOptions = {}): Promise<WeightsResponse> => {
  const response = await consensusClient.get<WeightsResponse>("/weights", { signal: options.signal });
  const data = response.data ?? {};
  return {
    weights: {
      touche: getNumber((data.weights as ModuleWeights | undefined)?.touche, 0.35),
      fundamental: getNumber((data.weights as ModuleWeights | undefined)?.fundamental, 0.30),
      news: getNumber((data.weights as ModuleWeights | undefined)?.news, 0.20),
      sentinel: getNumber((data.weights as ModuleWeights | undefined)?.sentinel, 0.10),
      quantum: getNumber((data.weights as ModuleWeights | undefined)?.quantum, 0.05),
    },
    drift_total: getNumber(data.drift_total, 0),
    drift_limit: getNumber(data.drift_limit, 0.15),
    drift_frozen: data.drift_frozen ?? false,
    backup_exists: data.backup_exists ?? false,
    week_start: data.week_start,
  };
};

export const fetchTradeAttribution = async (
  trade_pnl: number,
  entry_scores: Record<string, number>,
  exit_scores: Record<string, number>,
  symbol: string = "UNKNOWN",
  holding_period: number = 0,
  options: RequestOptions = {}
): Promise<TradeAttributionResult> => {
  const response = await consensusClient.post<TradeAttributionResult>(
    "/attribution/calculate",
    { trade_pnl, entry_scores, exit_scores, symbol, holding_period },
    { signal: options.signal }
  );
  const data = response.data ?? {};
  return {
    attribution_ref: data.attribution_ref ?? "",
    winning_modules: data.winning_modules ?? [],
    losing_modules: data.losing_modules ?? [],
    contribution_pct: data.contribution_pct ?? {},
    error: data.error,
  };
};

/**
 * Fetch consensus for multiple assets in parallel with retry logic.
 * Max 3 retries per asset, 2s exponential backoff.
 * Failed assets return fallback HOLD response.
 * horizon — "short" | "medium" | "long" — forwarded to all downstream services.
 */
export const fetchConsensusBatch = async (
  symbols: string[] = ["BTC", "XAU", "EMX", "HG", "VIX"],
  timeframe: string = "1d",
  horizon: string = "medium",
  options: RequestOptions = {}
): Promise<Record<string, ConsensusResponse>> => {
  const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

  const fetchWithRetry = async (symbol: string): Promise<[string, ConsensusResponse]> => {
    const compactSymbol = symbol.replace("/USDT", "").replace("/", "");
    let lastError: Error | null = null;

    for (let attempt = 1; attempt <= 3; attempt++) {
      try {
        console.log(`[apiV2] Fetching ${compactSymbol} horizon=${horizon} (attempt ${attempt})`);

        const [gatewaySettled, processSettled] = await Promise.allSettled([
          gatewayClient.get<RawConsensusGatewayResponse>("/api/consensus", {
            params: { symbol, timeframe, horizon },
            signal: options.signal,
          }),
          consensusClient.post<RawConsensusProcessResponse>(
            "/process",
            { symbol: compactSymbol, timeframe, horizon },
            { signal: options.signal }
          ),
        ]);

        if (gatewaySettled.status === "rejected") throw gatewaySettled.reason;

        if (processSettled.status === "rejected") {
          console.warn(
            `[apiV2] /process failed for ${symbol} (gateway-only):`,
            processSettled.reason instanceof Error
              ? processSettled.reason.message
              : processSettled.reason
          );
        }

        return [
          symbol,
          normalizeConsensus(
            gatewaySettled.value.data,
            processSettled.status === "fulfilled" ? processSettled.value.data : null,
            processSettled.status === "rejected"
          ),
        ];
      } catch (err) {
        lastError = err instanceof Error ? err : new Error(String(err));
        if (attempt < 3) {
          const backoffMs = 2000 * Math.pow(2, attempt - 1);
          await sleep(backoffMs);
        }
      }
    }

    console.warn(`[apiV2] All retries exhausted for ${symbol}:`, lastError?.message);
    return [
      symbol,
      {
        asset: symbol.replace("/USDT", "").replace("/", ""),
        action: "HOLD" as const,
        confidence: 0,
        weighted_score: 0,
        verified: false,
        warnings: [
          "Signal is not verified because source data is stale/fallback/mock.",
          "Client fallback response used after consensus fetch retries failed.",
        ],
        module_sources: {
          technical: normalizeConsensusModuleSource(undefined, {
            module: "technical",
            service: "client",
            source: "client_fallback",
            sourceData: "fetch_failed",
            value: 0,
          }),
          fundamental: normalizeConsensusModuleSource(undefined, {
            module: "fundamental",
            service: "client",
            source: "client_fallback",
            sourceData: "fetch_failed",
            value: 0,
          }),
          news: normalizeConsensusModuleSource(undefined, {
            module: "news",
            service: "client",
            source: "client_fallback",
            sourceData: "fetch_failed",
            value: 0,
          }),
          sentinel: normalizeConsensusModuleSource(undefined, {
            module: "sentinel",
            service: "client",
            source: "client_fallback",
            sourceData: "fetch_failed",
            value: 0,
          }),
          quantum: normalizeConsensusModuleSource(undefined, {
            module: "quantum",
            service: "client",
            source: "client_fallback",
            sourceData: "fetch_failed",
            value: 0,
          }),
        },
        green_light: false,
        green_light_reason: "fetch_failed",
        failed_criteria: ["network_error"],
        criteria: normalizeCriteria(undefined, false),
        module_scores: { touche: 0, fundamental: 0, news: 0, sentinel: 0, quantum: 0 },
        module_weights: { touche: 0, fundamental: 0, news: 0, sentinel: 0, quantum: 0 },
        components: {
          touche: { score: 0, weight: 0 },
          fundamental: { score: 0, weight: 0 },
          news: { score: 0, weight: 0 },
        },
        five_module_score: 0,
        position_size: 0,
        symbol,
        timeframe,
        source: "client_fallback",
        last_updated: null,
        fallback_used: true,
        data_status: "FALLBACK",
        timestamp: null,
        cbr: { sample_count: 0, win_rate_pct: 0, similarity_score: 0, include_in_consensus: false, is_historical_weak: true, confidence_modifier: 0.5, reason: "fetch_failed" },
        multi_tf: { is_valid: false, final_signal: "HOLD", reason: "fetch_failed", holding_period_hours: 0 },
        sentinel: { risk_multiplier: 0, regime_context: { event_risk_score: 0, hours_to_event: 0, is_low_risk: false, source: "error" } },
      },
    ];
  };

  const results = await Promise.all(symbols.map((s) => fetchWithRetry(s)));
  return Object.fromEntries(results);
};
