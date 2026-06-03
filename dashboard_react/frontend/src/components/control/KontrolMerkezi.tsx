/**
 * KontrolMerkezi — AEGIS ana kontrol paneli.
 * 3 zone: Karar | Performans | Risk
 * Tek bakışta: "Şu an ne durumdasın?"
 */

import React from "react";
import { LineChart, Line, ResponsiveContainer, Tooltip, ReferenceLine } from "recharts";
import type { ConsensusResponse, MacroViewModel } from "../../types/dashboardV2";
import { DataStatusBadge } from "../ui/DataStatusBadge";
import { formatDataAge } from "../../utils/dataFreshness";

interface DailyPnL {
  date: string;
  realized_pnl: number;
  trade_count: number;
  kill_switch_threshold: number;
  kill_switch_active: boolean;
  message: string;
}

interface EquityPoint { timestamp: string; balance: number; }
interface OpenPosition { symbol: string; quantity: number; entry_price: number; current_price?: number; pnl?: number; }
interface PaperSession {
  current_balance: number;
  initial_capital: number;
  pnl: number;
  pnl_pct: number;
  equity_curve: EquityPoint[];
  positions: OpenPosition[];
  trades: { id: string; side: string; price: number; quantity: number; }[];
}

interface RationaleState {
  text: string;
  source: "groq" | "ollama" | "rule_based" | null;
  loading: boolean;
}

