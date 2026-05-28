import { useEffect, useRef, useState } from "react";
import { fetchConsensus, fetchExitAttribution, fetchHistoricalEdge, fetchMacro } from "../services/apiV2";
import { SystemSnapshot, SystemState } from "../types/dashboardV2";

export const useSystemState = (
  symbol: string = "BTC/USDT",
  timeframe: string = "1h",
  period: string = "7d"
): SystemState => {
  const [state, setState] = useState<SystemState>({
    consensus: null,
    macro: null,
    attribution: null,
    cbr: null,
    loading: true,
    error: null,
    lastUpdated: null,
    lastKnownState: null,
  });
  const lastKnownStateRef = useRef<SystemSnapshot | null>(null);

  useEffect(() => {
    let isActive = true;
    let intervalId = 0;
    let currentController: AbortController | null = null;

    const refreshState = async () => {
      currentController?.abort();
      const controller = new AbortController();
      currentController = controller;

      const settled = await Promise.allSettled([
        fetchMacro("medium", { signal: controller.signal }),
        fetchConsensus(symbol, timeframe, { signal: controller.signal }),
        fetchExitAttribution(period, { signal: controller.signal }),
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
              consensus.cbr.similarity_score,
              { signal: controller.signal }
            )
          : null;

        if (!isActive) {
          return;
        }

        const errors = settled
          .filter((result) => result.status === "rejected")
          .map((result) => result.reason instanceof Error ? result.reason.message : "Request failed")
          .join(" | ");

        if (macro && consensus && attribution && cbr) {
          const snapshot: SystemSnapshot = { macro, consensus, attribution, cbr };
          lastKnownStateRef.current = snapshot;

          setState({
            macro,
            consensus,
            attribution,
            cbr,
            loading: false,
            error: errors.length > 0 ? errors : null,
            lastUpdated: [macro.timestamp, consensus.timestamp].filter(Boolean).sort().reverse()[0] ?? new Date().toISOString(),
            lastKnownState: snapshot,
          });
          return;
        }

        if (lastKnownStateRef.current) {
          setState({
            ...lastKnownStateRef.current,
            loading: false,
            error: errors.length > 0 ? errors : "System state partially unavailable",
            lastUpdated: lastKnownStateRef.current.consensus.timestamp,
            lastKnownState: lastKnownStateRef.current,
          });
          return;
        }

        setState({
          macro,
          consensus,
          attribution,
          cbr,
          loading: false,
          error: errors.length > 0 ? errors : "System state partially unavailable",
          lastUpdated: [macro?.timestamp, consensus?.timestamp].filter(Boolean).sort().reverse()[0] ?? null,
          lastKnownState: null,
        });
      } catch (error) {
        if (!isActive) {
          return;
        }

        const snapshot = lastKnownStateRef.current;

        setState((current) => ({
          macro: snapshot?.macro ?? current.macro,
          consensus: snapshot?.consensus ?? current.consensus,
          attribution: snapshot?.attribution ?? current.attribution,
          cbr: snapshot?.cbr ?? current.cbr,
          loading: false,
          error: error instanceof Error ? error.message : "System state refresh failed",
          lastUpdated: current.lastUpdated || snapshot?.consensus.timestamp || snapshot?.macro.timestamp || null,
          lastKnownState: snapshot ?? current.lastKnownState,
        }));
      }
    };

    void refreshState();
    intervalId = window.setInterval(() => {
      void refreshState();
    }, 5000);

    return () => {
      isActive = false;
      currentController?.abort();
      window.clearInterval(intervalId);
    };
  }, [period, symbol, timeframe]);

  return state;
};