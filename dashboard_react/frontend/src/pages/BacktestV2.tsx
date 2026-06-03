/**
 * pages/BacktestV2.tsx
 * AEGIS v7.5 — Redesigned Backtest Page with Horizon Integration
 *
 * Features:
 * - Horizon selector (short/medium/long) → auto date range + kelly + weights
 * - Type-safe API responses (BacktestResultV2)
 * - ScoreBar for module scores with weight overlays
 * - MetricCardV2 with trend indicators + risk badge
 * - Skeleton loader during loading
 * - Retry button on error
 * - Responsive trades table (horizontal scroll on mobile)
 * - Auto-recalculate on horizon change (debounced)
 * - Explainability panel (v7.5)
 * - Risk control presets (v7.5)
 * - What-If Scenario Simulator (v7.5)
 * - Expert mode with weight overrides (v7.5)
 * - Advanced lead-lag analytics (v7.5)
 */
import React, { useState, useCallback, useRef, useEffect } from "react";
import { SkeletonLoader } from "../components/ui/SkeletonLoader";
import { ScoreBar } from "../components/backtest/ScoreBar";
import { MetricCardV2 } from "../components/backtest/MetricCardV2";
import { TradesTable } from "../components/backtest/TradesTable";
import type {
  BacktestResultV2,
  BacktestParamsV2,
  MetricTrend,
  BacktestModuleScores,
} from "../types/backtestV2";
import { MODULE_COLORS, validateBacktestResult } from "../types/backtestV2";
import { RegimeProbabilityChart } from "../components/backtest/RegimeProbabilityChart";
import { ActionEngineCard } from "../components/backtest/ActionEngineCard";
import { LiquidityScoreCard } from "../components/backtest/LiquidityScoreCard";
import { VolatilityCard } from "../components/backtest/VolatilityCard";
import { ExplainabilityPanel } from "../components/backtest/ExplainabilityPanel";
import { RiskControlCard } from "../components/backtest/RiskControlCard";
import { ScenarioSimulator } from "../components/backtest/ScenarioSimulator";
import { ExpertControls } from "../components/backtest/ExpertControls";
import { AdvancedAnalytics } from "../components/backtest/AdvancedAnalytics";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8502";

const SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"] as const;
const TIMEFRAMES = ["1h", "4h", "1d"] as const;

const MAX_RETRIES = 2;
const RETRY_DELAY = 2000;

/* ── Horizon Configuration ── */
type Horizon = "short" | "medium" | "long";

interface HorizonConfig {
  days: number;
  kelly: number;
  riskLevel: "high" | "medium" | "low";
  riskLabel: string;
  riskColor: string;
  label: string;
  description: string;
  defaultTf: string;
  moduleWeights: Record<keyof BacktestModuleScores, number>;
}

const HORIZON_CONFIGS: Record<Horizon, HorizonConfig> = {
  short: {
    days: 30,
    kelly: 0.30,
    riskLevel: "high",
    riskLabel: "Aggressive",
    riskColor: "text-amber-400 bg-amber-500/20 border-amber-500/30",
    label: "Short (1-4W)",
    description: "Technical-focused · High frequency · Aggressive sizing",
    defaultTf: "1h",
    moduleWeights: { touche: 0.40, fundamental: 0.15, quantum: 0.20, sentinel: 0.10, news: 0.15 },
  },
  medium: {
    days: 90,
    kelly: 0.25,
    riskLevel: "medium",
    riskLabel: "Balanced",
    riskColor: "text-blue-400 bg-blue-500/20 border-blue-500/30",
    label: "Medium (1-3M)",
    description: "Balanced consensus · Moderate frequency · Standard sizing",
    defaultTf: "4h",
    moduleWeights: { touche: 0.25, fundamental: 0.30, quantum: 0.15, sentinel: 0.15, news: 0.15 },
  },
  long: {
    days: 180,
    kelly: 0.15,
    riskLevel: "low",
    riskLabel: "Conservative",
    riskColor: "text-emerald-400 bg-emerald-500/20 border-emerald-500/30",
    label: "Long (6M+)",
    description: "Macro-driven · Low frequency · Conservative sizing",
    defaultTf: "1d",
    moduleWeights: { touche: 0.10, fundamental: 0.40, quantum: 0.10, sentinel: 0.25, news: 0.15 },
  },
};

