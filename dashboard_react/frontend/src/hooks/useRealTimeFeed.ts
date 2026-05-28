/**
 * hooks/useRealTimeFeed.ts
 * AEGIS v7.0 — Enhanced SSE hook for Faz 4
 *
 * Extends useRealTimeData with:
 *   - event:snapshot  → same state shape as useRealTimeData
 *   - event:weights   → dispatches SET_WEIGHTS to ConsensusStore
 *   - event:alert     → surfaces latestAlert (deduped by type+ts)
 *   - event:ping      → no-op (keeps connection alive)
 *
 * Reconnect: exponential backoff 1s → 2s → 4s (2^n), capped at 5 failures
 * After 5 failures: polling fallback via direct API calls every 5 s
 */

import { useEffect, useRef, useState } from "react";
import {
  fetchConsensus,
  fetchExitAttribution,
  fetchHistoricalEdge,
  fetchMacro,
} from "../services/apiV2";
import type { SystemSnapshot, SystemState, WeightsResponse } from "../types/dashboardV2";
import { useConsensusStore } from "../store/consensusStore";
import { getDataTimestamp, type FreshnessLike } from "../utils/dataFreshness";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8502";
const MAX_RETRIES = 5;
const FALLBACK_INTERVAL_MS = 5000;

export type LiveConnectionStatus = "live" | "reconnecting" | "fallback";

export interface AlertEvent {
  type: string;
  message: string;
  severity: "info" | "warning" | "critical";
  ts: string;
}

interface LiveFeedPayload {
  timestamp?: string | null;
  last_updated?: string | null;
  source?: string;
  fallback_used?: boolean;
  data_status?: string;
  error?: string;
  system_health?: { status?: string; services?: Record<string, string> };
  snapshot?: SystemSnapshot;
}

interface WeightsPayload {
  symbol?: string;
  weights?: Record<string, number>;
  drift_total?: number;
  drift_limit?: number;
  drift_frozen?: boolean;
  backup_exists?: boolean;
  week_start?: string;
  frozen_reason?: string | null;
  updated_at?: string;
}

interface AlertPayload {
  alert_type?: string;
  message?: string;
  severity?: string;
  ts?: string;
}

export interface RealTimeFeedState extends SystemState {
  connectionStatus: LiveConnectionStatus;
  reconnectAttempts: number;
  connectionMessage: string | null;
  systemHealth: string;
  weights: WeightsResponse | null;
  latestAlert: AlertEvent | null;
}

const buildInitialState = (): RealTimeFeedState => ({
  consensus: null,
  macro: null,
  attribution: null,
  cbr: null,
  loading: true,
  error: null,
  lastUpdated: null,
  lastKnownState: null,
  connectionStatus: "reconnecting",
  reconnectAttempts: 0,
  connectionMessage: "Live stream baglantisi kuruluyor.",
  systemHealth: "AWAITING DATA",
  weights: null,
  latestAlert: null,
});

const pickLatestTimestamp = (...sources: FreshnessLike[]): string | null => {
  const timestamps = sources
    .map((item) => getDataTimestamp(item))
    .filter((value): value is string => typeof value === "string" && Number.isFinite(Date.parse(value)))
    .sort((left, right) => Date.parse(right) - Date.parse(left));

  return timestamps[0] ?? null;
};

