/**
 * AgentControlPanel - AEGIS agent command center.
 *
 * Safety: this panel controls the agent loop and configuration only. It does
 * not send orders or final execution commands.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";

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

interface ResearchSummary {
  summary?: {
    sample_size: number;
    by_decision: Record<string, number>;
    by_direction: Record<string, number>;
    safe_mode: string;
  };
  optional_metrics?: Record<string, string>;
  safe_mode?: string;
}

interface ResearchSuggestions {
  thresholds?: {
    status: string;
    proposed_thresholds: Record<string, number>;
    sample_size: number;
    reason: string;
    shadow_only: boolean;
  };
  metrics?: {
    hit_rate: number | null;
    calibration_error: number | null;
    sample_size: number;
  };
  safe_mode?: string;
}

const DECISION_STYLE: Record<string, { label: string; cls: string }> = {
  no_action:               { label: "Yön yok",          cls: "text-slate-400 bg-slate-700/35" },
  would_signal:            { label: "Sinyal kaydı",     cls: "text-sky-300 bg-sky-500/10" },
  queued_for_approval:     { label: "Onay kuyruğu",     cls: "text-amber-300 bg-amber-500/10" },
  auto_execute_logged:     { label: "Loglandı",         cls: "text-indigo-300 bg-indigo-500/10" },
  blocked_kill_switch:     { label: "Kill switch",      cls: "text-rose-300 bg-rose-500/10" },
  rejected_low_conviction: { label: "Zayıf kanaat",     cls: "text-slate-400 bg-slate-700/35" },
  rejected_daily_limit:    { label: "Limit dolu",       cls: "text-amber-300 bg-amber-500/10" },
  rejected_price_unverified:{ label: "Fiyat şüpheli",   cls: "text-rose-300 bg-rose-500/10" },
};

const MODE_INFO: Record<string, { label: string; cls: string; desc: string }> = {
  DRY_RUN: {
    label: "DRY RUN",
    cls: "text-emerald-300 border-emerald-500/40 bg-emerald-500/10",
    desc: "Emir açılmaz, yalnızca karar günlüğü tutulur.",
  },
  MANUAL_APPROVAL: {
    label: "MANUAL",
    cls: "text-amber-300 border-amber-500/40 bg-amber-500/10",
    desc: "Sinyaller onay kuyruğuna düşer; insan onayı gerekir.",
  },
  AUTO_LIMITED: {
    label: "AUTO LIMITED",
    cls: "text-rose-300 border-rose-500/40 bg-rose-500/10",
    desc: "Bu panel emir göndermez; yalnızca agent yönlendirmesini izler.",
  },
};

const DIRECTION_STYLE: Record<string, { label: string; cls: string }> = {
  BUY:  { label: "Pozitif", cls: "text-emerald-300" },
  SELL: { label: "Negatif", cls: "text-rose-300" },
  HOLD: { label: "Nötr",    cls: "text-slate-400" },
};

const TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d", "1w"] as const;
const HORIZONS = [
  { value: "short", label: "Kısa" },
  { value: "medium", label: "Orta" },
  { value: "long", label: "Uzun" },
] as const;
const INTERVALS = [60, 300, 900, 1800, 3600] as const;
const CONFIDENCE_LEVELS = [0.55, 0.6, 0.62, 0.65, 0.7] as const;
const EDGE_LEVELS = [0.04, 0.06, 0.08, 0.1, 0.12] as const;
const DAILY_LIMITS = [3, 6, 10, 20] as const;

function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

function pct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function clampPct(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, value));
}

function formatInterval(seconds: number): string {
  if (seconds < 60) return `${seconds} sn`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} dk`;
  return `${Math.round(seconds / 3600)} sa`;
}

function formatAge(seconds: number | null): string {
  if (seconds == null) return "Döngü yok";
  if (seconds < 60) return `${Math.round(seconds)} sn önce`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} dk önce`;
  return `${Math.round(seconds / 3600)} sa önce`;
}

function formatTimestamp(ts: string | null): string {
  if (!ts) return "Yok";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "Geçersiz";
  return new Intl.DateTimeFormat("tr-TR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d);
}

function parseSymbols(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim().toUpperCase())
    .filter(Boolean);
}

function directionFor(action: string): { label: string; cls: string } {
  return DIRECTION_STYLE[action.toUpperCase()] ?? { label: "Bilinmiyor", cls: "text-slate-500" };
}

function statusLabel(status: AgentStatus): { label: string; cls: string; dot: string } {
  if (status.running) {
    return {
      label: "Çalışıyor",
      cls: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
      dot: "bg-emerald-400 animate-pulse",
    };
  }
  return {
    label: "Durdu",
    cls: "border-slate-600 bg-slate-800 text-slate-300",
    dot: "bg-slate-500",
  };
}

function heartbeatState(status: AgentStatus): { label: string; cls: string } {
  const age = status.heartbeat_age_sec;
  if (!status.running && age == null) {
    return { label: "Beklemede", cls: "text-slate-400 border-slate-700 bg-slate-800/60" };
  }
  if (age == null) {
    return { label: "Bilinmiyor", cls: "text-slate-400 border-slate-700 bg-slate-800/60" };
  }
  if (age > status.config.interval_sec * 2) {
    return { label: "Gecikmiş", cls: "text-amber-300 border-amber-500/40 bg-amber-500/10" };
  }
  return { label: "Taze", cls: "text-emerald-300 border-emerald-500/40 bg-emerald-500/10" };
}

export const AgentControlPanel: React.FC = () => {
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [journal, setJournal] = useState<Decision[]>([]);
  const [research, setResearch] = useState<ResearchSummary | null>(null);
  const [suggestions, setSuggestions] = useState<ResearchSuggestions | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [symbolDraft, setSymbolDraft] = useState("");

  const fetchStatus = useCallback(async () => {
    try {
      const [statusRes, journalRes, researchRes, suggestionsRes] = await Promise.all([
        fetch(`${API_BASE}/api/agent/status`),
        fetch(`${API_BASE}/api/agent/journal?limit=40`),
        fetch(`${API_BASE}/api/agent/research/summary?limit=500`),
        fetch(`${API_BASE}/api/agent/research/suggestions?limit=500`),
      ]);

      if (!statusRes.ok) throw new Error(`status ${statusRes.status}`);

      const nextStatus = (await statusRes.json()) as AgentStatus;
      setStatus(nextStatus);
      setLoadError(null);

      if (journalRes.ok) {
        const data = (await journalRes.json()) as { decisions?: Decision[] };
        setJournal(data.decisions ?? []);
      }
      if (researchRes.ok) {
        setResearch((await researchRes.json()) as ResearchSummary);
      }
      if (suggestionsRes.ok) {
        setSuggestions((await suggestionsRes.json()) as ResearchSuggestions);
      }
    } catch {
      setLoadError("Agent API erişilemedi.");
    }
  }, []);

  useEffect(() => {
    void fetchStatus();
    const id = window.setInterval(() => void fetchStatus(), 10_000);
    return () => window.clearInterval(id);
  }, [fetchStatus]);

  useEffect(() => {
    if (status) {
      setSymbolDraft(status.config.watch_symbols.join(", "));
    }
  }, [status?.config.watch_symbols]);

  const action = async (path: string, label: string) => {
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch(`${API_BASE}/api/agent/${path}`, { method: "POST" });
      const data = (await res.json()) as { status?: string; error?: string };
      if (!res.ok || data.status === "error") {
        throw new Error(data.error || data.status || "hata");
      }
      setMsg(`${label}: ${data.status ?? "ok"}`);
      await fetchStatus();
    } catch (err) {
      const text = err instanceof Error ? err.message : "hata";
      setMsg(`${label}: ${text}`);
    } finally {
      setBusy(false);
    }
  };

  const updateConfig = async (patch: Record<string, unknown>, label: string) => {
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch(`${API_BASE}/api/agent/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      const data = (await res.json()) as { status?: string; error?: string };
      if (!res.ok || data.status === "error") {
        throw new Error(data.error || data.status || "hata");
      }
      setMsg(`${label} güncellendi`);
      await fetchStatus();
    } catch (err) {
      const text = err instanceof Error ? err.message : "hata";
      setMsg(`${label}: ${text}`);
    } finally {
      setBusy(false);
    }
  };

  const saveSymbols = () => {
    const symbols = parseSymbols(symbolDraft);
    if (symbols.length === 0) {
      setMsg("İzleme listesi boş olamaz.");
      return;
    }
    void updateConfig({ watch_symbols: symbols }, "İzleme listesi");
  };

  const latestDecision = journal[0] ?? null;
  const journalStats = useMemo(() => {
    const signals = journal.filter((d) => d.decision === "would_signal" || d.decision === "queued_for_approval").length;
    const blocked = journal.filter((d) => d.decision.startsWith("rejected_") || d.decision === "blocked_kill_switch").length;
    return { signals, blocked };
  }, [journal]);

  if (!status) {
    return (
      <section className="rounded-2xl border border-slate-700/60 bg-slate-900 p-5 shadow-md">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">
              AEGIS Agent
            </p>
            <p className="mt-2 text-sm text-slate-400">
              {loadError ?? "Agent durumu yükleniyor..."}
            </p>
          </div>
          <button
            type="button"
            onClick={() => void fetchStatus()}
            className="rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-300 hover:border-cyan-500/50 hover:text-cyan-200"
          >
            Yenile
          </button>
        </div>
      </section>
    );
  }

  const cfg = status.config;
  const mode = MODE_INFO[cfg.execution_mode] ?? {
    label: cfg.execution_mode,
    cls: "text-slate-300 border-slate-600 bg-slate-800",
    desc: "Çalışma modu backend tarafından bildirildi.",
  };
  const runState = statusLabel(status);
  const hb = heartbeatState(status);
  const limitPct = clampPct((status.signals_today / Math.max(1, cfg.max_signals_per_day)) * 100);
  const canSaveSymbols = parseSymbols(symbolDraft).join(",") !== cfg.watch_symbols.map((s) => s.trim().toUpperCase()).join(",");

  return (
    <section className="overflow-hidden rounded-2xl border border-cyan-500/25 bg-slate-900 shadow-lg ring-1 ring-cyan-500/10">
      <div className="grid gap-4 border-b border-slate-800 p-4 lg:p-5 xl:grid-cols-[minmax(300px,0.82fr)_minmax(0,1.18fr)]">
        <div className="flex min-w-0 flex-col justify-between gap-5 rounded-xl border border-slate-800 bg-slate-950/35 p-4">
          <div className="flex items-start gap-4">
            <div className="grid h-14 w-14 shrink-0 place-items-center rounded-xl border border-cyan-500/30 bg-cyan-500/10 font-mono text-lg font-black text-cyan-200 shadow-inner shadow-cyan-500/10">
              AI
            </div>
            <div className="min-w-0">
              <p className="text-[10px] font-semibold uppercase tracking-[0.24em] text-cyan-400">
                AEGIS Agent
              </p>
              <h2 className="mt-1 text-lg font-semibold leading-tight text-slate-100">
                Otonom sinyal döngüsü
              </h2>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <span className={cx("inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-bold", runState.cls)}>
                  <span className={cx("h-1.5 w-1.5 rounded-full", runState.dot)} />
                  {runState.label}
                </span>
                <span className={cx("rounded-lg border px-2.5 py-1 text-[11px] font-bold", mode.cls)} title={mode.desc}>
                  {mode.label}
                </span>
                <span className={cx("rounded-lg border px-2.5 py-1 text-[11px] font-semibold", hb.cls)}>
                  {hb.label}
                </span>
              </div>
            </div>
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-900/70 px-3 py-2 text-[11px] leading-5 text-slate-400">
            {mode.desc} Agent bu panelden emir göndermez.
          </div>

          <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
            {!status.running ? (
              <button
                type="button"
                onClick={() => void action("start", "Başlat")}
                disabled={busy}
                className="inline-flex min-h-[40px] items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-bold text-white transition-colors hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <span className="h-0 w-0 border-y-[5px] border-l-[8px] border-y-transparent border-l-white" />
                Başlat
              </button>
            ) : (
              <button
                type="button"
                onClick={() => void action("stop", "Durdur")}
                disabled={busy}
                className="inline-flex min-h-[40px] items-center justify-center gap-2 rounded-lg bg-rose-600 px-4 py-2 text-xs font-bold text-white transition-colors hover:bg-rose-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <span className="h-2.5 w-2.5 rounded-[2px] bg-white" />
                Durdur
              </button>
            )}
            <button
              type="button"
              onClick={() => void action("run_once", "Tek döngü")}
              disabled={busy}
              className="inline-flex min-h-[40px] items-center justify-center rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-200 transition-colors hover:border-cyan-500/50 hover:text-cyan-200 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Tek döngü
            </button>
            <button
              type="button"
              onClick={() => void fetchStatus()}
              disabled={busy}
              className="col-span-2 inline-flex min-h-[40px] items-center justify-center rounded-lg border border-slate-800 bg-slate-900 px-4 py-2 text-xs font-semibold text-slate-400 transition-colors hover:border-slate-600 hover:text-slate-200 disabled:cursor-not-allowed disabled:opacity-50 sm:col-span-1"
            >
              Yenile
            </button>
          </div>

          {(msg || loadError || status.last_error) && (
            <div className="space-y-2 text-[11px]">
              {msg && <p className="rounded-lg border border-cyan-500/20 bg-cyan-500/10 px-3 py-2 text-cyan-200">{msg}</p>}
              {loadError && <p className="rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-amber-200">{loadError}</p>}
              {status.last_error && <p className="rounded-lg border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-rose-200">Son hata: {status.last_error}</p>}
            </div>
          )}
        </div>

        <div className="grid min-w-0 gap-3 sm:grid-cols-2 xl:grid-cols-6">
          <div className="rounded-xl border border-slate-800 bg-slate-950/35 p-4">
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">Döngü</p>
            <p className="mt-2 font-mono text-2xl font-bold text-slate-100">{status.cycle_count}</p>
            <p className="mt-1 text-[11px] text-slate-500">{formatAge(status.heartbeat_age_sec)}</p>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/35 p-4">
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">Son kayıt</p>
            <p className="mt-2 truncate font-mono text-sm font-semibold text-slate-200">
              {latestDecision ? latestDecision.symbol : "Yok"}
            </p>
            <p className="mt-1 text-[11px] text-slate-500">{latestDecision ? formatTimestamp(latestDecision.ts) : "Günlük boş"}</p>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/35 p-4">
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">Sinyal bütçesi</p>
            <p className="mt-2 font-mono text-2xl font-bold text-slate-100">
              {status.signals_today}<span className="text-sm text-slate-500">/{cfg.max_signals_per_day}</span>
            </p>
            <div className="mt-2 h-1.5 rounded-full bg-slate-800">
              <div
                className={cx("h-1.5 rounded-full", limitPct >= 100 ? "bg-rose-500" : "bg-amber-400")}
                style={{ width: `${limitPct}%` }}
              />
            </div>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/35 p-4">
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">Günlük</p>
            <p className="mt-2 font-mono text-2xl font-bold text-slate-100">{status.journal_size}</p>
            <p className="mt-1 text-[11px] text-slate-500">
              {journalStats.signals} sinyal · {journalStats.blocked} blok
            </p>
          </div>
        </div>
      </div>

      <div className="grid gap-4 p-4 lg:p-5 xl:grid-cols-[minmax(320px,0.82fr)_minmax(0,1.18fr)]">
        <div className="space-y-4">
          <div className="rounded-xl border border-slate-800 bg-slate-950/25 p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                  Çalışma ayarları
                </p>
                <p className="mt-1 text-[11px] text-slate-500">
                  {cfg.timeframe} · {cfg.horizon} · {formatInterval(cfg.interval_sec)}
                </p>
              </div>
              <span className="rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1 font-mono text-[11px] text-slate-300">
                {pct(cfg.min_confidence)}
              </span>
            </div>

            <div className="mt-4 space-y-4">
              <div>
                <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">Timeframe</p>
                <div className="grid grid-cols-3 gap-1.5 sm:grid-cols-6">
                  {TIMEFRAMES.map((tf) => (
                    <button
                      key={tf}
                      type="button"
                      onClick={() => void updateConfig({ timeframe: tf }, `Timeframe ${tf}`)}
                      disabled={busy || cfg.timeframe === tf}
                      className={cx(
                        "min-h-[34px] rounded-lg px-2 text-[11px] font-bold transition-colors disabled:cursor-not-allowed",
                        cfg.timeframe === tf
                          ? "bg-cyan-600 text-white"
                          : "border border-slate-700 bg-slate-800/70 text-slate-400 hover:border-cyan-500/40 hover:text-slate-200",
                      )}
                    >
                      {tf}
                    </button>
                  ))}
                </div>
              </div>

              {/* Vade kaldırıldı — Timeframe zaten analiz periyodunu belirliyor, Vade gereksizdi */}
              <div>
                <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">Döngü aralığı</p>
                <div className="grid grid-cols-5 gap-1.5">
                  {INTERVALS.map((seconds) => (
                    <button
                      key={seconds}
                      type="button"
                      onClick={() => void updateConfig({ interval_sec: seconds }, `Aralık ${formatInterval(seconds)}`)}
                      disabled={busy || cfg.interval_sec === seconds}
                      className={cx(
                        "min-h-[34px] rounded-lg px-1 text-[10px] font-semibold transition-colors disabled:cursor-not-allowed",
                        cfg.interval_sec === seconds
                          ? "bg-slate-600 text-white"
                          : "border border-slate-700 bg-slate-800/70 text-slate-400 hover:border-slate-500 hover:text-slate-200",
                      )}
                    >
                      {formatInterval(seconds)}
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">Min güven</p>
                  <div className="grid grid-cols-5 gap-1.5">
                    {CONFIDENCE_LEVELS.map((confidence) => (
                      <button
                        key={confidence}
                        type="button"
                        onClick={() => void updateConfig({ min_confidence: confidence }, `Min güven ${pct(confidence)}`)}
                        disabled={busy || Math.abs(cfg.min_confidence - confidence) < 0.001}
                        className={cx(
                          "min-h-[34px] rounded-lg px-1 text-[10px] font-semibold transition-colors disabled:cursor-not-allowed",
                          Math.abs(cfg.min_confidence - confidence) < 0.001
                            ? "bg-slate-600 text-white"
                            : "border border-slate-700 bg-slate-800/70 text-slate-400 hover:border-slate-500 hover:text-slate-200",
                        )}
                      >
                        {pct(confidence)}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">Min kenar</p>
                  <div className="grid grid-cols-5 gap-1.5">
                    {EDGE_LEVELS.map((edge) => (
                      <button
                        key={edge}
                        type="button"
                        onClick={() => void updateConfig({ min_score_edge: edge }, `Min kenar ${pct(edge)}`)}
                        disabled={busy || Math.abs(cfg.min_score_edge - edge) < 0.001}
                        className={cx(
                          "min-h-[34px] rounded-lg px-1 text-[10px] font-semibold transition-colors disabled:cursor-not-allowed",
                          Math.abs(cfg.min_score_edge - edge) < 0.001
                            ? "bg-slate-600 text-white"
                            : "border border-slate-700 bg-slate-800/70 text-slate-400 hover:border-slate-500 hover:text-slate-200",
                        )}
                      >
                        {pct(edge)}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div>
                <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">Günlük sinyal limiti</p>
                <div className="grid grid-cols-4 gap-1.5">
                  {DAILY_LIMITS.map((limit) => (
                    <button
                      key={limit}
                      type="button"
                      onClick={() => void updateConfig({ max_signals_per_day: limit }, `Günlük limit ${limit}`)}
                      disabled={busy || cfg.max_signals_per_day === limit}
                      className={cx(
                        "min-h-[34px] rounded-lg px-2 text-[11px] font-semibold transition-colors disabled:cursor-not-allowed",
                        cfg.max_signals_per_day === limit
                          ? "bg-slate-600 text-white"
                          : "border border-slate-700 bg-slate-800/70 text-slate-400 hover:border-slate-500 hover:text-slate-200",
                      )}
                    >
                      {limit}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-950/25 p-4">
            <div className="flex items-center justify-between gap-3">
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">İzleme listesi</p>
              <span className="font-mono text-[10px] text-slate-500">{cfg.watch_symbols.length} sembol</span>
            </div>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {cfg.watch_symbols.map((symbol) => (
                <span key={symbol} className="rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1 font-mono text-[11px] text-slate-200">
                  {symbol}
                </span>
              ))}
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-[minmax(0,1fr)_96px]">
              <input
                value={symbolDraft}
                onChange={(event) => setSymbolDraft(event.target.value)}
                className="min-h-[38px] min-w-0 rounded-lg border border-slate-700 bg-slate-900 px-3 font-mono text-xs text-slate-200 outline-none transition-colors placeholder:text-slate-600 focus:border-cyan-500/60"
                placeholder="BTC/USDT, ETH/USDT"
              />
              <button
                type="button"
                onClick={saveSymbols}
                disabled={busy || !canSaveSymbols}
                className="min-h-[38px] rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-3 text-xs font-bold text-cyan-200 transition-colors hover:bg-cyan-500/20 disabled:cursor-not-allowed disabled:border-slate-700 disabled:bg-slate-800 disabled:text-slate-500"
              >
                Kaydet
              </button>
            </div>
          </div>
        </div>

        <div className="min-w-0 rounded-xl border border-slate-800 bg-slate-950/25 p-4">
          <div className="flex flex-col gap-2 border-b border-slate-800 pb-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">Karar günlüğü</p>
              <p className="mt-1 text-[11px] text-slate-500">
                Son döngü: {formatTimestamp(status.last_cycle_ts)} · Başlangıç: {formatTimestamp(status.started_at)}
              </p>
            </div>
            <div className="flex items-center gap-2 text-[10px] text-slate-500">
              <span>{journal.length} gösteriliyor</span>
              <span className="h-1 w-1 rounded-full bg-slate-600" />
              <span>{status.journal_size} toplam</span>
            </div>
          </div>

          <div className="mt-3 hidden grid-cols-[70px_92px_74px_68px_116px_minmax(0,1fr)] gap-2 px-2 text-[9px] font-semibold uppercase tracking-[0.14em] text-slate-600 md:grid">
            <span>Saat</span>
            <span>Sembol</span>
            <span>Eğilim</span>
            <span>Skor</span>
            <span>Durum</span>
            <span>Gerekçe</span>
          </div>

          <div className="mt-2 max-h-[31rem] space-y-1.5 overflow-y-auto pr-1">
            {journal.length === 0 ? (
              <div className="grid min-h-[220px] place-items-center rounded-xl border border-dashed border-slate-800 bg-slate-950/40 px-4 text-center">
                <div>
                  <p className="text-sm font-semibold text-slate-400">Kayıt yok</p>
                  <p className="mt-1 text-[11px] text-slate-600">Agent döngüsü karar ürettiğinde burada listelenir.</p>
                </div>
              </div>
            ) : (
              journal.map((decision, index) => {
                const st = DECISION_STYLE[decision.decision] ?? { label: decision.decision, cls: "text-slate-400 bg-slate-700/35" };
                const direction = directionFor(decision.action);
                return (
                  <div
                    key={`${decision.ts}-${decision.symbol}-${index}`}
                    className="grid min-w-0 grid-cols-[64px_minmax(72px,0.8fr)_minmax(0,1.2fr)] gap-2 rounded-lg border border-slate-800/70 bg-slate-900/65 px-2.5 py-2 text-[11px] transition-colors hover:border-slate-700 md:grid-cols-[70px_92px_74px_68px_116px_minmax(0,1fr)]"
                  >
                    <span className="font-mono text-slate-500">{decision.ts ? decision.ts.slice(11, 19) : "--:--:--"}</span>
                    <span className="min-w-0 truncate font-mono font-semibold text-slate-200">{decision.symbol}</span>
                    <span className={cx("font-bold", direction.cls)}>{direction.label}</span>
                    <span className="hidden font-mono text-slate-500 md:block">{pct(decision.score)}</span>
                    <span className={cx("hidden w-fit rounded-md px-2 py-0.5 font-semibold md:block", st.cls)}>{st.label}</span>
                    <span className="col-span-3 min-w-0 truncate text-slate-500 md:col-span-1" title={decision.reason}>
                      {decision.reason}
                    </span>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </section>
  );
};
