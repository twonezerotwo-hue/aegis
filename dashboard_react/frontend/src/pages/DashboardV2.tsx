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
import { SystemStatus } from "../components/SystemStatus";
import { KontrolMerkezi } from "../components/control/KontrolMerkezi";
import { AgentControlPanel } from "../components/control/AgentControlPanel";
import { AlertsPanel } from "../components/control/AlertsPanel";
import { SymbolSelector, type SymbolOption } from "../components/SymbolSelector";
import { TimeframeSelector } from "../components/TimeframeSelector";
import { NewsHeadlines } from "../components/NewsHeadlines";
import { useMetrics } from "../hooks/useMetrics";

import { useRealTimeFeed } from "../hooks/useRealTimeFeed";
import { fetchConsensus, fetchMacro } from "../services/apiV2";
import type { ConsensusResponse, MacroViewModel } from "../types/dashboardV2";

// Lazy-load heavy tab pages
const Backtest = lazy(() => import("./BacktestV2"));
const PaperTrading = lazy(() => import("./PaperTrading").then((m) => ({ default: m.default ?? m })));

// ── Tab definitions ────────────────────────────────────────────────────────────
type TabId = "control" | "portfolio" | "metrics" | "backtest" | "paper_trading";

const TABS: { id: TabId; label: string }[] = [
  { id: "control",       label: "Agent" },
  { id: "portfolio",     label: "Analiz" },
  { id: "metrics",       label: "Metrikler" },
  { id: "backtest",      label: "Backtest" },
  { id: "paper_trading", label: "Paper Trading" },
];

// ── Asset catalogue ───────────────────────────────────────────────────────────
const ASSETS = [
  { key: "gold",      symbol: "XAU/USDT",  label: "XAU — Altın",    tradeable: true  },
  { key: "btc",       symbol: "BTC/USDT",  label: "BTC — Bitcoin",  tradeable: true  },
  { key: "eth",       symbol: "ETH/USDT",  label: "ETH — Ethereum", tradeable: true  },
  { key: "sol",       symbol: "SOL/USDT",  label: "SOL — Solana",   tradeable: true  },
  { key: "xrp",       symbol: "XRP/USDT",  label: "XRP — Ripple",   tradeable: true  },
  { key: "commodity", symbol: "XAG/USDT",  label: "XAG — Gümüş",   tradeable: true  },
  { key: "bond",      symbol: "BOND/USDT", label: "BOND — Tahvil",  tradeable: false },
  { key: "cash",      symbol: "CASH/USDT", label: "CASH — Nakit",   tradeable: false },
] as const;

// Metrikler sekmesi: tüm trade edilebilir semboller SymbolSelector'a geçilir
const METRICS_SYMBOLS: SymbolOption[] = ASSETS
  .filter((a) => a.tradeable)
  .map(({ symbol, label }) => ({ symbol, label }));

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
  eth:       { data: null, loading: true, error: null, lastSuccessfulData: null },
  sol:       { data: null, loading: true, error: null, lastSuccessfulData: null },
  xrp:       { data: null, loading: true, error: null, lastSuccessfulData: null },
  commodity: { data: null, loading: true, error: null, lastSuccessfulData: null },
  bond:      { data: null, loading: true, error: null, lastSuccessfulData: null },
  cash:      { data: null, loading: true, error: null, lastSuccessfulData: null },
};

const VADE_OPTIONS: { value: Vade; label: string; sub: string }[] = [
  { value: "short",  label: "Kısa",  sub: "1–4 Hafta" },
  { value: "medium", label: "Orta",  sub: "1–3 Ay" },
  { value: "long",   label: "Uzun",  sub: "6 Ay+" },
];

// ── Sparkline: son N skor noktası mini SVG grafiği ──────────────────────────
const Sparkline: React.FC<{ data: number[]; color: string }> = ({ data, color }) => {
  if (!data || data.length < 2) {
    // Geçmiş henüz birikmedi — sabit genişlikte boş yer tut (layout kaymasın)
    return <span className="inline-block w-12 shrink-0" aria-hidden="true" />;
  }
  const W = 48, H = 14;
  const min = Math.min(...data), max = Math.max(...data);
  const range = max - min || 0.01;
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * W;
    const y = H - ((v - min) / range) * H;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const trend = data[data.length - 1] - data[0];
  const strokeCls = trend > 0.02 ? "stroke-emerald-400" : trend < -0.02 ? "stroke-rose-400" : "stroke-slate-500";
  return (
    <svg width={W} height={H} className="shrink-0" aria-label="trend">
      <polyline points={pts} fill="none" className={strokeCls} strokeWidth="1.2" strokeLinejoin="round" />
    </svg>
  );
};

