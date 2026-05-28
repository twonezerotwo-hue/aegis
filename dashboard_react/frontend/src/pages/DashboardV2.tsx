/**
 * src/pages/DashboardV2.tsx
 * AEGIS v7.1 — Horizon-Driven Dynamic Pipeline.
 * Vade seçimi → AbortController abort → paralel fetch → dinamik label güncelleme.
 * Mevcut SSE feed (useRealTimeFeed) ve routing yapısı korunmuştur.
 */

import React from "react";

import { VadeProvider, useVadeContext } from "../context/VadeContext";
import type { Vade } from "../context/VadeContext";

import { MacroRegimeCommentary } from "../components/macro/MacroRegimeCommentary";
import { AllocationWithTip } from "../components/portfolio/AllocationWithTip";
import { AssetConsensusCard } from "../components/assets/AssetConsensusCard";
import { CrossAlignmentPanel } from "../components/validation/CrossAlignmentPanel";
import type { AssetResult } from "../components/validation/CrossAlignmentPanel";
import { GlobalHeader } from "../components/layout/GlobalHeader";
import { Toast } from "../components/layout/Toast";
import type { ToastItem, ToastTone } from "../components/layout/Toast";
import { ErrorBoundary } from "../components/ui/ErrorBoundary";
import { DataStatusBadge } from "../components/ui/DataStatusBadge";
import { SkeletonLoader } from "../components/ui/SkeletonLoader";
import { DataSyncMonitor } from "../components/debug/DataSyncMonitor";

import { useRealTimeFeed } from "../hooks/useRealTimeFeed";
import { fetchConsensus, fetchMacro } from "../services/apiV2";
import type { ConsensusResponse, MacroViewModel } from "../types/dashboardV2";

