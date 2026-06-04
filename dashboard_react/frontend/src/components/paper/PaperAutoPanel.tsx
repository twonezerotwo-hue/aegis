/**
 * PaperAutoPanel — agent'ın config'ini gerçek zamanlı, parasız test eder.
 * Backtest sinyal mantığını canlı veride çalıştırır, sanal P&L izler.
 */
import React, { useState, useEffect, useCallback } from "react";
import { LineChart, Line, ResponsiveContainer, Tooltip, ReferenceLine } from "recharts";

const API_BASE = (import.meta as any).env?.VITE_API_URL || "http://localhost:8502";

interface Trade {
  side: string; entry_price: number; exit_price: number;
  entry_time: string; exit_time: string; pnl_pct: number; pnl_usd: number; reason: string;
}
interface PaperStatus {
  running: boolean; symbol: string; timeframe: string;
  config_summary: string; cycle_count: number; last_cycle_ts: string | null;
  balance: number; equity: number; initial_capital: number;
  total_pnl_usd: number; total_pnl_pct: number;
  position: string | null; entry_price: number | null; entry_z: number | null;
  position_size_pct: number; open_pnl_pct: number;
  last_price: number | null; last_signal: number | null; last_z: number | null;
  trade_count: number; win_count: number; win_rate: number;
  recent_trades: Trade[];
  equity_curve_compact: { ts: string; equity: number }[];
  message: string; started_at: string | null;
}

const REASON_TR: Record<string, string> = {
  stop_loss: "Stop", take_profit: "Kâr Al", z_reversion: "Z dönüş", reverse_signal: "Ters sinyal",
};

