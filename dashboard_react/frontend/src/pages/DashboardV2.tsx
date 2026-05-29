/**
 * DashboardV2 — AEGIS unified dashboard.
 * Tabs: Portföy | Metrikler | AI Analiz | Backtest | Paper Trading
 */

import React, { Suspense, lazy } from "react";

import { VadeProvider, useVadeContext } from "../context/VadeContext";
import type { Vade } from "../context/VadeContext";

import { MacroRegimeCommentary } from "../components/macro/MacroRegimeCommentary";
import { AllocationWithTip } from "../components/portfolio/AllocationWithTip";
import { RealEstateDecisionPanel } from "../components/portfolio/RealEstateDecisionPanel";
import { AssetConsensusCard } from "../components/assets/AssetConsensusCard";
import { CrossAlignmentPanel } from "../components/validation/CrossAlignmentPanel";
import type { AssetResult } from "../components/validation/CrossAlignmentPanel";
import { GlobalHeader } from "../components/layout/GlobalHeader";
import { Toast } from "../components/layout/Toast";
import type { ToastItem, ToastTone } from "../components/layout/Toast";
import { ErrorBoundary } from "../components/ui/ErrorBoundary";
import { SkeletonLoader } from "../components/ui/SkeletonLoader";
import { DataSyncMonitor } from "../components/debug/DataSyncMonitor";

// V1 components
import { MetricCard } from "../components/MetricCard";
import { ConsensusCard } from "../components/ConsensusCard";
import { SystemStatus } from "../components/SystemStatus";
import { AlertBanner } from "../components/AlertBanner";
import AIAnalysisCard from "../components/AIAnalysisCard";
import { SymbolSelector } from "../components/SymbolSelector";
import { TimeframeSelector } from "../components/TimeframeSelector";
import { useMetrics } from "../hooks/useMetrics";

import { useRealTimeFeed } from "../hooks/useRealTimeFeed";
import { fetchConsensus, fetchMacro } from "../services/apiV2";
import type { ConsensusResponse, MacroViewModel } from "../types/dashboardV2";

// Lazy-load heavy tab pages
const Backtest = lazy(() => import("./Backtest").then((m) => ({ default: m.default ?? m })));
const PaperTrading = lazy(() => import("./PaperTrading").then((m) => ({ default: m.default ?? m })));

// ── Tab definitions ────────────────────────────────────────────────────────────
type TabId = "portfolio" | "metrics" | "ai_analysis" | "backtest" | "paper_trading";

const TABS: { id: TabId; label: string }[] = [
  { id: "portfolio",     label: "Portföy" },
  { id: "metrics",       label: "Metrikler" },
  { id: "ai_analysis",   label: "AI Analiz" },
  { id: "backtest",      label: "Backtest" },
  { id: "paper_trading", label: "Paper Trading" },
];

// ── Asset catalogue ───────────────────────────────────────────────────────────
const ASSETS = [
  { key: "gold",      symbol: "XAU/USDT",  label: "XAU — Altın",   tradeable: true  },
  { key: "btc",       symbol: "BTC/USDT",  label: "BTC — Bitcoin", tradeable: true  },
  { key: "commodity", symbol: "XAG/USDT",  label: "XAG — Emtia",  tradeable: true  },
  { key: "bond",      symbol: "BOND/USDT", label: "BOND — Tahvil", tradeable: false },
  { key: "cash",      symbol: "CASH/USDT", label: "CASH — Nakit",  tradeable: false },
] as const;

type AssetKey = (typeof ASSETS)[number]["key"];

interface AssetState {
  data: ConsensusResponse | null;
  loading: boolean;
  error: string | null;
  lastSuccessfulData: ConsensusResponse | null;
}

const INITIAL_ASSET_STATE: Record<AssetKey, AssetState> = {
  gold:      { data: null, loading: true, error: null, lastSuccessfulData: null },
  btc:       { data: null, loading: true, error: null, lastSuccessfulData: null },
  commodity: { data: null, loading: true, error: null, lastSuccessfulData: null },
  bond:      { data: null, loading: true, error: null, lastSuccessfulData: null },
  cash:      { data: null, loading: true, error: null, lastSuccessfulData: null },
};

const VADE_OPTIONS: { value: Vade; label: string; sub: string }[] = [
  { value: "short",  label: "Kısa",  sub: "1–4 Hafta" },
  { value: "medium", label: "Orta",  sub: "1–3 Ay" },
  { value: "long",   label: "Uzun",  sub: "6 Ay+" },
];

const TabFallback: React.FC = () => (
  <div className="flex items-center justify-center py-20">
    <div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-700 border-t-emerald-400" />
  </div>
);