// ── Veri kaynağı tipi: gerçek mi simüle mi? ─────────────────────────────────
function dataSourceKind(summary: string): { real: boolean; label: string } {
  const s = (summary || "").toLowerCase();
  if (s.includes("simüle") || s.includes("mock") || s.includes("simule")) {
    return { real: false, label: "kısmi simüle" };
  }
  if (s.includes("veri yok") || s.includes("bağlanmadı") || s.includes("ulaşılamadı")) {
    return { real: false, label: "veri yok" };
  }
  return { real: true, label: "canlı" };
}

// ── Çelişki uyarısı: yalnız GERÇEK çelişkileri ayıkla ───────────────────────
// "⚠ MVRV/NUPL simüle" gibi veri-kaynağı notları DEĞİL — onlar amber nokta ile
// zaten gösteriliyor. Sadece "aşırı ... ama sinyal nötr" türü çelişkiler kutuya çıkar.
function extractWarning(summary: string): string | null {
  const idx = (summary || "").indexOf("⚠");
  if (idx < 0) return null;
  const text = summary.slice(idx + 1).trim().split("·")[0].trim();
  if (!text) return null;
  // Gerçek çelişki sinyalleri: aşırı alım/satım + nötr sinyal, dip/tepe riski
  const isContradiction = /aşırı|dip fırsat|tepe risk|nötr|çelişk/i.test(text);
  const isDataNote = /simüle|mock|bağlanmadı|veri yok/i.test(text);
  if (isDataNote && !isContradiction) return null;   // veri notu → kutu yok
  return text;
}

// ── "Bu skoru neden verdi?" — dinamik açıklama üreteci ───────────────────────
type MetricRaw = { score: number; summary?: string; health?: string; source?: string; data_status?: string };

