import { useEffect, useRef, useState } from "react";
import { fetchConsensus, fetchExitAttribution, fetchHistoricalEdge, fetchMacro } from "../services/apiV2";
import { SystemSnapshot, SystemState } from "../types/dashboardV2";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8502";

export type LiveConnectionStatus = "live" | "reconnecting" | "fallback";

interface LiveFeedPayload {
  timestamp?: string;
  error?: string;
  system_health?: {
    status?: string;
    services?: Record<string, string>;
  };
  snapshot?: SystemSnapshot;
}

interface RealTimeDataState extends SystemState {
  connectionStatus: LiveConnectionStatus;
  reconnectAttempts: number;
  connectionMessage: string | null;
  systemHealth: string;
}

const buildInitialState = (): RealTimeDataState => ({
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
});

export const useRealTimeData = (
  symbol: string = "BTC/USDT",
  timeframe: string = "1h",
  period: string = "7d"
): RealTimeDataState => {
  const [state, setState] = useState<RealTimeDataState>(buildInitialState);
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const fallbackIntervalRef = useRef<number | null>(null);
  const retryCountRef = useRef<number>(0);
  const lastKnownStateRef = useRef<SystemSnapshot | null>(null);
  const fallbackStartedRef = useRef<boolean>(false);

  useEffect(() => {
    let isActive = true;

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

    const runFallbackRefresh = async () => {
      const settled = await Promise.allSettled([
        fetchMacro(),
        fetchConsensus(symbol, timeframe),
        fetchExitAttribution(period),
      ]);

      if (!isActive) {
        return;
      }

      try {
        const macro = settled[0].status === "fulfilled" ? settled[0].value : null;
        const consensus = settled[1].status === "fulfilled" ? settled[1].value : null;
        const attribution = settled[2].status === "fulfilled" ? settled[2].value : null;

        const cbr = consensus
          ? await fetchHistoricalEdge(
              consensus.symbol.replace("/USDT", "").replace("/", ""),
              consensus.cbr.sample_count,
              consensus.cbr.win_rate_pct,
              consensus.cbr.similarity_score
            )
          : null;

        if (!isActive) {
          return;
        }

        const errors = settled
          .filter((result) => result.status === "rejected")
          .map((result) => (result.status === "rejected" && result.reason instanceof Error ? result.reason.message : "Request failed"))
          .join(" | ");

        if (macro && consensus && attribution && cbr) {
          const snapshot: SystemSnapshot = { macro, consensus, attribution, cbr };
          lastKnownStateRef.current = snapshot;
          setState((current) => ({
            ...current,
            macro,
            consensus,
            attribution,
            cbr,
            loading: false,
            error: errors.length > 0 ? errors : null,
            lastUpdated: [macro.timestamp, consensus.timestamp].filter(Boolean).sort().reverse()[0] ?? new Date().toISOString(),
            lastKnownState: snapshot,
            connectionStatus: "fallback",
            connectionMessage: "Baglanti kesik, manuel senkronizasyon aktif.",
            systemHealth: errors.length > 0 ? "DEGRADED" : "HEALTHY",
          }));
          return;
        }

        if (lastKnownStateRef.current) {
          setState((current) => ({
            ...current,
            ...lastKnownStateRef.current,
            loading: false,
            error: errors.length > 0 ? errors : "System state partially unavailable",
            lastUpdated: lastKnownStateRef.current?.consensus.timestamp ?? current.lastUpdated,
            lastKnownState: lastKnownStateRef.current,
            connectionStatus: "fallback",
            connectionMessage: "Baglanti kesik, manuel senkronizasyon aktif.",
            systemHealth: "DEGRADED",
          }));
        }
      } catch (error) {
        if (!isActive) {
          return;
        }

        setState((current) => ({
          ...current,
          loading: false,
          error: error instanceof Error ? error.message : "Fallback sync failed",
          connectionStatus: "fallback",
          connectionMessage: "Baglanti kesik, manuel senkronizasyon aktif.",
          systemHealth: "DEGRADED",
        }));
      }
    };

    const startFallbackPolling = () => {
      if (fallbackStartedRef.current) {
        return;
      }

      fallbackStartedRef.current = true;
      closeEventSource();
      clearReconnectTimeout();
      void runFallbackRefresh();
      fallbackIntervalRef.current = window.setInterval(() => {
        void runFallbackRefresh();
      }, 5000);
    };

    const scheduleReconnect = () => {
      clearReconnectTimeout();
      const nextAttempt = retryCountRef.current + 1;

      if (nextAttempt >= 5) {
        retryCountRef.current = nextAttempt;
        setState((current) => ({
          ...current,
          connectionStatus: "fallback",
          reconnectAttempts: nextAttempt,
          connectionMessage: "Baglanti kesik, manuel senkronizasyon aktif.",
          systemHealth: "DEGRADED",
        }));
        startFallbackPolling();
        return;
      }

      retryCountRef.current = nextAttempt;
      setState((current) => ({
        ...current,
        loading: false,
        connectionStatus: "reconnecting",
        reconnectAttempts: nextAttempt,
        connectionMessage: `Reconnecting... (${nextAttempt}/5)`,
        systemHealth: current.systemHealth === "AWAITING DATA" ? "DEGRADED" : current.systemHealth,
      }));

      reconnectTimeoutRef.current = window.setTimeout(() => {
        connectStream();
      }, Math.min(5000, 1000 * nextAttempt));
    };

    const handleSnapshot = (payload: LiveFeedPayload) => {
      const snapshot = payload.snapshot;
      if (!snapshot) {
        return;
      }

      lastKnownStateRef.current = snapshot;
      retryCountRef.current = 0;

      setState({
        macro: snapshot.macro,
        consensus: snapshot.consensus,
        attribution: snapshot.attribution,
        cbr: snapshot.cbr,
        loading: false,
        error: payload.error ?? null,
        lastUpdated: payload.timestamp ?? snapshot.consensus.timestamp ?? snapshot.macro.timestamp,
        lastKnownState: snapshot,
        connectionStatus: "live",
        reconnectAttempts: 0,
        connectionMessage: null,
        systemHealth: payload.system_health?.status ?? (snapshot.macro.status.toUpperCase() === "OK" ? "HEALTHY" : snapshot.macro.status.toUpperCase()),
      });
    };

    const connectStream = () => {
      if (!isActive || fallbackStartedRef.current) {
        return;
      }

      closeEventSource();
      const endpoint = `${API_BASE_URL.replace(/\/$/, "")}/api/live-feed?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}&period=${encodeURIComponent(period)}`;
      const source = new EventSource(endpoint);
      eventSourceRef.current = source;

      source.onopen = () => {
        retryCountRef.current = 0;
        setState((current) => ({
          ...current,
          loading: current.lastKnownState ? false : current.loading,
          connectionStatus: "live",
          reconnectAttempts: 0,
          connectionMessage: null,
        }));
      };

      source.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as LiveFeedPayload;
          handleSnapshot(payload);
        } catch (error) {
          setState((current) => ({
            ...current,
            error: error instanceof Error ? error.message : "SSE payload parse failed",
          }));
        }
      };

      source.addEventListener("snapshot", (event) => {
        try {
          const payload = JSON.parse((event as MessageEvent<string>).data) as LiveFeedPayload;
          handleSnapshot(payload);
        } catch (error) {
          setState((current) => ({
            ...current,
            error: error instanceof Error ? error.message : "SSE snapshot parse failed",
          }));
        }
      });

      source.onerror = () => {
        closeEventSource();
        if (!isActive || fallbackStartedRef.current) {
          return;
        }
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
  }, [period, symbol, timeframe]);

  return state;
};