// ── Inner (needs VadeContext) ─────────────────────────────────────────────────
const DashboardV2Inner: React.FC = () => {
  const {
    vade,
    setHorizon,
    timeframe,
    tfLabel,
    windowLabel,
    kellyLabel,
    abortController,
  } = useVadeContext();

  // ── Tab state ──────────────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = React.useState<TabId>("portfolio");

  // ── Metrics tab state (independent symbol/TF) ─────────────────────────────
  const [metricsSymbol, setMetricsSymbol] = React.useState("BTC/USDT");
  const [metricsTimeframe, setMetricsTimeframe] = React.useState("1h");
  const metricsRefreshMs = ["4h", "1d", "1w", "1month"].includes(metricsTimeframe) ? 60000 : 10000;
  const { data: metricsData, loading: metricsLoading } = useMetrics(
    metricsSymbol,
    metricsTimeframe,
    metricsRefreshMs
  );

  // ── Toast ──────────────────────────────────────────────────────────────────
  const [toasts, setToasts] = React.useState<ToastItem[]>([]);
  const toastIdRef = React.useRef(0);
  const lastAlertTsRef = React.useRef<string>("");

  // ── SSE feed ───────────────────────────────────────────────────────────────
  const {
    macro,
    consensus: btcConsensusFromSSE,
    loading,
    error,
    lastSuccessfulUpdate,
    connectionStatus,
    connectionMessage,
    systemHealth,
    latestAlert,
  } = useRealTimeFeed("BTC/USDT", timeframe, "7d", vade);

  // ── Per-asset consensus ────────────────────────────────────────────────────
  const [assetConsensus, setAssetConsensus] = React.useState<Record<AssetKey, AssetState>>(
    INITIAL_ASSET_STATE
  );

  const [macroHorizon, setMacroHorizon] = React.useState<MacroViewModel | null>(null);
  const [macroFetchError, setMacroFetchError] = React.useState<string | null>(null);

  const pushToast = React.useCallback(
    (opts: { title: string; message: string; tone: ToastTone }) => {
      toastIdRef.current += 1;
      setToasts((cur) => [...cur, { id: toastIdRef.current, ...opts }]);
    },
    []
  );

  React.useEffect(() => {
    if (!latestAlert || latestAlert.ts === lastAlertTsRef.current) return;
    lastAlertTsRef.current = latestAlert.ts;
    pushToast({
      title:   latestAlert.type.replace(/_/g, " "),
      message: latestAlert.message,
      tone:
        latestAlert.severity === "critical" ? "error" :
        latestAlert.severity === "warning"  ? "warning" : "info",
    });
  }, [latestAlert, pushToast]);

  React.useEffect(() => {
    if (connectionStatus !== "fallback") return;
    pushToast({
      title:   "Bağlantı kesik",
      message: connectionMessage ?? "Manuel senkronizasyon aktif.",
      tone:    "warning",
    });
  }, [connectionStatus, connectionMessage, pushToast]);

  // ── Sentinel high-risk toast (fires once per threshold crossing) ───────────
  const sentinelWarnedRef = React.useRef(false);
  React.useEffect(() => {
    if (!metricsData) return;
    const score = metricsData.metrics.sentinel.score;
    if (score < 0.45 && !sentinelWarnedRef.current) {
      sentinelWarnedRef.current = true;
      pushToast({
        title:   "Sentinel — Yüksek Olay Riski",
        message: `Makro risk skoru kritik eşiği aştı (${Math.round((1 - score) * 100)}%). Pozisyon boyutlandırmasına dikkat.`,
        tone:    "warning",
      });
    } else if (score >= 0.45) {
      sentinelWarnedRef.current = false; // reset so next crossing fires again
    }
  }, [metricsData, pushToast]);

  // ── Horizon-driven batch fetch ─────────────────────────────────────────────
  React.useEffect(() => {
    const signal = abortController.signal;

    setAssetConsensus((current) =>
      Object.fromEntries(
        ASSETS.map(({ key }) => [
          key,
          {
            data: null,
            loading: true,
            error: null,
            lastSuccessfulData: current[key].lastSuccessfulData,
          },
        ])
      ) as Record<AssetKey, AssetState>
    );
    setMacroHorizon(null);
    setMacroFetchError(null);

    fetchMacro(vade, { signal })
      .then((data) => {
        if (signal.aborted) return;
        setMacroHorizon(data);
        setMacroFetchError(null);
      })
      .catch((err: unknown) => {
        if (signal.aborted) return;
        const msg = err instanceof Error ? err.message : "Makro veri alınamadı";
        setMacroFetchError(msg);
      });

    for (const { key, symbol } of ASSETS) {
      fetchConsensus(symbol, timeframe, { signal }, vade)
        .then((data) => {
          if (signal.aborted) return;
          setAssetConsensus((cur) => ({
            ...cur,
            [key]: { data, loading: false, error: null, lastSuccessfulData: data },
          }));
        })
        .catch((err: unknown) => {
          if (signal.aborted) return;
          const msg = err instanceof Error ? err.message : "Veri alınamadı";
          setAssetConsensus((cur) => ({
            ...cur,
            [key]: {
              data: null,
              loading: false,
              error: msg,
              lastSuccessfulData: cur[key].lastSuccessfulData,
            },
          }));
        });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vade, abortController]);

  // BTC SSE override
  React.useEffect(() => {
    if (!btcConsensusFromSSE) return;
    setAssetConsensus((cur) => ({
      ...cur,
      btc: {
        data: btcConsensusFromSSE,
        loading: false,
        error: null,
        lastSuccessfulData: btcConsensusFromSSE,
      },
    }));
  }, [btcConsensusFromSSE]);

  const handleRefetch = React.useCallback(
    async (symbol: string) => {
      const target = ASSETS.find((a) => a.symbol === symbol);
      if (!target) return;
      setAssetConsensus((cur) => ({
        ...cur,
        [target.key]: { data: null, loading: true, error: null, lastSuccessfulData: cur[target.key].lastSuccessfulData },
      }));
      try {
        const data = await fetchConsensus(symbol, timeframe, { signal: abortController.signal }, vade);
        setAssetConsensus((cur) => ({
          ...cur,
          [target.key]: { data, loading: false, error: null, lastSuccessfulData: data },
        }));
      } catch (err: unknown) {
        if (abortController.signal.aborted) return;
        const msg = err instanceof Error ? err.message : "Veri alınamadı";
        setAssetConsensus((cur) => ({
          ...cur,
          [target.key]: { data: null, loading: false, error: msg, lastSuccessfulData: cur[target.key].lastSuccessfulData },
        }));
      }
    },
    [abortController, timeframe, vade]
  );

  // Derived values
  const effectiveMacro = macroHorizon ?? macro;
  const macroTimestamp = effectiveMacro?.last_updated ?? effectiveMacro?.timestamp ?? null;
  const macroNeedsVisibilityWarning = Boolean(
    effectiveMacro &&
      (effectiveMacro.data_status !== "LIVE" ||
        effectiveMacro.verified !== true ||
        effectiveMacro.live !== true)
  );
  const effectiveLiveStatus = macroNeedsVisibilityWarning ? "fallback" : connectionStatus;
  const effectiveLiveMessage = macroNeedsVisibilityWarning
    ? effectiveMacro?.warning ?? "Macro data is not verified live data."
    : connectionStatus === "live" ? null : connectionMessage ?? null;

  const regime        = effectiveMacro?.regime ?? "WAITING";
  const derivedHealth = error
    ? "DEGRADED"
    : !effectiveMacro
    ? "AWAITING DATA"
    : effectiveMacro.status.toUpperCase() === "OK"
    ? "HEALTHY"
    : effectiveMacro.status.toUpperCase();

  const anyAssetReady = Object.values(assetConsensus).some((s) => !s.loading);

  const alignmentAssets = React.useMemo<Record<string, AssetResult>>(() => {
    const result: Record<string, AssetResult> = {};
    for (const { key, label } of ASSETS) {
      result[key] = { label, consensus: assetConsensus[key].data };
    }
    return result;
  }, [assetConsensus]);

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-slate-950 pb-6 text-slate-100">
      <Toast
        toasts={toasts}
        onDismiss={(id) => setToasts((cur) => cur.filter((t) => t.id !== id))}
      />

      <div className="mx-auto max-w-screen-2xl space-y-4 px-4 py-4">

        {/* GlobalHeader */}
        <ErrorBoundary fallback="Header">
          <GlobalHeader
            regime={regime}
            systemHealth={systemHealth || derivedHealth}
            lastUpdated={effectiveMacro ? macroTimestamp : lastSuccessfulUpdate ?? null}
            currentMode="v2"
            liveStatus={effectiveLiveStatus}
            liveMessage={effectiveLiveMessage}
            alertCount={latestAlert ? 1 : 0}
          />
        </ErrorBoundary>

        {/* ── Tab Bar ──────────────────────────────────────────────────────── */}
        <div className="rounded-2xl border border-slate-700/60 bg-slate-900 px-2 py-1.5">
          <div className="flex gap-1">
            {TABS.map(({ id, label }) => (
              <button
                key={id}
                type="button"
                onClick={() => setActiveTab(id)}
                aria-pressed={activeTab === id}
                className={`flex-1 rounded-xl px-3 py-2 text-xs font-semibold uppercase tracking-wider transition-all duration-200 ${
                  activeTab === id
                    ? "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-400/40"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* ── PORTFÖY TAB ───────────────────────────────────────────────────── */}
        {activeTab === "portfolio" && (
          <>
            {/* Vade seçimi */}
            <div className="rounded-2xl border border-slate-700/60 bg-slate-900 px-5 py-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">
                    Yatırım Vadesi
                  </p>
                  <p className="mt-0.5 text-[11px] font-mono text-emerald-400/80">
                    {tfLabel}&nbsp;·&nbsp;{windowLabel}&nbsp;·&nbsp;{kellyLabel}
                  </p>
                </div>
                <div className="flex gap-2" role="group" aria-label="Vade seçimi">
                  {VADE_OPTIONS.map(({ value, label, sub }) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setHorizon(value)}
                      aria-pressed={vade === value}
                      className={`flex flex-col items-center rounded-xl border px-4 py-2.5 text-xs
                        font-semibold uppercase tracking-wider transition-all duration-200
                        ${
                          vade === value
                            ? "border-emerald-400/60 bg-emerald-500/10 text-emerald-300 ring-2 ring-emerald-400/30"
                            : "border-slate-700 bg-slate-800 text-slate-400 hover:border-slate-600 hover:text-white"
                        }`}
                    >
                      <span>{label}</span>
                      <span className="mt-0.5 text-[9px] font-normal normal-case tracking-normal text-slate-500">
                        {sub}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Makro Rejim */}
            <ErrorBoundary fallback="Makro Rejim">
              {loading && !effectiveMacro ? (
                <SkeletonLoader variant="card" lines={3} />
              ) : effectiveMacro ? (
                <MacroRegimeCommentary macro={effectiveMacro} />
              ) : (
                <div className="rounded-2xl border border-slate-700/60 bg-slate-900 p-5 text-sm text-slate-500">
                  Makro veri bekleniyor…
                </div>
              )}
            </ErrorBoundary>

            {/* Portföy Dağılımı */}
            <ErrorBoundary fallback="Portföy Dağılımı">
              {loading && !effectiveMacro ? (
                <SkeletonLoader variant="bar-chart" lines={5} />
              ) : effectiveMacro ? (
                <AllocationWithTip macro={effectiveMacro} vade={vade} />
              ) : null}
            </ErrorBoundary>

            {/* Varlık Bazlı Konsensüs */}
            <ErrorBoundary fallback="Varlık Kartları">
              <div>
                <p className="mb-2 px-1 text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">
                  Varlık Bazlı Konsensüs&nbsp;·&nbsp;
                  <span className="font-mono text-emerald-500/80">{tfLabel}</span>
                </p>
                <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
                  {ASSETS.map(({ key, label, symbol, tradeable }) => (
                    <AssetConsensusCard
                      key={key}
                      assetKey={key}
                      symbol={symbol}
                      assetLabel={label}
                      tradeable={tradeable}
                      consensus={assetConsensus[key].data}
                      lastSuccessfulData={assetConsensus[key].lastSuccessfulData}
                      loading={assetConsensus[key].loading}
                      error={assetConsensus[key].error}
                      onRefetch={handleRefetch}
                    />
                  ))}
                </div>
              </div>
            </ErrorBoundary>

            {/* Cross-Validasyon */}
            {effectiveMacro && anyAssetReady && (
              <ErrorBoundary fallback="Cross-Validasyon">
                <CrossAlignmentPanel
                  macro={effectiveMacro}
                  assets={alignmentAssets}
                  vade={vade}
                />
              </ErrorBoundary>
            )}

            {/* Real Estate Decision Layer — bottom of portfolio tab */}
            <ErrorBoundary fallback="Gayrimenkul Karar Paneli">
              <RealEstateDecisionPanel
                decision={effectiveMacro?.real_estate_decision}
              />
            </ErrorBoundary>

            {error && (
              <div className="rounded-2xl border border-amber-500/30 bg-amber-500/5 p-4 text-xs text-amber-200">
                <span className="font-semibold">Canlı veri degraded:</span>{" "}
                Son bilinen snapshot ile çalışılıyor.&nbsp;{error}
              </div>
            )}
          </>
        )}

        {/* ── METRİKLER TAB ─────────────────────────────────────────────────── */}
        {activeTab === "metrics" && (
          <div className="space-y-6">
            {/* Symbol + Timeframe selectors */}
            <div className="rounded-2xl border border-slate-700/60 bg-slate-900 px-5 py-4">
              <div className="flex flex-wrap items-center gap-4">
                <SymbolSelector
                  currentSymbol={metricsSymbol}
                  onSymbolChange={setMetricsSymbol}
                />
                <TimeframeSelector
                  currentTimeframe={metricsTimeframe}
                  onTimeframeChange={setMetricsTimeframe}
                />
                <div className="flex items-center gap-2">
                  <span className="text-xs text-slate-500">
                    Her {metricsRefreshMs / 1000}s güncellenir
                  </span>
                  {metricsLoading && metricsData && (
                    <span className="flex items-center gap-1 text-[10px] text-slate-500">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                      yenileniyor
                    </span>
                  )}
                </div>
              </div>
            </div>

            {metricsLoading && !metricsData ? (
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {Array.from({ length: 3 }).map((_, i) => (
                  <SkeletonLoader key={i} variant="stat" />
                ))}
              </div>
            ) : metricsData ? (
              <>
                <AlertBanner data={metricsData} />

                {/* Only Touche / Fundamental / News enter the consensus —
                    Sentinel and Quantum are background-only risk filters. */}
                <div className={`grid gap-4 md:grid-cols-2 lg:grid-cols-3 transition-opacity duration-200 ${metricsLoading ? "opacity-50" : "opacity-100"}`}>
                  {(["touche", "fundamental", "news"] as const).map((key) => (
                    <MetricCard key={key} metric={metricsData.metrics[key]} />
                  ))}
                </div>

                {/* Sentinel high-risk inline notice (non-alarming) */}
                {metricsData.metrics.sentinel.score < 0.45 && (
                  <div className="flex items-start gap-2 rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-3">
                    <span className="mt-0.5 shrink-0 text-amber-400 text-sm">⚠</span>
                    <div>
                      <p className="text-[11px] font-semibold text-amber-300">Sentinel — Yüksek Olay Riski</p>
                      <p className="text-[10px] text-amber-200/70 mt-0.5">
                        {metricsData.metrics.sentinel.summary ?? "Makro olay riski eşiğin üzerinde — pozisyon boyutlandırmasına dikkat."}
                      </p>
                    </div>
                  </div>
                )}

                <div className="grid gap-4 lg:grid-cols-3">
                  <ConsensusCard data={metricsData.consensus} />
                  <SystemStatus
                    health={metricsData.health}
                    sentinelScore={metricsData.metrics.sentinel.score}
                    quantumScore={metricsData.metrics.quantum.score}
                  />
                </div>

                <p className="text-center text-xs text-slate-600">
                  Son güncelleme:{" "}
                  {metricsData.last_updated ?? metricsData.timestamp ?? "—"}
                </p>
              </>
            ) : (
              <div className="rounded-2xl border border-slate-700/60 bg-slate-900 p-10 text-center text-sm text-slate-500">
                Backend bağlantısı bekleniyor — http://localhost:8502
              </div>
            )}
          </div>
        )}

        {/* ── AI ANALİZ TAB ─────────────────────────────────────────────────── */}
        {activeTab === "ai_analysis" && (
          <div className="space-y-4">
            <div className="rounded-2xl border border-slate-700/60 bg-slate-900 px-5 py-4">
              <div className="flex flex-wrap items-center gap-4">
                <SymbolSelector
                  currentSymbol={metricsSymbol}
                  onSymbolChange={setMetricsSymbol}
                />
                <TimeframeSelector
                  currentTimeframe={metricsTimeframe}
                  onTimeframeChange={setMetricsTimeframe}
                />
              </div>
            </div>
            <AIAnalysisCard symbol={metricsSymbol} timeframe={metricsTimeframe} />
          </div>
        )}

        {/* ── BACKTEST TAB ──────────────────────────────────────────────────── */}
        {activeTab === "backtest" && (
          <Suspense fallback={<TabFallback />}>
            <Backtest />
          </Suspense>
        )}

        {/* ── PAPER TRADING TAB ─────────────────────────────────────────────── */}
        {activeTab === "paper_trading" && (
          <Suspense fallback={<TabFallback />}>
            <PaperTrading />
          </Suspense>
        )}

      </div>
      <DataSyncMonitor />
    </div>
  );
};

// Outer wrapper — provides VadeContext
export const DashboardV2: React.FC = () => (
  <VadeProvider>
    <DashboardV2Inner />
  </VadeProvider>
);
