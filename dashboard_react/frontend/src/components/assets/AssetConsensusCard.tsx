import React from "react";
import type { ConsensusModuleSource, ConsensusResponse } from "../../types/dashboardV2";
import { DataStatusBadge } from "../ui/DataStatusBadge";
import { formatDataAge, getDataSource, getDataTimestamp } from "../../utils/dataFreshness";

interface Props {
  assetKey: string;
  symbol: string;
  assetLabel: string;
  consensus: ConsensusResponse | null;
  lastSuccessfulData?: ConsensusResponse | null;
  loading: boolean;
  error: string | null;
  onRefetch?: (symbol: string) => Promise<void>;
}

const ACTION_CFG = {
  BUY: { label: "AL", cls: "border-emerald-500/40 bg-emerald-500/15 text-emerald-300", ring: "ring-1 ring-emerald-500/20" },
  HOLD: { label: "TUT", cls: "border-amber-500/40 bg-amber-500/15 text-amber-300", ring: "ring-1 ring-amber-500/20" },
  SELL: { label: "AZALT", cls: "border-rose-500/40 bg-rose-500/15 text-rose-300", ring: "ring-1 ring-rose-500/20" },
} as const;

const MODULE_BAR: Record<string, string> = {
  touche: "bg-violet-400",
  fundamental: "bg-sky-400",
  news: "bg-amber-400",
  sentinel: "bg-rose-400",
  quantum: "bg-emerald-400",
};

const MODULE_SHORT: Record<string, string> = {
  touche: "T",
  fundamental: "F",
  news: "N",
  sentinel: "S",
  quantum: "Q",
  technical: "T",
};

const MODULE_LABEL: Record<string, string> = {
  technical: "Technical",
  fundamental: "Fundamental",
  news: "News",
  sentinel: "Sentinel",
  quantum: "Quant",
};

const MODULES = ["touche", "fundamental", "news", "sentinel", "quantum"] as const;
const DETAIL_MODULES = ["technical", "fundamental", "news", "sentinel", "quantum"] as const;
const UNVERIFIED_SIGNAL_STATUSES = new Set(["STALE", "FALLBACK", "MOCK", "MISSING", "UNKNOWN", "PARTIAL_FALLBACK"]);

const SkeletonCard: React.FC<{ label: string }> = ({ label }) => (
  <div className="animate-pulse rounded-2xl border border-slate-700/60 bg-slate-900 p-4">
    <p className="mb-3 text-[10px] uppercase tracking-wider text-slate-600">{label}</p>
    <div className="mb-3 h-5 w-2/3 rounded bg-slate-700/60" />
    <div className="space-y-2">
      {MODULES.map((mod) => (
        <div key={mod} className="flex items-center gap-2">
          <div className="h-2 w-4 rounded bg-slate-700/50" />
          <div className="h-1.5 flex-1 rounded-full bg-slate-700/50" />
          <div className="h-2 w-6 rounded bg-slate-700/50" />
        </div>
      ))}
    </div>
  </div>
);

const boolLabel = (value: boolean | undefined): string => (value ? "true" : "false");

const renderModuleSourceMeta = (module: string, moduleSource: ConsensusModuleSource) => {
  const warnings = Array.from(
    new Set([
      ...(moduleSource.shared_score ? ["Shared module score, not asset-specific."] : []),
      ...moduleSource.warnings,
    ])
  );

  return (
    <div key={module} className="rounded-xl border border-slate-800 bg-slate-950/40 p-2">
      <div className="mb-1 flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-300">
          {MODULE_SHORT[module]} {MODULE_LABEL[module]}
        </span>
        <span className="font-mono text-[10px] text-slate-400">
          {Math.min(100, Math.max(0, Math.round(moduleSource.value * 100)))}%
        </span>
      </div>
      <div className="space-y-0.5 text-[9px] leading-4 text-slate-500">
        <p>Status: <span className="font-mono text-slate-300">{moduleSource.data_status}</span></p>
        <p>Source: <span className="font-mono text-slate-300">{moduleSource.source}</span></p>
        <p>Service: <span className="font-mono text-slate-300">{moduleSource.service}</span></p>
        <p>Updated: <span className="font-mono text-slate-300">{formatDataAge(moduleSource.timestamp)}</span></p>
        <p>Verified: <span className={`font-mono ${moduleSource.verified ? "text-emerald-300" : "text-amber-300"}`}>{boolLabel(moduleSource.verified)}</span></p>
        <p>Fallback used: <span className={`font-mono ${moduleSource.fallback_used ? "text-amber-300" : "text-slate-300"}`}>{boolLabel(moduleSource.fallback_used)}</span></p>
        {warnings.map((warning) => (
          <p key={warning} className="text-amber-300">
            {warning}
          </p>
        ))}
      </div>
    </div>
  );
};