interface KontrolProps {
  macro: MacroViewModel | null;
  btcConsensus: ConsensusResponse | null;
  dailyPnl: DailyPnL | null;
  loading: boolean;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

const ACTION_CLS: Record<string, string> = {
  BUY:  "text-emerald-400 border-emerald-500/40 bg-emerald-500/10",
  HOLD: "text-amber-400  border-amber-500/40  bg-amber-500/10",
  SELL: "text-rose-400   border-rose-500/40   bg-rose-500/10",
};

const ACTION_TR: Record<string, string> = {
  BUY: "AL", HOLD: "TUT", SELL: "SAT",
};

const riskColor = (score: number) =>
  score < 0.35 ? "text-emerald-400"
  : score < 0.55 ? "text-amber-400"
  : "text-rose-400";

const riskLabel = (score: number) =>
  score < 0.35 ? "Düşük" : score < 0.55 ? "Orta" : "Yüksek";

const pnlColor = (v: number) => v >= 0 ? "text-emerald-400" : "text-rose-400";

const MODULE_COLORS: Record<string, string> = {
  touche: "bg-violet-400", fundamental: "bg-sky-400",
  news: "bg-amber-400", sentinel: "bg-rose-400", quantum: "bg-emerald-400",
};

// ── Zone 1: Karar Paneli ─────────────────────────────────────────────────────

const KararPaneli: React.FC<{ consensus: ConsensusResponse | null; loading: boolean }> = ({
  consensus, loading,
}) => {
  if (loading) return (
    <div className="animate-pulse space-y-3">
      <div className="h-16 rounded-xl bg-slate-700/50" />
      <div className="h-4 w-3/4 rounded bg-slate-700/50" />
      <div className="space-y-2">
        {[1,2,3,4,5].map(i => <div key={i} className="h-2 rounded-full bg-slate-700/40" />)}
      </div>
    </div>
  );

  if (!consensus) return (
    <div className="flex flex-col items-center justify-center py-6 text-slate-600">
      <p className="text-xs">BTC sinyali bekleniyor…</p>
    </div>
  );

  const action = consensus.action;
  const cls = ACTION_CLS[action] ?? ACTION_CLS.HOLD;
  const confidencePct = Math.round(consensus.confidence * 100);
  const fiveModScore = (consensus.five_module_score * 100).toFixed(1);
  const scores = consensus.module_scores;

  return (
    <div className="space-y-4">
      {/* Sinyal */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">BTC Sinyali</p>
          <p className={`mt-0.5 text-3xl font-extrabold leading-none ${cls.split(" ")[0]}`}>
            {ACTION_TR[action] ?? action}
          </p>
        </div>
        <div className="text-right">
          <p className="text-[9px] uppercase tracking-wider text-slate-600">Güven</p>
          <p className="font-mono text-2xl font-bold text-white">{confidencePct}<span className="text-sm text-slate-500">%</span></p>
          <p className="text-[9px] text-slate-600">5-Mod: {fiveModScore}</p>
        </div>
      </div>

      {/* Green light */}
      {consensus.green_light && consensus.verified && (
        <div className="flex items-center gap-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-2.5 py-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-[10px] font-semibold text-emerald-400">ONAY — Tüm filtreler geçildi</span>
        </div>
      )}

      {/* Modül skorları */}
      <div className="space-y-1.5">
        {Object.entries(scores).map(([mod, val]) => {
          const pct = Math.min(100, Math.max(0, Math.round((val as number) * 100)));
          return (
            <div key={mod} className="flex items-center gap-2">
              <span className="w-3 shrink-0 font-mono text-[9px] font-bold uppercase text-slate-500">
                {mod[0].toUpperCase()}
              </span>
              <div className="h-1.5 flex-1 rounded-full bg-slate-700/60">
                <div
                  className={`h-1.5 rounded-full ${MODULE_COLORS[mod] ?? "bg-slate-400"} transition-all duration-500`}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="w-6 shrink-0 text-right font-mono text-[9px] text-slate-500">{pct}</span>
            </div>
          );
        })}
      </div>

      {/* Data status */}
      <DataStatusBadge data={consensus} compact className="mt-1" />
    </div>
  );
};

// ── Zone 2: Performans ────────────────────────────────────────────────────────

const PerformansPaneli: React.FC<{ pnl: DailyPnL | null; paper: PaperSession | null }> = ({ pnl, paper }) => {
  const initialCapital = paper?.initial_capital ?? 10000;
  const curveData = (paper?.equity_curve ?? []).map(p => ({
    ts: new Date(p.timestamp).getTime(),
    v: p.balance,
  }));
  const firstBalance = curveData[0]?.v ?? initialCapital;

  return (
    <div className="space-y-3">
      <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">
        Performans
      </p>

      {/* Kill switch P&L */}
      {pnl && (
        <div className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2">
          <div>
            <p className="text-[9px] text-slate-600">Günlük P&L</p>
            <p className={`font-mono text-lg font-bold ${pnlColor(pnl.realized_pnl)}`}>
              {pnl.realized_pnl >= 0 ? "+" : ""}${pnl.realized_pnl.toFixed(2)}
            </p>
          </div>
          <div className="text-right">
            <p className="text-[9px] text-slate-600">{pnl.trade_count} işlem</p>
            <p className={`text-[10px] font-semibold ${pnl.kill_switch_active ? "text-rose-400" : "text-emerald-400"}`}>
              {pnl.kill_switch_active ? "⚠ LİMİT" : "● Normal"}
            </p>
          </div>
        </div>
      )}

      {/* Equity Curve */}
      <div>
        <div className="mb-1 flex items-center justify-between">
          <p className="text-[9px] text-slate-600">Equity Curve — Paper</p>
          {paper && (
            <p className={`font-mono text-[10px] font-semibold ${pnlColor(paper.pnl)}`}>
              ${paper.current_balance.toFixed(0)}
              <span className="ml-1 text-[9px] text-slate-600">
                ({paper.pnl >= 0 ? "+" : ""}{paper.pnl_pct.toFixed(1)}%)
              </span>
            </p>
          )}
        </div>

        {curveData.length >= 2 ? (
          <div className="h-16 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={curveData} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
                <ReferenceLine y={firstBalance} stroke="#334155" strokeDasharray="3 3" />
                <Line
                  type="monotone"
                  dataKey="v"
                  stroke={paper && paper.pnl >= 0 ? "#34d399" : "#f87171"}
                  strokeWidth={1.5}
                  dot={false}
                  isAnimationActive={false}
                />
                <Tooltip
                  contentStyle={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 6, fontSize: 10 }}
                  formatter={(v: number) => [`$${v.toFixed(0)}`, "Bakiye"]}
                  labelFormatter={() => ""}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="flex h-16 items-center justify-center rounded-lg border border-slate-800 bg-slate-950/30">
            <p className="text-[9px] text-slate-700">
              {paper ? "Yeterli veri yok" : "Paper trading başlatılmadı"}
            </p>
          </div>
        )}
      </div>

      {/* Açık Pozisyonlar */}
      <div>
        <p className="mb-1.5 text-[9px] font-semibold uppercase tracking-wider text-slate-600">
          Açık Pozisyonlar {paper?.positions?.length ? `(${paper.positions.length})` : ""}
        </p>
        {paper?.positions?.length ? (
          <div className="space-y-1.5">
            {paper.positions.slice(0, 3).map((pos, i) => (
              <div key={i} className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-950/30 px-2.5 py-1.5">
                <div className="flex items-center gap-2">
                  <span className="text-[9px] font-bold text-slate-400">{pos.symbol.replace("/USDT", "")}</span>
                  <span className="text-[9px] text-slate-600">{pos.quantity.toFixed(4)}</span>
                </div>
                <div className="text-right">
                  <p className="font-mono text-[9px] text-slate-400">${pos.entry_price.toFixed(0)}</p>
                  {pos.pnl !== undefined && (
                    <p className={`font-mono text-[9px] font-semibold ${pnlColor(pos.pnl)}`}>
                      {pos.pnl >= 0 ? "+" : ""}${pos.pnl.toFixed(1)}
                    </p>
                  )}
                </div>
              </div>
            ))}
            {paper.positions.length > 3 && (
              <p className="text-[9px] text-slate-700">+{paper.positions.length - 3} pozisyon daha</p>
            )}
          </div>
        ) : (
          <p className="text-[9px] italic text-slate-700">Açık pozisyon yok</p>
        )}
      </div>
    </div>
  );
};

// ── Zone 3: Risk Göstergesi ────────────────────────────────────────────────────

const RiskPaneli: React.FC<{ macro: MacroViewModel | null; pnl: DailyPnL | null }> = ({ macro, pnl }) => {
  const eventRisk = macro?.metrics?.event_risk_score ?? null;
  const vix       = macro?.metrics?.vix ?? null;
  const hyg       = (macro?.metrics as Record<string, number> | undefined)?.hyg ?? null;
  const funding   = (macro?.metrics as Record<string, number> | undefined)?.funding_rate ?? null;

  const killActive = pnl?.kill_switch_active ?? false;

  return (
    <div className="space-y-3">
      <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">
        Risk Monitörü
      </p>

      {/* Kill Switch */}
      <div className={`flex items-center justify-between rounded-lg border px-3 py-2 ${
        killActive
          ? "border-rose-500/50 bg-rose-500/10"
          : "border-emerald-500/20 bg-emerald-500/5"
      }`}>
        <span className="text-[11px] font-semibold text-slate-300">Kill Switch</span>
        <span className={`text-[11px] font-bold ${killActive ? "text-rose-400" : "text-emerald-400"}`}>
          {killActive ? "⚠ AKTİF" : "● KAPALI"}
        </span>
      </div>

      {/* Makro risk göstergeleri */}
      <div className="space-y-2 rounded-xl border border-slate-800 bg-slate-950/40 p-3">
        {[
          { label: "Olay Riski",  value: eventRisk !== null ? `${(eventRisk * 100).toFixed(0)}%` : "—", color: eventRisk !== null ? riskColor(eventRisk) : "text-slate-600", sub: eventRisk !== null ? riskLabel(eventRisk) : "" },
          { label: "VIX",         value: vix !== null ? vix.toFixed(1) : "—",  color: vix !== null ? (vix < 18 ? "text-emerald-400" : vix < 28 ? "text-amber-400" : "text-rose-400") : "text-slate-600", sub: vix !== null ? (vix < 18 ? "Sakin" : vix < 28 ? "Normal" : "Yüksek") : "" },
          { label: "HYG",         value: hyg !== null ? hyg.toFixed(1) : "—",  color: hyg !== null ? (hyg > 77 ? "text-emerald-400" : hyg > 74 ? "text-amber-400" : "text-rose-400") : "text-slate-600", sub: hyg !== null ? (hyg > 77 ? "Güçlü" : hyg > 74 ? "Zayıflıyor" : "Bozulmuş") : "" },
          { label: "Funding",     value: funding !== null ? `${(funding * 100).toFixed(3)}%` : "—", color: funding !== null ? (Math.abs(funding) < 0.02 ? "text-emerald-400" : Math.abs(funding) < 0.05 ? "text-amber-400" : "text-rose-400") : "text-slate-600", sub: funding !== null ? (funding > 0.05 ? "Uzun Kalabalık" : funding < -0.05 ? "Kısa Kalabalık" : "Normal") : "" },
        ].map(({ label, value, color, sub }) => (
          <div key={label} className="flex items-center justify-between">
            <span className="text-[10px] text-slate-500">{label}</span>
            <div className="text-right">
              <span className={`font-mono text-[11px] font-semibold ${color}`}>{value}</span>
              {sub && <span className="ml-1.5 text-[9px] text-slate-600">{sub}</span>}
            </div>
          </div>
        ))}
      </div>

      {/* Makro rejim */}
      {macro && (
        <div className="rounded-lg border border-slate-800 bg-slate-950/30 px-3 py-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-slate-500">Rejim</span>
            <span className="font-mono text-[11px] font-semibold text-sky-300">{macro.regime}</span>
          </div>
          <div className="flex items-center justify-between mt-1">
            <span className="text-[10px] text-slate-500">Makro Durum</span>
            <DataStatusBadge data={macro} compact />
          </div>
        </div>
      )}
    </div>
  );
};

// ── Ana Bileşen ───────────────────────────────────────────────────────────────

const SOURCE_BADGE: Record<string, string> = {
  groq:       "text-violet-400",
  ollama:     "text-emerald-400",
  rule_based: "text-slate-500",
};
const SOURCE_LABEL: Record<string, string> = {
  groq:       "Groq",
  ollama:     "Ollama",
  rule_based: "Kural",
};

export const KontrolMerkezi: React.FC<KontrolProps> = ({
  macro, btcConsensus, dailyPnl, loading,
}) => {
  const [rationale, setRationale] = React.useState<RationaleState>({
    text: "", source: null, loading: false,
  });

  // Paper trading session — 30s polling
  const [paper, setPaper] = React.useState<PaperSession | null>(null);
  React.useEffect(() => {
    const API = (import.meta.env.VITE_API_URL as string | undefined) || "http://localhost:8502";
    const fetch_ = () =>
      fetch(`${API}/api/paper/status`)
        .then(r => r.ok ? r.json() : null)
        .then(d => d && setPaper(d))
        .catch(() => {});
    fetch_();
    const id = setInterval(fetch_, 30_000);
    return () => clearInterval(id);
  }, []);

  const fetchRationale = React.useCallback(async () => {
    if (!btcConsensus || rationale.loading) return;
    setRationale(r => ({ ...r, loading: true }));

    const API = (import.meta.env.VITE_API_URL as string | undefined) || "http://localhost:8502";
    const ctx = {
      action:            btcConsensus.action,
      confidence_pct:    Math.round(btcConsensus.confidence * 100),
      five_module_score: btcConsensus.five_module_score,
      regime:            macro?.regime ?? "NORMALIZATION",
      event_risk_pct:    (macro?.metrics?.event_risk_score ?? 0.3) * 100,
      vix:               macro?.metrics?.vix ?? null,
      hyg:               (macro?.metrics as Record<string, number> | undefined)?.hyg ?? null,
      funding_rate_pct:  ((macro?.metrics as Record<string, number> | undefined)?.funding_rate ?? 0) * 100,
      module_scores:     btcConsensus.module_scores,
      symbol:            btcConsensus.symbol ?? "BTC",
      timeframe:         btcConsensus.timeframe ?? "4h",
      warnings:          btcConsensus.warnings ?? [],
    };

    try {
      const res = await fetch(`${API}/api/signal/rationale`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(ctx),
      });
      const data = await res.json();
      setRationale({ text: data.text, source: data.source, loading: false });
    } catch {
      setRationale({ text: "Gerekçe alınamadı.", source: "rule_based", loading: false });
    }
  }, [btcConsensus, macro, rationale.loading]);

