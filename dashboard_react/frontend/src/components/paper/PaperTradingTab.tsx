import React, { useEffect, useState } from "react";
import { ToastTone } from "../layout/Toast";
import { AnimatedNumber } from "../ui/AnimatedNumber";
import { ErrorFallback } from "../ui/ErrorFallback";
import { SkeletonLoader } from "../ui/SkeletonLoader";

interface EquityPoint {
  timestamp: string;
  balance: number;
}

interface Position {
  symbol: string;
  quantity: number;
  entry_price: number;
  current_price: number;
  pnl: number;
  pnl_pct: number;
}

interface PaperTrade {
  id: string;
  timestamp: string;
  symbol: string;
  side: "BUY" | "SELL";
  price: number;
  quantity: number;
  commission: number;
  pnl?: number;
}

interface PaperTradingSession {
  id: string;
  symbol: string;
  initial_capital: number;
  current_balance: number;
  positions: Position[];
  trades: PaperTrade[];
  pnl: number;
  pnl_pct: number;
  status: "running" | "stopped";
  created_at: string;
  equity_curve: EquityPoint[];
}

interface ToastPayload {
  title: string;
  message: string;
  tone: ToastTone;
}

interface PaperTradingTabProps {
  onToast: (toast: ToastPayload) => void;
}

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8502";

const formatMoney = (value: number): string =>
  value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  });

const toSparklinePoints = (curve: EquityPoint[]): string => {
  if (curve.length === 0) {
    return "0,60 120,60";
  }

  const balances = curve.map((point) => point.balance);
  const minBalance = Math.min(...balances);
  const maxBalance = Math.max(...balances);
  const spread = Math.max(1, maxBalance - minBalance);

  return curve
    .map((point, index) => {
      const x = curve.length === 1 ? 60 : (index / (curve.length - 1)) * 120;
      const y = 95 - ((point.balance - minBalance) / spread) * 70;
      return `${x},${y}`;
    })
    .join(" ");
};

const getWinRate = (trades: PaperTrade[]): number => {
  const closedTrades = trades.filter((trade) => trade.side === "SELL" && typeof trade.pnl === "number");

  if (closedTrades.length === 0) {
    return 0;
  }

  const wins = closedTrades.filter((trade) => (trade.pnl ?? 0) > 0).length;
  return (wins / closedTrades.length) * 100;
};

const getSessionAge = (createdAt: string): string => {
  const elapsedMs = Date.now() - new Date(createdAt).getTime();
  const elapsedMinutes = Math.max(0, Math.floor(elapsedMs / 60000));

  if (elapsedMinutes < 60) {
    return `${elapsedMinutes} dk`;
  }

  const hours = Math.floor(elapsedMinutes / 60);
  const minutes = elapsedMinutes % 60;
  return `${hours}s ${minutes}dk`;
};

