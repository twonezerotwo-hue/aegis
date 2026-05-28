import React, { useEffect, useState } from "react";
import { ToastTone } from "../layout/Toast";
import { ErrorFallback } from "../ui/ErrorFallback";
import { SkeletonLoader } from "../ui/SkeletonLoader";

interface UnifiedOptimizerStatus {
  enabled: boolean;
  error?: string;
  weights?: Record<string, number>;
  phase_params?: Record<string, Record<string, number>>;
  stats?: {
    total_trades?: number;
    winning_trades?: number;
    losing_trades?: number;
    win_rate?: number;
    total_pnl?: number;
    avg_pnl?: number;
    optimization_count?: number;
    last_optimization?: string | null;
  };
  optimization_count?: number;
  last_optimization?: string | null;
}

interface OptimizerTrade {
  pnl: number;
  is_winning: boolean;
  winning_phases: number[];
  losing_phases: number[];
  timestamp: string;
  volatility: number;
}

interface OptimizationRecord {
  optimization_type?: string;
  optimizer?: string;
  timestamp?: string;
  best_score?: number;
  trades_analyzed?: number;
  new_params?: Record<string, Record<string, number>>;
}

interface ToastPayload {
  title: string;
  message: string;
  tone: ToastTone;
}

interface OptimizerTabProps {
  onToast: (toast: ToastPayload) => void;
}

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8502";

const phaseNames: Record<string, string> = {
  "1": "Likidite",
  "2": "Piyasa Yapisi",
  "3": "Bolgeler",
  "4": "Teyit",
  "5": "Zamanlama",
  "6": "Risk",
  "7": "Makro",
};

const formatSigned = (value: number): string => `${value >= 0 ? "+" : ""}${value.toFixed(2)}`;

const computeRealizedDrawdown = (trades: OptimizerTrade[]): number => {
  let equity = 100000;
  let peak = equity;
  let maxDrawdown = 0;

  trades.forEach((trade) => {
    equity += trade.pnl;
    peak = Math.max(peak, equity);
    maxDrawdown = Math.max(maxDrawdown, ((peak - equity) / peak) * 100);
  });

  return maxDrawdown;
};