function getHorizonDates(h: Horizon): { start: string; end: string } {
  const end = new Date();
  const start = new Date(end.getTime() - HORIZON_CONFIGS[h].days * 86400000);
  return { start: start.toISOString().slice(0, 10), end: end.toISOString().slice(0, 10) };
}

async function fetchWithRetry(url: string, init: RequestInit, retries = MAX_RETRIES): Promise<Response> {
  for (let i = 0; i <= retries; i++) {
    try {
      const res = await fetch(url, init);
      if (res.ok) return res;
      if (i < retries && res.status >= 500) {
        await new Promise((r) => setTimeout(r, RETRY_DELAY * (i + 1)));
        continue;
      }
      throw new Error(`Server error: ${res.status} ${res.statusText}`);
    } catch (err) {
      if (i === retries) throw err;
      await new Promise((r) => setTimeout(r, RETRY_DELAY * (i + 1)));
    }
  }
  throw new Error("Request failed after retries");
}

export const BacktestV2: React.FC = () => {
  const [horizon, setHorizon] = useState<Horizon>("medium");
  const [symbol, setSymbol] = useState<string>("BTC/USDT");
  const [timeframe, setTimeframe] = useState<string>("4h");
  const [manualDates, setManualDates] = useState(false);
  const [startDate, setStartDate] = useState(() => getHorizonDates("medium").start);
  const [endDate, setEndDate] = useState(() => getHorizonDates("medium").end);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BacktestResultV2 | null>(null);
  const [error, setError] = useState<string | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [macroData, setMacroData] = useState<any>(null);
  // v7.5 — Expert mode & risk controls
  const [expertMode, setExpertMode] = useState(false);
  const [weightOverrides, setWeightOverrides] = useState<Record<string, number>>({
    touche: 0.3, fundamental: 0.4, news: 0.1, sentinel: 0.15, quantum: 0.05,
  });
  const [riskProfile, setRiskProfile] = useState("moderate");
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [customRisk, setCustomRisk] = useState({ kelly: 0.25, sl: 2.0, tp: 4.0 });
  const abortRef = useRef<AbortController | null>(null);
  const hasRunRef = useRef(false);

  const hConfig = HORIZON_CONFIGS[horizon];

  // When horizon changes → update dates + timeframe (unless manual)
  useEffect(() => {
    if (!manualDates) {
      const { start, end } = getHorizonDates(horizon);
      setStartDate(start);
      setEndDate(end);
    }
    setTimeframe(HORIZON_CONFIGS[horizon].defaultTf);
  }, [horizon, manualDates]);

  // Auto-recalculate on horizon change (debounced, only after first run)
  useEffect(() => {
    if (!hasRunRef.current) return;
    const timer = setTimeout(() => {
      handleRun();
    }, 600);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [horizon]);

  const handleRun = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);
    hasRunRef.current = true;

    const effectiveDates = manualDates
      ? { start_date: startDate, end_date: endDate }
      : { start_date: getHorizonDates(horizon).start, end_date: getHorizonDates(horizon).end };

    const params: BacktestParamsV2 = {
      symbol,
      timeframe,
      horizon,
      ...effectiveDates,
      initial_capital: 10000,
      risk_per_trade: hConfig.kelly * 0.1,
      use_live_data: true,
      include_fees: true,
    };

    try {
      const res = await fetchWithRetry(
        `${API_BASE}/backtest/run`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(params),
          signal: controller.signal,
        },
      );

      const data = await res.json();

      if (!validateBacktestResult(data)) {
        console.error("[BacktestV2] Schema validation failed:", data);
        throw new Error("API response schema mismatch — check console");
      }

      console.log(`[BacktestV2] horizon=${horizon} kelly=${hConfig.kelly} dates=${effectiveDates.start_date}→${effectiveDates.end_date}`);
      console.log("[BacktestV2] module_scores loaded", data.module_scores);
      setResult(data);

      // Fetch macro data for v7.4 cards
      try {
        const macroRes = await fetchWithRetry(`${API_BASE}/api/macro?horizon=${horizon}`, {});
        const macroJson = await macroRes.json();
        setMacroData(macroJson);
      } catch (macroErr) {
        console.warn("[BacktestV2] macro fetch failed:", macroErr);
      }
    } catch (err) {
      if (controller.signal.aborted) return;
      const msg = err instanceof Error ? err.message : "Backtest failed";
      if (msg.includes("Failed to fetch") || msg.includes("NetworkError")) {
        setError("Backend unreachable, retrying...");
      } else if (msg.includes("timeout") || msg.includes("Timeout")) {
        setError("Request timeout — try a shorter date range");
      } else {
        setError(msg);
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [symbol, timeframe, startDate, endDate, horizon, manualDates, hConfig.kelly]);

  const pnlTrend = (v: number): MetricTrend => (v > 0 ? "up" : v < 0 ? "down" : "neutral");

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">
              AEGIS v7.5 — AI Backtest Engine
            </h1>
            <p className="text-sm text-slate-500 mt-1">
              5-module consensus · explainability · scenario simulator · expert mode
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setExpertMode(!expertMode)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                expertMode
                  ? "bg-purple-600 text-white ring-1 ring-purple-400/50"
                  : "bg-slate-700 text-slate-400 hover:bg-slate-600"
              }`}
            >
              {expertMode ? "Expert 🛠️" : "Normal"}
            </button>
            <span className="px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/20 text-emerald-300">
              LIVE
            </span>
          </div>
        </div>

        {/* v7.5 — Expert controls & Scenario Simulator */}
        {expertMode && (
          <ExpertControls weights={weightOverrides} onChange={setWeightOverrides} />
        )}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <RiskControlCard
            onProfileChange={setRiskProfile}
            onCustomChange={(k, s, t) => setCustomRisk({ kelly: k, sl: s, tp: t })}
          />
          <ScenarioSimulator />
        </div>

        {/* Horizon Selector */}
        <div className="rounded-xl border border-slate-700/50 bg-slate-900/80 p-4">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Investment Horizon
            </span>
            <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${hConfig.riskColor}`}>
              {hConfig.riskLabel} · Kelly {(hConfig.kelly * 100).toFixed(0)}%
            </span>
          </div>
          <div className="grid grid-cols-3 gap-2">
            {(["short", "medium", "long"] as Horizon[]).map((h) => {
              const cfg = HORIZON_CONFIGS[h];
              const active = horizon === h;
              return (
                <button
                  key={h}
                  onClick={() => { setHorizon(h); setManualDates(false); }}
                  className={`px-4 py-3 rounded-lg text-left transition-all duration-200 border
                    ${active
                      ? "bg-blue-600/20 border-blue-500/50 ring-1 ring-blue-500/30"
                      : "bg-slate-800/50 border-slate-700/30 hover:bg-slate-800 hover:border-slate-600"}`}
                  aria-pressed={active}
                >
                  <div className="text-sm font-semibold">{cfg.label}</div>
                  <div className="text-xs text-slate-500 mt-0.5">{cfg.description}</div>
                  <div className="text-xs text-slate-600 mt-1">
                    {cfg.days}d · Kelly {(cfg.kelly * 100).toFixed(0)}% · {cfg.defaultTf}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Controls */}
        <div className="rounded-xl border border-slate-700/50 bg-slate-900/80 p-5">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
            {/* Symbol */}
            <div>
              <label htmlFor="bt-symbol" className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1.5">
                Trading Pair
              </label>
              <select
                id="bt-symbol"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-slate-600 bg-slate-800 text-white text-sm focus:ring-2 focus:ring-blue-500 outline-none"
              >
                {SYMBOLS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>

            {/* Timeframe */}
            <div>
              <label htmlFor="bt-tf" className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1.5">
                Timeframe
              </label>
              <select
                id="bt-tf"
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-slate-600 bg-slate-800 text-white text-sm focus:ring-2 focus:ring-blue-500 outline-none"
              >
                {TIMEFRAMES.map((tf) => <option key={tf} value={tf}>{tf}</option>)}
              </select>
            </div>

            {/* Start */}
            <div>
              <label htmlFor="bt-start" className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1.5">
                Start Date
                {!manualDates && <span className="ml-1 text-blue-400">(auto)</span>}
              </label>
              <input
                id="bt-start"
                type="date"
                value={startDate}
                onChange={(e) => { setStartDate(e.target.value); setManualDates(true); }}
                className="w-full px-3 py-2 rounded-lg border border-slate-600 bg-slate-800 text-white text-sm focus:ring-2 focus:ring-blue-500 outline-none"
              />
            </div>

            {/* End */}
            <div>
              <label htmlFor="bt-end" className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1.5">
                End Date
                {!manualDates && <span className="ml-1 text-blue-400">(auto)</span>}
              </label>
              <input
                id="bt-end"
                type="date"
                value={endDate}
                onChange={(e) => { setEndDate(e.target.value); setManualDates(true); }}
                className="w-full px-3 py-2 rounded-lg border border-slate-600 bg-slate-800 text-white text-sm focus:ring-2 focus:ring-blue-500 outline-none"
              />
            </div>

            {/* Run */}
            <div className="flex items-end">
              <button
                onClick={handleRun}
                disabled={loading}
                aria-label="Run Backtest"
                className="w-full px-4 py-2 rounded-lg font-semibold text-sm transition-all duration-200
                  bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:text-slate-500
                  focus:ring-2 focus:ring-blue-400 focus:ring-offset-2 focus:ring-offset-slate-950 outline-none"
              >
                {loading ? "Running..." : "Run Backtest"}
              </button>
            </div>
          </div>

          {/* Horizon info bar */}
          <div className="mt-3 flex items-center gap-4 text-xs text-slate-500">
            <span>📅 {startDate} → {endDate} ({hConfig.days}d)</span>
            <span>⚖️ Kelly: {(hConfig.kelly * 100).toFixed(0)}%</span>
            <span>🎚️ Risk: {hConfig.riskLabel}</span>
            {riskProfile !== "moderate" && (
              <span className="text-purple-400">🛡️ {riskProfile}</span>
            )}
            {manualDates && (
              <button
                onClick={() => setManualDates(false)}
                className="text-blue-400 hover:text-blue-300 underline"
              >
                Reset to auto dates
              </button>
            )}
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 flex items-center justify-between">
            <p className="text-red-300 text-sm">{error}</p>
            <button
              onClick={handleRun}
              className="ml-4 px-4 py-1.5 rounded-lg bg-red-600 hover:bg-red-500 text-white text-xs font-semibold transition-colors
                focus:ring-2 focus:ring-red-400 outline-none"
              aria-label="Retry backtest"
            >
              Retry
            </button>
          </div>
        )}

        {/* Loading Skeleton */}
        {loading && (
          <div className="space-y-4 animate-pulse">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {Array.from({ length: 6 }).map((_, i) => (
                <SkeletonLoader key={i} variant="stat" />
              ))}
            </div>
            <SkeletonLoader variant="bar-chart" lines={5} />
            <SkeletonLoader variant="card" lines={4} />
          </div>
        )}

        {/* Results */}
        {!loading && result && (
          <div className="space-y-6 animate-[fadeSlideUp_0.5s_ease-out_forwards]">
            {/* Key Metrics */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <MetricCardV2
                title="Total PnL"
                value={`${result.metrics.pnl.total_pnl >= 0 ? "+" : ""}${result.metrics.pnl.total_pnl.toFixed(2)}`}
                trend={pnlTrend(result.metrics.pnl.total_pnl)}
                subtitle={`$${result.metrics.initial_capital.toLocaleString()} → $${result.metrics.final_capital.toLocaleString()}`}
                icon="💰"
              />
              <MetricCardV2
                title="Return"
                value={`${result.metrics.pnl.total_pnl_pct >= 0 ? "+" : ""}${result.metrics.pnl.total_pnl_pct.toFixed(2)}%`}
                trend={pnlTrend(result.metrics.pnl.total_pnl_pct)}
                subtitle={`${result.metrics.pnl.num_trades} trades · ${hConfig.label}`}
              />
              <MetricCardV2
                title="Win Rate"
                value={`${result.metrics.win_loss.win_rate.toFixed(1)}%`}
                trend={result.metrics.win_loss.win_rate >= 50 ? "up" : result.metrics.win_loss.win_rate >= 40 ? "neutral" : "down"}
                subtitle={`${result.metrics.win_loss.win_count}W / ${result.metrics.win_loss.loss_count}L`}
                icon="🎯"
              />
              <MetricCardV2
                title="Profit Factor"
                value={`${result.metrics.win_loss.profit_factor.toFixed(2)}x`}
                trend={result.metrics.win_loss.profit_factor >= 1.5 ? "up" : result.metrics.win_loss.profit_factor >= 1.0 ? "neutral" : "down"}
                icon="📊"
              />
              <MetricCardV2
                title="Max Drawdown"
                value={`${result.metrics.drawdown.max_drawdown_pct.toFixed(2)}%`}
                trend="down"
                subtitle={`$${result.metrics.drawdown.max_drawdown.toFixed(2)}`}
                icon="📉"
              />
              <MetricCardV2
                title="Sharpe Ratio"
                value={result.metrics.sharpe_ratio.toFixed(2)}
                trend={result.metrics.sharpe_ratio >= 1.5 ? "up" : result.metrics.sharpe_ratio >= 0.5 ? "neutral" : "down"}
                subtitle={`Sortino: ${result.metrics.sortino_ratio.toFixed(2)}`}
                icon="⚡"
              />
            </div>

            {/* Kelly & Risk Config Card */}
            <div className="rounded-xl border border-slate-700/50 bg-slate-900/80 p-5">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500 mb-3">
                Position Sizing & Risk
              </h3>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <div className="text-center">
                  <div className="text-2xl font-bold font-mono text-blue-400">{(hConfig.kelly * 100).toFixed(0)}%</div>
                  <div className="text-xs text-slate-500 mt-1">Kelly Fraction</div>
                </div>
                <div className="text-center">
                  <div className={`text-2xl font-bold font-mono ${
                    hConfig.riskLevel === "high" ? "text-amber-400" : hConfig.riskLevel === "low" ? "text-emerald-400" : "text-blue-400"
                  }`}>{hConfig.riskLabel}</div>
                  <div className="text-xs text-slate-500 mt-1">Risk Level</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold font-mono text-slate-300">${(10000 * hConfig.kelly * 0.1).toFixed(0)}</div>
                  <div className="text-xs text-slate-500 mt-1">Risk per Trade</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold font-mono text-slate-300">{hConfig.days}d</div>
                  <div className="text-xs text-slate-500 mt-1">Lookback Period</div>
                </div>
              </div>
            </div>

            {/* Module Scores + Weight Overlay */}
            <div className="rounded-xl border border-slate-700/50 bg-slate-900/80 p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
                  Module Scores & Weights
                </h3>
                <span className={`px-2 py-0.5 rounded-full text-xs font-semibold border ${hConfig.riskColor}`}>
                  {horizon.toUpperCase()} weights
                </span>
              </div>
              <div className="space-y-3">
                {(Object.keys(result.module_scores) as Array<keyof typeof result.module_scores>).map((key) => {
                  const weight = hConfig.moduleWeights[key] ?? 0;
                  return (
                    <div key={key} className="flex items-center gap-3">
                      <div className="flex-1">
                        <ScoreBar
                          label={key.charAt(0).toUpperCase() + key.slice(1)}
                          value={result.module_scores[key]}
                          color={MODULE_COLORS[key] || "#6b7280"}
                        />
                      </div>
                      <span className="w-14 text-right text-xs font-mono text-slate-500">
                        w:{(weight * 100).toFixed(0)}%
                      </span>
                    </div>
                  );
                })}
              </div>
              {/* Weight summary bar */}
              <div className="mt-4 pt-3 border-t border-slate-700/30">
                <div className="flex h-3 rounded-full overflow-hidden">
                  {(Object.keys(hConfig.moduleWeights) as Array<keyof BacktestModuleScores>).map((key) => (
                    <div
                      key={key}
                      className="h-full transition-all duration-500"
                      style={{ width: `${hConfig.moduleWeights[key] * 100}%`, backgroundColor: MODULE_COLORS[key] || "#6b7280" }}
                      title={`${key}: ${(hConfig.moduleWeights[key] * 100).toFixed(0)}%`}
                    />
                  ))}
                </div>
                <div className="flex justify-between mt-1.5 text-xs text-slate-600">
                  {(Object.keys(hConfig.moduleWeights) as Array<keyof BacktestModuleScores>).map((key) => (
                    <span key={key} style={{ color: MODULE_COLORS[key] || "#6b7280" }}>
                      {key.slice(0, 3).toUpperCase()} {(hConfig.moduleWeights[key] * 100).toFixed(0)}%
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* Win Rate Progress */}
            {result.portfolio_allocation && Object.keys(result.portfolio_allocation).length > 0 && (
              <div className="rounded-xl border border-slate-700/50 bg-slate-900/80 p-5">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
                    Portfolio Allocation
                  </h3>
                  <div className="flex items-center gap-2">
                    {result.regime && (
                      <span className={`px-2 py-0.5 rounded-full text-xs font-semibold border ${
                        result.regime.includes("RISK_OFF") ? "text-red-400 bg-red-500/20 border-red-500/30"
                          : result.regime.includes("LIQ") || result.regime.includes("ACCUMULATION")
                            ? "text-emerald-400 bg-emerald-500/20 border-emerald-500/30"
                            : "text-blue-400 bg-blue-500/20 border-blue-500/30"
                      }`}>
                        {result.regime}
                      </span>
                    )}
                    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold border ${hConfig.riskColor}`}>
                      {horizon.toUpperCase()}
                    </span>
                  </div>
                </div>
                <div className="space-y-2">
                  {Object.entries(result.portfolio_allocation)
                    .sort(([, a], [, b]) => (b as { allocation_pct: number }).allocation_pct - (a as { allocation_pct: number }).allocation_pct)
                    .map(([asset, info]) => {
                      const pct = (info as { allocation_pct: number; rationale: string }).allocation_pct;
                      const rationale = (info as { allocation_pct: number; rationale: string }).rationale;
                      const assetColors: Record<string, string> = {
                        cash: "#94a3b8", bond: "#60a5fa", gold: "#fbbf24", btc: "#f97316", commodity: "#a78bfa",
                      };
                      const color = assetColors[asset] || "#6b7280";
                      return (
                        <div key={asset} className="flex items-center gap-3">
                          <span className="w-20 text-xs font-semibold uppercase tracking-wider" style={{ color }}>
                            {asset}
                          </span>
                          <div className="flex-1 h-5 rounded-full bg-slate-700/60 overflow-hidden">
                            <div
                              className="h-full rounded-full transition-all duration-700"
                              style={{ width: `${pct}%`, backgroundColor: color }}
                            />
                          </div>
                          <span className="w-14 text-right text-sm font-mono text-slate-300">
                            {pct.toFixed(0)}%
                          </span>
                          <span className="text-xs text-slate-500 hidden sm:inline w-48 truncate" title={rationale}>
                            {rationale}
                          </span>
                        </div>
                      );
                    })}
                </div>
              </div>
            )}

            {/* ═══ AEGIS v7.5 — Explainability Panel ═══ */}
            {result.score_attribution && (
              <ExplainabilityPanel
                attribution={result.score_attribution as Record<string, { feature: string; value: string | number; impact: number }[]>}
              />
            )}

            {/* ═══ AEGIS v7.4 — Intelligence Cards ═══ */}
            {macroData && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                {macroData.regime_probability_distribution && (
                  <RegimeProbabilityChart
                    distribution={macroData.regime_probability_distribution}
                  />
                )}
                <ActionEngineCard
                  consensusScore={result.module_scores ? Object.values(result.module_scores as unknown as Record<string, number>).reduce((a, b) => a + b, 0) / Object.keys(result.module_scores).length : undefined}
                  action={
                    result.metrics.pnl.total_pnl_pct > 0.5 ? "BUY" : result.metrics.pnl.total_pnl_pct < -0.5 ? "SELL" : "HOLD"
                  }
                  confidence={Math.min(Math.abs(result.metrics.pnl.total_pnl_pct) / 5, 1)}
                />
                {macroData.liquidity_composite && (
                  <LiquidityScoreCard liquidity={macroData.liquidity_composite} />
                )}
                {macroData.volatility_composite && (
                  <VolatilityCard volatility={macroData.volatility_composite} />
                )}
              </div>
            )}

            {/* ═══ AEGIS Masterclass Analytics ═══ */}
            <AdvancedAnalytics
              backtestId={result?.backtest_id}
              metrics={result?.metrics as any}
              leadLag={macroData?.correlation?.lead_lag}
            />

            {/* Win Rate Progress - original */}
            <div className="rounded-xl border border-slate-700/50 bg-slate-900/80 p-5">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500 mb-3">
                Win Rate Distribution
              </h3>
              <div className="flex items-center gap-3">
                <div className="flex-1 h-4 rounded-full bg-slate-700/60 overflow-hidden flex">
                  <div
                    className="h-full bg-emerald-500 transition-all duration-700"
                    style={{ width: `${result.metrics.win_loss.win_rate}%` }}
                  />
                  <div
                    className="h-full bg-red-500 transition-all duration-700"
                    style={{ width: `${100 - result.metrics.win_loss.win_rate}%` }}
                  />
                </div>
                <span className="text-sm font-mono text-slate-400 w-16 text-right">
                  {result.metrics.win_loss.win_rate.toFixed(1)}%
                </span>
              </div>
              <div className="flex justify-between mt-2 text-xs text-slate-500">
                <span>{result.metrics.win_loss.win_count} wins (avg +${result.metrics.win_loss.avg_win.toFixed(2)})</span>
                <span>{result.metrics.win_loss.loss_count} losses (avg −${Math.abs(result.metrics.win_loss.avg_loss).toFixed(2)})</span>
              </div>
            </div>

            {/* Trades Table */}
            {result.trades && result.trades.length > 0 && (
              <div className="rounded-xl border border-slate-700/50 bg-slate-900/80 p-5">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
                    Trade History ({result.trades.length})
                  </h3>
                  <span className="text-xs text-slate-600">
                    {result.date_range.start} → {result.date_range.end}
                  </span>
                </div>
                <TradesTable trades={result.trades} />
              </div>
            )}

            {/* Info + Export */}
            <div className="rounded-xl border border-blue-500/20 bg-blue-500/5 p-4 flex items-center justify-between">
              <div className="text-xs text-blue-300/80">
                <span className="font-semibold">Backtest ID:</span> {result.backtest_id}
                {" · "}
                <span className="font-semibold">Data Points:</span> {result.data_points}
                {result.data_source && <> · <span className="font-semibold">Source:</span> {result.data_source}</>}
              </div>
              <button
                onClick={async () => {
                  try {
                    const r = await fetch(`${API_BASE}/backtest/export/${result.backtest_id}`);
                    const data = await r.json();
                    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = `aegis_report_${result.backtest_id.slice(0, 8)}.json`;
                    a.click();
                    URL.revokeObjectURL(url);
                  } catch (e) { console.error("Export failed:", e); }
                }}
                className="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-xs font-semibold text-white transition-colors"
              >
                📥 Export Report
              </button>
            </div>
          </div>
        )}

        {/* Empty State */}
        {!loading && !result && !error && (
          <div className="text-center py-16 rounded-xl border border-slate-700/30 bg-slate-900/40">
            <p className="text-slate-500 text-lg">Select a horizon and run a backtest</p>
            <p className="text-slate-600 text-sm mt-2">
              {hConfig.label} · {hConfig.days}d · Kelly {(hConfig.kelly * 100).toFixed(0)}% · {hConfig.description}
            </p>
          </div>
        )}
      </div>
    </div>
  );
};