export const useRealTimeFeed = (
  symbol: string = "BTC/USDT",
  timeframe: string = "1h",
  period: string = "7d",
  horizon: string = "medium"
): RealTimeFeedState => {
  const [state, setState] = useState<RealTimeFeedState>(buildInitialState);
  const { dispatch: storeDispatch } = useConsensusStore();

  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const fallbackIntervalRef = useRef<number | null>(null);
  const retryCountRef = useRef<number>(0);
  const lastKnownStateRef = useRef<SystemSnapshot | null>(null);
  const fallbackStartedRef = useRef<boolean>(false);
  const lastAlertKeyRef = useRef<string>("");

  useEffect(() => {
    let isActive = true;
    lastKnownStateRef.current = null;
    fallbackStartedRef.current = false;
    lastAlertKeyRef.current = "";
    retryCountRef.current = 0;
    setState(buildInitialState());

    const clearReconnectTimeout = () => {
      if (reconnectTimeoutRef.current !== null) {
        window.clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };

    const clearFallbackInterval = () => {
      if (fallbackIntervalRef.current !== null) {
        window.clearInterval(fallbackIntervalRef.current);
        fallbackIntervalRef.current = null;
      }
    };

    const closeEventSource = () => {
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
    };

    // ── Fallback polling ───────────────────────────────────────────────────────

    const runFallbackRefresh = async () => {
      const settled = await Promise.allSettled([
        fetchMacro(horizon),
        fetchConsensus(symbol, timeframe, {}, horizon),
        fetchExitAttribution(period),
      ]);

      if (!isActive) return;

      try {
        const macro = settled[0].status === "fulfilled" ? settled[0].value : null;
        const consensus = settled[1].status === "fulfilled" ? settled[1].value : null;
        const attribution = settled[2].status === "fulfilled" ? settled[2].value : null;
        let cbr = lastKnownStateRef.current?.cbr ?? null;

        if (consensus) {
          try {
            cbr = await fetchHistoricalEdge(
              consensus.symbol.replace("/USDT", "").replace("/", ""),
              consensus.cbr.sample_count,
              consensus.cbr.win_rate_pct,
              consensus.cbr.similarity_score
            );
          } catch (cbrError) {
            console.warn(
              "[useRealTimeFeed] historical edge refresh failed:",
              cbrError instanceof Error ? cbrError.message : cbrError
            );
          }
        }

        if (!isActive) return;

        const errors = settled
          .filter((r) => r.status === "rejected")
          .map((r) =>
            r.status === "rejected" && r.reason instanceof Error
              ? r.reason.message
              : "Request failed"
          )
          .join(" | ");

        if (macro && consensus && attribution && cbr) {
          const snapshot: SystemSnapshot = { macro, consensus, attribution, cbr };
          const latestTimestamp = pickLatestTimestamp(macro, consensus);
          lastKnownStateRef.current = snapshot;
          setState((cur) => ({
            ...cur,
            macro,
            consensus,
            attribution,
            cbr,
            loading: false,
            error: errors.length > 0 ? errors : null,
            lastUpdated: latestTimestamp,
            lastSuccessfulUpdate: latestTimestamp,
            lastKnownState: snapshot,
            connectionStatus: "fallback",
            connectionMessage: "Baglanti kesik, manuel senkronizasyon aktif.",
            systemHealth: errors.length > 0 ? "DEGRADED" : "HEALTHY",
          }));
          return;
        }

        if (lastKnownStateRef.current) {
          const lastSuccessfulUpdate = pickLatestTimestamp(
            lastKnownStateRef.current.macro,
            lastKnownStateRef.current.consensus
          );
          setState((cur) => ({
            ...cur,
            ...lastKnownStateRef.current,
            loading: false,
            error: errors.length > 0 ? errors : "System state partially unavailable",
            lastUpdated: lastSuccessfulUpdate,
            lastSuccessfulUpdate,
            lastKnownState: lastKnownStateRef.current,
            connectionStatus: "fallback",
            connectionMessage: "Baglanti kesik, manuel senkronizasyon aktif.",
            systemHealth: "DEGRADED",
          }));
        }
      } catch (err) {
        if (!isActive) return;
        setState((cur) => ({
          ...cur,
          loading: false,
          error: err instanceof Error ? err.message : "Fallback sync failed",
          connectionStatus: "fallback",
          connectionMessage: "Baglanti kesik, manuel senkronizasyon aktif.",
          systemHealth: "DEGRADED",
        }));
      }
    };

    const startFallbackPolling = () => {
      if (fallbackStartedRef.current) return;
      fallbackStartedRef.current = true;
      closeEventSource();
      clearReconnectTimeout();
      void runFallbackRefresh();
      fallbackIntervalRef.current = window.setInterval(
        () => void runFallbackRefresh(),
        FALLBACK_INTERVAL_MS
      );
    };

    // ── Reconnect scheduling — exponential 1s/2s/4s ────────────────────────────

    const scheduleReconnect = () => {
      clearReconnectTimeout();
      const attempt = retryCountRef.current + 1;

      if (attempt >= MAX_RETRIES) {
        retryCountRef.current = attempt;
        setState((cur) => ({
          ...cur,
          connectionStatus: "fallback",
          reconnectAttempts: attempt,
          connectionMessage: "Baglanti kesik, manuel senkronizasyon aktif.",
          systemHealth: "DEGRADED",
        }));
        startFallbackPolling();
        return;
      }

      retryCountRef.current = attempt;
      setState((cur) => ({
        ...cur,
        loading: false,
        connectionStatus: "reconnecting",
        reconnectAttempts: attempt,
        connectionMessage: `Yeniden baglaniliyor... (${attempt}/${MAX_RETRIES})`,
        systemHealth:
          cur.systemHealth === "AWAITING DATA" ? "DEGRADED" : cur.systemHealth,
      }));

      // 2^(attempt-1) * 1000: 1s, 2s, 4s, 8s, …
      const delay = Math.pow(2, attempt - 1) * 1000;
      reconnectTimeoutRef.current = window.setTimeout(() => {
        connectStream();
      }, delay);
    };

    // ── Event handlers ────────────────────────────────────────────────────────

    const handleSnapshot = (raw: LiveFeedPayload) => {
      const snapshot = raw.snapshot;
      if (!snapshot) return;

      const latestTimestamp = pickLatestTimestamp(snapshot.macro, snapshot.consensus);
      lastKnownStateRef.current = snapshot;
      retryCountRef.current = 0;

      setState((cur) => ({
        ...cur,
        macro: snapshot.macro,
        consensus: snapshot.consensus,
        attribution: snapshot.attribution,
        cbr: snapshot.cbr,
        loading: false,
        error: raw.error ?? null,
        lastUpdated: latestTimestamp,
        lastSuccessfulUpdate: latestTimestamp,
        lastKnownState: snapshot,
        connectionStatus: "live",
        reconnectAttempts: 0,
        connectionMessage: null,
        systemHealth:
          raw.system_health?.status ??
          (snapshot.macro.status.toUpperCase() === "OK"
            ? "HEALTHY"
            : snapshot.macro.status.toUpperCase()),
      }));
    };

    const handleWeights = (raw: WeightsPayload) => {
      const w: WeightsResponse = {
        weights: (raw.weights ?? {}) as unknown as WeightsResponse["weights"],
        drift_total: raw.drift_total ?? 0,
        drift_limit: raw.drift_limit ?? 0.15,
        drift_frozen: raw.drift_frozen ?? false,
        backup_exists: raw.backup_exists ?? false,
        week_start: raw.week_start,
      };
      storeDispatch({ type: "SET_WEIGHTS", payload: w });
      setState((cur) => ({ ...cur, weights: w }));
    };

    const handleAlert = (raw: AlertPayload) => {
      const key = `${raw.alert_type ?? ""}:${raw.ts ?? ""}`;
      if (key === lastAlertKeyRef.current) return; // deduplicate
      lastAlertKeyRef.current = key;

      const severity =
        raw.severity === "critical"
          ? "critical"
          : raw.severity === "warning"
          ? "warning"
          : "info";

      const alert: AlertEvent = {
        type: raw.alert_type ?? "UNKNOWN",
        message: raw.message ?? "",
        severity,
        ts: raw.ts ?? "",
      };

      setState((cur) => ({ ...cur, latestAlert: alert }));
    };

    // ── EventSource connection ────────────────────────────────────────────────

    const connectStream = () => {
      if (!isActive || fallbackStartedRef.current) return;

      closeEventSource();
      const endpoint = `${API_BASE_URL.replace(/\/$/, "")}/api/live-feed?symbol=${encodeURIComponent(
        symbol
      )}&timeframe=${encodeURIComponent(timeframe)}&period=${encodeURIComponent(period)}&horizon=${encodeURIComponent(horizon)}`;

      const source = new EventSource(endpoint);
      eventSourceRef.current = source;

      source.onopen = () => {
        retryCountRef.current = 0;
        setState((cur) => ({
          ...cur,
          loading: cur.lastKnownState ? false : cur.loading,
          connectionStatus: "live",
          reconnectAttempts: 0,
          connectionMessage: null,
        }));
      };

      // Unnamed messages — treat as snapshot for backwards compat
      source.onmessage = (event) => {
        try {
          handleSnapshot(JSON.parse(event.data as string) as LiveFeedPayload);
        } catch {
          /* ignore malformed */
        }
      };

      source.addEventListener("snapshot", (event) => {
        try {
          handleSnapshot(
            JSON.parse((event as MessageEvent<string>).data) as LiveFeedPayload
          );
        } catch {
          /* ignore malformed */
        }
      });

      source.addEventListener("weights", (event) => {
        try {
          handleWeights(
            JSON.parse((event as MessageEvent<string>).data) as WeightsPayload
          );
        } catch {
          /* ignore malformed */
        }
      });

      source.addEventListener("alert", (event) => {
        try {
          handleAlert(
            JSON.parse((event as MessageEvent<string>).data) as AlertPayload
          );
        } catch {
          /* ignore malformed */
        }
      });

      // ping — keep-alive, nothing to do
      source.addEventListener("ping", (_event) => {
        /* heartbeat received */
      });

      source.onerror = () => {
        closeEventSource();
        if (!isActive || fallbackStartedRef.current) return;
        scheduleReconnect();
      };
    };

    connectStream();

    return () => {
      isActive = false;
      closeEventSource();
      clearReconnectTimeout();
      clearFallbackInterval();
    };
  }, [horizon, period, symbol, timeframe, storeDispatch]);

  return state;
};
