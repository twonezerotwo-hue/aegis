/**
 * src/components/debug/DataSyncMonitor.tsx
 * Canlı API ↔ UI debug overlay. Ctrl+Shift+D ile aç/kapa.
 * Fetch'leri intercept ederek hangi URL'ye istek atıldığını ve
 * backend'den hangi yanıtın döndüğünü anlık gösterir.
 */

import React, { useEffect, useState } from "react";

interface LogEntry {
  t: string;
  type: "REQ" | "RES" | "ERR";
  msg: string;
}

export const DataSyncMonitor: React.FC = () => {
  const [visible, setVisible] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([]);

  const pushLog = (entry: LogEntry) =>
    setLogs((prev) => [...prev.slice(-49), entry]);

  useEffect(() => {
    const origFetch = window.fetch;

    window.fetch = async (...args: Parameters<typeof fetch>) => {
      const url =
        typeof args[0] === "string"
          ? args[0]
          : args[0] instanceof URL
          ? args[0].toString()
          : (args[0] as Request).url;

      const isTracked =
        url.includes("/api/") ||
        url.includes("/touche/") ||
        url.includes("/consensus/") ||
        url.includes("/macro");

      if (isTracked) {
        pushLog({ t: new Date().toLocaleTimeString(), type: "REQ", msg: url });
      }

      let res: Response;
      try {
        res = await origFetch(...args);
      } catch (err) {
        if (isTracked) {
          pushLog({
            t: new Date().toLocaleTimeString(),
            type: "ERR",
            msg: `${url} → ${err instanceof Error ? err.message : "Network Error"}`,
          });
        }
        throw err;
      }

      if (isTracked) {
        res
          .clone()
          .json()
          .then((data: Record<string, unknown>) => {
            const hint =
              (data.horizon_applied as string | undefined) ??
              (data.action as string | undefined) ??
              (data.status as string | undefined) ??
              "OK";
            pushLog({
              t: new Date().toLocaleTimeString(),
              type: "RES",
              msg: `${url} → ${hint}`,
            });
          })
          .catch(() => {
            pushLog({
              t: new Date().toLocaleTimeString(),
              type: "RES",
              msg: `${url} → (non-JSON)`,
            });
          });
      }

      return res;
    };

    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && e.key === "D") {
        e.preventDefault();
        setVisible((v) => !v);
      }
    };
    window.addEventListener("keydown", handler);

    return () => {
      window.fetch = origFetch;
      window.removeEventListener("keydown", handler);
    };
  }, []);

  if (!visible) return null;

  return (
    <div
      className="fixed bottom-20 left-4 z-50 w-96 max-h-72 overflow-y-auto
        rounded-xl border border-slate-700 bg-slate-900/95 p-3 shadow-2xl"
      role="log"
      aria-label="API monitor"
      aria-live="polite"
    >
      {/* Header */}
      <div className="mb-2 flex items-center justify-between border-b border-slate-700 pb-1.5">
        <span className="font-mono text-[11px] font-bold text-emerald-400">
          📡 CANLI API ↔ UI MONITOR
        </span>
        <button
          type="button"
          onClick={() => setVisible(false)}
          className="text-slate-400 hover:text-white text-sm leading-none"
          aria-label="Kapat"
        >
          ✕
        </button>
      </div>

      {/* Log entries */}
      <div className="space-y-0.5">
        {logs.length === 0 ? (
          <span className="font-mono text-[10px] text-slate-500">
            Henüz istek yok…
          </span>
        ) : (
          logs.slice(-8).map((l, i) => (
            <div
              key={i}
              className={`font-mono text-[10px] leading-4 ${
                l.type === "REQ"
                  ? "text-sky-300"
                  : l.type === "ERR"
                  ? "text-rose-400"
                  : "text-amber-300"
              }`}
            >
              [{l.t}] <span className="opacity-60">{l.type}</span> {l.msg}
            </div>
          ))
        )}
      </div>

      <div className="mt-2 border-t border-slate-800 pt-1.5 font-mono text-[9px] text-slate-600">
        Ctrl+Shift+D ile aç/kapa &nbsp;·&nbsp; {logs.length} istek kayıtlı
      </div>
    </div>
  );
};
