/**
 * AgentControlPanel — AEGIS otonom agent kontrol merkezi.
 *
 * GÜVENLİK: Agent gerçek emir göndermez. DRY_RUN'da sadece karar günlüğü,
 * MANUAL_APPROVAL'da insan onayı bekler. Panel start/stop, config, karar
 * günlüğünü gösterir.
 */
import React, { useState, useEffect, useCallback } from "react";

const API_BASE = (import.meta as any).env?.VITE_API_URL || "http://localhost:8502";

interface AgentConfig {
  enabled: boolean;
  interval_sec: number;
  watch_symbols: string[];
  timeframe: string;
  horizon: string;
  min_confidence: number;
  min_score_edge: number;
  max_signals_per_day: number;
  execution_mode: string;
}

interface AgentStatus {
  running: boolean;
  config: AgentConfig;
  cycle_count: number;
  last_cycle_ts: string | null;
  started_at: string | null;
  last_error: string | null;
  signals_today: number;
  journal_size: number;
  heartbeat_age_sec: number | null;
}

interface Decision {
  ts: string;
  symbol: string;
  timeframe: string;
  action: string;
  score: number;
  confidence: number;
  decision: string;
  reason: string;
  mode: string;
  signal_id?: string | null;
}

const DECISION_STYLE: Record<string, { label: string; cls: string }> = {
  no_action:               { label: "İşlem yok",        cls: "text-slate-500 bg-slate-700/30" },
  would_signal:            { label: "Sinyal (DRY)",     cls: "text-sky-400 bg-sky-500/10" },
  queued_for_approval:     { label: "Onay bekliyor",    cls: "text-amber-400 bg-amber-500/10" },
  auto_execute_logged:     { label: "Oto (loglandı)",   cls: "text-indigo-400 bg-indigo-500/10" },
  blocked_kill_switch:     { label: "Kill switch",      cls: "text-rose-400 bg-rose-500/10" },
  rejected_low_conviction: { label: "Zayıf kanaat",     cls: "text-slate-500 bg-slate-700/30" },
  rejected_daily_limit:    { label: "Günlük limit",     cls: "text-amber-500 bg-amber-500/10" },
  rejected_price_unverified:{ label: "Fiyat şüpheli",   cls: "text-rose-400 bg-rose-500/10" },
};

const MODE_INFO: Record<string, { label: string; cls: string; desc: string }> = {
  DRY_RUN:        { label: "DRY_RUN",        cls: "text-emerald-400 border-emerald-500/40 bg-emerald-500/10", desc: "Güvenli — emir açılmaz, sadece karar günlüğü" },
  MANUAL_APPROVAL:{ label: "MANUAL_APPROVAL",cls: "text-amber-400 border-amber-500/40 bg-amber-500/10",       desc: "Her sinyal insan onayı bekler" },
  AUTO_LIMITED:   { label: "AUTO_LIMITED",   cls: "text-rose-400 border-rose-500/40 bg-rose-500/10",          desc: "Otomatik — gerçek emir ayrı endpoint gerektirir" },
};