  return (
    <div className="space-y-4">
    <div className="grid gap-4 lg:grid-cols-3">

      {/* Zone 1: Karar */}
      <div className="rounded-2xl border border-slate-700/60 bg-slate-900 p-5 shadow-md">
        <p className="mb-4 text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">
          Karar Paneli
        </p>
        <KararPaneli consensus={btcConsensus} loading={loading} />
      </div>

      {/* Zone 2: Performans */}
      <div className="rounded-2xl border border-slate-700/60 bg-slate-900 p-5 shadow-md">
        <PerformansPaneli pnl={dailyPnl} paper={paper} />
      </div>

      {/* Zone 3: Risk */}
      <div className="rounded-2xl border border-slate-700/60 bg-slate-900 p-5 shadow-md">
        <RiskPaneli macro={macro} pnl={dailyPnl} />
      </div>

    </div>

    {/* LLM Sinyal Gerekçesi */}
    <div className="rounded-2xl border border-slate-700/40 bg-slate-900/60 p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">
            AI Gerekçe
          </p>
          {rationale.source && (
            <span className={`text-[9px] font-mono ${SOURCE_BADGE[rationale.source] ?? "text-slate-600"}`}>
              [{SOURCE_LABEL[rationale.source] ?? rationale.source}]
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={fetchRationale}
          disabled={rationale.loading || !btcConsensus}
          className="flex shrink-0 items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-[10px] font-semibold text-slate-300 transition-colors hover:border-violet-500/50 hover:text-violet-300 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {rationale.loading ? (
            <>
              <span className="h-2 w-2 animate-spin rounded-full border-2 border-slate-600 border-t-violet-400" />
              Üretiliyor…
            </>
          ) : (
            <>
              <span className="text-[11px]">✦</span>
              {rationale.text ? "Yenile" : "Gerekçe Üret"}
            </>
          )}
        </button>
      </div>

      {rationale.text ? (
        <p className="mt-3 text-[12px] leading-6 text-slate-300">
          {rationale.text}
        </p>
      ) : (
        <p className="mt-2 text-[10px] italic text-slate-700">
          Mevcut sinyal için Groq veya Ollama'dan Türkçe gerekçe almak için butona bas.
        </p>
      )}
    </div>
    </div>
  );
};
