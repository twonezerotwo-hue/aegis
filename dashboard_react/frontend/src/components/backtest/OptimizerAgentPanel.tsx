/**
 * OptimizerAgentPanel — Strateji uzayını tarayan optimizasyon agent'ı.
 *
 * Tüm parametre kombinasyonlarını dener (akıllı örnekleme), her adayı
 * OUT-OF-SAMPLE doğrular, OOS'de kârlı olan en iyiyi OTOMATİK uygular.
 * OOS'i geçen yoksa mevcut ayar korunur (overfitting koruması).
 */
import React, { useState, useEffect, useCallback } from "react";

const API_BASE = (import.meta as any).env?.VITE_API_URL || "http://localhost:8502";

interface OptResult {
  timeframe: string;
  params: {
    z_threshold: number; stop_loss_pct: number; take_profit_pct: number;
    z_exit_long: number; adx_min: number; kelly_cap: number;
    contrarian: boolean; weights: Record<string, number>;
  };
  full_pnl_pct: number;
  oos_pnl_pct: number | null;
  is_pnl_pct: number | null;
  win_rate: number;
  profit_factor: number;
  sharpe: number;
  max_dd_pct: number;
  num_trades: number;
  oos_trades: number;
  oos_validated: boolean;
  robust_score?: number;
}

interface AutoStatus {
  auto_enabled: boolean;
  interval_hours: number;
  last_auto_run: string | null;
  next_auto_run: string | null;
  min_profit_factor: number;
}

interface OptStatus {
  running: boolean;
  progress: number;
  current_tf: string;
  evaluated: number;
  total: number;
  message: string;
  best: OptResult | null;
  applied: OptResult | null;
  last_error: string | null;
  results_count: number;
  config: { timeframes: string[]; n_candidates_per_tf: number; oos_fraction: number };
  auto?: AutoStatus;
}

