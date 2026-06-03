/**
 * AdvancedAnalytics — Masterclass backtest metrikleri
 *
 * VectorBT + QuantStats + backtesting.py + Zipline + Freqtrade ilhamı:
 *   - VaR / CVaR gaugeleri
 *   - Monte Carlo bootstrap güven aralıkları
 *   - Benchmark (BTC buy & hold) alpha/beta
 *   - Calmar, Omega, Sharpe, Sortino yan yana
 *   - Slippage maliyet özeti
 */
import React, { useState, useEffect } from "react";

/* ── Tipler ─────────────────────────────────────────────────────── */
interface McDist {
  p5: number; p25: number; p50: number; p75: number; p95: number;
  mean: number; std: number;
}

interface MonteCarloResult {
  n_sims:       number;
  n_trades:     number;
  total_return: McDist;
  win_rate:     McDist;
  max_drawdown: McDist;
  sharpe_ratio: McDist;
  original: { total_return: number; win_rate: number; max_drawdown: number };
  confidence: {
    return_percentile:  number;
    winrate_percentile: number;
    edge_real:          boolean;
    interpretation:     string;
  };
}

interface AdvancedMetrics {
  calmar_ratio?:             number;
  omega_ratio?:              number;
  var_95_pct?:               number;
  cvar_95_pct?:              number;
  var_95_dollar?:            number;
  cvar_95_dollar?:           number;
  annualized_return_pct?:    number;
  max_drawdown_duration_bars?: number;
  alpha?:                    number;
  beta?:                     number;
  information_ratio?:        number;
  tracking_error_pct?:       number;
  benchmark_ann_return_pct?: number;
  avg_trade_duration_h?:     number;
  total_slippage_pct?:       number;
}

interface AdvancedAnalyticsProps {
  backtestId?:    string;
  metrics?:       AdvancedMetrics;
  /** Lead-lag (eski props — geriye dönük uyumluluk için) */
  leadLag?:       Record<string, { corr: number; lag_days: number; leads: boolean }>;
}

const API_BASE = (import.meta as any).env?.VITE_API_URL || "http://localhost:8502";

/* ── Mini bileşenler ─────────────────────────────────────────────── */

const Pill: React.FC<{ label: string; value: string | number; color?: string; unit?: string }> = ({
  label, value, color = "text-white", unit = "",
}) => (
  <div className="flex flex-col items-center gap-0.5 rounded-xl border border-slate-700/50 bg-slate-800/60 px-3 py-2 min-w-[80px]">
    <span className="text-[9px] font-semibold uppercase tracking-widest text-slate-500">{label}</span>
    <span className={`font-mono text-sm font-bold ${color}`}>
      {typeof value === "number" ? value.toFixed(2) : value}{unit}
    </span>
  </div>
);

const BarRange: React.FC<{
  label: string; dist: McDist; original: number;
  positiveGood?: boolean; unit?: string;
}> = ({ label, dist, original, positiveGood = true, unit = "%" }) => {
  const min = Math.min(dist.p5, original);
  const max = Math.max(dist.p95, original);
  const range = max - min || 1;
  const pct = (v: number) => ((v - min) / range) * 100;
  const origColor = positiveGood
    ? original >= dist.p50 ? "bg-emerald-400" : "bg-rose-400"
    : original <= dist.p50 ? "bg-emerald-400" : "bg-rose-400";

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-[10px] text-slate-400">
        <span className="font-semibold text-slate-300">{label}</span>
        <span className="font-mono">
          P5: <span className="text-slate-300">{dist.p5.toFixed(1)}{unit}</span>
          {" · "}P50: <span className="text-slate-300">{dist.p50.toFixed(1)}{unit}</span>
          {" · "}P95: <span className="text-slate-300">{dist.p95.toFixed(1)}{unit}</span>
        </span>
      </div>
      <div className="relative h-3 w-full rounded-full bg-slate-700/50">
        {/* IQR (P25–P75) */}
        <div
          className="absolute top-0 h-full rounded-full bg-slate-600/60"
          style={{ left: `${pct(dist.p25)}%`, width: `${pct(dist.p75) - pct(dist.p25)}%` }}
        />
        {/* Orijinal değer */}
        <div
          className={`absolute top-0 h-full w-1 rounded-full ${origColor} shadow-sm`}
          style={{ left: `${Math.max(0, Math.min(98, pct(original)))}%` }}
          title={`Gerçek: ${original.toFixed(1)}${unit}`}
        />
      </div>
      <div className="text-right text-[9px] text-slate-500">
        Gerçek: <span className={`font-mono font-semibold ${origColor.replace("bg-", "text-")}`}>
          {original.toFixed(1)}{unit}
        </span>
      </div>
    </div>
  );
};