// ── Asset catalogue ───────────────────────────────────────────────────────────
const ASSETS = [
  { key: "gold",      symbol: "XAU/USDT",  label: "XAU — Altın" },
  { key: "btc",       symbol: "BTC/USDT",  label: "BTC — Bitcoin" },
  { key: "commodity", symbol: "XAG/USDT",  label: "XAG — Emtia" },
  { key: "bond",      symbol: "BOND/USDT", label: "BOND — Tahvil" },
  { key: "cash",      symbol: "CASH/USDT", label: "CASH — Nakit" },
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

// ── Vade toggle options ───────────────────────────────────────────────────────
const VADE_OPTIONS: { value: Vade; label: string; sub: string }[] = [
  { value: "short",  label: "Kısa",  sub: "1–4 Hafta" },
  { value: "medium", label: "Orta",  sub: "1–3 Ay" },
  { value: "long",   label: "Uzun",  sub: "6 Ay+" },
];

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

  const [toasts, setToasts] = React.useState<ToastItem[]>([]);
  const toastIdRef = React.useRef(0);
  const lastAlertTsRef = React.useRef<string>("");

  // SSE feed (macro + BTC consensus from live stream)
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

  // Per-asset consensus — re-fetched whenever horizon changes
  const [assetConsensus, setAssetConsensus] = React.useState<Record<AssetKey, AssetState>>(
    INITIAL_ASSET_STATE
  );

  // Horizon-specific macro — overrides SSE macro when available
  const [macroHorizon, setMacroHorizon] = React.useState<MacroViewModel | null>(null);
  const [macroFetchError, setMacroFetchError] = React.useState<string | null>(null);

  const pushToast = React.useCallback(
    (opts: { title: string; message: string; tone: ToastTone }) => {
      toastIdRef.current += 1;
      setToasts((cur) => [...cur, { id: toastIdRef.current, ...opts }]);
    },
    []
  );

  // SSE alert → toast
  React.useEffect(() => {
    if (!latestAlert || latestAlert.ts === lastAlertTsRef.current) return;
    lastAlertTsRef.current = latestAlert.ts;
    pushToast({
      title:   latestAlert.type.replace(/_/g, " "),
      message: latestAlert.message,
      tone:
        latestAlert.severity === "critical" ? "error"   :
        latestAlert.severity === "warning"  ? "warning" : "info",
    });
  }, [latestAlert, pushToast]);

  // Connectivity toast
  React.useEffect(() => {
    if (connectionStatus !== "fallback") return;
    pushToast({
      title:   "Bağlantı kesik",
      message: connectionMessage ?? "Manuel senkronizasyon aktif.",
      tone:    "warning",
    });
  }, [connectionStatus, connectionMessage, pushToast]);

  // ── Horizon-driven batch fetch ────────────────────────────────────────────
  // Deps: [vade, abortController] — both change atomically via setHorizon().
  // abortController.signal already aborted when this effect re-runs, so
  // in-flight requests from the previous horizon are cancelled automatically.
  React.useEffect(() => {
    const signal = abortController.signal;

    // 🐛 DEBUG: Horizon değişimi logu
    console.group('[DashboardV2] Horizon State Changed');
    console.log('  Seçili Vade:', vade);
    console.log('  TF Label:', tfLabel);
    console.log('  Window:', windowLabel);
    console.log('  Kelly:', kellyLabel);
    console.groupEnd();

    // Reset all to loading state immediately while preserving the last successful payload.
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

    // ── Macro re-fetch for this horizon ──────────────────────────────────────
    console.log('[DashboardV2] Horizon Changed → Fetching Macro', vade);
    fetchMacro(vade, { signal })
      .then((data) => {
        if (signal.aborted) return;
        setMacroHorizon(data);
        setMacroFetchError(null);
        console.log('[DashboardV2] Macro updated for horizon', vade, data.regime);
      })
      .catch((err: unknown) => {
        if (signal.aborted) return;
        const msg = err instanceof Error ? err.message : "Makro veri alinamadi";
        setMacroFetchError(msg);
        console.warn('[DashboardV2] fetchMacro failed, SSE fallback active:', msg);
      });

    // Fetch each asset independently — failures are isolated
    for (const { key, symbol } of ASSETS) {
      // 🐛 DEBUG: Fetch çağrısı logu
      console.log('[DashboardV2] Calling fetchConsensus:', {
        symbol,
        timeframe,
        horizon: vade,
        signalStatus: signal.aborted ? 'aborted' : 'active',
      });

      fetchConsensus(symbol, timeframe, { signal }, vade)
        .then((data) => {
          if (signal.aborted) return;
          // 🐛 DEBUG: Gelen veri logu
          console.log(`[DashboardV2] fetchConsensus result [${symbol}]:`, {
            action: data.action,
            confidence: data.confidence,
            horizon_applied: (data as unknown as Record<string, unknown>).horizon_applied ?? vade,
          });
          setAssetConsensus((cur) => ({
            ...cur,
            [key]: { data, loading: false, error: null, lastSuccessfulData: data },
          }));
        })
        .catch((err: unknown) => {
          if (signal.aborted) return;
          const msg = err instanceof Error ? err.message : "Veri alınamadı";
          console.warn(`[DashboardV2] fetchConsensus error [${symbol}]:`, msg);
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

  // BTC card: prefer live SSE consensus (fresher) over batch fetch
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

  // ── Retry butonu parent seviyesinde gercek refetch tetikler ──────────────
  const handleRefetch = React.useCallback(
    async (symbol: string) => {
      const target = ASSETS.find((asset) => asset.symbol === symbol);
      if (!target) return;

      setAssetConsensus((cur) => ({
        ...cur,
        [target.key]: {
          data: null,
          loading: true,
          error: null,
          lastSuccessfulData: cur[target.key].lastSuccessfulData,
        },
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
          [target.key]: {
            data: null,
            loading: false,
            error: msg,
            lastSuccessfulData: cur[target.key].lastSuccessfulData,
          },
        }));
      }
    },
    [abortController, timeframe, vade]
  );

  // ── aegis:horizon-changed event listener (debug / forced trigger) ───────────
  React.useEffect(() => {
    const handler = () =>
      console.log(`[DashboardV2] Horizon event received: ${vade}`);
    window.addEventListener("aegis:horizon-changed", handler);
    return () => window.removeEventListener("aegis:horizon-changed", handler);
  }, [vade]);

  // Derived values
  // Prefer horizon-specific macro (re-fetched on vade change) over SSE macro
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
    : connectionStatus === "live"
      ? null
      : connectionMessage ?? null;
  const sseSelectionMismatch = Boolean(
    btcConsensusFromSSE &&
      (btcConsensusFromSSE.symbol !== "BTC/USDT" || btcConsensusFromSSE.timeframe !== timeframe)
  );

  const regime        = effectiveMacro?.regime ?? "WAITING";
  const derivedHealth = error
    ? "DEGRADED"
    : !effectiveMacro
    ? "AWAITING DATA"
    : effectiveMacro.status.toUpperCase() === "OK"
    ? "HEALTHY"
    : effectiveMacro.status.toUpperCase();

  const anyAssetReady = Object.values(assetConsensus).some((s) => !s.loading);

  // Build alignment assets map
  const alignmentAssets = React.useMemo<Record<string, AssetResult>>(() => {
    const result: Record<string, AssetResult> = {};
    for (const { key, label } of ASSETS) {
      result[key] = { label, consensus: assetConsensus[key].data };
    }
    return result;
  }, [assetConsensus]);

  return (
    <div className="min-h-screen bg-slate-950 pb-6 text-slate-100">
      <Toast
        toasts={toasts}
        onDismiss={(id) => setToasts((cur) => cur.filter((t) => t.id !== id))}
      />

      <div className="mx-auto max-w-screen-2xl space-y-4 px-4 py-4">

        {/* ── GlobalHeader ─────────────────────────────────────────────────── */}
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

        <div className="rounded-2xl border border-slate-700/60 bg-slate-900 px-5 py-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">
                Data Source Binding
              </p>
              <p className="mt-1 text-xs text-slate-300">
                V2 requests should use BTC/USDT with <span className="font-mono">{timeframe}</span> and horizon <span className="font-mono">{vade}</span>.
              </p>
            </div>
            <DataStatusBadge
              data={effectiveMacro}
              timestamp={macroTimestamp}
              showDetails
              className="lg:items-end"
            />
          </div>
          {macroNeedsVisibilityWarning && (
            <div className="mt-3 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-100">
              <span className="font-semibold">
                Macro data is not verified live data. Displayed values may be fallback, partial, or stale.
              </span>
              {effectiveMacro?.warning && (
                <span className="block pt-1 text-amber-200/80">{effectiveMacro.warning}</span>
              )}
            </div>
          )}
          {sseSelectionMismatch && (
            <div className="mt-3 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-200">
              SSE feed uses default symbol/timeframe; data may not match selected view.
            </div>
          )}
          {macroFetchError && (
            <div className="mt-3 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-200">
              Selected-horizon macro refresh failed. Last successful data keeps its original timestamp and source metadata.
              <span className="block pt-1 text-amber-300/80">{macroFetchError}</span>
            </div>
          )}
        </div>

        {/* ── 1. VADE SEÇİMİ ───────────────────────────────────────────────── */}
        <div className="rounded-2xl border border-slate-700/60 bg-slate-900 px-5 py-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">
                Yatırım Vadesi
              </p>
              {/* Dynamic label — updates instantly on horizon change */}
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

        {/* ── 2. MAKRO REJİM + AI YORUMU ──────────────────────────────────── */}
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

        {/* ── 3. PORTFÖY DAĞILIMI + AI ÖNERİSİ ───────────────────────────── */}
        <ErrorBoundary fallback="Portföy Dağılımı">
          {loading && !effectiveMacro ? (
            <SkeletonLoader variant="bar-chart" lines={5} />
          ) : effectiveMacro ? (
            <AllocationWithTip macro={effectiveMacro} vade={vade} />
          ) : null}
        </ErrorBoundary>

        {/* ── 4. VARLIK BAZLI KONSENSÜS KARTLARI ──────────────────────────── */}
        <ErrorBoundary fallback="Varlık Kartları">
          <div>
            {/* Dynamic TF label from active horizon */}
            <p className="mb-2 px-1 text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">
              Varlık Bazlı Konsensüs&nbsp;·&nbsp;
              <span className="font-mono text-emerald-500/80">{tfLabel}</span>
            </p>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
              {ASSETS.map(({ key, label, symbol }) => (
                <AssetConsensusCard
                  key={key}
                  assetKey={key}
                  symbol={symbol}
                  assetLabel={label}
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

        {/* ── 5. UYUM & KROSS-VALIDASYON ──────────────────────────────────── */}
        {effectiveMacro && anyAssetReady && (
          <ErrorBoundary fallback="Cross-Validasyon">
            <CrossAlignmentPanel
              macro={effectiveMacro}
              assets={alignmentAssets}
              vade={vade}
            />
          </ErrorBoundary>
        )}

        {/* ── Error banner ─────────────────────────────────────────────────── */}
        {error && (
          <div className="rounded-2xl border border-amber-500/30 bg-amber-500/5 p-4 text-xs text-amber-200">
            <span className="font-semibold">Canlı veri degraded:</span>{" "}
            Son bilinen snapshot ile çalışılıyor.&nbsp;Detay:&nbsp;{error}
          </div>
        )}
      </div>
      <DataSyncMonitor />
    </div>
  );
};

// ── Outer wrapper — provides VadeContext ──────────────────────────────────────
export const DashboardV2: React.FC = () => (
  <VadeProvider>
    <DashboardV2Inner />
  </VadeProvider>
);