export const PaperAutoPanel: React.FC = () => {
  const [s, setS] = useState<PaperStatus | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    fetch(`${API_BASE}/api/paper_auto/status`).then(r => r.json()).then(setS).catch(() => {});
  }, []);
  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 8000);
    return () => clearInterval(id);
  }, [refresh]);

  const act = async (path: string, body?: any) => {
    setBusy(true);
    try {
      await fetch(`${API_BASE}/api/paper_auto/${path}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
      refresh();
    } finally { setBusy(false); }
  };

  if (!s) return null;

  const pnlCls = (v: number) => v > 0 ? "text-emerald-400" : v < 0 ? "text-rose-400" : "text-slate-400";
  const sigLabel = s.last_signal === 1 ? "AL" : s.last_signal === -1 ? "SAT" : "BEKLE";
  const sigCls = s.last_signal === 1 ? "text-emerald-400" : s.last_signal === -1 ? "text-rose-400" : "text-slate-500";
  const curve = (s.equity_curve_compact ?? []).map((p, i) => ({ i, equity: p.equity }));

  return (
    <div className="rounded-2xl border border-cyan-500/30 bg-slate-900 p-5 shadow-lg ring-1 ring-cyan-500/10">
      {/* Başlık */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2">
          <span className="text-cyan-400 text-lg">📝</span>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-cyan-400">Otonom Paper Trading</p>
            <p className="font-mono text-[10px] text-slate-500">agent config'i · gerçek zamanlı · parasız test</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {s.running ? (
            <button onClick={() => act("stop")} disabled={busy}
              className="rounded-lg bg-rose-600 px-4 py-2 text-xs font-bold text-white hover:bg-rose-500 disabled:opacity-50">■ Durdur</button>
          ) : (
            <button onClick={() => act("start")} disabled={busy}
              className="rounded-lg bg-cyan-600 px-4 py-2 text-xs font-bold text-white hover:bg-cyan-500 disabled:opacity-50">▶ Başlat</button>
          )}
          <button onClick={() => act("reset")} disabled={busy}
            className="rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-700 disabled:opacity-50">↻ Sıfırla</button>
        </div>
      </div>

      {/* Test edilen config */}
      <div className="mb-3 flex flex-wrap items-center gap-2 rounded-xl border border-slate-700/50 bg-slate-800/40 px-3 py-2 text-[10px]">
        <span className="font-semibold text-slate-400">Test edilen ayar:</span>
        <span className="font-mono text-cyan-300">{s.config_summary || "—"}</span>
        <span className={`ml-auto flex items-center gap-1 ${s.running ? "text-emerald-400" : "text-slate-500"}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${s.running ? "bg-emerald-400 animate-pulse" : "bg-slate-600"}`} />
          {s.running ? `canlı · ${s.cycle_count} cycle` : "durdu"}
        </span>
      </div>

      {/* Ana metrikler */}
      <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {[
          { k: "Equity", v: `$${s.equity.toLocaleString("en-US", { maximumFractionDigits: 0 })}`, cls: "text-white" },
          { k: "Toplam P&L", v: `${s.total_pnl_pct >= 0 ? "+" : ""}${s.total_pnl_pct.toFixed(2)}%`, cls: pnlCls(s.total_pnl_pct) },
          { k: "İşlem", v: `${s.win_count}/${s.trade_count} (${s.win_rate}%)`, cls: "text-slate-300" },
          { k: "Anlık Fiyat", v: s.last_price ? `$${s.last_price.toLocaleString("en-US", { maximumFractionDigits: 0 })}` : "—", cls: "text-slate-300" },
        ].map(({ k, v, cls }) => (
          <div key={k} className="rounded-xl border border-slate-700/40 bg-slate-800/40 px-3 py-2">
            <p className="text-[8px] uppercase tracking-widest text-slate-600">{k}</p>
            <p className={`font-mono text-sm font-bold ${cls}`}>{v}</p>
          </div>
        ))}
      </div>

      {/* Açık pozisyon / sinyal durumu */}
      <div className={`mb-3 rounded-xl border px-3 py-2.5 ${
        s.position ? "border-cyan-500/30 bg-cyan-500/5" : "border-slate-700/50 bg-slate-800/30"
      }`}>
        {s.position ? (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px]">
            <span className={`rounded-md border px-2 py-0.5 font-bold ${
              s.position === "LONG" ? "border-emerald-500/40 text-emerald-400" : "border-rose-500/40 text-rose-400"
            }`}>{s.position === "LONG" ? "LONG (AL)" : "SHORT (SAT)"}</span>
            <span className="text-slate-400">giriş ${s.entry_price} (z={s.entry_z})</span>
            <span className="text-slate-500">boyut {(s.position_size_pct * 100).toFixed(0)}%</span>
            <span className={`font-mono font-bold ${pnlCls(s.open_pnl_pct)}`}>anlık {s.open_pnl_pct >= 0 ? "+" : ""}{s.open_pnl_pct.toFixed(2)}%</span>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px]">
            <span className="text-slate-400">Pozisyon yok — sinyal bekleniyor</span>
            <span className="text-slate-500">şu anki sinyal: <span className={`font-bold ${sigCls}`}>{sigLabel}</span></span>
            <span className="text-slate-500">z-score: <span className="font-mono text-slate-300">{s.last_z}</span></span>
          </div>
        )}
      </div>

      {/* Equity eğrisi */}
      {curve.length > 2 && (
        <div className="mb-3 h-28 rounded-xl border border-slate-800 bg-slate-950/40 p-2">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={curve}>
              <ReferenceLine y={s.initial_capital} stroke="#475569" strokeDasharray="3 3" />
              <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", fontSize: 10 }}
                       formatter={(v: any) => [`$${Number(v).toFixed(0)}`, "Equity"]} labelFormatter={() => ""} />
              <Line type="monotone" dataKey="equity" stroke={s.total_pnl_pct >= 0 ? "#34d399" : "#fb7185"}
                    strokeWidth={1.5} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Son işlemler */}
      <div>
        <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-slate-500">Son İşlemler</p>
        {s.recent_trades.length === 0 ? (
          <p className="py-3 text-center text-[11px] text-slate-600">
            {s.running ? "Henüz işlem yok — agent sinyal bekliyor (1d nadiren işlem açar)" : "Başlat ile testi aç"}
          </p>
        ) : (
          <div className="max-h-48 space-y-1 overflow-y-auto">
            {s.recent_trades.map((t, i) => (
              <div key={i} className="flex items-center gap-2 rounded-lg bg-slate-800/40 px-2.5 py-1.5 text-[10px]">
                <span className="font-mono text-slate-600">{(t.exit_time || "").slice(5, 16).replace("T", " ")}</span>
                <span className={`w-12 shrink-0 font-bold ${t.side === "LONG" ? "text-emerald-400" : "text-rose-400"}`}>{t.side}</span>
                <span className="font-mono text-slate-500">${t.entry_price}→${t.exit_price}</span>
                <span className={`font-mono font-bold ${pnlCls(t.pnl_pct)}`}>{t.pnl_pct >= 0 ? "+" : ""}{t.pnl_pct}%</span>
                <span className={`font-mono ${pnlCls(t.pnl_usd)}`}>${t.pnl_usd}</span>
                <span className="ml-auto rounded bg-slate-700/40 px-1.5 py-0.5 text-slate-400">{REASON_TR[t.reason] ?? t.reason}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <p className="mt-2 text-[9px] leading-4 text-slate-600">
        🛡 Sanal — gerçek emir yok. Agent'ın OOS-doğrulanmış config'i canlı fiyatta gerçek zamanlı test edilir.
        Backtest'in canlıda gerçekten çalışıp çalışmadığını gösterir. 1d config az işlem açar — sabırlı ol.
      </p>
    </div>
  );
};
