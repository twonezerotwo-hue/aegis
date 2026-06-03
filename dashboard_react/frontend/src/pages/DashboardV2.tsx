/**
 * DashboardV2 — AEGIS unified dashboard.
 * Tabs: Kontrol | Analiz | Metrikler | Backtest | Paper Trading
 */

import React, { Suspense, lazy } from "react";

import { VadeProvider, useVadeContext } from "../context/VadeContext";
import type { Vade } from "../context/VadeContext";

import { MacroRegimeCommentary } from "../components/macro/MacroRegimeCommentary";
import { AllocationWithTip } from "../components/portfolio/AllocationWithTip";
import { RealEstateDecisionPanel } from "../components/portfolio/RealEstateDecisionPanel";
import { AssetConsensusCard } from "../components/assets/AssetConsensusCard";
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
import { KontrolMerkezi } from "../components/control/KontrolMerkezi";
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
type TabId = "control" | "portfolio" | "metrics" | "backtest" | "paper_trading";

const TABS: { id: TabId; label: string }[] = [
  { id: "control",       label: "Kontrol" },
  { id: "portfolio",     label: "Analiz" },
  { id: "metrics",       label: "Metrikler" },
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

const CONSENSUS_STATUS_STRENGTH: Record<string, number> = {
  UNKNOWN: 0,
  MISSING: 1,
  FALLBACK: 2,
  MOCK: 3,
  PARTIAL_FALLBACK: 4,
  STALE: 5,
  RECENT: 6,
  LIVE: 7,
};

const getConsensusStatusStrength = (consensus: ConsensusResponse | null): number => {
  const status = consensus?.data_status ?? "UNKNOWN";
  return CONSENSUS_STATUS_STRENGTH[status] ?? 0;
};

const getConsensusTimestamp = (consensus: ConsensusResponse | null): string | null =>
  consensus?.last_updated ?? consensus?.timestamp ?? null;

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
  const [activeTab, setActiveTab] = React.useState<TabId>("control");

  // ── Daily P&L / Kill Switch ────────────────────────────────────────────────
  const [dailyPnl, setDailyPnl] = React.useState<{
    realized_pnl: number; trade_count: number;
    kill_switch_threshold: number; kill_switch_active: boolean;
    message: string; date: string;
  } | null>(null);

  React.useEffect(() => {
    const API = import.meta.env.VITE_API_URL || "http://localhost:8502";
    const fetchPnl = () =>
      fetch(`${API}/api/pnl/daily`)
        .then(r => r.json())
        .then(setDailyPnl)
        .catch(() => {});
    fetchPnl();
    const interval = setInterval(fetchPnl, 30_000);
    return () => clearInterval(interval);
  }, []);

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
    setAssetConsensus((cur) => {
      const current = cur.btc.data ?? cur.btc.lastSuccessfulData;
      const incomingStrength = getConsensusStatusStrength(btcConsensusFromSSE);
      const currentStrength = getConsensusStatusStrength(current);
      const currentTs = getConsensusTimestamp(current);
      const incomingTs = getConsensusTimestamp(btcConsensusFromSSE);
      const shouldReplace =
        current === null ||
        (currentStrength <= CONSENSUS_STATUS_STRENGTH.MISSING &&
          incomingStrength > currentStrength) ||
        (currentStrength <= CONSENSUS_STATUS_STRENGTH.MISSING &&
          incomingStrength === currentStrength &&
          (currentTs === null || (incomingTs !== null && incomingTs >= currentTs)));

      if (!shouldReplace) {
        return cur;
      }

      return {
        ...cur,
        btc: {
          data: btcConsensusFromSSE,
          loading: false,
          error: null,
          lastSuccessfulData: btcConsensusFromSSE,
        },
      };
    });
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
            liveStatus={effectiveLiveStatus}
            liveMessage={effectiveLiveMessage}
            alertCount={latestAlert ? 1 : 0}
            killSwitchActive={dailyPnl?.kill_switch_active ?? false}
            dailyPnl={dailyPnl?.realized_pnl ?? null}
            dailyTradeCount={dailyPnl?.trade_count ?? 0}
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

        {/* ── KONTROL MERKEZİ TAB ─────────────────────────────────────────── */}
        {activeTab === "control" && (
          <KontrolMerkezi
            macro={effectiveMacro}
            btcConsensus={assetConsensus.btc.data ?? null}
            dailyPnl={dailyPnl}
            loading={loading && !effectiveMacro}
          />
        )}

        {/* ── ANALİZ TAB (eski Portföy) ─────────────────────────────────── */}
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
          <div className="space-y-4">
            {/* Seçiciler — kompakt */}
            <div className="rounded-2xl border border-slate-700/60 bg-slate-900 px-4 py-3">
              <div className="flex flex-wrap items-center gap-3">
                <SymbolSelector currentSymbol={metricsSymbol} onSymbolChange={setMetricsSymbol} />
                <TimeframeSelector currentTimeframe={metricsTimeframe} onTimeframeChange={setMetricsTimeframe} />
                {metricsLoading && metricsData && (
                  <span className="flex items-center gap-1 text-[10px] text-slate-500">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                    yenileniyor
                  </span>
                )}
              </div>
            </div>

            {metricsLoading && !metricsData ? (
              <SkeletonLoader variant="card" lines={5} />
            ) : metricsData ? (
              <div className={`transition-opacity duration-200 ${metricsLoading ? "opacity-50" : "opacity-100"}`}>

                {/* ── Tek Panel ─────────────────────────────────────────────── */}
                <div className="rounded-2xl border border-slate-700/60 bg-slate-900 p-5 shadow-md">

                  {/* Header: consensus karar + sağlık noktaları */}
                  {(() => {
                    const cons  = metricsData.consensus;
                    const act   = cons?.action ?? "HOLD";
                    const score = ((cons?.weighted_score ?? 0) * 100).toFixed(1);
                    const conf  = ((cons?.confidence ?? 0) * 100).toFixed(0);
                    const actCls = act === "BUY" ? "text-emerald-400 border-emerald-500/40 bg-emerald-500/10"
                                 : act === "SELL" ? "text-rose-400 border-rose-500/40 bg-rose-500/10"
                                 : "text-amber-400 border-amber-500/40 bg-amber-500/10";
                    const actTr = act === "BUY" ? "AL" : act === "SELL" ? "SAT" : "TUT";
                    const svcs  = metricsData.health?.services ?? {};
                    const svcList = [
                      { k: "touche",      label: "T" },
                      { k: "fundamental", label: "F" },
                      { k: "news",        label: "N" },
                      { k: "sentinel",    label: "S" },
                      { k: "quantum",     label: "Q" },
                    ];
                    return (
                      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                        <div className="flex items-center gap-3">
                          <span className={`inline-flex rounded-xl border px-4 py-1.5 text-lg font-extrabold ${actCls}`}>
                            {actTr}
                          </span>
                          <div>
                            <p className="font-mono text-xl font-bold text-white">{score}<span className="text-sm text-slate-500">%</span></p>
                            <p className="text-[9px] text-slate-600">Güven {conf}%</p>
                          </div>
                        </div>
                        {/* Servis sağlık noktaları */}
                        <div className="flex items-center gap-1.5">
                          {svcList.map(({ k, label }) => (
                            <div key={k} className="flex flex-col items-center gap-0.5">
                              <span className={`h-2 w-2 rounded-full ${(svcs as Record<string,string>)[k] === "UP" ? "bg-emerald-400" : "bg-rose-400"}`} title={k} />
                              <span className="font-mono text-[8px] text-slate-700">{label}</span>
                            </div>
                          ))}
                          <span className={`ml-1 text-[9px] font-semibold ${Object.values(svcs).filter(s => s === "UP").length >= 4 ? "text-emerald-400" : "text-amber-400"}`}>
                            {Object.values(svcs).filter(s => s === "UP").length}/{svcList.length} UP
                          </span>
                        </div>
                      </div>
                    );
                  })()}

                  {/* Modül satırları */}
                  <div className="space-y-1">
                    {/* Consensus'a giren modüller */}
                    {(["touche", "fundamental", "news"] as const).map((key) => {
                      const m   = metricsData.metrics[key];
                      const pct = Math.round(m.score * 100);
                      const BAR: Record<string, string> = { touche: "bg-violet-400", fundamental: "bg-sky-400", news: "bg-amber-400" };
                      const NAME: Record<string, string> = { touche: "Touche EQS", fundamental: "Fundamental", news: "Haber" };
                      const sc  = m.score > 0.65 ? "text-emerald-400" : m.score < 0.35 ? "text-rose-400" : "text-slate-300";
                      return (
                        <div key={key} className="group rounded-xl px-3 py-2.5 hover:bg-slate-800/40 transition-colors">
                          <div className="mb-1.5 flex items-center gap-2">
                            <span className="w-20 shrink-0 text-[10px] font-semibold text-slate-400">{NAME[key]}</span>
                            <div className="h-1.5 flex-1 rounded-full bg-slate-700/60">
                              <div className={`h-1.5 rounded-full ${BAR[key]} transition-all duration-500`} style={{ width: `${pct}%` }} />
                            </div>
                            <span className={`w-8 shrink-0 text-right font-mono text-[11px] font-bold ${sc}`}>{pct}</span>
                          </div>
                          <p className="pl-[5.5rem] text-[9px] leading-4 text-slate-600">{m.summary}</p>
                        </div>
                      );
                    })}

                    {/* Ayırıcı */}
                    <div className="my-2 flex items-center gap-2 px-3">
                      <div className="h-px flex-1 bg-slate-800" />
                      <span className="text-[8px] uppercase tracking-wider text-slate-700">arka plan (consensus dışı)</span>
                      <div className="h-px flex-1 bg-slate-800" />
                    </div>

                    {/* Arka plan modülleri */}
                    {(["sentinel", "quantum"] as const).map((key) => {
                      const m   = metricsData.metrics[key];
                      const pct = Math.round(m.score * 100);
                      const BAR: Record<string, string> = { sentinel: "bg-rose-400", quantum: "bg-emerald-400" };
                      const NAME: Record<string, string> = { sentinel: "Sentinel", quantum: "Quantum" };
                      const badge: Record<string, { label: string; cls: string }> = {
                        sentinel: m.score >= 0.55 ? { label: "✓ Düşük Risk", cls: "text-emerald-500" }
                                : m.score >= 0.45 ? { label: "~ Orta Risk",  cls: "text-amber-500"  }
                                : { label: "✗ Yüksek Risk", cls: "text-rose-500" },
                        quantum:  Math.abs(m.score - 0.5) < 0.01
                                ? { label: "~ Veri Yok",     cls: "text-slate-600" }
                                : m.score >= 0.55 ? { label: "✓ Likidite İyi", cls: "text-emerald-500" }
                                : { label: "✗ Düşük Likidite", cls: "text-rose-500" },
                      };
                      return (
                        <div key={key} className="rounded-xl px-3 py-2 opacity-60 hover:opacity-90 transition-opacity">
                          <div className="flex items-center gap-2">
                            <span className="w-20 shrink-0 text-[10px] text-slate-500">{NAME[key]}</span>
                            <div className="h-1 flex-1 rounded-full bg-slate-800">
                              <div className={`h-1 rounded-full ${BAR[key]} opacity-50`} style={{ width: `${pct}%` }} />
                            </div>
                            <span className="w-8 shrink-0 text-right font-mono text-[10px] text-slate-600">{pct}</span>
                            <span className={`text-[9px] font-semibold ${badge[key].cls}`}>{badge[key].label}</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {/* Footer: son güncelleme */}
                  <p className="mt-2 text-right font-mono text-[9px] text-slate-700">
                    {metricsData.last_updated ?? metricsData.timestamp ?? "—"}
                  </p>
                </div>

                {/* ── Modül Açıklamaları ─────────────────────────────────── */}
                {(() => {
                  const [open, setOpen] = React.useState(false);
                  const modules = [
                    {
                      key: "touche",
                      name: "Touche EQS",
                      color: "border-violet-500/30",
                      dot: "bg-violet-400",
                      lines: [
                        "Varlığın fiyat hareketini teknik analiz yöntemleriyle (EMA, MACD, RSI, Bollinger, Swing, FVG) inceler; alım veya satım baskısının yönünü ölçer.",
                        "Seçili timeframe'in sinyalini üst timeframe'lerle ağırlıklı oylamaya sokar — tüm TF'ler aynı yönde ise skor güçlenir, çelişki varsa ortaya çekilir.",
                        "Consensus sinyaline %50 ağırlıkla en doğrudan katkıyı yapar; piyasa yapısı, diverjans, likidite süpürmesi ve CMF hacim teyidini birleştirir.",
                      ],
                    },
                    {
                      key: "fundamental",
                      name: "Fundamental Score",
                      color: "border-sky-500/30",
                      dot: "bg-sky-400",
                      lines: [
                        "Bitcoin zinciri üzerindeki on-chain metrikleri (MVRV Z-Score ve NUPL) kullanarak piyasanın gerçek değerleme durumunu ölçer.",
                        "MVRV Z < 1 = ucuz (birikim), 1–3 = makul, > 3.5 = pahalı (dağıtım); NUPL ise sahiplerin ortalama kâr/zarar oranını gösterir.",
                        "Kısa TF için birikim bölgesi analizi (momentum), uzun TF için MVRV/NUPL mutlak seviyeleri ağırlıklıdır. Şu an Glassnode key olmadığından simüle veri kullanılmaktadır.",
                      ],
                    },
                    {
                      key: "news",
                      name: "Haber Duygusu",
                      color: "border-amber-500/30",
                      dot: "bg-amber-400",
                      lines: [
                        "SEC, Fed, CFTC, PBOC, kripto borsaları ve küresel finans medyasından 20+ RSS kaynağındaki haberleri NLP ile analiz eder.",
                        "Her haberın kripto piyasasına potansiyel etkisini, düzenleyici baskı/destek yönünü ve güven skorunu değerlendirerek toplu bir duygu puanı üretir.",
                        "Kısa TF'de güncel haber akışı tam ağırlıkla etkilerken, uzun vadeli pozisyonlarda haberin önemi azalıp temel veriler öne çıkar (1h=%92 etki, 1w=%45).",
                      ],
                    },
                    {
                      key: "sentinel",
                      name: "Sentinel (arka plan)",
                      color: "border-rose-500/20",
                      dot: "bg-rose-400",
                      lines: [
                        "VIX (volatilite korku endeksi), DXY (dolar endeksi), US10Y (tahvil faizi), HYG (kredi sağlığı) ve BTC funding rate gibi makro göstergeleri izler.",
                        "Bu göstergelerin bütünsel durumuna göre piyasanın rejimini (RISK_ON/OFF/NORMALIZATION) ve anlık olay riskini hesaplar.",
                        "Consensus sinyaline doğrudan girmez; bunun yerine kill switch kararlarına ve portföy dağılımındaki rejim overlay'ine girdi sağlar.",
                      ],
                    },
                    {
                      key: "quantum",
                      name: "Quantum (arka plan)",
                      color: "border-emerald-500/20",
                      dot: "bg-emerald-400",
                      lines: [
                        "Emir defteri derinliği, bid/ask dengesizliği ve slippage (kayma) gibi piyasa mikroyapısını ölçerek işlem kalitesini değerlendirir.",
                        "Yüksek skor: büyük bir emri fiyatı bozmadan çalıştırmak mümkün; düşük skor: likidite yetersiz, emirleri parçala veya bölgeyi değiştir.",
                        "Şu an gerçek veri bağlantısı bulunmadığından nötr (0.50) sabit değer göstermektedir; Binance order book entegrasyonu planlanmaktadır.",
                      ],
                    },
                  ];
                  return (
                    <div className="rounded-2xl border border-slate-800 bg-slate-950/40">
                      <button
                        type="button"
                        onClick={() => setOpen(v => !v)}
                        className="flex w-full items-center justify-between px-4 py-3 text-left text-[10px] font-semibold uppercase tracking-widest text-slate-600 transition-colors hover:text-slate-400"
                      >
                        <span>Modüller Ne Yapar?</span>
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                          className={`h-3.5 w-3.5 transition-transform duration-200 ${open ? "rotate-180" : ""}`}>
                          <polyline points="6 9 12 15 18 9" />
                        </svg>
                      </button>
                      {open && (
                        <div className="grid gap-3 px-4 pb-4 sm:grid-cols-2 lg:grid-cols-3">
                          {modules.map(mod => (
                            <div key={mod.key} className={`rounded-xl border ${mod.color} bg-slate-900/60 p-3`}>
                              <div className="mb-2 flex items-center gap-2">
                                <span className={`h-2 w-2 shrink-0 rounded-full ${mod.dot}`} />
                                <p className="text-[10px] font-bold text-slate-300">{mod.name}</p>
                              </div>
                              <ol className="space-y-1.5 list-none">
                                {mod.lines.map((line, i) => (
                                  <li key={i} className="flex gap-1.5">
                                    <span className="shrink-0 font-mono text-[8px] text-slate-700 mt-0.5">{i+1}.</span>
                                    <p className="text-[10px] leading-4 text-slate-500">{line}</p>
                                  </li>
                                ))}
                              </ol>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })()}
              </div>
            ) : (
              <div className="rounded-2xl border border-slate-700/60 bg-slate-900 p-10 text-center text-sm text-slate-500">
                Backend bağlantısı bekleniyor — http://localhost:8502
              </div>
            )}
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