export const PaperTradingTab: React.FC<PaperTradingTabProps> = ({ onToast }) => {
  const [session, setSession] = useState<PaperTradingSession | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState<boolean>(false);
  const [isStopping, setIsStopping] = useState<boolean>(false);
  const [isExporting, setIsExporting] = useState<boolean>(false);
  const [refreshTick, setRefreshTick] = useState<number>(0);

  useEffect(() => {
    let cancelled = false;

    const fetchStatus = async () => {
      if (!cancelled) {
        setLoading((current) => (session ? current : true));
      }

      try {
        const response = await fetch(`${API_BASE_URL}/api/paper/status`);

        if (response.status === 404) {
          if (!cancelled) {
            setSession(null);
            setError(null);
          }
          return;
        }

        if (!response.ok) {
          throw new Error(`Paper status failed: ${response.status}`);
        }

        const payload: PaperTradingSession = await response.json();
        if (!cancelled) {
          setSession(payload);
          setError(null);
        }
      } catch (requestError) {
        if (!cancelled) {
          setError(requestError instanceof Error ? requestError.message : "Paper trading verisi alinamadi.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void fetchStatus();
    const intervalId = window.setInterval(() => {
      void fetchStatus();
    }, 5000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [refreshTick, session]);

  const handleStart = async () => {
    setIsStarting(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/paper/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: "BTC/USDT",
          initial_capital: 100000,
          strategy: "dashboard_v2_consensus",
        }),
      });

      if (!response.ok) {
        throw new Error(`Paper start failed: ${response.status}`);
      }

      const payload: PaperTradingSession = await response.json();
      setSession(payload);
      onToast({
        title: "Paper Trading basladi",
        message: `${payload.symbol} uzerinde sanal oturum acildi.`,
        tone: "success",
      });
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "Session baslatilamadi.";
      setError(message);
      onToast({ title: "Paper Trading hatasi", message, tone: "error" });
    } finally {
      setIsStarting(false);
      setLoading(false);
    }
  };

  const handleStop = async () => {
    setIsStopping(true);

    try {
      const response = await fetch(`${API_BASE_URL}/api/paper/stop`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });

      if (!response.ok) {
        throw new Error(`Paper stop failed: ${response.status}`);
      }

      const payload = (await response.json()) as { final_balance: number; pnl_pct: number };
      setSession(null);
      onToast({
        title: "Paper Trading durduruldu",
        message: `Final bakiye ${formatMoney(payload.final_balance)} ve getiri ${payload.pnl_pct.toFixed(2)}% olarak kaydedildi.`,
        tone: "warning",
      });
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "Session durdurulamadi.";
      setError(message);
      onToast({ title: "Paper Trading hatasi", message, tone: "error" });
    } finally {
      setIsStopping(false);
      setRefreshTick((current) => current + 1);
    }
  };

  const handleExport = async () => {
    setIsExporting(true);

    try {
      const response = await fetch(`${API_BASE_URL}/api/paper/export`);

      if (!response.ok) {
        throw new Error(`Paper export failed: ${response.status}`);
      }

      const payload = (await response.json()) as { content: string; filename: string };
      const blob = new Blob([payload.content], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = payload.filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);

      onToast({
        title: "Statement hazir",
        message: `${payload.filename} indirildi.`,
        tone: "info",
      });
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "Statement export basarisiz.";
      setError(message);
      onToast({ title: "Export hatasi", message, tone: "error" });
    } finally {
      setIsExporting(false);
    }
  };

  if (error && !session) {
    return (
      <ErrorFallback
        title="Paper Trading baglantisi"
        message={error}
        details="Paper session endpoint'i gecici olarak ulasilamaz olabilir. Sonraki poll dongusu ile veri otomatik tekrar denenecek."
        onRetry={() => {
          setLoading(true);
          setError(null);
          setRefreshTick((current) => current + 1);
        }}
      />
    );
  }

  if (loading && !session) {
    return (
      <div className="grid gap-3 lg:grid-cols-3">
        <SkeletonLoader lines={6} />
        <SkeletonLoader lines={6} />
        <SkeletonLoader lines={6} />
      </div>
    );
  }

  if (!session) {
    return (
      <div className="rounded-2xl border border-slate-700 bg-slate-900/90 p-6">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Paper Trading</p>
        <h3 className="mt-3 text-2xl font-semibold text-white">Aktif sanal oturum yok</h3>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-300">
          Tek tikla 100k USDT sanal sermaye ile BTC/USDT simulasyonu baslatilir. Equity curve, acik pozisyonlar ve kapanmis trade performansi bu sekmede akar.
        </p>
        <button
          type="button"
          onClick={handleStart}
          disabled={isStarting}
          className="mt-5 rounded-xl border border-emerald-400/20 bg-emerald-400 px-4 py-2.5 text-sm font-semibold text-slate-950 transition-colors hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isStarting ? "Baslatiliyor..." : "Simulasyonu baslat"}
        </button>
      </div>
    );
  }

  const winRate = getWinRate(session.trades);
  const sparklinePoints = toSparklinePoints(session.equity_curve);
  const isPositive = session.pnl >= 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 rounded-2xl border border-slate-700 bg-slate-900/90 p-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Paper Session</p>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <h3 className="text-xl font-semibold text-white">{session.symbol}</h3>
            <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-emerald-300">
              {session.status}
            </span>
            <span className="rounded-full border border-slate-600 bg-slate-800 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-300">
              Yas {getSessionAge(session.created_at)}
            </span>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={handleExport}
            disabled={isExporting}
            className="rounded-xl border border-slate-600 bg-slate-800 px-4 py-2 text-sm font-medium text-slate-200 transition-colors hover:border-slate-500 hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isExporting ? "Hazirlaniyor..." : "Statement Export"}
          </button>
          <button
            type="button"
            onClick={handleStop}
            disabled={isStopping}
            className="rounded-xl border border-rose-400/20 bg-rose-500/90 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-rose-400 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isStopping ? "Durduruluyor..." : "Stop Session"}
          </button>
        </div>
      </div>

      <div className="grid gap-3 xl:grid-cols-4">
        <div className="rounded-2xl border border-slate-700 bg-slate-900/90 px-4 py-3">
          <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Balance</p>
          <p className="mt-2 font-mono text-xl">
            <AnimatedNumber
              value={session.current_balance}
              formatter={formatMoney}
              neutralClassName="text-white"
              positiveClassName="text-emerald-300"
              negativeClassName="text-rose-300"
              className="font-mono"
            />
          </p>
        </div>
        <div className="rounded-2xl border border-slate-700 bg-slate-900/90 px-4 py-3">
          <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Total PnL</p>
          <p className="mt-2 font-mono text-xl">
            <AnimatedNumber
              value={session.pnl}
              formatter={(value) => `${value >= 0 ? "+" : ""}${formatMoney(value)}`}
              neutralClassName={isPositive ? "text-emerald-300" : "text-rose-300"}
              positiveClassName="text-emerald-300"
              negativeClassName="text-rose-300"
              className="font-mono"
            />
          </p>
        </div>
        <div className="rounded-2xl border border-slate-700 bg-slate-900/90 px-4 py-3">
          <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">PnL %</p>
          <p className="mt-2 font-mono text-xl">
            <AnimatedNumber
              value={session.pnl_pct}
              formatter={(value) => `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`}
              neutralClassName={isPositive ? "text-emerald-300" : "text-rose-300"}
              positiveClassName="text-emerald-300"
              negativeClassName="text-rose-300"
              className="font-mono"
            />
          </p>
        </div>
        <div className="rounded-2xl border border-slate-700 bg-slate-900/90 px-4 py-3">
          <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Win Rate</p>
          <p className="mt-2 font-mono text-xl text-white">{winRate.toFixed(1)}%</p>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
        <div className="rounded-2xl border border-slate-700 bg-slate-900/90 p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Equity Curve</p>
              <p className="mt-2 text-sm text-slate-300">Realized balance hareketi ve oturum ivmesi</p>
            </div>
            <p className="font-mono text-sm text-slate-200">{session.equity_curve.length} nokta</p>
          </div>
          <div className="mt-4 overflow-hidden rounded-2xl border border-slate-700 bg-slate-950/70 p-4">
            <svg viewBox="0 0 120 100" className="h-48 w-full">
              <defs>
                <linearGradient id="paperEquityFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={isPositive ? "#34d399" : "#fb7185"} stopOpacity="0.28" />
                  <stop offset="100%" stopColor={isPositive ? "#34d399" : "#fb7185"} stopOpacity="0" />
                </linearGradient>
              </defs>
              <polyline fill="none" stroke="rgba(148, 163, 184, 0.16)" strokeWidth="1" points="0,75 120,75" />
              <polygon fill="url(#paperEquityFill)" points={`0,100 ${sparklinePoints} 120,100`} />
              <polyline
                fill="none"
                stroke={isPositive ? "#34d399" : "#fb7185"}
                strokeWidth="3"
                strokeLinecap="round"
                strokeLinejoin="round"
                points={sparklinePoints}
              />
            </svg>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-700 bg-slate-900/90 p-4">
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Open Positions</p>
          <div className="mt-4 space-y-3">
            {session.positions.length === 0 ? (
              <div className="rounded-2xl border border-slate-700 bg-slate-950/70 p-4 text-sm text-slate-400">Acik pozisyon yok.</div>
            ) : (
              session.positions.map((position) => (
                <div key={`${position.symbol}-${position.entry_price}`} className="rounded-2xl border border-slate-700 bg-slate-950/70 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-white">{position.symbol}</p>
                      <p className="mt-1 font-mono text-xs text-slate-500">Qty {position.quantity.toFixed(4)}</p>
                    </div>
                    <p className={`font-mono text-sm ${position.pnl >= 0 ? "text-emerald-300" : "text-rose-300"}`}>
                      {position.pnl >= 0 ? "+" : ""}
                      {formatMoney(position.pnl)}
                    </p>
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-3 text-xs text-slate-400">
                    <div>
                      <p className="uppercase tracking-[0.16em] text-slate-500">Entry</p>
                      <p className="mt-1 font-mono text-slate-200">{formatMoney(position.entry_price)}</p>
                    </div>
                    <div>
                      <p className="uppercase tracking-[0.16em] text-slate-500">Mark</p>
                      <p className="mt-1 font-mono text-slate-200">{formatMoney(position.current_price)}</p>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-700 bg-slate-900/90 p-4">
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Recent Trades</p>
          <p className="font-mono text-xs text-slate-400">{session.trades.length} kayit</p>
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          {session.trades.slice().reverse().slice(0, 6).map((trade) => (
            <div key={trade.id} className="rounded-2xl border border-slate-700 bg-slate-950/70 p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-white">{trade.side} {trade.symbol}</p>
                  <p className="mt-1 text-xs text-slate-500">{new Date(trade.timestamp).toLocaleString("tr-TR")}</p>
                </div>
                <span className={`rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] ${trade.side === "BUY" ? "bg-emerald-500/10 text-emerald-300" : "bg-rose-500/10 text-rose-300"}`}>
                  {trade.side}
                </span>
              </div>
              <div className="mt-3 grid grid-cols-3 gap-3 text-xs text-slate-400">
                <div>
                  <p className="uppercase tracking-[0.16em] text-slate-500">Price</p>
                  <p className="mt-1 font-mono text-slate-200">{formatMoney(trade.price)}</p>
                </div>
                <div>
                  <p className="uppercase tracking-[0.16em] text-slate-500">Qty</p>
                  <p className="mt-1 font-mono text-slate-200">{trade.quantity.toFixed(4)}</p>
                </div>
                <div>
                  <p className="uppercase tracking-[0.16em] text-slate-500">PnL</p>
                  <p className={`mt-1 font-mono ${typeof trade.pnl === "number" && trade.pnl < 0 ? "text-rose-300" : "text-emerald-300"}`}>
                    {typeof trade.pnl === "number" ? `${trade.pnl >= 0 ? "+" : ""}${formatMoney(trade.pnl)}` : "--"}
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};