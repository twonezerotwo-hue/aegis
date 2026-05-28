/**
 * useLiveFeed — SSE hook connecting to /api/live-feed
 *
 * Returns the latest parsed payload, connection status, and error.
 * Automatically reconnects on disconnect with 3-second backoff.
 */
import { useEffect, useRef, useState, useCallback } from "react";
import { LiveFeedPayload } from "../types";

const BACKEND_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8502";
const RECONNECT_DELAY_MS = 3000;

export interface UseLiveFeedResult {
  data: LiveFeedPayload | null;
  connected: boolean;
  error: string | null;
  reconnect: () => void;
}

export function useLiveFeed(symbol: string): UseLiveFeedResult {
  const [data, setData] = useState<LiveFeedPayload | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    // Clean up previous connection
    if (esRef.current) {
      esRef.current.close();
    }
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
    }

    const url = `${BACKEND_URL}/api/live-feed?symbol=${encodeURIComponent(symbol)}`;
    const es = new EventSource(url);
    esRef.current = es;

    es.onopen = () => {
      setConnected(true);
      setError(null);
    };

    es.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data) as LiveFeedPayload;
        if (parsed.type === "error") {
          setError(parsed.message ?? "Stream error");
        } else {
          setData(parsed);
        }
      } catch {
        // ignore malformed frames
      }
    };

    es.onerror = () => {
      setConnected(false);
      es.close();
      // Reconnect after delay
      reconnectTimerRef.current = setTimeout(() => {
        connect();
      }, RECONNECT_DELAY_MS);
    };
  }, [symbol]);

  useEffect(() => {
    connect();
    return () => {
      esRef.current?.close();
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    };
  }, [connect]);

  return { data, connected, error, reconnect: connect };
}
