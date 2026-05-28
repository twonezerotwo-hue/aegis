export type DataStatus =
  | "LIVE"
  | "RECENT"
  | "STALE"
  | "PARTIAL_FALLBACK"
  | "FALLBACK"
  | "MOCK"
  | "MISSING"
  | "UNKNOWN";

export interface FreshnessOptions {
  maxAgeSeconds?: number;
  liveAgeSeconds?: number;
}

export type FreshnessLike = {
  data_status?: unknown;
  status?: unknown;
  source?: unknown;
  fallback?: unknown;
  fallback_used?: unknown;
  mock?: unknown;
  is_mock?: unknown;
  isMock?: unknown;
  timestamp?: unknown;
  last_updated?: unknown;
  updated_at?: unknown;
  updatedAt?: unknown;
  generated_at?: unknown;
  created_at?: unknown;
} | null | undefined;

const VALID_STATUSES: DataStatus[] = [
  "LIVE",
  "RECENT",
  "STALE",
  "PARTIAL_FALLBACK",
  "FALLBACK",
  "MOCK",
  "MISSING",
  "UNKNOWN",
];

const MOCK_SOURCE_HINTS = ["mock", "demo", "sample", "static"];
const FALLBACK_SOURCE_HINTS = ["fallback", "cache", "gateway_only", "missing_metric", "hardcoded_fallback"];

const DEFAULT_MAX_AGE_SECONDS = 5 * 60;
const DEFAULT_LIVE_AGE_SECONDS = 60;

const normalizeStatus = (value: unknown): DataStatus | null => {
  if (typeof value !== "string") {
    return null;
  }

  const upper = value.trim().toUpperCase();
  return VALID_STATUSES.includes(upper as DataStatus) ? (upper as DataStatus) : null;
};

const hasSourceHint = (source: string | null, hints: string[]): boolean => {
  if (!source) {
    return false;
  }

  const normalized = source.toLowerCase();
  return hints.some((hint) => normalized.includes(hint));
};

const toTimestamp = (value: unknown): string | null => {
  if (typeof value !== "string") {
    return null;
  }

  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
};

export const getDataTimestamp = (data: FreshnessLike): string | null => {
  if (!data) {
    return null;
  }

  return (
    toTimestamp(data.last_updated) ??
    toTimestamp(data.updatedAt) ??
    toTimestamp(data.updated_at) ??
    toTimestamp(data.timestamp) ??
    toTimestamp(data.generated_at) ??
    toTimestamp(data.created_at)
  );
};

export const getDataSource = (data: FreshnessLike): string | null => {
  if (!data || typeof data.source !== "string") {
    return null;
  }

  const trimmed = data.source.trim();
  return trimmed.length > 0 ? trimmed : null;
};

export const isStale = (
  timestamp: string | null | undefined,
  maxAgeSeconds: number,
  nowMs: number = Date.now()
): boolean => {
  if (!timestamp) {
    return true;
  }

  const parsed = Date.parse(timestamp);
  if (!Number.isFinite(parsed)) {
    return true;
  }

  return nowMs - parsed > maxAgeSeconds * 1000;
};

export const formatDataAge = (
  timestamp: string | null | undefined,
  nowMs: number = Date.now()
): string => {
  if (!timestamp) {
    return "timestamp unavailable";
  }

  const parsed = Date.parse(timestamp);
  if (!Number.isFinite(parsed)) {
    return "timestamp invalid";
  }

  const ageMs = Math.max(0, nowMs - parsed);
  const ageSeconds = Math.floor(ageMs / 1000);

  if (ageSeconds < 5) {
    return "just now";
  }

  if (ageSeconds < 60) {
    return `${ageSeconds}s ago`;
  }

  const ageMinutes = Math.floor(ageSeconds / 60);
  if (ageMinutes < 60) {
    return `${ageMinutes}m ago`;
  }

  const ageHours = Math.floor(ageMinutes / 60);
  if (ageHours < 24) {
    const remMinutes = ageMinutes % 60;
    return remMinutes > 0 ? `${ageHours}h ${remMinutes}m ago` : `${ageHours}h ago`;
  }

  const ageDays = Math.floor(ageHours / 24);
  return `${ageDays}d ago`;
};

export const classifyDataStatus = (
  data: FreshnessLike,
  options: FreshnessOptions = {}
): DataStatus => {
  if (data == null) {
    return "MISSING";
  }

  const explicitStatus = normalizeStatus(data.data_status) ?? normalizeStatus(data.status);
  if (explicitStatus) {
    return explicitStatus;
  }

  const source = getDataSource(data);

  if (
    data.mock === true ||
    data.is_mock === true ||
    data.isMock === true ||
    hasSourceHint(source, MOCK_SOURCE_HINTS)
  ) {
    return "MOCK";
  }

  if (
    data.fallback === true ||
    data.fallback_used === true ||
    hasSourceHint(source, FALLBACK_SOURCE_HINTS)
  ) {
    return "FALLBACK";
  }

  const timestamp = getDataTimestamp(data);
  if (!timestamp) {
    return "UNKNOWN";
  }

  const parsed = Date.parse(timestamp);
  if (!Number.isFinite(parsed)) {
    return "UNKNOWN";
  }

  const maxAgeSeconds = options.maxAgeSeconds ?? DEFAULT_MAX_AGE_SECONDS;
  const liveAgeSeconds = Math.min(
    maxAgeSeconds,
    options.liveAgeSeconds ?? DEFAULT_LIVE_AGE_SECONDS
  );
  const ageMs = Math.max(0, Date.now() - parsed);

  if (ageMs > maxAgeSeconds * 1000) {
    return "STALE";
  }

  if (ageMs <= liveAgeSeconds * 1000) {
    return "LIVE";
  }

  return "RECENT";
};