/* ── Ana bileşen ─────────────────────────────────────────────────── */
export const AdvancedAnalytics: React.FC<AdvancedAnalyticsProps> = ({
  backtestId, metrics = {}, leadLag,
}) => {
  const [mc, setMc]           = useState<MonteCarloResult | null>(null);
  const [mcLoading, setMcLoading] = useState(false);
  const [mcError, setMcError] = useState<string | null>(null);
  const [advanced, setAdvanced] = useState<any | null>(null);
  const [advLoading, setAdvLoading] = useState(false);
  const [tab, setTab]         = useState<"risk" | "monte" | "benchmark">("risk");

  // Gelişmiş metrikler + MC backtest_id ile
  useEffect(() => {
    if (!backtestId) return;
    setAdvLoading(true);
    fetch(`${API_BASE}/backtest/advanced/${backtestId}?n_mc_sims=500`)
      .then(r => r.json())
      .then(d => {
        setAdvanced(d);
        if (d.monte_carlo) setMc(d.monte_carlo);
      })
      .catch(e => console.warn("Advanced fetch failed", e))
      .finally(() => setAdvLoading(false));
  }, [backtestId]);

  // Metrics prop'tan da okuyabilir
  const m: AdvancedMetrics = advanced?.metrics ?? metrics;

  const fmtPct  = (v?: number) => v != null ? `${v > 0 ? "+" : ""}${v.toFixed(2)}%` : "—";
  const fmtNum  = (v?: number, d = 2) => v != null ? v.toFixed(d) : "—";
  const colorDir = (v?: number, invert = false) => {
    if (v == null) return "text-slate-400";
    const good = invert ? v < 0 : v > 0;
    return good ? "text-emerald-400" : "text-rose-400";
  };

  return (
    <div className="rounded-2xl border border-slate-700/50 bg-slate-900/80 p-5 space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-xs font-semibold uppercase tracking-widest text-slate-400">
          Masterclass Analytics
        </h3>
        <div className="flex gap-1">
          {(["risk", "monte", "benchmark"] as const).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded-lg px-3 py-1 text-[10px] font-semibold uppercase tracking-wide transition-colors ${
                tab === t
                  ? "bg-violet-600 text-white"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {t === "risk" ? "Risk" : t === "monte" ? "Monte Carlo" : "Benchmark"}
            </button>
          ))}
        </div>
      </div>

      {/* ── RİSK METRİKLERİ ────────────────────────────────────────── */}
      {tab === "risk" && (
        <div className="space-y-4">
          {/* Risk-adjusted return satırı */}
          <div className="flex flex-wrap gap-2">
            <Pill label="Calmar"
              value={fmtNum(m.calmar_ratio)}
              color={m.calmar_ratio != null && m.calmar_ratio > 1 ? "text-emerald-400" : m.calmar_ratio != null && m.calmar_ratio > 0 ? "text-amber-400" : "text-rose-400"}
            />
            <Pill label="Omega"
              value={fmtNum(m.omega_ratio)}
              color={m.omega_ratio != null && m.omega_ratio > 1.5 ? "text-emerald-400" : "text-amber-400"}
            />
            <Pill label="Yıllık Getiri"
              value={fmtPct(m.annualized_return_pct)}
              color={colorDir(m.annualized_return_pct)}
            />
            <Pill label="Max DD Süre"
              value={m.max_drawdown_duration_bars ?? "—"}
              unit=" bar"
              color="text-slate-300"
            />
            <Pill label="Avg İşlem"
              value={m.avg_trade_duration_h != null ? `${m.avg_trade_duration_h}h` : "—"}
              color="text-slate-300"
            />
          </div>

          {/* VaR / CVaR */}
          <div className="rounded-xl border border-rose-500/20 bg-rose-500/5 p-4">
            <p className="mb-3 text-[10px] font-semibold uppercase tracking-widest text-rose-400">
              Value at Risk (95% Güven Aralığı)
            </p>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div>
                <p className="text-[9px] text-slate-500">VaR 95% (Günlük)</p>
                <p className={`font-mono text-base font-bold ${colorDir(m.var_95_pct, true)}`}>
                  {m.var_95_pct != null ? `${m.var_95_pct.toFixed(2)}%` : "—"}
                </p>
                <p className="text-[9px] text-slate-600">
                  {m.var_95_dollar != null ? `$${m.var_95_dollar.toLocaleString("en-US", { maximumFractionDigits: 0 })}` : ""}
                </p>
              </div>
              <div>
                <p className="text-[9px] text-slate-500">CVaR 95% (Beklenen Kay.)</p>
                <p className={`font-mono text-base font-bold text-rose-400`}>
                  {m.cvar_95_pct != null ? `${m.cvar_95_pct.toFixed(2)}%` : "—"}
                </p>
                <p className="text-[9px] text-slate-600">
                  {m.cvar_95_dollar != null ? `$${m.cvar_95_dollar.toLocaleString("en-US", { maximumFractionDigits: 0 })}` : ""}
                </p>
              </div>
              <div>
                <p className="text-[9px] text-slate-500">Toplam Slippage</p>
                <p className="font-mono text-base font-bold text-amber-400">
                  {m.total_slippage_pct != null ? `${m.total_slippage_pct.toFixed(3)}%` : "—"}
                </p>
                <p className="text-[9px] text-slate-600">spread + piyasa etkisi</p>
              </div>
              <div>
                <p className="text-[9px] text-slate-500">Tracking Error</p>
                <p className="font-mono text-base font-bold text-slate-300">
                  {m.tracking_error_pct != null ? `${m.tracking_error_pct.toFixed(2)}%` : "—"}
                </p>
                <p className="text-[9px] text-slate-600">benchmark'tan sapma</p>
              </div>
            </div>
            <p className="mt-2 text-[9px] text-slate-600">
              VaR: %5 olasılıkla bu günlük kayıp aşılmaz · CVaR: VaR aşıldığında beklenen ortalama kayıp
            </p>
          </div>
        </div>
      )}

      {/* ── MONTE CARLO ─────────────────────────────────────────────── */}
      {tab === "monte" && (
        <div className="space-y-4">
          {advLoading && (
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <span className="h-2 w-2 animate-pulse rounded-full bg-violet-400" />
              {mc ? `${mc.n_sims} simülasyon hesaplanıyor...` : "Yükleniyor..."}
            </div>
          )}

          {mc ? (
            <>
              {/* Güven yorumu */}
              <div className={`rounded-xl border px-4 py-3 ${
                mc.confidence.edge_real
                  ? "border-emerald-500/30 bg-emerald-500/5"
                  : "border-amber-500/30 bg-amber-500/5"
              }`}>
                <p className={`text-xs font-semibold ${mc.confidence.edge_real ? "text-emerald-400" : "text-amber-400"}`}>
                  {mc.confidence.interpretation}
                </p>
                <p className="mt-1 text-[10px] text-slate-500">
                  {mc.n_sims} Bootstrap · {mc.n_trades} işlem · Gerçek getiri simülasyonların{" "}
                  <span className="font-semibold text-slate-300">
                    {mc.confidence.return_percentile.toFixed(0)}. yüzdeliğinde
                  </span>
                </p>
              </div>

              {/* Dağılım çubukları */}
              <div className="space-y-5">
                <BarRange
                  label="Toplam Getiri"
                  dist={mc.total_return}
                  original={mc.original.total_return}
                  positiveGood
                  unit="%"
                />
                <BarRange
                  label="Win Rate"
                  dist={mc.win_rate}
                  original={mc.original.win_rate}
                  positiveGood
                  unit="%"
                />
                <BarRange
                  label="Maks Drawdown"
                  dist={mc.max_drawdown}
                  original={mc.original.max_drawdown}
                  positiveGood={false}
                  unit="%"
                />
                <BarRange
                  label="Sharpe Oranı"
                  dist={mc.sharpe_ratio}
                  original={0}
                  positiveGood
                  unit=""
                />
              </div>

              <p className="text-[9px] text-slate-600">
                Gri bant: %25–%75 · Çizgi: gerçek backtest · Yeşil=iyi, Kırmızı=kötü
              </p>
            </>
          ) : !advLoading ? (
            <div className="rounded-xl border border-slate-700/40 bg-slate-800/40 px-4 py-6 text-center">
              <p className="text-xs text-slate-500">Monte Carlo verisi yok</p>
              <p className="mt-1 text-[10px] text-slate-600">Önce bir backtest çalıştırın</p>
            </div>
          ) : null}
        </div>
      )}

      {/* ── BENCHMARK ──────────────────────────────────────────────── */}
      {tab === "benchmark" && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-3">
              <p className="text-[9px] font-semibold uppercase tracking-widest text-slate-500">Alpha</p>
              <p className={`mt-1 font-mono text-lg font-bold ${colorDir(m.alpha)}`}>
                {fmtPct(m.alpha)}
              </p>
              <p className="text-[9px] text-slate-600">BTC'ye göre artı değer</p>
            </div>
            <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-3">
              <p className="text-[9px] font-semibold uppercase tracking-widest text-slate-500">Beta</p>
              <p className={`mt-1 font-mono text-lg font-bold ${
                m.beta != null && m.beta < 0.8 ? "text-emerald-400"
                : m.beta != null && m.beta > 1.2 ? "text-rose-400"
                : "text-amber-400"
              }`}>
                {fmtNum(m.beta, 3)}
              </p>
              <p className="text-[9px] text-slate-600">
                {m.beta != null && m.beta < 0.8 ? "Düşük piyasa hassasiyeti"
                : m.beta != null && m.beta > 1.2 ? "Yüksek piyasa hassasiyeti"
                : "Piyasaya yakın hareket"}
              </p>
            </div>
            <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-3">
              <p className="text-[9px] font-semibold uppercase tracking-widest text-slate-500">Information Ratio</p>
              <p className={`mt-1 font-mono text-lg font-bold ${colorDir(m.information_ratio)}`}>
                {fmtNum(m.information_ratio, 3)}
              </p>
              <p className="text-[9px] text-slate-600">alpha / tracking error</p>
            </div>
          </div>

          {/* BTC vs Strateji karşılaştırma */}
          {(m.benchmark_ann_return_pct != null || m.annualized_return_pct != null) && (
            <div className="rounded-xl border border-slate-700/40 bg-slate-800/30 p-4">
              <p className="mb-3 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
                Yıllık Getiri Karşılaştırması
              </p>
              <div className="space-y-2">
                {[
                  {
                    label: "AEGIS Strateji",
                    value: m.annualized_return_pct,
                    color: m.annualized_return_pct != null && m.annualized_return_pct > 0 ? "bg-violet-500" : "bg-rose-500",
                  },
                  {
                    label: "BTC Buy & Hold",
                    value: m.benchmark_ann_return_pct,
                    color: "bg-amber-500",
                  },
                ].map(({ label, value, color }) => {
                  const max = Math.max(
                    Math.abs(m.annualized_return_pct ?? 0),
                    Math.abs(m.benchmark_ann_return_pct ?? 0),
                    1
                  );
                  const w = value != null ? Math.min(Math.abs(value) / max * 100, 100) : 0;
                  return (
                    <div key={label} className="space-y-0.5">
                      <div className="flex justify-between text-[10px]">
                        <span className="text-slate-400">{label}</span>
                        <span className={`font-mono font-semibold ${colorDir(value)}`}>
                          {fmtPct(value)}
                        </span>
                      </div>
                      <div className="h-2 w-full rounded-full bg-slate-700/40">
                        <div
                          className={`h-full rounded-full ${color} transition-all duration-700`}
                          style={{ width: `${w}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          <p className="text-[9px] text-slate-600">
            Alpha: risk-free oran ve beta ayarlanmış fazla getiri ·
            Beta &lt;1: piyasadan az etkilenme (düşük risk) ·
            IR &gt;0.5: iyi aktif yönetim
          </p>
        </div>
      )}

      {/* Lead-Lag (eski veri, uyumluluk) */}
      {leadLag && Object.keys(leadLag).length > 0 && tab === "risk" && (
        <div className="mt-3 border-t border-slate-700/40 pt-3">
          <p className="mb-2 text-[9px] font-semibold uppercase tracking-widest text-slate-600">Lead-Lag Korelasyon</p>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-slate-500 border-b border-slate-700">
                  <th className="py-1.5 text-left">Sembol</th>
                  <th className="py-1.5 text-center">Korelasyon</th>
                  <th className="py-1.5 text-center">Lag</th>
                  <th className="py-1.5 text-center">Yön</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(leadLag)
                  .sort(([, a], [, b]) => Math.abs(b.corr) - Math.abs(a.corr))
                  .map(([sym, d]) => (
                    <tr key={sym} className="border-b border-slate-800/40">
                      <td className="py-1.5 font-semibold text-white">{sym}</td>
                      <td className="py-1.5 text-center font-mono text-slate-300">{d.corr.toFixed(2)}</td>
                      <td className="py-1.5 text-center font-mono text-slate-400">{d.lag_days > 0 ? "+" : ""}{d.lag_days}d</td>
                      <td className="py-1.5 text-center">
                        <span className={`rounded-full px-2 py-0.5 text-[9px] font-semibold ${
                          d.leads ? "bg-emerald-500/20 text-emerald-300" : "bg-amber-500/20 text-amber-300"
                        }`}>
                          {d.leads ? "Öncü" : "Geride"}
                        </span>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