export const OptimizerTab: React.FC<OptimizerTabProps> = ({ onToast }) => {
  const [status, setStatus] = useState<UnifiedOptimizerStatus | null>(null);
  const [trades, setTrades] = useState<OptimizerTrade[]>([]);
  const [history, setHistory] = useState<OptimizationRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState<number>(0);
  const [busyAction, setBusyAction] = useState<"optimize" | "save" | "load" | null>(null);

  useEffect(() => {
    let cancelled = false;

    const fetchOptimizer = async () => {
      if (!cancelled) {
        setLoading((current) => (status ? current : true));
      }

      try {
        const [statusResponse, tradesResponse, historyResponse] = await Promise.all([
          fetch(`${API_BASE_URL}/api/optimizer/status`),
          fetch(`${API_BASE_URL}/api/optimizer/trade-history?limit=12`),
          fetch(`${API_BASE_URL}/api/optimizer/optimization-history?limit=6`),
        ]);

        if (!statusResponse.ok) {
          throw new Error(`Optimizer status failed: ${statusResponse.status}`);
        }

        const statusPayload = (await statusResponse.json()) as UnifiedOptimizerStatus;
        const tradesPayload = tradesResponse.ok ? ((await tradesResponse.json()) as { trades?: OptimizerTrade[] }) : { trades: [] };
        const historyPayload = historyResponse.ok ? ((await historyResponse.json()) as { history?: OptimizationRecord[] }) : { history: [] };

        if (!cancelled) {
          setStatus(statusPayload);
          setTrades(Array.isArray(tradesPayload.trades) ? tradesPayload.trades : []);
          setHistory(Array.isArray(historyPayload.history) ? historyPayload.history : []);
          setError(statusPayload.enabled === false ? statusPayload.error ?? "Optimizer kullanilamiyor." : null);
        }
      } catch (requestError) {
        if (!cancelled) {
          setError(requestError instanceof Error ? requestError.message : "Optimizer verisi alinamadi.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void fetchOptimizer();
    const intervalId = window.setInterval(() => {
      void fetchOptimizer();
    }, 8000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [refreshTick, status]);

  const runAction = async (kind: "optimize" | "save" | "load") => {
    setBusyAction(kind);

    try {
      const endpoint =
        kind === "optimize"
          ? `${API_BASE_URL}/api/optimizer/periodic-optimize?optimization_type=light`
          : kind === "save"
            ? `${API_BASE_URL}/api/optimizer/save-config?filepath=dashboard_v2_optimizer.yaml`
            : `${API_BASE_URL}/api/optimizer/load-config?filepath=dashboard_v2_optimizer.yaml`;

      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });

      const payload = (await response.json()) as { success?: boolean; message?: string; best_score?: number; detail?: string };

      if (!response.ok || payload.success === false) {
        throw new Error(payload.detail ?? payload.message ?? `${kind} action failed`);
      }

      onToast({
        title: kind === "optimize" ? "Optimizer calisti" : kind === "save" ? "Optimizer config kaydedildi" : "Optimizer config yuklendi",
        message:
          kind === "optimize"
            ? `Light optimize tamamlandi. Best score ${payload.best_score?.toFixed(2) ?? "--"}.`
            : payload.message ?? "Islem tamamlandi.",
        tone: "success",
      });
      setRefreshTick((current) => current + 1);
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "Optimizer islemi basarisiz.";
      setError(message);
      onToast({ title: "Optimizer hatasi", message, tone: "error" });
    } finally {
      setBusyAction(null);
    }
  };

  if (error && !status) {
    return (
      <ErrorFallback
        title="Optimizer baglantisi"
        message={error}
        details="Optimizer gateway endpoint'leri gecici olarak donmuyor olabilir. Runtime status tekrar denendiginde panel otomatik toparlanir."
        onRetry={() => {
          setLoading(true);
          setError(null);
          setRefreshTick((current) => current + 1);
        }}
      />
    );
  }

  if (loading && !status) {
    return (
      <div className="grid gap-3 lg:grid-cols-4">
        <SkeletonLoader lines={4} />
        <SkeletonLoader lines={4} />
        <SkeletonLoader lines={4} />
        <SkeletonLoader lines={4} />
      </div>
    );
  }

  if (!status?.enabled) {
    return (
      <ErrorFallback
        title="Optimizer offline"
        message={status?.error ?? error ?? "Unified optimizer su anda erisilebilir degil."}
        details="Bu durumda panelde sadece son alinabilen metrikler gorulebilir. Yeniden deneme butonu status endpoint'ini tekrar sorgular."
        onRetry={() => setRefreshTick((current) => current + 1)}
      />
    );
  }

  const latestHistory = history[history.length - 1] ?? null;
  const weights = Object.entries(status.weights ?? {}).sort(([left], [right]) => Number(left) - Number(right));
  const phaseParams = Object.entries(latestHistory?.new_params ?? status.phase_params ?? {}).sort(
    ([left], [right]) => Number(left) - Number(right)
  );
  const realizedDrawdown = computeRealizedDrawdown(trades);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 rounded-2xl border border-slate-700 bg-slate-900/90 p-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Optimizer Runtime</p>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <h3 className="text-xl font-semibold text-white">Unified Optimizer</h3>
            <span className="rounded-full border border-sky-500/20 bg-sky-500/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-sky-300">
              Active Study LIVE-ADAPTIVE
            </span>
            {status.last_optimization ? (
              <span className="rounded-full border border-slate-600 bg-slate-800 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-300">
                Son optimize {new Date(status.last_optimization).toLocaleString("tr-TR")}
              </span>
            ) : null}
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void runAction("optimize")}
            disabled={busyAction !== null}
            className="rounded-xl border border-emerald-400/20 bg-emerald-400 px-4 py-2 text-sm font-semibold text-slate-950 transition-colors hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busyAction === "optimize" ? "Calisiyor..." : "Light Optimize"}
          </button>
          <button
            type="button"
            onClick={() => void runAction("save")}
            disabled={busyAction !== null}
            className="rounded-xl border border-slate-600 bg-slate-800 px-4 py-2 text-sm font-medium text-slate-200 transition-colors hover:border-slate-500 hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busyAction === "save" ? "Kaydediliyor..." : "Snapshot Save"}
          </button>
          <button
            type="button"
            onClick={() => void runAction("load")}
            disabled={busyAction !== null}
            className="rounded-xl border border-slate-600 bg-slate-800 px-4 py-2 text-sm font-medium text-slate-200 transition-colors hover:border-slate-500 hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busyAction === "load" ? "Yukleniyor..." : "Restore Snapshot"}
          </button>
          <button
            type="button"
            disabled
            title="Consensus apply bridge bu dashboard backend'inde mevcut degil."
            className="cursor-not-allowed rounded-xl border border-slate-700 bg-slate-900 px-4 py-2 text-sm font-medium text-slate-500"
          >
            Apply to Consensus
          </button>
          <button
            type="button"
            disabled
            title="Rollback endpoint V2 gateway uzerinden expose edilmiyor."
            className="cursor-not-allowed rounded-xl border border-slate-700 bg-slate-900 px-4 py-2 text-sm font-medium text-slate-500"
          >
            Rollback
          </button>
        </div>
      </div>

      <div className="grid gap-3 xl:grid-cols-4">
        <div className="rounded-2xl border border-slate-700 bg-slate-900/90 px-4 py-3">
          <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Sharpe Proxy</p>
          <p className="mt-2 font-mono text-xl text-white">{latestHistory?.best_score?.toFixed(2) ?? "--"}</p>
        </div>
        <div className="rounded-2xl border border-slate-700 bg-slate-900/90 px-4 py-3">
          <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Win Rate</p>
          <p className="mt-2 font-mono text-xl text-white">{status.stats?.win_rate?.toFixed(1) ?? "0.0"}%</p>
        </div>
        <div className="rounded-2xl border border-slate-700 bg-slate-900/90 px-4 py-3">
          <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Realized DD</p>
          <p className="mt-2 font-mono text-xl text-white">{realizedDrawdown.toFixed(2)}%</p>
        </div>
        <div className="rounded-2xl border border-slate-700 bg-slate-900/90 px-4 py-3">
          <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Total PnL</p>
          <p className={`mt-2 font-mono text-xl ${(status.stats?.total_pnl ?? 0) >= 0 ? "text-emerald-300" : "text-rose-300"}`}>
            {formatSigned(status.stats?.total_pnl ?? 0)}
          </p>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.1fr_1fr]">
        <div className="rounded-2xl border border-slate-700 bg-slate-900/90 p-4">
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Recommended Weights</p>
            <p className="font-mono text-xs text-slate-400">{weights.length} faz</p>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
            {weights.map(([phaseId, weight]) => (
              <div key={phaseId} className="rounded-2xl border border-slate-700 bg-slate-950/70 p-4">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-semibold text-white">{phaseNames[phaseId] ?? `Phase ${phaseId}`}</p>
                  <span className="font-mono text-sm text-slate-200">{(weight * 100).toFixed(1)}%</span>
                </div>
                <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-800">
                  <div className="h-2 rounded-full bg-cyan-400 shadow-lg shadow-cyan-950/40" style={{ width: `${Math.max(6, weight * 100)}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-2xl border border-slate-700 bg-slate-900/90 p-4">
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Best Config Params</p>
            <p className="text-xs text-slate-400">{latestHistory?.optimizer ?? "runtime"}</p>
          </div>
          <div className="mt-4 space-y-3">
            {phaseParams.length === 0 ? (
              <div className="rounded-2xl border border-slate-700 bg-slate-950/70 p-4 text-sm text-slate-400">Henüz optimize edilmis parametre yok.</div>
            ) : (
              phaseParams.slice(0, 4).map(([phaseId, params]) => (
                <div key={phaseId} className="rounded-2xl border border-slate-700 bg-slate-950/70 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-semibold text-white">{phaseNames[phaseId] ?? `Phase ${phaseId}`}</p>
                    <span className="text-[11px] uppercase tracking-[0.16em] text-slate-500">Top params</span>
                  </div>
                  <div className="mt-3 grid gap-2 text-sm text-slate-300">
                    {Object.entries(params)
                      .slice(0, 4)
                      .map(([key, value]) => (
                        <div key={key} className="flex items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/80 px-3 py-2">
                          <span className="truncate text-slate-400">{key}</span>
                          <span className="font-mono text-slate-100">{typeof value === "number" ? value.toFixed(3) : String(value)}</span>
                        </div>
                      ))}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_1.1fr]">
        <div className="rounded-2xl border border-slate-700 bg-slate-900/90 p-4">
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Optimization History</p>
            <p className="font-mono text-xs text-slate-400">{history.length} kayit</p>
          </div>
          <div className="mt-4 space-y-3">
            {history.length === 0 ? (
              <div className="rounded-2xl border border-slate-700 bg-slate-950/70 p-4 text-sm text-slate-400">Optimization history henuz bos.</div>
            ) : (
              history.slice().reverse().map((record, index) => (
                <div key={`${record.timestamp ?? index}-${index}`} className="rounded-2xl border border-slate-700 bg-slate-950/70 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-white">{record.optimization_type ?? "optimize"}</p>
                      <p className="mt-1 text-xs text-slate-500">{record.timestamp ? new Date(record.timestamp).toLocaleString("tr-TR") : "timestamp yok"}</p>
                    </div>
                    <p className="font-mono text-sm text-emerald-300">{record.best_score?.toFixed(2) ?? "--"}</p>
                  </div>
                  <div className="mt-3 flex items-center justify-between text-xs text-slate-400">
                    <span>Optimizer {record.optimizer ?? "runtime"}</span>
                    <span>{record.trades_analyzed ?? 0} trade analiz edildi</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="rounded-2xl border border-slate-700 bg-slate-900/90 p-4">
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Recent Trade Feedback</p>
            <p className="font-mono text-xs text-slate-400">{trades.length} trade</p>
          </div>
          <div className="mt-4 space-y-3">
            {trades.length === 0 ? (
              <div className="rounded-2xl border border-slate-700 bg-slate-950/70 p-4 text-sm text-slate-400">Feedback trade history henuz bos.</div>
            ) : (
              trades.slice().reverse().map((trade, index) => (
                <div key={`${trade.timestamp}-${index}`} className="rounded-2xl border border-slate-700 bg-slate-950/70 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-semibold text-white">{trade.is_winning ? "Winning feedback" : "Losing feedback"}</p>
                    <span className={`rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] ${trade.is_winning ? "bg-emerald-500/10 text-emerald-300" : "bg-rose-500/10 text-rose-300"}`}>
                      {trade.is_winning ? "WIN" : "LOSS"}
                    </span>
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-3 text-xs text-slate-400">
                    <div>
                      <p className="uppercase tracking-[0.16em] text-slate-500">PnL</p>
                      <p className={`mt-1 font-mono ${trade.pnl >= 0 ? "text-emerald-300" : "text-rose-300"}`}>{formatSigned(trade.pnl)}</p>
                    </div>
                    <div>
                      <p className="uppercase tracking-[0.16em] text-slate-500">Volatility</p>
                      <p className="mt-1 font-mono text-slate-200">{trade.volatility.toFixed(2)}</p>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {trade.winning_phases.map((phaseId) => (
                      <span key={`w-${trade.timestamp}-${phaseId}`} className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-emerald-300">
                        {phaseNames[String(phaseId)] ?? `P${phaseId}`}
                      </span>
                    ))}
                    {trade.losing_phases.map((phaseId) => (
                      <span key={`l-${trade.timestamp}-${phaseId}`} className="rounded-full border border-rose-500/20 bg-rose-500/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-rose-300">
                        {phaseNames[String(phaseId)] ?? `P${phaseId}`}
                      </span>
                    ))}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};