export const AssetConsensusCard: React.FC<Props> = ({
  assetKey,
  symbol,
  assetLabel,
  consensus,
  lastSuccessfulData = null,
  loading,
  error,
  onRefetch,
}) => {
  const [expanded, setExpanded] = React.useState(false);
  const [retrying, setRetrying] = React.useState(false);
  const detailId = React.useId();

  const handleRetry = async () => {
    if (!onRefetch) {
      return;
    }

    setRetrying(true);
    try {
      await onRefetch(symbol);
    } finally {
      setRetrying(false);
    }
  };

  const lastSuccessfulTimestamp = getDataTimestamp(lastSuccessfulData);
  const lastSuccessfulSource = getDataSource(lastSuccessfulData);

  if (loading) {
    return <SkeletonCard label={assetLabel} />;
  }

  if (error !== null || !consensus) {
    return (
      <div className="rounded-2xl border border-rose-500/40 bg-slate-900 p-4 transition-colors duration-200 hover:border-rose-500/60">
        <div className="mb-2 flex items-start justify-between">
          <p className="text-[10px] uppercase tracking-wider text-slate-500">{assetLabel}</p>
          <span className="text-base">!</span>
        </div>
        <p className="mb-3 text-xs text-rose-300">Data unavailable</p>
        <div className="mb-3 max-h-16 overflow-y-auto text-[11px] leading-4 text-rose-400/70">
          {error && error !== "Veri alinamadi" ? error : "Network baglantisi basarisiz. Lutfen yeniden deneyin."}
        </div>
        <DataStatusBadge
          data={lastSuccessfulData}
          status={lastSuccessfulData ? undefined : "MISSING"}
          source={lastSuccessfulSource}
          timestamp={lastSuccessfulTimestamp}
          showDetails
          compact
          className="mb-3"
        />
        <div className="mb-3 space-y-1 text-[10px] text-slate-500">
          <p>Last successful update: {lastSuccessfulTimestamp ? formatDataAge(lastSuccessfulTimestamp) : "none recorded"}</p>
          <p>Source: {lastSuccessfulSource ?? "unknown"}</p>
          {lastSuccessfulData && (
            <p>
              Last successful selection: {lastSuccessfulData.symbol} / {lastSuccessfulData.timeframe}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={handleRetry}
          disabled={retrying || !onRefetch}
          className="w-full rounded-lg border border-rose-500/30 bg-rose-500/5 px-3 py-2 text-xs font-semibold text-rose-400 transition-colors duration-150 hover:bg-rose-500/10 disabled:opacity-50"
        >
          {retrying ? "Deneniyor..." : "Yeniden Dene"}
        </button>
      </div>
    );
  }

  const action = consensus.action;
  const cfg = ACTION_CFG[action] ?? ACTION_CFG.HOLD;
  const confidencePct = (consensus.confidence * 100).toFixed(0);
  const fiveModPct = (consensus.five_module_score * 100).toFixed(1);
  const dataStatus = consensus.data_status ?? "UNKNOWN";
  const consensusSource = getDataSource(consensus) ?? consensus.source ?? "unknown";
  const consensusUpdated = getDataTimestamp(consensus);
  const signalUnverified = consensus.verified === false || UNVERIFIED_SIGNAL_STATUSES.has(dataStatus);
  const topLevelWarnings = Array.from(new Set(consensus.warnings ?? []));
  const moduleSourceEntries = DETAIL_MODULES
    .map((module) => [module, consensus.module_sources?.[module] ?? null] as const)
    .filter((entry): entry is readonly [typeof DETAIL_MODULES[number], ConsensusModuleSource] => entry[1] !== null);

  return (
    <div
      className={`rounded-2xl border border-slate-700/60 bg-slate-900 p-4 shadow-md transition-all duration-300 hover:border-slate-600 hover:shadow-lg hover:shadow-slate-950/40 ${cfg.ring}`}
      data-asset-card={assetKey}
    >
      <div className="mb-3 flex items-center justify-between">
        <p className="mr-2 truncate text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
          {assetLabel}
        </p>
        <span className={`inline-flex flex-shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-bold ${cfg.cls}`}>
          {cfg.label}
        </span>
      </div>

      <DataStatusBadge data={consensus} compact showDetails className="mb-3" />

      <div className="mb-3 flex items-center justify-between text-[10px] text-slate-500">
        <span className="font-mono">{consensus.symbol}</span>
        <span className="font-mono">{consensus.timeframe}</span>
      </div>

      <div className="mb-3 grid grid-cols-2 gap-x-3 gap-y-1 rounded-xl border border-slate-800 bg-slate-950/50 p-2 text-[9px] text-slate-400">
        <p>Data Status: <span className="font-mono text-slate-200">{dataStatus}</span></p>
        <p>Verified: <span className={`font-mono ${consensus.verified ? "text-emerald-300" : "text-amber-300"}`}>{boolLabel(consensus.verified)}</span></p>
        <p>Source: <span className="font-mono text-slate-200">{consensusSource}</span></p>
        <p>Fallback used: <span className={`font-mono ${consensus.fallback_used ? "text-amber-300" : "text-slate-200"}`}>{boolLabel(consensus.fallback_used)}</span></p>
        <p className="col-span-2">Updated: <span className="font-mono text-slate-200">{formatDataAge(consensusUpdated)}</span></p>
      </div>

      {signalUnverified && (
        <div className="mb-3 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[10px] leading-4 text-amber-200">
          Signal is not verified because source data is stale/fallback/mock.
        </div>
      )}

      <div className="mb-3 flex items-baseline gap-3">
        <div>
          <p className="text-[9px] uppercase tracking-wider text-slate-600">Guven</p>
          <p className="mt-0.5 font-mono text-lg font-bold leading-none text-white">
            {confidencePct}<span className="text-xs text-slate-400">%</span>
          </p>
        </div>
        <div>
          <p className="text-[9px] uppercase tracking-wider text-slate-600">5-Mod</p>
          <p className="mt-0.5 font-mono text-lg font-bold leading-none text-white">{fiveModPct}</p>
        </div>
        {consensus.green_light && !signalUnverified && (
          <span className="ml-auto inline-flex flex-shrink-0 items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[9px] font-semibold text-emerald-400">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
            ONAY
          </span>
        )}
        {consensus.green_light && signalUnverified && (
          <span className="ml-auto inline-flex flex-shrink-0 items-center gap-1 rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[9px] font-semibold text-amber-300">
            UNVERIFIED
          </span>
        )}
      </div>

      <div className="space-y-1.5">
        {MODULES.map((module) => {
          const score = consensus.module_scores[module];
          const pct = Math.min(100, Math.max(0, Math.round(score * 100)));
          return (
            <div key={module} className="flex items-center gap-2">
              <span className="w-4 shrink-0 font-mono text-[10px] font-bold text-slate-500">
                {MODULE_SHORT[module]}
              </span>
              <div className="h-1.5 flex-1 rounded-full bg-slate-700/60">
                <div
                  className={`h-1.5 rounded-full ${MODULE_BAR[module]} transition-all duration-500`}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="w-7 shrink-0 text-right font-mono text-[10px] text-slate-400">{pct}</span>
            </div>
          );
        })}
      </div>

      <button
        type="button"
        className="mt-3 flex w-full items-center justify-between text-[10px] font-semibold uppercase tracking-wider text-slate-600 transition-colors duration-150 hover:text-slate-300"
        aria-expanded={expanded}
        aria-controls={detailId}
        onClick={() => setExpanded((value) => !value)}
      >
        <span>Detay</span>
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          className={`h-3.5 w-3.5 transition-transform duration-200 ${expanded ? "rotate-180" : ""}`}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      <div
        id={detailId}
        role="region"
        aria-label={`${assetLabel} ${assetKey} detail`}
        className={`overflow-hidden transition-all duration-250 ${expanded ? "mt-3 max-h-[72rem]" : "max-h-0"}`}
      >
        <div className="space-y-3 border-t border-slate-700/50 pt-3">
          {consensus.confidence_interval && (
            <p className="font-mono text-[10px] text-slate-400">
              CI [{consensus.confidence_interval[0].toFixed(1)}, {consensus.confidence_interval[1].toFixed(1)}]
            </p>
          )}

          <div className="grid grid-cols-1 gap-y-1">
            {(Object.entries(consensus.criteria) as [string, boolean][]).map(([key, pass]) => (
              <div key={key} className="flex items-center gap-1.5">
                <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${pass ? "bg-emerald-400" : "bg-rose-400"}`} />
                <span className="truncate text-[9px] capitalize text-slate-500">{key.replace(/_/g, " ")}</span>
                <span className={`ml-auto font-mono text-[9px] ${pass ? "text-emerald-500" : "text-rose-500"}`}>
                  {pass ? "OK" : "NO"}
                </span>
              </div>
            ))}
          </div>

          {consensus.failed_criteria.length > 0 && (
            <p className="text-[10px] leading-5 text-rose-400">
              Failed: {consensus.failed_criteria.map((item) => item.replace(/_/g, " ")).join(" | ")}
            </p>
          )}

          {topLevelWarnings.length > 0 && (
            <div className="space-y-1 rounded-xl border border-amber-500/20 bg-amber-500/5 p-2">
              {topLevelWarnings.map((warning) => (
                <p key={warning} className="text-[10px] leading-4 text-amber-200">
                  {warning}
                </p>
              ))}
            </div>
          )}

          <div className="grid grid-cols-1 gap-2">
            {moduleSourceEntries.map(([module, moduleSource]) => renderModuleSourceMeta(module, moduleSource))}
          </div>
        </div>
      </div>
    </div>
  );
};