export const AgentControlPanel: React.FC = () => {
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [journal, setJournal] = useState<Decision[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const fetchStatus = useCallback(() => {
    fetch(`${API_BASE}/api/agent/status`).then(r => r.json()).then(setStatus).catch(() => {});
    fetch(`${API_BASE}/api/agent/journal?limit=30`).then(r => r.json())
      .then(d => setJournal(d.decisions ?? [])).catch(() => {});
  }, []);

  useEffect(() => {
    fetchStatus();
    const id = setInterval(fetchStatus, 10_000);
    return () => clearInterval(id);
  }, [fetchStatus]);

  const action = async (path: string, label: string) => {
    setBusy(true); setMsg(null);
    try {
      const r = await fetch(`${API_BASE}/api/agent/${path}`, { method: "POST" });
      const d = await r.json();
      setMsg(`${label}: ${d.status ?? "ok"}`);
      fetchStatus();
    } catch {
      setMsg(`${label}: hata`);
    } finally {
      setBusy(false);
    }
  };

  if (!status) {
    return (
      <div className="rounded-2xl border border-slate-700/60 bg-slate-900 p-5">
        <p className="text-xs text-slate-500">Agent durumu yükleniyor…</p>
      </div>
    );
  }

  const cfg = status.config;
  const mode = MODE_INFO[cfg.execution_mode] ?? MODE_INFO.DRY_RUN;
  const heartbeat = status.heartbeat_age_sec;
  const hbStale = heartbeat != null && heartbeat > cfg.interval_sec * 2;

  return (
    <div className="rounded-2xl border border-slate-700/60 bg-slate-900 p-5 space-y-4">
      {/* Başlık + durum */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-bold ${
            status.running ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-400"
                           : "border-slate-600 bg-slate-800 text-slate-400"
          }`}>
            <span className={`h-2 w-2 rounded-full ${status.running ? "bg-emerald-400 animate-pulse" : "bg-slate-600"}`} />
            {status.running ? "ÇALIŞIYOR" : "DURDU"}
          </span>
          <div>
            <p className="text-[10px] uppercase tracking-widest text-slate-500">Otonom Agent</p>
            <p className="font-mono text-[11px] text-slate-400">
              {status.cycle_count} döngü · bugün {status.signals_today} sinyal
            </p>
          </div>
        </div>
        <span className={`rounded-lg border px-2.5 py-1 text-[11px] font-bold ${mode.cls}`} title={mode.desc}>
          {mode.label}
        </span>
      </div>

      {/* Güvenlik notu */}
      <div className="rounded-xl border border-slate-700/50 bg-slate-800/40 px-3 py-2 text-[10px] leading-4 text-slate-500">
        🛡 {mode.desc}. Agent <b className="text-slate-400">gerçek emir göndermez</b> — yalnız karar üretir
        {cfg.execution_mode === "MANUAL_APPROVAL" ? " ve onaya sunar." : "."}
      </div>

      {/* Kontroller */}
      <div className="flex flex-wrap items-center gap-2">
        {!status.running ? (
          <button onClick={() => action("start", "Başlat")} disabled={busy}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-xs font-bold text-white hover:bg-emerald-500 disabled:opacity-50">
            ▶ Başlat
          </button>
        ) : (
          <button onClick={() => action("stop", "Durdur")} disabled={busy}
            className="rounded-lg bg-rose-600 px-4 py-2 text-xs font-bold text-white hover:bg-rose-500 disabled:opacity-50">
            ■ Durdur
          </button>
        )}
        <button onClick={() => action("run_once", "Tek döngü")} disabled={busy}
          className="rounded-lg border border-slate-600 bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-700 disabled:opacity-50">
          ↻ Tek döngü çalıştır
        </button>
        {msg && <span className="text-[11px] text-slate-400">{msg}</span>}
      </div>

      {/* Config özeti */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {[
          { k: "Aralık", v: `${cfg.interval_sec}s` },
          { k: "Timeframe", v: cfg.timeframe },
          { k: "Min Güven", v: `${Math.round(cfg.min_confidence * 100)}%` },
          { k: "Günlük Limit", v: `${status.signals_today}/${cfg.max_signals_per_day}` },
        ].map(({ k, v }) => (
          <div key={k} className="rounded-lg border border-slate-700/40 bg-slate-800/40 px-2.5 py-1.5">
            <p className="text-[8px] uppercase tracking-widest text-slate-600">{k}</p>
            <p className="font-mono text-xs font-bold text-slate-300">{v}</p>
          </div>
        ))}
      </div>

      {/* İzlenen semboller */}
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[9px] uppercase tracking-widest text-slate-600">İzlenen:</span>
        {cfg.watch_symbols.map(s => (
          <span key={s} className="rounded-md bg-slate-800 px-2 py-0.5 font-mono text-[10px] text-slate-300">{s}</span>
        ))}
      </div>

      {/* Heartbeat uyarısı */}
      {status.running && hbStale && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-[10px] text-amber-400">
          ⚠ Heartbeat gecikmesi: son döngü {heartbeat}s önce (beklenen ~{cfg.interval_sec}s)
        </div>
      )}
      {status.last_error && (
        <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-1.5 text-[10px] text-rose-400">
          Son hata: {status.last_error}
        </div>
      )}

      {/* Karar günlüğü */}
      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">Karar Günlüğü</p>
          <span className="text-[9px] text-slate-600">{status.journal_size} kayıt</span>
        </div>
        <div className="max-h-72 space-y-1 overflow-y-auto">
          {journal.length === 0 ? (
            <p className="py-4 text-center text-[11px] text-slate-600">Henüz karar yok — döngü çalıştırın</p>
          ) : (
            journal.map((d, i) => {
              const st = DECISION_STYLE[d.decision] ?? { label: d.decision, cls: "text-slate-500 bg-slate-700/30" };
              const actCls = d.action === "BUY" ? "text-emerald-400" : d.action === "SELL" ? "text-rose-400" : "text-slate-500";
              return (
                <div key={i} className="flex items-center gap-2 rounded-lg bg-slate-800/40 px-2.5 py-1.5 text-[10px]">
                  <span className="font-mono text-slate-600">{(d.ts || "").slice(11, 19)}</span>
                  <span className="w-16 shrink-0 font-mono font-semibold text-slate-300">{d.symbol}</span>
                  <span className={`w-9 shrink-0 font-bold ${actCls}`}>{d.action}</span>
                  <span className="w-12 shrink-0 font-mono text-slate-500">{Math.round(d.score * 100)}%</span>
                  <span className={`shrink-0 rounded px-1.5 py-0.5 font-semibold ${st.cls}`}>{st.label}</span>
                  <span className="truncate text-slate-600" title={d.reason}>{d.reason}</span>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
};
