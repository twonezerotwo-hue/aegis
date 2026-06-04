/**
 * AlertsPanel — sistem uyarı akışı (sinyal, hata, kill-switch, optimizer).
 * Telegram yapılandırılmışsa oraya da gider; uygulama-içi her zaman çalışır.
 */
import React, { useState, useEffect, useCallback } from "react";

const API_BASE = (import.meta as any).env?.VITE_API_URL || "http://localhost:8502";

interface Alert {
  ts: string; category: string; level: string; message: string;
  telegram_sent?: boolean;
}

const LEVEL_STYLE: Record<string, { dot: string; text: string }> = {
  info:     { dot: "bg-slate-500",  text: "text-slate-400" },
  signal:   { dot: "bg-cyan-400",   text: "text-cyan-300" },
  success:  { dot: "bg-emerald-400",text: "text-emerald-300" },
  warning:  { dot: "bg-amber-400",  text: "text-amber-300" },
  error:    { dot: "bg-rose-400",   text: "text-rose-300" },
  critical: { dot: "bg-rose-500 animate-pulse", text: "text-rose-300 font-bold" },
};
const CAT_TR: Record<string, string> = {
  signal: "Sinyal", kill_switch: "Kill Switch", optimizer: "Optimizer",
  error: "Hata", system: "Sistem",
};

export const AlertsPanel: React.FC = () => {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [tgConfigured, setTgConfigured] = useState(false);
  const [testing, setTesting] = useState(false);

  const refresh = useCallback(() => {
    fetch(`${API_BASE}/api/alerts?limit=40`).then(r => r.json())
      .then(d => setAlerts(d.alerts ?? [])).catch(() => {});
    fetch(`${API_BASE}/api/alerts/status`).then(r => r.json())
      .then(d => setTgConfigured(d.telegram_configured ?? false)).catch(() => {});
  }, []);
  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 8000);
    return () => clearInterval(id);
  }, [refresh]);

  const sendTest = async () => {
    setTesting(true);
    try { await fetch(`${API_BASE}/api/alerts/test`, { method: "POST" }); refresh(); }
    finally { setTesting(false); }
  };

  return (
    <div className="rounded-2xl border border-slate-700/60 bg-slate-900 p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">🔔</span>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-400">Uyarı Akışı</p>
            <p className="font-mono text-[10px] text-slate-500">sinyal · kill-switch · optimizer · hata</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={`flex items-center gap-1 rounded-md border px-2 py-1 text-[10px] ${
            tgConfigured ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-400"
                         : "border-slate-700 bg-slate-800 text-slate-500"
          }`}>
            <span className={`h-1.5 w-1.5 rounded-full ${tgConfigured ? "bg-emerald-400" : "bg-slate-600"}`} />
            Telegram {tgConfigured ? "bağlı" : "kapalı"}
          </span>
          <button onClick={sendTest} disabled={testing}
            className="rounded-md border border-slate-600 bg-slate-800 px-2.5 py-1 text-[10px] font-semibold text-slate-300 hover:bg-slate-700 disabled:opacity-50">
            Test
          </button>
        </div>
      </div>

      {!tgConfigured && (
        <div className="mb-2 rounded-lg border border-slate-700/50 bg-slate-800/40 px-3 py-1.5 text-[9px] text-slate-500">
          💡 Telegram bildirimi için <span className="font-mono text-slate-400">TELEGRAM_BOT_TOKEN</span> +
          <span className="font-mono text-slate-400"> TELEGRAM_CHAT_ID</span> env ekle. Uygulama-içi akış zaten çalışıyor.
        </div>
      )}

      <div className="max-h-72 space-y-1 overflow-y-auto">
        {alerts.length === 0 ? (
          <p className="py-6 text-center text-[11px] text-slate-600">Henüz uyarı yok</p>
        ) : (
          alerts.map((a, i) => {
            const st = LEVEL_STYLE[a.level] ?? LEVEL_STYLE.info;
            return (
              <div key={i} className="flex items-start gap-2 rounded-lg bg-slate-800/40 px-2.5 py-1.5 text-[10px]">
                <span className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${st.dot}`} />
                <span className="font-mono text-slate-600">{(a.ts || "").slice(11, 19)}</span>
                <span className="w-16 shrink-0 text-slate-500">{CAT_TR[a.category] ?? a.category}</span>
                <span className={`flex-1 ${st.text}`}>{a.message}</span>
                {a.telegram_sent && <span className="shrink-0 text-[8px] text-emerald-500" title="Telegram'a gönderildi">✈</span>}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