function whyLines(key: string, m: MetricRaw, tf: string): string[] {
  const pct = Math.round(m.score * 100);
  const summary = m.summary ?? "";

  if (key === "touche") {
    // summary: "EQS 17.1 (kuresel) - 15m: BUY - 1h: NEUTRAL - 4h: SELL - 1d: SELL - cogunluk negatif."
    const tfMatches = [...summary.matchAll(/(\d+[mhd]+):\s*(BUY|SELL|NEUTRAL)/gi)];
    const tfs: { tf: string; sig: string }[] = tfMatches.map(m2 => ({ tf: m2[1].toLowerCase(), sig: m2[2].toUpperCase() }));
    const eqsMatch  = summary.match(/EQS\s*([\d.]+)/);
    const eqs       = eqsMatch ? eqsMatch[1] : "—";
    const indMatch  = summary.match(/\|\s*([^|]+RSI[^|]+)/);  // "4H RSI=18↓ MACD=↓ EMA=↓trend"
    const indStr    = indMatch ? indMatch[1].trim() : null;
    const current   = tfs.find(t => t.tf === tf.toLowerCase());
    const conflict  = tfs.filter(t => ["4h","1d","1w"].includes(t.tf) && current && t.sig !== current.sig && current.sig !== "NEUTRAL");

    const l1 = tfs.length
      ? `Teknik analiz ${tfs.map(t => `${t.tf.toUpperCase()}=${t.sig}`).join(" · ")} sinyali ürettti; küresel EQS ${eqs}/100.`
      : `Teknik analiz EQS ${eqs}/100 skoru üretti.`;
    const l2 = indStr
      ? `Öne çıkan göstergeler: ${indStr}.`
      : current
        ? `Seçili ${tf.toUpperCase()}'de sinyal ${current.sig}${conflict.length ? `; ancak üst TF'ler (${conflict.map(t=>t.tf.toUpperCase()).join(", ")}) çelişiyor` : "; üst TF'ler de aynı yönde"}.`
        : `${tf.toUpperCase()} için sinyal yok, küresel EQS kullanıldı.`;
    const l3 = conflict.length
      ? `Çelişki yüzünden ağırlıklı oy ortaya çekildi → nihai skor %${pct}.`
      : `TF'ler uyumlu → skor ${pct >= 65 ? "pozitif aday bolgesi" : pct >= 45 ? "notr bekleme" : "negatif aday bolgesi"}; %${pct}.`;
    return [l1, l2, l3];
  }

  if (key === "fundamental") {
    const mvrvM = summary.match(/MVRV Z[^:]*:\s*([\d.]+)/);
    const nuplM = summary.match(/NUPL[^:]*:\s*([\d.]+)/);
    const mvrv = mvrvM ? parseFloat(mvrvM[1]) : null;
    const nupl = nuplM ? parseFloat(nuplM[1]) : null;
    const isMock = summary.includes("simüle");
    const l1 = mvrv != null
      ? `MVRV Z-Score ${mvrv}: ${mvrv < 1 ? "piyasa ucuz bölgede (birikim fırsatı)" : mvrv > 3.5 ? "piyasa pahalı (dağıtım riski yüksek)" : "değerleme makul — ne çok pahalı ne çok ucuz"}.`
      : "MVRV Z-Score verisi alınamadı.";
    const l2 = nupl != null
      ? `NUPL ${nupl}: ${nupl < 0 ? "sahiplerin çoğu zararda — kapitülasyon bölgesi" : nupl > 0.75 ? "piyasa öfori aşamasında — dikkat" : "sahiplerin ortalaması kârda, istikrarlı ortam"}.`
      : "NUPL verisi alınamadı.";
    const l3 = isMock
      ? `Glassnode API key olmadığından simüle veri kullanıldı; bu iki değerin bileşimi %${pct} skoru üretti.`
      : `Bu iki göstergenin bileşimi, seçili ${tf.toUpperCase()} TF ağırlığıyla %${pct} skoru üretti.`;
    return [l1, l2, l3];
  }

  if (key === "news") {
    const countM  = summary.match(/(\d+)\s*haber/);
    const impactM = summary.match(/Etki[:\s]*([\d.]+)/);
    const confM   = summary.match(/Güven[:\s]*([\d.]+)/i);
    const sentM   = summary.match(/duygu[:\s]*([\w]+)/i);
    const count   = countM  ? countM[1]  : "?";
    const impact  = impactM ? impactM[1] : "?";
    const conf    = confM   ? confM[1]   : "?";
    const sent    = sentM   ? sentM[1]   : "belirsiz";
    const relevMap: Record<string,number> = {"5m":100,"15m":98,"1h":92,"4h":80,"1d":65,"1w":45,"1month":25};
    const relev = relevMap[tf] ?? 80;
    return [
      `${count} haber NLP ile analiz edildi: kripto etki skoru ${impact}/100, güven %${conf}.`,
      `Haberların genel duygusu "${sent}" — düzenleyici, ekonomik ve kripto sektörü haberleri bir arada değerlendirildi.`,
      `${tf.toUpperCase()} timeframe için haber ağırlığı %${relev}'e düşürüldü (uzun vadede haber etkisi azalır) → nihai %${pct}.`,
    ];
  }

  if (key === "sentinel") {
    const riskM  = summary.match(/Olay riski[:\s]*([\d.]+)%/i);
    const liqM   = summary.match(/Likidite[:\s]*([\d.]+)/i);
    const volM   = summary.match(/Oynaklık[:\s]*([\d.]+)/i);
    const regM   = summary.match(/Rejim[:\s]*([^·.]+)/i);
    const risk   = riskM ? riskM[1] : "?";
    const liq    = liqM  ? liqM[1]  : "?";
    const reg    = regM  ? regM[1].trim() : "?";
    return [
      `Olay riski %${risk} (${parseFloat(risk||"50") < 30 ? "düşük — kritik makro tetikleyici yok" : parseFloat(risk||"50") < 55 ? "orta — dikkat gerekiyor" : "yüksek — pozisyon küçült"}). Piyasa likiditesi ${liq}/100.`,
      `Makro rejim: ${reg}. VIX, DXY, US10Y, HYG ve BTC funding rate bütünü bu rejimi işaret etti.`,
      `Ters çevirme (%100 − %${risk} = %${Math.round(100 - parseFloat(risk||"50"))}) ile Sentinel skoru %${pct} oldu. Consensus'a girmez; kill switch ve portföy overlay'e katkı sağlar.`,
    ];
  }

  // quantum
  return [
    `Skor %${pct} — ${Math.abs(pct - 50) < 2 ? "sabit nötr değer: gerçek order book verisi henüz bağlanmadı" : pct > 55 ? "likidite uygun görünüyor" : "likidite zayıf uyarısı"}.`,
    "Binance emir defteri derinliği, bid/ask dengesizliği ve slippage ölçülür; yüksek skor büyük emri fiyatı bozmadan çalıştırmayı, düşük skor parçalı emir açmayı önerir.",
    "Veri bağlantısı kurulduğunda bu skor her TF ve varlık için gerçek zamanlı değişecektir.",
  ];
}

