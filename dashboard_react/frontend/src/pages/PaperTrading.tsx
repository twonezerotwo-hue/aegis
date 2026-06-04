import React, { useState, useEffect } from 'react';
import { paperTradingApi, PaperTradingSession } from '../services/paperTradingApi';
import { PaperAutoPanel } from '../components/paper/PaperAutoPanel';

const PaperTrading: React.FC = () => {
  const [session, setSession] = useState<PaperTradingSession | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshInterval, setRefreshInterval] = useState<number | null>(null);

  const symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT'];
  const [selectedSymbol, setSelectedSymbol] = useState('BTC/USDT');
  const [initialCapital] = useState(100000);

  useEffect(() => {
    return () => {
      if (refreshInterval) clearInterval(refreshInterval);
    };
  }, [refreshInterval]);

  const handleStart = async () => {
    setLoading(true);
    setError(null);

    try {
      const newSession = await paperTradingApi.start({
        symbol: selectedSymbol,
        initial_capital: initialCapital,
        strategy: 'sma_crossover',
      });

      setSession(newSession);
      setIsRunning(true);

      // Auto-refresh every 5 seconds
      const interval = setInterval(async () => {
        try {
          const updated = await paperTradingApi.getStatus();
          setSession(updated);
        } catch (err) {
          console.error('Failed to refresh session:', err);
        }
      }, 5000);

      setRefreshInterval(interval);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start paper trading');
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    setLoading(true);
    setError(null);

    try {
      if (refreshInterval) clearInterval(refreshInterval);

      const result = await paperTradingApi.stop();
      setIsRunning(false);
      setSession(null);

      alert(
        `Paper Trading Stopped\nFinal Balance: $${result.final_balance.toFixed(2)}`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to stop paper trading');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* ÖNCELİK: Agent config'iyle otonom paper trading */}
      <PaperAutoPanel />

      {/* Manuel paper trading (eski) */}
      <div className="bg-white dark:bg-gray-900 rounded-lg shadow-lg p-6 border border-gray-200 dark:border-gray-700">
        <h1 className="text-3xl font-bold text-gray-800 dark:text-white mb-4">
          📝 Paper Trading (Manuel)
        </h1>
        <p className="text-gray-600 dark:text-gray-400 mb-4">
          Practice trading with $100,000 virtual capital
        </p>
        <div className="flex items-center gap-2">
          <div
            className={`w-3 h-3 rounded-full ${
              isRunning ? 'bg-green-500 animate-pulse' : 'bg-gray-400'
            }`}
          ></div>
          <span className="text-gray-700 dark:text-gray-300 font-semibold">
            {isRunning ? 'Trading Active' : 'Not Running'}
          </span>
        </div>
      </div>

      {/* Controls */}
      {!isRunning ? (
        <div className="bg-white dark:bg-gray-900 rounded-lg shadow-lg p-6 border border-gray-200 dark:border-gray-700">
          <h2 className="text-xl font-bold text-gray-800 dark:text-white mb-4">
            ⚙️ Setup Paper Trading
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            {/* Symbol */}
            <div>
              <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                Trading Pair
              </label>
              <select
                value={selectedSymbol}
                onChange={(e) => setSelectedSymbol(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none"
              >
                {symbols.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>

            {/* Capital */}
            <div>
              <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                Initial Capital
              </label>
              <div className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-white font-semibold">
                ${initialCapital.toLocaleString()}
              </div>
            </div>

            {/* Status */}
            <div className="flex items-end">
              <button
                onClick={handleStart}
                disabled={loading}
                className="w-full px-4 py-2 bg-green-500 hover:bg-green-600 disabled:bg-gray-400 text-white font-semibold rounded-lg transition duration-200"
              >
                {loading ? '⏳ Starting...' : '▶️ Start Trading'}
              </button>
            </div>
          </div>

          {error && (
            <div className="p-4 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200 rounded-lg">
              ⚠️ {error}
            </div>
          )}
        </div>
      ) : session ? (
        <>
          {/* Session Status */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-white dark:bg-gray-900 rounded-lg shadow-lg p-4 border border-gray-200 dark:border-gray-700">
              <p className="text-gray-600 dark:text-gray-400 text-sm font-semibold mb-2">
                Current Balance
              </p>
              <p className="text-2xl font-bold text-blue-500">
                ${session.current_balance.toFixed(2)}
              </p>
            </div>

            <div className="bg-white dark:bg-gray-900 rounded-lg shadow-lg p-4 border border-gray-200 dark:border-gray-700">
              <p className="text-gray-600 dark:text-gray-400 text-sm font-semibold mb-2">
                Total PnL
              </p>
              <p
                className={`text-2xl font-bold ${
                  session.pnl >= 0 ? 'text-green-500' : 'text-red-500'
                }`}
              >
                ${session.pnl.toFixed(2)}
              </p>
            </div>

            <div className="bg-white dark:bg-gray-900 rounded-lg shadow-lg p-4 border border-gray-200 dark:border-gray-700">
              <p className="text-gray-600 dark:text-gray-400 text-sm font-semibold mb-2">
                Return %
              </p>
              <p
                className={`text-2xl font-bold ${
                  session.pnl_pct >= 0 ? 'text-green-500' : 'text-red-500'
                }`}
              >
                {session.pnl_pct.toFixed(2)}%
              </p>
            </div>

            <div className="bg-white dark:bg-gray-900 rounded-lg shadow-lg p-4 border border-gray-200 dark:border-gray-700">
              <p className="text-gray-600 dark:text-gray-400 text-sm font-semibold mb-2">
                Total Trades
              </p>
              <p className="text-2xl font-bold text-gray-800 dark:text-white">
                {session.trades.length}
              </p>
            </div>
          </div>

          {/* Positions */}
          {session.positions && session.positions.length > 0 && (
            <div className="bg-white dark:bg-gray-900 rounded-lg shadow-lg overflow-hidden border border-gray-200 dark:border-gray-700">
              <div className="p-6 border-b border-gray-200 dark:border-gray-700">
                <h3 className="text-lg font-bold text-gray-800 dark:text-white">
                  📊 Open Positions
                </h3>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
                      <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">
                        Symbol
                      </th>
                      <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">
                        Quantity
                      </th>
                      <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">
                        Entry Price
                      </th>
                      <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">
                        Current Price
                      </th>
                      <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">
                        PnL
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {session.positions.map((pos, idx) => (
                      <tr
                        key={idx}
                        className="border-b border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 transition"
                      >
                        <td className="px-6 py-4 text-gray-900 dark:text-white font-semibold">
                          {pos.symbol}
                        </td>
                        <td className="px-6 py-4 text-gray-900 dark:text-white">
                          {pos.quantity.toFixed(4)}
                        </td>
                        <td className="px-6 py-4 text-gray-900 dark:text-white">
                          ${pos.entry_price.toFixed(2)}
                        </td>
                        <td className="px-6 py-4 text-gray-900 dark:text-white">
                          ${pos.current_price.toFixed(2)}
                        </td>
                        <td
                          className={`px-6 py-4 font-semibold ${
                            pos.pnl >= 0 ? 'text-green-500' : 'text-red-500'
                          }`}
                        >
                          ${pos.pnl.toFixed(2)} ({pos.pnl_pct.toFixed(2)}%)
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Trade History */}
          {session.trades && session.trades.length > 0 && (
            <div className="bg-white dark:bg-gray-900 rounded-lg shadow-lg overflow-hidden border border-gray-200 dark:border-gray-700">
              <div className="p-6 border-b border-gray-200 dark:border-gray-700">
                <h3 className="text-lg font-bold text-gray-800 dark:text-white">
                  📜 Trade History
                </h3>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
                      <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">
                        Time
                      </th>
                      <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">
                        Side
                      </th>
                      <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">
                        Quantity
                      </th>
                      <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">
                        Price
                      </th>
                      <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">
                        Commission
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {session.trades.slice(-10).reverse().map((trade, idx) => (
                      <tr
                        key={idx}
                        className="border-b border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 transition"
                      >
                        <td className="px-6 py-4 text-gray-900 dark:text-white text-sm">
                          {new Date(trade.timestamp).toLocaleTimeString()}
                        </td>
                        <td
                          className={`px-6 py-4 font-semibold ${
                            trade.side === 'BUY' ? 'text-green-500' : 'text-red-500'
                          }`}
                        >
                          {trade.side}
                        </td>
                        <td className="px-6 py-4 text-gray-900 dark:text-white">
                          {trade.quantity.toFixed(4)}
                        </td>
                        <td className="px-6 py-4 text-gray-900 dark:text-white">
                          ${trade.price.toFixed(2)}
                        </td>
                        <td className="px-6 py-4 text-gray-900 dark:text-white">
                          ${trade.commission.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Stop Button */}
          <div className="flex gap-4">
            <button
              onClick={handleStop}
              disabled={loading}
              className="flex-1 px-4 py-2 bg-red-500 hover:bg-red-600 disabled:bg-gray-400 text-white font-semibold rounded-lg transition duration-200"
            >
              {loading ? '⏳ Stopping...' : '⏹️ Stop Trading'}
            </button>
          </div>
        </>
      ) : null}

      {/* Info Box */}
      {!isRunning && (
        <div className="bg-blue-50 dark:bg-blue-900 border border-blue-200 dark:border-blue-700 rounded-lg p-4">
          <p className="text-blue-900 dark:text-blue-200 text-sm">
            ℹ️ Paper trading simulates real trading with $100,000 virtual capital. All trades
            are simulated and will not execute real transactions.
          </p>
        </div>
      )}
    </div>
  );
};

export default PaperTrading;
