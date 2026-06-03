import React, { useState, useEffect } from 'react';
import { backtestApi, BacktestResult, AIBacktestParams } from '../services/backtestApi';

const API = (import.meta.env.VITE_API_URL as string | undefined) || 'http://localhost:8502';

// ── Hyperopt Panel ────────────────────────────────────────────────────────────
interface HyperoptTrial {
  trial: number;
  params: { z_threshold: number; stop_loss_pct: number; take_profit_pct: number; z_exit_long: number; adx_min: number; kelly_cap: number; };
  metrics: { win_rate: number; profit_factor: number; pnl_pct: number; sharpe: number; max_dd_pct: number; num_trades: number; };
  score: number;
}
interface HyperoptResult {
  success: boolean; symbol: string; timeframe: string;
  total_trials: number; elapsed_sec: number; objective: string;
  best: HyperoptTrial | null; results: HyperoptTrial[];
}

const HyperoptPanel: React.FC<{ symbol: string; timeframe: string; startDate: string; endDate: string }> = ({
  symbol, timeframe, startDate, endDate,
}) => {
  const [nTrials, setNTrials] = useState(20);
  const [objective, setObjective] = useState('composite');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<HyperoptResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setLoading(true); setError(null); setResult(null);
    try {
      const r = await fetch(`${API}/backtest/optimize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol, timeframe, start_date: startDate, end_date: endDate,
          n_trials: nTrials, objective, initial_capital: 10000 }),
      });
      const d = await r.json();
      if (!d.success) throw new Error(d.error || 'Optimize failed');
      setResult(d);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Hata');
    } finally {
      setLoading(false);
    }
  };

  const pct = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;
  const fmt = (v: number, d = 2) => v.toFixed(d);

  return (
    <div className="rounded-2xl border border-violet-500/30 bg-slate-900 p-5">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-bold uppercase tracking-wider text-violet-400">⚡ Hyperopt</span>
          <span className="text-[9px] text-slate-600">Latin Hypercube + Bayesian</span>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1.5">
            <label className="text-[10px] text-slate-500">Deneme</label>
            <select value={nTrials} onChange={e => setNTrials(+e.target.value)}
              className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-[10px] text-slate-300">
              {[10,20,30,50].map(n => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
          <div className="flex items-center gap-1.5">
            <label className="text-[10px] text-slate-500">Hedef</label>
            <select value={objective} onChange={e => setObjective(e.target.value)}
              className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-[10px] text-slate-300">
              <option value="composite">Bileşik</option>
              <option value="sharpe">Sharpe</option>
              <option value="win_rate">Win Rate</option>
              <option value="pnl">PnL</option>
            </select>
          </div>
          <button onClick={run} disabled={loading}
            className="rounded-lg border border-violet-500/50 bg-violet-500/10 px-4 py-1.5 text-[10px] font-bold text-violet-300 hover:bg-violet-500/20 disabled:opacity-40 transition-colors">
            {loading ? `Çalışıyor… (${nTrials} deneme)` : '▶ Optimize'}
          </button>
        </div>
      </div>

      {error && <p className="mb-3 text-xs text-rose-400">{error}</p>}

      {loading && (
        <div className="flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-slate-700 border-t-violet-400" />
          <p className="text-[11px] text-slate-400">{nTrials} farklı parametre kombinasyonu deneniyor…</p>
        </div>
      )}

      {result && (
        <div className="space-y-4">
          {/* Özet */}
          <div className="rounded-xl border border-violet-500/20 bg-violet-500/5 p-3">
            <p className="mb-1 text-[10px] text-slate-500">
              {result.total_trials} deneme · {result.elapsed_sec}s · Hedef: {result.objective}
            </p>
            {result.best && (
              <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
                {[
                  { l: 'Win Rate', v: `${result.best.metrics.win_rate.toFixed(1)}%` },
                  { l: 'P. Factor', v: fmt(result.best.metrics.profit_factor) },
                  { l: 'PnL', v: pct(result.best.metrics.pnl_pct) },
                  { l: 'Sharpe', v: fmt(result.best.metrics.sharpe) },
                  { l: 'Max DD', v: `${result.best.metrics.max_dd_pct.toFixed(1)}%` },
                  { l: 'İşlem', v: String(result.best.metrics.num_trades) },
                ].map(({ l, v }) => (
                  <div key={l} className="text-center">
                    <p className="text-[8px] uppercase text-slate-600">{l}</p>
                    <p className="font-mono text-[12px] font-bold text-white">{v}</p>
                  </div>
                ))}
              </div>
            )}
            {result.best && (
              <div className="mt-2 flex flex-wrap gap-2">
                <p className="text-[9px] text-slate-500">En iyi parametreler:</p>
                {Object.entries(result.best.params).map(([k, v]) => (
                  <span key={k} className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[9px] text-violet-300">
                    {k}={typeof v === 'number' ? v.toFixed(3) : v}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Sonuç tablosu */}
          <div className="overflow-x-auto">
            <table className="w-full text-[9px]">
              <thead>
                <tr className="border-b border-slate-800 text-left text-slate-600">
                  <th className="pb-1.5 pr-2">#</th>
                  <th className="pb-1.5 pr-2">WR%</th>
                  <th className="pb-1.5 pr-2">PF</th>
                  <th className="pb-1.5 pr-2">PnL%</th>
                  <th className="pb-1.5 pr-2">Sharpe</th>
                  <th className="pb-1.5 pr-2">İşlem</th>
                  <th className="pb-1.5 pr-2">z_thr</th>
                  <th className="pb-1.5 pr-2">sl</th>
                  <th className="pb-1.5 pr-2">tp</th>
                  <th className="pb-1.5 pr-2">adx</th>
                  <th className="pb-1.5">Skor</th>
                </tr>
              </thead>
              <tbody>
                {result.results.slice(0, 10).map((r, i) => (
                  <tr key={r.trial} className={`border-b border-slate-800/50 ${i === 0 ? 'bg-violet-500/5' : ''}`}>
                    <td className="py-1 pr-2 font-mono text-slate-500">{i + 1}</td>
                    <td className={`py-1 pr-2 font-mono font-semibold ${r.metrics.win_rate >= 50 ? 'text-emerald-400' : 'text-slate-400'}`}>
                      {r.metrics.win_rate.toFixed(1)}
                    </td>
                    <td className={`py-1 pr-2 font-mono ${r.metrics.profit_factor >= 1.5 ? 'text-emerald-400' : 'text-slate-400'}`}>
                      {r.metrics.profit_factor.toFixed(2)}
                    </td>
                    <td className={`py-1 pr-2 font-mono ${r.metrics.pnl_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {pct(r.metrics.pnl_pct)}
                    </td>
                    <td className={`py-1 pr-2 font-mono ${r.metrics.sharpe >= 1 ? 'text-emerald-400' : 'text-slate-400'}`}>
                      {r.metrics.sharpe.toFixed(2)}
                    </td>
                    <td className="py-1 pr-2 font-mono text-slate-400">{r.metrics.num_trades}</td>
                    <td className="py-1 pr-2 font-mono text-slate-500">{r.params.z_threshold.toFixed(2)}</td>
                    <td className="py-1 pr-2 font-mono text-slate-500">{r.params.stop_loss_pct.toFixed(3)}</td>
                    <td className="py-1 pr-2 font-mono text-slate-500">{r.params.take_profit_pct.toFixed(2)}</td>
                    <td className="py-1 pr-2 font-mono text-slate-500">{r.params.adx_min}</td>
                    <td className="py-1 font-mono font-semibold text-violet-400">{r.score.toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!result && !loading && (
        <p className="text-center text-[10px] text-slate-700 py-4">
          Latin Hypercube örnekleme ile {nTrials} parametre kombinasyonu dener, en iyi konfigürasyonu bulur.
        </p>
      )}
    </div>
  );
};

const Backtest: React.FC = () => {
  const [symbol, setSymbol] = useState('BTC/USDT');
  const [timeframe, setTimeframe] = useState('1h');
  const [startDate, setStartDate] = useState('2024-01-01');
  const [endDate, setEndDate] = useState('2024-03-31');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT'];
  const timeframes = ['5m', '15m', '1h', '4h', '1d', '1w', '1month'];

  const handleRunBacktest = async () => {
    setLoading(true);
    setError(null);

    try {
      const params: AIBacktestParams = {
        symbol,
        timeframe,
        start_date: startDate,
        end_date: endDate,
      };

      const backtest = await backtestApi.runBacktest(params);
      setResult(backtest);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Backtest failed');
    } finally {
      setLoading(false);
    }
  };

  const handleExportCSV = async () => {
    if (!result) return;

    try {
      const blob = await backtestApi.exportCSV(result.symbol, result.timeframe);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `backtest_${result.symbol}_${result.timeframe}_${startDate}_to_${endDate}.csv`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed');
    }
  };

  const handleExportHTML = async () => {
    if (!result) return;

    try {
      const blob = await backtestApi.exportHTML(result.symbol, result.timeframe);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `backtest_${result.symbol}_${result.timeframe}_${startDate}_to_${endDate}.html`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed');
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white dark:bg-gray-900 rounded-lg shadow-lg p-6 border border-gray-200 dark:border-gray-700">
        <h1 className="text-3xl font-bold text-gray-800 dark:text-white mb-4">
          📈 AI-Driven Backtest Engine
        </h1>
        <p className="text-gray-600 dark:text-gray-400 mb-2">
          Backtest using Consensus AI decisions: Touche 50% + Fundamental 35% + News 15%
        </p>
        <p className="text-sm text-gray-500 dark:text-gray-500">
          6 AI modules analyzing price action, on-chain metrics, news sentiment, and liquidity
        </p>
      </div>

      {/* Controls */}
      <div className="bg-white dark:bg-gray-900 rounded-lg shadow-lg p-6 border border-gray-200 dark:border-gray-700">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
          {/* Symbol Selector */}
          <div>
            <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
              Trading Pair
            </label>
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none"
            >
              {symbols.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>

          {/* Timeframe Selector */}
          <div>
            <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
              Timeframe
            </label>
            <select
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none"
            >
              {timeframes.map((tf) => (
                <option key={tf} value={tf}>
                  {tf}
                </option>
              ))}
            </select>
          </div>

          {/* Start Date */}
          <div>
            <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
              Start Date
            </label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none"
            />
          </div>

          {/* End Date */}
          <div>
            <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
              End Date
            </label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none"
            />
          </div>

          {/* Run Button */}
          <div className="flex items-end">
            <button
              onClick={handleRunBacktest}
              disabled={loading}
              className="w-full px-4 py-2 bg-blue-500 hover:bg-blue-600 disabled:bg-gray-400 text-white font-semibold rounded-lg transition duration-200"
            >
              {loading ? '⏳ Running...' : '▶️ Run Backtest'}
            </button>
          </div>
        </div>

        {/* Error Message */}
        {error && (
          <div className="p-4 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200 rounded-lg">
            ⚠️ {error}
          </div>
        )}
      </div>

      {/* Results */}
      {result && result.metrics && (
        <>
          {/* Key Metrics */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[
              {
                label: 'Total PnL',
                value: `$${result.metrics.pnl.total_pnl.toFixed(2)}`,
                color: result.metrics.pnl.total_pnl >= 0 ? 'text-green-500' : 'text-red-500',
              },
              {
                label: 'Return %',
                value: `${result.metrics.pnl.total_pnl_pct.toFixed(2)}%`,
                color: result.metrics.pnl.total_pnl_pct >= 0 ? 'text-green-500' : 'text-red-500',
              },
              {
                label: 'Win Rate',
                value: `${result.metrics.win_loss.win_rate.toFixed(1)}%`,
                color: 'text-blue-500',
              },
              {
                label: 'Profit Factor',
                value: `${result.metrics.win_loss.profit_factor.toFixed(2)}x`,
                color: 'text-blue-500',
              },
              {
                label: 'Max Drawdown',
                value: `${result.metrics.drawdown.max_drawdown_pct.toFixed(2)}%`,
                color: 'text-red-500',
              },
              {
                label: 'Sharpe Ratio',
                value: `${result.metrics.sharpe_ratio.toFixed(2)}`,
                color: 'text-blue-500',
              },
            ].map((metric, idx) => (
              <div
                key={idx}
                className="bg-white dark:bg-gray-900 rounded-lg shadow-lg p-4 border border-gray-200 dark:border-gray-700"
              >
                <p className="text-gray-600 dark:text-gray-400 text-sm font-semibold mb-2">
                  {metric.label}
                </p>
                <p className={`text-2xl font-bold ${metric.color}`}>{metric.value}</p>
              </div>
            ))}
          </div>

          {/* Statistics */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Win/Loss Stats */}
            <div className="bg-white dark:bg-gray-900 rounded-lg shadow-lg p-6 border border-gray-200 dark:border-gray-700">
              <h3 className="text-lg font-bold text-gray-800 dark:text-white mb-4">
                📊 Trade Statistics
              </h3>
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-gray-600 dark:text-gray-400">Total Trades:</span>
                  <span className="font-semibold text-gray-800 dark:text-white">
                    {result.metrics.pnl.num_trades}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600 dark:text-gray-400">Winning Trades:</span>
                  <span className="font-semibold text-green-500">
                    {result.metrics.win_loss.win_count}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600 dark:text-gray-400">Losing Trades:</span>
                  <span className="font-semibold text-red-500">
                    {result.metrics.win_loss.loss_count}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600 dark:text-gray-400">Avg Win:</span>
                  <span className="font-semibold text-gray-800 dark:text-white">
                    ${result.metrics.win_loss.avg_win.toFixed(2)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600 dark:text-gray-400">Avg Loss:</span>
                  <span className="font-semibold text-gray-800 dark:text-white">
                    ${result.metrics.win_loss.avg_loss.toFixed(2)}
                  </span>
                </div>
              </div>
            </div>

            {/* Capital Summary */}
            <div className="bg-white dark:bg-gray-900 rounded-lg shadow-lg p-6 border border-gray-200 dark:border-gray-700">
              <h3 className="text-lg font-bold text-gray-800 dark:text-white mb-4">
                💰 Capital Summary
              </h3>
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-gray-600 dark:text-gray-400">Initial Capital:</span>
                  <span className="font-semibold text-gray-800 dark:text-white">
                    ${result.metrics.initial_capital.toFixed(2)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600 dark:text-gray-400">Final Capital:</span>
                  <span className="font-semibold text-gray-800 dark:text-white">
                    ${result.metrics.final_capital.toFixed(2)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600 dark:text-gray-400">Max Drawdown:</span>
                  <span className="font-semibold text-red-500">
                    ${result.metrics.drawdown.max_drawdown.toFixed(2)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600 dark:text-gray-400">Sortino Ratio:</span>
                  <span className="font-semibold text-gray-800 dark:text-white">
                    {result.metrics.sortino_ratio.toFixed(2)}
                  </span>
                </div>
                <div className="flex justify-between pt-3 border-t border-gray-300 dark:border-gray-600">
                  <span className="text-gray-600 dark:text-gray-400 font-semibold">Data Points:</span>
                  <span className="font-semibold text-gray-800 dark:text-white">
                    {result.data_points}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Export Buttons */}
          <div className="flex gap-4">
            <button
              onClick={handleExportCSV}
              className="flex-1 px-4 py-2 bg-green-500 hover:bg-green-600 text-white font-semibold rounded-lg transition duration-200"
            >
              📥 Export CSV
            </button>
            <button
              onClick={handleExportHTML}
              className="flex-1 px-4 py-2 bg-purple-500 hover:bg-purple-600 text-white font-semibold rounded-lg transition duration-200"
            >
              📊 Export Report
            </button>
          </div>

          {/* Info Box */}
          <div className="bg-blue-50 dark:bg-blue-900 border border-blue-200 dark:border-blue-700 rounded-lg p-4">
            <p className="text-blue-900 dark:text-blue-200 text-sm">
              ✨ <strong>AI-Driven Strategy:</strong> {result.strategy}
            </p>
            <p className="text-blue-900 dark:text-blue-200 text-sm mt-2">
              📅 <strong>Period:</strong> {result.date_range.start} to {result.date_range.end}
            </p>
          </div>
        </>
      )}

      {/* No Results */}
      {!result && !loading && (
        <div className="text-center py-12 bg-white dark:bg-gray-900 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700">
          <p className="text-gray-600 dark:text-gray-400 text-lg">
            📈 Run a backtest to see AI performance
          </p>
        </div>
      )}

      {/* ── Hyperopt Panel ─────────────────────────────────────────────────── */}
      <HyperoptPanel
        symbol={symbol}
        timeframe={timeframe}
        startDate={startDate}
        endDate={endDate}
      />
    </div>
  );
};

export default Backtest;