// ── MetricsModuleInfo bileşeni ────────────────────────────────────────────────
const _MOD_META: Record<string, { name: string; color: string; dot: string }> = {
  touche:      { name: "Touche EQS",         color: "border-violet-500/30", dot: "bg-violet-400" },
  fundamental: { name: "Fundamental Score",  color: "border-sky-500/30",   dot: "bg-sky-400"    },
  news:        { name: "Haber Duygusu",      color: "border-amber-500/30",  dot: "bg-amber-400"  },
  sentinel:    { name: "Sentinel",           color: "border-rose-500/20",   dot: "bg-rose-400"   },
  quantum:     { name: "Quantum",            color: "border-emerald-500/20",dot: "bg-emerald-400"},
};

const MetricsModuleInfo: React.FC<{
  open: boolean;
  onToggle: () => void;
  metrics: Record<string, MetricRaw>;
  timeframe: string;
}> = ({ open, onToggle, metrics, timeframe }) => (
  <div className="rounded-2xl border border-slate-800 bg-slate-950/40">
    <button
      type="button"
      onClick={onToggle}
      className="flex w-full items-center justify-between px-4 py-3 text-left text-[10px] font-semibold uppercase tracking-widest text-slate-600 transition-colors hover:text-slate-400"
    >
      <span>Bu skoru neden verdi?</span>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
        className={`h-3.5 w-3.5 transition-transform duration-200 ${open ? "rotate-180" : ""}`}>
        <polyline points="6 9 12 15 18 9" />
      </svg>
    </button>
    {open && (
      <div className="grid gap-3 px-4 pb-4 sm:grid-cols-2 lg:grid-cols-3">
        {Object.entries(_MOD_META).map(([key, meta]) => {
          const m = metrics[key];
          if (!m) return null;
          const lines = whyLines(key, m, timeframe);
          const pct   = Math.round(m.score * 100);
          const sc    = m.score > 0.65 ? "text-emerald-400" : m.score < 0.35 ? "text-rose-400" : "text-slate-300";
          return (
            <div key={key} className={`rounded-xl border ${meta.color} bg-slate-900/60 p-3`}>
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5">
                  <span className={`h-2 w-2 shrink-0 rounded-full ${meta.dot}`} />
                  <p className="text-[10px] font-bold text-slate-300">{meta.name}</p>
                </div>
                <span className={`font-mono text-[11px] font-bold ${sc}`}>{pct}%</span>
              </div>
              <ol className="list-none space-y-1.5">
                {lines.map((line, i) => (
                  <li key={i} className="flex gap-1.5">
                    <span className="mt-0.5 shrink-0 font-mono text-[8px] text-slate-700">{i + 1}.</span>
                    <p className="text-[10px] leading-4 text-slate-500">{line}</p>
                  </li>
                ))}
              </ol>
            </div>
          );
        })}
      </div>
    )}
  </div>
);

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

  // ── Metrikler modül açıklaması accordion — varsayılan açık ───────────────
  const [metricsInfoOpen, setMetricsInfoOpen] = React.useState(true);

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

  // ── Fiyat ticker (30s önbellekli) ─────────────────────────────────────────
  const [metricsTicker, setMetricsTicker] = React.useState<{
    price: number; change_24h_pct: number; currency: string; available: boolean;
  } | null>(null);

  React.useEffect(() => {
    const API = import.meta.env.VITE_API_URL || "http://localhost:8502";
    const fetchTicker = () =>
      fetch(`${API}/api/price/ticker?symbol=${encodeURIComponent(metricsSymbol)}`)
        .then(r => r.json())
        .then(d => setMetricsTicker({
          price:          d.price ?? 0,
          change_24h_pct: d.change_24h_pct ?? 0,
          currency:       d.currency ?? "USD",
          available:      d.available ?? false,
        }))
        .catch(() => setMetricsTicker(null));

    fetchTicker();
    const id = setInterval(fetchTicker, 30_000);
    return () => clearInterval(id);
  }, [metricsSymbol]);
  const { data: metricsData, loading: metricsLoading } = useMetrics(
    metricsSymbol,
    metricsTimeframe,
    metricsRefreshMs
  );

  // ── Metrik geçmişi (24s sparkline için ring buffer) ───────────────────────
  const [metricHistory, setMetricHistory] = React.useState<Record<string, number[]>>({});
  const lastHistTs = React.useRef<number>(0);
  React.useEffect(() => {
    if (!metricsData?.metrics) return;
    const now = Date.now();
    // En fazla 30 saniyede bir nokta ekle (spam önle)
    if (now - lastHistTs.current < 25_000) return;
    lastHistTs.current = now;
    setMetricHistory((prev) => {
      const next = { ...prev };
      (["touche", "fundamental", "news", "ml", "sentinel", "quantum"] as const).forEach((k) => {
        const sc = (metricsData.metrics as any)[k]?.score;
        if (typeof sc === "number") {
          const arr = [...(next[k] ?? []), sc];
          next[k] = arr.slice(-40);   // son 40 nokta (~20 dk @30s)
        }
      });
      return next;
    });
  }, [metricsData]);

  // Sembol/TF değişince geçmişi sıfırla
  React.useEffect(() => { setMetricHistory({}); lastHistTs.current = 0; }, [metricsSymbol, metricsTimeframe]);

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
          <div className="flex min-w-0 gap-1">
            {TABS.map(({ id, label }) => (
              <button
                key={id}
                type="button"
                onClick={() => setActiveTab(id)}
                aria-pressed={activeTab === id}
                className={`min-w-0 flex-1 rounded-xl px-2 py-2 text-xs font-semibold uppercase tracking-wider transition-all duration-200 sm:px-3 ${
                  activeTab === id
                    ? "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-400/40"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
                }`}
              >
                <span className="block truncate">{label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* ── KONTROL MERKEZİ TAB ─────────────────────────────────────────── */}
        {activeTab === "control" && (
          <div className="space-y-5">
            <AgentControlPanel />

            <AlertsPanel />

            <KontrolMerkezi
              macro={effectiveMacro}
              btcConsensus={assetConsensus.btc.data ?? null}
              dailyPnl={dailyPnl}
              loading={loading && !effectiveMacro}
            />
          </div>
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
                <SymbolSelector currentSymbol={metricsSymbol} onSymbolChange={setMetricsSymbol} symbols={METRICS_SYMBOLS} />
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

                  {/* Header: consensus karar + fiyat + sağlık noktaları */}
                  {(() => {
                    const cons  = metricsData.consensus;
                    const act   = cons?.action ?? "HOLD";
                    const score = ((cons?.weighted_score ?? 0) * 100).toFixed(1);
                    const conf  = ((cons?.confidence ?? 0) * 100).toFixed(0);
                    const actCls = act === "BUY" ? "text-emerald-400 border-emerald-500/40 bg-emerald-500/10"
                                 : act === "SELL" ? "text-rose-400 border-rose-500/40 bg-rose-500/10"
                                 : "text-amber-400 border-amber-500/40 bg-amber-500/10";
                    const actTr = act === "BUY" ? "Pozitif aday" : act === "SELL" ? "Negatif aday" : "Aday yok";
                    const svcs  = metricsData.health?.services ?? {};
                    const svcList = [
                      { k: "touche",      label: "T" },
                      { k: "fundamental", label: "F" },
                      { k: "news",        label: "N" },
                      { k: "sentinel",    label: "S" },
                      { k: "quantum",     label: "Q" },
                    ];
                    // Fiyat formatı — büyük fiyatlar için kısalt
                    const formatPrice = (p: number, cur: string) => {
                      if (!p) return "—";
                      const prefix = cur === "USDT" ? "$" : "$";
                      if (p >= 1000) return `${prefix}${p.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
                      if (p >= 1)    return `${prefix}${p.toFixed(4)}`;
                      return `${prefix}${p.toFixed(6)}`;
                    };
                    const chgCls = !metricsTicker ? "" :
                      metricsTicker.change_24h_pct >= 0 ? "text-emerald-400" : "text-rose-400";
                    return (
                      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                        <div className="flex items-center gap-3">
                          {/* Fiyat bloğu */}
                          <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 px-3 py-2 min-w-[110px]">
                            <p className="text-[9px] font-semibold uppercase tracking-widest text-slate-500 mb-0.5">
                              {METRICS_SYMBOLS.find(s => s.symbol === metricsSymbol)?.label ?? metricsSymbol}
                            </p>
                            {metricsTicker?.available ? (
                              <div className="flex items-baseline gap-1.5">
                                <span className="font-mono text-base font-bold text-white">
                                  {formatPrice(metricsTicker.price, metricsTicker.currency)}
                                </span>
                                <span className={`font-mono text-[10px] font-semibold ${chgCls}`}>
                                  {metricsTicker.change_24h_pct >= 0 ? "+" : ""}
                                  {metricsTicker.change_24h_pct.toFixed(2)}%
                                </span>
                              </div>
                            ) : (
                              <span className="font-mono text-sm text-slate-500">—</span>
                            )}
                          </div>
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
                  {(() => {
                    // Consensus ağırlıkları (her modülün karara katkısı)
                    const cw = (metricsData.consensus as any)?.weights ?? {};
                    const wMap: Record<string, number> = {
                      touche: cw.touche ?? 0, fundamental: cw.fundamental ?? 0,
                      news: cw.news ?? 0, ml: cw.ml ?? 0,
                    };
                    // Konsensüs katkısı: ağırlık × (skor - 0.5) × 100 → +/- puan
                    const contrib = (key: string, score: number) => {
                      const w = wMap[key] ?? 0;
                      if (w <= 0) return null;
                      const c = w * (score - 0.5) * 200;  // -100..+100 ölçek
                      return c;
                    };
                    return (
                  <div className="space-y-1">
                    {/* Consensus başlık */}
                    <div className="mb-1 flex items-center gap-2 px-3">
                      <span className="text-[8px] font-bold uppercase tracking-wider text-emerald-600">● Consensus'a giren</span>
                      <div className="h-px flex-1 bg-slate-800" />
                    </div>

                    {/* Consensus'a giren modüller: touche, fundamental, news */}
                    {(["touche", "fundamental", "news"] as const).map((key) => {
                      const m   = metricsData.metrics[key];
                      const pct = Math.round(m.score * 100);
                      const BAR: Record<string, string> = { touche: "bg-violet-400", fundamental: "bg-sky-400", news: "bg-amber-400" };
                      const NAME: Record<string, string> = { touche: "Touche EQS", fundamental: "Fundamental", news: "Haber" };
                      const sc  = m.score > 0.65 ? "text-emerald-400" : m.score < 0.35 ? "text-rose-400" : "text-slate-300";
                      const src = dataSourceKind(m.summary ?? "");
                      const warn = extractWarning(m.summary ?? "");
                      const c = contrib(key, m.score);
                      const hist = metricHistory[key] ?? [];
                      return (
                        <div key={key} className="group rounded-xl px-3 py-2.5 hover:bg-slate-800/40 transition-colors">
                          <div className="mb-1.5 flex items-center gap-2">
                            {/* Gerçek/simüle veri noktası */}
                            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${src.real ? "bg-emerald-400" : "bg-amber-400"}`}
                                  title={src.real ? "Canlı veri" : src.label} />
                            <span className="w-16 shrink-0 text-[10px] font-semibold text-slate-400">{NAME[key]}</span>
                            <div className="h-1.5 flex-1 rounded-full bg-slate-700/60">
                              <div className={`h-1.5 rounded-full ${BAR[key]} transition-all duration-500`} style={{ width: `${pct}%` }} />
                            </div>
                            <Sparkline data={hist} color={BAR[key]} />
                            <span className={`w-7 shrink-0 text-right font-mono text-[11px] font-bold ${sc}`}>{pct}</span>
                            {/* Consensus katkısı */}
                            {c !== null && (
                              <span className={`w-12 shrink-0 text-right font-mono text-[9px] font-semibold ${c > 1 ? "text-emerald-500" : c < -1 ? "text-rose-500" : "text-slate-600"}`}
                                    title="Bu modülün consensus'a katkısı">
                                {c > 0 ? "+" : ""}{c.toFixed(0)}p
                              </span>
                            )}
                          </div>
                          {/* Çelişki uyarısı */}
                          {warn && (
                            <div className="mb-1 ml-[1.4rem] rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[9px] text-amber-400">
                              ⚠ {warn}
                            </div>
                          )}
                          <p className="ml-[1.4rem] text-[9px] leading-4 text-slate-600">{m.summary}</p>
                        </div>
                      );
                    })}

                    {/* ML Predictor — consensus'a girer (ağırlık %{ml}) */}
                    {metricsData.metrics.ml && (() => {
                      const ml = metricsData.metrics.ml as unknown as { score: number; summary: string; ml_detail?: { signal?: string; buy_prob?: number; sell_prob?: number; confidence?: number; trained?: boolean } };
                      const pct = Math.round(ml.score * 100);
                      const sc  = ml.score > 0.65 ? "text-emerald-400" : ml.score < 0.35 ? "text-rose-400" : "text-slate-300";
                      const detail = ml.ml_detail;
                      const c = detail?.trained ? contrib("ml", ml.score) : null;
                      const hist = metricHistory.ml ?? [];
                      const sigBadge = detail?.signal === "BUY" ? "text-emerald-400 border-emerald-500/30 bg-emerald-500/5"
                                     : detail?.signal === "SELL" ? "text-rose-400 border-rose-500/30 bg-rose-500/5"
                                     : "text-amber-400 border-amber-500/30 bg-amber-500/5";
                      return (
                        <div className="group rounded-xl border border-indigo-500/20 bg-indigo-500/5 px-3 py-2.5 hover:bg-indigo-500/10 transition-colors">
                          <div className="mb-1.5 flex items-center gap-2">
                            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${detail?.trained ? "bg-emerald-400" : "bg-slate-600"}`} />
                            <span className="w-16 shrink-0 text-[10px] font-semibold text-indigo-400">ML Predictor</span>
                            <div className="h-1.5 flex-1 rounded-full bg-slate-700/60">
                              <div className="h-1.5 rounded-full bg-indigo-400 transition-all duration-500" style={{ width: `${pct}%` }} />
                            </div>
                            <Sparkline data={hist} color="bg-indigo-400" />
                            <span className={`w-7 shrink-0 text-right font-mono text-[11px] font-bold ${sc}`}>{pct}</span>
                            {c !== null ? (
                              <span className={`w-12 shrink-0 text-right font-mono text-[9px] font-semibold ${c > 1 ? "text-emerald-500" : c < -1 ? "text-rose-500" : "text-slate-600"}`}>
                                {c > 0 ? "+" : ""}{c.toFixed(0)}p
                              </span>
                            ) : <span className="w-12 shrink-0" />}
                          </div>
                          {detail?.trained ? (
                            <div className="ml-[1.4rem] flex items-center gap-2 text-[9px] text-slate-600">
                              {detail?.signal && (
                                <span className={`rounded border px-1.5 py-0.5 font-mono text-[8px] font-bold ${sigBadge}`}>
                                  {detail.signal === "BUY" ? "POS" : detail.signal === "SELL" ? "NEG" : "NEU"}
                                </span>
                              )}
                              <span>Poz {Math.round((detail.buy_prob ?? 0) * 100)}%</span>
                              <span>Neg {Math.round((detail.sell_prob ?? 0) * 100)}%</span>
                              <span className="text-slate-700">· güven %{Math.round((detail.confidence ?? 0) * 100)}</span>
                              <span className="text-indigo-700">· XGBoost · consensus ağırlık %{Math.round((wMap.ml ?? 0) * 100)}</span>
                            </div>
                          ) : (
                            <p className="ml-[1.4rem] text-[9px] italic text-slate-700">Model eğitiliyor — birazdan hazır</p>
                          )}
                        </div>
                      );
                    })()}

                    {/* Ayırıcı */}
                    <div className="my-2 flex items-center gap-2 px-3">
                      <span className="text-[8px] font-bold uppercase tracking-wider text-slate-600">○ Arka plan (uyarı üretir, consensus'a girmez)</span>
                      <div className="h-px flex-1 bg-slate-800" />
                    </div>

                    {/* Arka plan modülleri: sentinel, quantum */}
                    {(["sentinel", "quantum"] as const).map((key) => {
                      const m   = metricsData.metrics[key];
                      const pct = Math.round(m.score * 100);
                      const BAR: Record<string, string> = { sentinel: "bg-rose-400", quantum: "bg-emerald-400" };
                      const NAME: Record<string, string> = { sentinel: "Sentinel", quantum: "Quantum" };
                      const src = dataSourceKind(m.summary ?? "");
                      const hist = metricHistory[key] ?? [];
                      const badge: Record<string, { label: string; cls: string }> = {
                        sentinel: m.score >= 0.55 ? { label: "✓ Düşük Risk", cls: "text-emerald-500" }
                                : m.score >= 0.45 ? { label: "~ Orta Risk",  cls: "text-amber-500"  }
                                : { label: "✗ Yüksek Risk", cls: "text-rose-500" },
                        quantum:  Math.abs(m.score - 0.5) < 0.01
                                ? { label: "~ Veri Yok",     cls: "text-slate-600" }
                                : m.score >= 0.55 ? { label: "✓ Likidite İyi", cls: "text-emerald-500" }
                                : m.score >= 0.45 ? { label: "~ Nötr", cls: "text-amber-500" }
                                : { label: "✗ Aşırı Pozisyon", cls: "text-rose-500" },
                      };
                      return (
                        <div key={key} className="rounded-xl px-3 py-2 hover:bg-slate-800/30 transition-colors">
                          <div className="flex items-center gap-2">
                            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${src.real ? "bg-emerald-400/70" : "bg-amber-400/70"}`} />
                            <span className="w-16 shrink-0 text-[10px] text-slate-500">{NAME[key]}</span>
                            <div className="h-1 flex-1 rounded-full bg-slate-800">
                              <div className={`h-1 rounded-full ${BAR[key]} opacity-60`} style={{ width: `${pct}%` }} />
                            </div>
                            <Sparkline data={hist} color={BAR[key]} />
                            <span className="w-7 shrink-0 text-right font-mono text-[10px] text-slate-500">{pct}</span>
                            <span className={`w-24 shrink-0 text-right text-[9px] font-semibold ${badge[key].cls}`}>{badge[key].label}</span>
                          </div>
                          <p className="ml-[1.4rem] mt-0.5 text-[9px] leading-4 text-slate-600">{m.summary}</p>
                        </div>
                      );
                    })}
                  </div>
                    );
                  })()}

                  {/* Footer: tazelik rozeti + son güncelleme */}
                  <div className="mt-3 flex items-center justify-between border-t border-slate-800 pt-2">
                    <div className="flex items-center gap-3 text-[9px]">
                      <span className="flex items-center gap-1 text-slate-500">
                        <span className={`h-1.5 w-1.5 rounded-full ${metricsLoading ? "bg-amber-400 animate-pulse" : "bg-emerald-400"}`} />
                        {metricsLoading ? "güncelleniyor" : "canlı"}
                      </span>
                      <span className="flex items-center gap-1 text-slate-600">
                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" /> gerçek veri
                        <span className="ml-1 h-1.5 w-1.5 rounded-full bg-amber-400" /> simüle
                      </span>
                      <span className="text-slate-600">· yenileme {metricsRefreshMs / 1000}s</span>
                    </div>
                    <p className="font-mono text-[9px] text-slate-700">
                      {(metricsData.last_updated ?? metricsData.timestamp ?? "—").toString().slice(11, 19)}
                    </p>
                  </div>
                </div>

                {/* ── Canlı Haber Akışı (gerçek RSS başlıkları) ───────────── */}
                <NewsHeadlines symbol={metricsSymbol} />

                {/* ── Modül Açıklamaları ─────────────────────────────────── */}
                <MetricsModuleInfo
                  open={metricsInfoOpen}
                  onToggle={() => setMetricsInfoOpen(v => !v)}
                  metrics={metricsData.metrics as unknown as Record<string, MetricRaw>}
                  timeframe={metricsTimeframe}
                />
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
