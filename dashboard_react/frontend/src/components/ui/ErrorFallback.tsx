import React from "react";

interface ErrorFallbackProps {
  title: string;
  message: string;
  details?: string;
  actionLabel?: string;
  onRetry?: () => void;
}

export const ErrorFallback: React.FC<ErrorFallbackProps> = ({
  title,
  message,
  details,
  actionLabel = "Tekrar dene",
  onRetry,
}) => {
  return (
    <div className="rounded-2xl border border-rose-500/20 bg-rose-500/10 p-5 shadow-lg shadow-slate-950/20">
      <div className="flex items-start gap-4">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-rose-500/20 bg-slate-900 text-rose-300">
          <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" stroke="currentColor" strokeWidth="1.8">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v4m0 4h.01M10.29 3.86l-8 14A1 1 0 003.15 19h17.7a1 1 0 00.86-1.5l-8-14a1 1 0 00-1.72 0z" />
          </svg>
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-rose-300">{title}</p>
          <p className="mt-3 text-sm leading-6 text-rose-50/90">{message}</p>
          <p className="mt-2 text-xs leading-6 text-rose-100/80">
            {details ?? "Veri kaynagi gecici olarak ulasilamaz olabilir. Sistem son bilinen snapshot uzerinden calismaya devam eder."}
          </p>
          <div className="mt-3 rounded-xl border border-rose-400/15 bg-slate-950/40 p-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-rose-200">Neler deneyebilirsiniz</p>
            <ul className="mt-2 list-disc space-y-1 pl-4 text-xs leading-5 text-rose-100/85">
              <li>Bagli servislerin ayakta oldugunu dogrulayin.</li>
              <li>Bir kac saniye sonra yeniden istek gonderin.</li>
              <li>Sorun suruyorsa backend loglarini kontrol edin.</li>
            </ul>
          </div>
          {onRetry ? (
            <button
              type="button"
              onClick={onRetry}
              className="mt-4 rounded-xl border border-rose-400/20 bg-slate-950/50 px-4 py-2 text-sm font-medium text-rose-100 transition-colors hover:border-rose-300/30 hover:bg-slate-900"
            >
              {actionLabel}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
};