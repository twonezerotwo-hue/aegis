import React from "react";
import clsx from "clsx";
import {
  classifyDataStatus,
  formatDataAge,
  getDataSource,
  getDataTimestamp,
  type DataStatus,
  type FreshnessLike,
  type FreshnessOptions,
} from "../../utils/dataFreshness";

interface DataStatusBadgeProps extends FreshnessOptions {
  data?: FreshnessLike;
  status?: DataStatus;
  source?: string | null;
  timestamp?: string | null;
  showDetails?: boolean;
  compact?: boolean;
  className?: string;
}

const STATUS_LABELS: Record<DataStatus, string> = {
  LIVE: "LIVE DATA",
  RECENT: "RECENT DATA",
  STALE: "STALE DATA",
  PARTIAL_FALLBACK: "PARTIAL FALLBACK",
  FALLBACK: "FALLBACK DATA",
  MOCK: "MOCK DATA",
  MISSING: "MISSING DATA",
  UNKNOWN: "UNKNOWN DATA",
};

const STATUS_CLASSES: Record<DataStatus, string> = {
  LIVE: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
  RECENT: "border-sky-500/30 bg-sky-500/10 text-sky-300",
  STALE: "border-amber-500/30 bg-amber-500/10 text-amber-300",
  PARTIAL_FALLBACK: "border-amber-400/40 bg-amber-500/10 text-amber-200",
  FALLBACK: "border-orange-500/30 bg-orange-500/10 text-orange-300",
  MOCK: "border-fuchsia-500/30 bg-fuchsia-500/10 text-fuchsia-300",
  MISSING: "border-rose-500/30 bg-rose-500/10 text-rose-300",
  UNKNOWN: "border-slate-500/30 bg-slate-500/10 text-slate-300",
};

export const DataStatusBadge: React.FC<DataStatusBadgeProps> = ({
  data,
  status,
  source,
  timestamp,
  showDetails = true,
  compact = false,
  className,
  maxAgeSeconds,
  liveAgeSeconds,
}) => {
  const resolvedStatus =
    status ?? classifyDataStatus(data, { maxAgeSeconds, liveAgeSeconds });
  const resolvedTimestamp = timestamp ?? getDataTimestamp(data);
  const resolvedSource = source ?? getDataSource(data);

  return (
    <div className={clsx("flex flex-col gap-1.5", className)}>
      <span
        className={clsx(
          "inline-flex w-fit items-center rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em]",
          STATUS_CLASSES[resolvedStatus],
          compact && "px-2 py-0.5 text-[9px]"
        )}
      >
        {STATUS_LABELS[resolvedStatus]}
      </span>
      {showDetails && (
        <div className="flex flex-wrap items-center gap-2 text-[10px] text-slate-500">
          <span>Source: {resolvedSource ?? "unknown"}</span>
          <span>
            Updated:{" "}
            {resolvedTimestamp ? formatDataAge(resolvedTimestamp) : "timestamp unavailable"}
          </span>
        </div>
      )}
    </div>
  );
};
