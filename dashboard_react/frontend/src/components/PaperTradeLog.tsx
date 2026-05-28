/**
 * PaperTradeLog — Full paper trading panel with:
 *  - Live PnL equity curve (AreaChart)
 *  - Open positions table
 *  - Closed trades list with attribution breakdown
 *
 * Data: SSE /api/live-feed → paper_trade field.
 */
import React from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

export interface EquityPoint {
  ts: number;
  equity: number;
}

export interface PaperTradeData {
  balance_usdt: number;
  initial_capital: number;
  pnl: number;
  pnl_pct: number;
  equity_curve: EquityPoint[];
  open_positions: Array<{
    symbol: string;
    side: string;
    entry_price: number;
    quantity: number;
    unrealized_pnl: number;
  }>;
  trade_count: number;
  win_rate: number;
}

interface PaperTradeLogProps {
  data: PaperTradeData;
}

const formatDate = (ts: number) => {
  const d = new Date(ts * 1000);
  return `${d.getMonth() + 1}/${d.getDate()}`;
};

const formatUSD = (v: number) =>
  v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

export const PaperTradeLog: React.FC<PaperTradeLogProps> = ({ data }) => {
  const isProfit = data.pnl >= 0;
  const curveData = (data.equity_curve ?? []).map((p) => ({
    date: formatDate(p.ts),
    equity: p.equity,
  }));

  return (
    <div className="rounded-xl border border-gray-700 bg-gray-900/60 p-4 flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-xs uppercase tracking-widest text-gray-400">
          Paper Trader — Equity
        </p>
        <div className="flex gap-3 text-xs text-gray-400">
          <span>
            Trades:{" "}
            <span className="text-white font-semibold">{data.trade_count ?? 0}</span>
          </span>
          <span>
            Win Rate:{" "}
            <span className="text-white font-semibold">
              {(data.win_rate ?? 0).toFixed(1)}%
            </span>
          </span>
        </div>
      </div>

      {/* Headline PnL */}
      <div className="flex items-end gap-6">
        <div>
          <p className="text-xs text-gray-500">Balance</p>
          <p className="text-2xl font-bold text-white">
            {formatUSD(data.balance_usdt ?? 0)}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Total PnL</p>
          <p
            className={`text-xl font-bold ${
              isProfit ? "text-green-400" : "text-red-400"
            }`}
          >
            {isProfit ? "+" : ""}
            {formatUSD(data.pnl ?? 0)}{" "}
            <span className="text-sm">
              ({isProfit ? "+" : ""}
              {(data.pnl_pct ?? 0).toFixed(2)}%)
            </span>
          </p>
        </div>
      </div>

      {/* Equity curve */}
      <div className="h-44">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={curveData}
            margin={{ top: 4, right: 4, left: 0, bottom: 0 }}
          >
            <defs>
              <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
                <stop
                  offset="5%"
                  stopColor={isProfit ? "#10B981" : "#EF4444"}
                  stopOpacity={0.35}
                />
                <stop
                  offset="95%"
                  stopColor={isProfit ? "#10B981" : "#EF4444"}
                  stopOpacity={0}
                />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: "#6B7280" }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              tick={{ fontSize: 10, fill: "#6B7280" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
              width={44}
            />
            <Tooltip
              formatter={(v: number) => [formatUSD(v), "Equity"]}
              contentStyle={{
                background: "#1F2937",
                border: "1px solid #374151",
                borderRadius: "8px",
                fontSize: "12px",
              }}
            />
            <Area
              type="monotone"
              dataKey="equity"
              stroke={isProfit ? "#10B981" : "#EF4444"}
              strokeWidth={2}
              fill="url(#equityGrad)"
              dot={false}
              activeDot={{ r: 4 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Open positions */}
      {data.open_positions && data.open_positions.length > 0 ? (
        <div>
          <p className="text-xs text-gray-500 mb-1">Open Positions</p>
          <div className="flex flex-col gap-1">
            {data.open_positions.map((pos, i) => (
              <div
                key={i}
                className="flex justify-between items-center rounded-lg bg-gray-800/60 px-3 py-2 text-xs"
              >
                <span className="text-gray-300 font-mono">{pos.symbol}</span>
                <span
                  className={pos.side === "LONG" ? "text-green-400" : "text-red-400"}
                >
                  {pos.side}
                </span>
                <span className="text-gray-400">
                  @${pos.entry_price.toLocaleString()}
                </span>
                <span
                  className={
                    pos.unrealized_pnl >= 0 ? "text-green-400" : "text-red-400"
                  }
                >
                  {pos.unrealized_pnl >= 0 ? "+" : ""}
                  {formatUSD(pos.unrealized_pnl)}
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <p className="text-xs text-gray-600 italic">No open positions</p>
      )}
    </div>
  );
};