export const OptimizerAgentPanel: React.FC = () => {
  const [status, setStatus] = useState<OptStatus | null>(null);
  const [results, setResults] = useState<OptResult[]>([]);
  const [applied, setApplied] = useState<any | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    fetch(`${API_BASE}/api/optimizer/status`).then(r => r.json()).then(setStatus).catch(() => {});
    fetch(`${API_BASE}/api/optimizer/results?limit=10`).then(r => r.json())
      .then(d => setResults(d.validated ?? [])).catch(() => {});
    fetch(`${API_BASE}/api/optimizer/applied`).then(r => r.json())
      .then(d => setApplied(d.applied)).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 4000);
    return () => clearInterval(id);
  }, [refresh]);

  const run = async () => {
    setBusy(true);
    try {
      await fetch(`${API_BASE}/api/optimizer/run`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ timeframes: ["4h", "1d"], n_candidates_per_tf: 80 }),
      });
      refresh();
    } finally { setBusy(false); }
  };
  const stop = async () => {
    setBusy(true);
    try { await fetch(`${API_BASE}/api/optimizer/stop`, { method: "POST" }); refresh(); }
    finally { setBusy(false); }
  };
  const toggleAuto = async (on: boolean) => {
    setBusy(true);
    try {
      await fetch(`${API_BASE}/api/optimizer/auto/${on ? "start" : "stop"}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: on ? JSON.stringify({ auto_interval_hours: 24, n_candidates_per_tf: 80 }) : undefined,
      });
      refresh();
    } finally { setBusy(false); }
  };

  if (!status) return null;
  const auto = status.auto;

  const pct = Math.round((status.progress ?? 0) * 100);
  const pnlCls = (v: number | null) => v == null ? "text-slate-500" : v > 0 ? "text-emerald-400" : "text-rose-400";

  return (
    <div className="rounded-2xl border border-violet-500/30 bg-slate-900 p-5 shadow-lg ring-1 ring-violet-500/10">
      {/* Başlık + kontroller */}
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2">
          <span className="text-violet-400 text-lg">🔬</span>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-violet-400">Optimizasyon Agent</p>
            <p className="font-mono text-[10px] text-slate-500">
              tüm uzayı tarar · OOS-doğrular · en iyiyi otomatik uygular
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Otonom mod düğmesi */}
          <button onClick={() => toggleAuto(!auto?.auto_enabled)} disabled={busy}
            className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-bold transition-colors disabled:opacity-50 ${
              auto?.auto_enabled
                ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-400"
                : "border-slate-600 bg-slate-800 text-slate-400 hover:bg-slate-700"
            }`}>
            <span className={`h-1.5 w-1.5 rounded-full ${auto?.auto_enabled ? "bg-emerald-400 animate-pulse" : "bg-slate-600"}`} />
            Otonom {auto?.auto_enabled ? "AÇIK" : "KAPALI"}
          </button>
          {status.running ? (
            <button onClick={stop} disabled={busy}
              className="rounded-lg bg-rose-600 px-4 py-2 text-xs font-bold text-white hover:bg-rose-500 disabled:opacity-50">
              ■ Durdur
            </button>
          ) : (
            <button onClick={run} disabled={busy}
              className="rounded-lg bg-violet-600 px-4 py-2 text-xs font-bold text-white hover:bg-violet-500 disabled:opacity-50">
              ▶ Tek Sefer Tara
            </button>
          )}
        </div>
      </div>

      {/* Otonom durum şeridi */}
      {auto?.auto_enabled && (
        <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-3 py-2 text-[10px] text-emerald-300">
          <span className="font-semibold">🔄 Otonom mod aktif</span>
          <span className="text-slate-400">her {auto.interval_hours}s'te yeniden tarar</span>
          <span className="text-slate-400">PF kapısı ≥ {auto.min_profit_factor}</span>
          {auto.next_auto_run && <span className="text-slate-500">sonraki: {auto.next_auto_run.slice(5, 16).replace("T", " ")}</span>}
        </div>
      )}

      {/* İlerleme */}
      {status.running && (
        <div className="mb-3">
          <div className="mb-1 flex justify-between text-[10px] text-slate-500">
            <span>Taranıyor: {status.current_tf} · {status.evaluated}/{status.total} aday · {status.results_count} geçerli backtest</span>
            <span className="font-mono">{pct}%</span>
          </div>
          <div className="h-2 w-full rounded-full bg-slate-800">
            <div className="h-2 rounded-full bg-violet-500 transition-all" style={{ width: `${pct}%` }} />
          </div>
        </div>
      )}

      {/* Mesaj */}
      <div className={`mb-3 rounded-xl border px-3 py-2 text-[11px] ${
        status.message.includes("✓") ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-300"
        : status.message.includes("⚠") ? "border-amber-500/30 bg-amber-500/5 text-amber-300"
        : "border-slate-700/50 bg-slate-800/40 text-slate-400"
      }`}>
        {status.message || "Hazır — “Optimizasyonu Başlat” ile tüm uzayı tara."}
      </div>

      {/* Uygulanan config */}
      {applied && (
        <div className="mb-3 rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-3">
          <p className="mb-1.5 text-[9px] font-bold uppercase tracking-widest text-emerald-500">✓ Sisteme Uygulanan Ayar</p>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px]">
            <span className="font-mono font-bold text-white">{applied.timeframe}</span>
            <span className="text-slate-400">{applied.params?.contrarian ? "Kontrarian" : "Momentum"}</span>
            <span className="text-slate-500">z={applied.params?.z_threshold} sl={applied.params?.stop_loss_pct} tp={applied.params?.take_profit_pct} adx={applied.params?.adx_min}</span>
            <span className={pnlCls(applied.evidence?.oos_pnl_pct)}>OOS +{applied.evidence?.oos_pnl_pct?.toFixed(1)}%</span>
            <span className="text-slate-500">WR {applied.evidence?.win_rate?.toFixed(0)}% · PF {applied.evidence?.profit_factor} · Sharpe {applied.evidence?.sharpe}</span>
          </div>
        </div>
      )}

      {/* Doğrulanmış sonuçlar tablosu */}
      <div>
        <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
          OOS-Doğrulanmış Adaylar (görülmemiş veride kârlı)
        </p>
        <div className="overflow-x-auto">
          {results.length === 0 ? (
            <p className="py-3 text-center text-[11px] text-slate-600">
              {status.running ? "Taranıyor…" : "Henüz doğrulanmış sonuç yok"}
            </p>
          ) : (
            <table className="w-full text-[10px]">
              <thead>
                <tr className="border-b border-slate-800 text-slate-600">
                  <th className="py-1.5 text-left">TF</th>
                  <th className="py-1.5 text-left">Yön</th>
                  <th className="py-1.5 text-right">Sağlam</th>
                  <th className="py-1.5 text-right">OOS PnL</th>
                  <th className="py-1.5 text-right">WR</th>
                  <th className="py-1.5 text-right">PF</th>
                  <th className="py-1.5 text-right">Sharpe</th>
                  <th className="py-1.5 text-right">MaxDD</th>
                  <th className="py-1.5 text-right">İşlem</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r, i) => (
                  <tr key={i} className={`border-b border-slate-800/50 ${i === 0 ? "bg-emerald-500/5" : ""}`}>
                    <td className="py-1.5 font-mono font-bold text-white">{r.timeframe}{i === 0 && " 🏆"}</td>
                    <td className="py-1.5 text-slate-400">{r.params.contrarian ? "Kont." : "Mom."}</td>
                    <td className="py-1.5 text-right font-mono font-bold text-violet-300">{r.robust_score ?? "—"}</td>
                    <td className={`py-1.5 text-right font-mono ${pnlCls(r.oos_pnl_pct)}`}>
                      {r.oos_pnl_pct != null ? `${r.oos_pnl_pct > 0 ? "+" : ""}${r.oos_pnl_pct.toFixed(1)}%` : "—"}
                    </td>
                    <td className="py-1.5 text-right font-mono text-slate-400">{r.win_rate.toFixed(0)}%</td>
                    <td className="py-1.5 text-right font-mono text-slate-400">{r.profit_factor}</td>
                    <td className="py-1.5 text-right font-mono text-slate-400">{r.sharpe}</td>
                    <td className="py-1.5 text-right font-mono text-rose-400/70">{r.max_dd_pct}%</td>
                    <td className="py-1.5 text-right font-mono text-slate-500">{r.num_trades}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <p className="mt-2 text-[9px] leading-4 text-slate-600">
        🛡 Güvenlik: aday config tüm geçmişte optimize edilir ama görülmemiş son %{Math.round((status.config?.oos_fraction ?? 0.3) * 100)}'te
        (out-of-sample) de kârlı olmazsa otomatik UYGULANMAZ — overfitting'den kaçınmak için. Gerçek Binance OHLCV +
        18-gösterge konfluens + gerçek haber verisiyle (mock yok). Paper trading ile canlı doğrulanır.
      </p>
    </div>
  );
};
