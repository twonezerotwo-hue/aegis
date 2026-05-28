/**
 * components/layout/Toast.tsx
 * AEGIS v7.0 — Premium slide-in toast notifications
 * Slide-in from right (300ms), auto-dismiss 4s, hover-pause, manual close.
 */

import React, { useEffect, useMemo, useRef, useState } from "react";

export type ToastTone = "success" | "error" | "warning" | "info";

export interface ToastItem {
  id: number;
  title: string;
  message: string;
  tone: ToastTone;
}

interface ToastProps {
  toasts: ToastItem[];
  onDismiss: (id: number) => void;
}

const TONE_BORDER: Record<ToastTone, string> = {
  success: "border-emerald-500/30",
  error:   "border-rose-500/30",
  warning: "border-amber-500/30",
  info:    "border-sky-500/30",
};

const TONE_BG: Record<ToastTone, string> = {
  success: "bg-emerald-500/8",
  error:   "bg-rose-500/8",
  warning: "bg-amber-500/8",
  info:    "bg-sky-500/8",
};

const TONE_DOT: Record<ToastTone, string> = {
  success: "bg-emerald-400",
  error:   "bg-rose-400",
  warning: "bg-amber-400",
  info:    "bg-sky-400",
};

const TONE_TITLE: Record<ToastTone, string> = {
  success: "text-emerald-200",
  error:   "text-rose-200",
  warning: "text-amber-200",
  info:    "text-sky-200",
};

const AUTO_DISMISS_MS = 4000;

interface SingleToastProps {
  item: ToastItem;
  onDismiss: (id: number) => void;
}

const SingleToast: React.FC<SingleToastProps> = ({ item, onDismiss }) => {
  const [visible, setVisible] = useState(false);
  const [hovered, setHovered] = useState(false);
  const timerRef = useRef<ReturnType<typeof window.setTimeout> | null>(null);

  // Animate in on mount
  useEffect(() => {
    const frame = window.requestAnimationFrame(() => setVisible(true));
    return () => window.cancelAnimationFrame(frame);
  }, []);

  // Auto-dismiss (paused on hover)
  useEffect(() => {
    if (hovered) {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      return;
    }
    timerRef.current = window.setTimeout(() => dismiss(), AUTO_DISMISS_MS);
    return () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    };
  }, [hovered]); // eslint-disable-line react-hooks/exhaustive-deps

  const dismiss = () => {
    setVisible(false);
    window.setTimeout(() => onDismiss(item.id), 300);
  };

  return (
    <div
      role="status"
      aria-live="polite"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className={`pointer-events-auto overflow-hidden rounded-2xl border shadow-2xl shadow-slate-950/60
        backdrop-blur-md transition-all duration-300 ease-out
        ${TONE_BORDER[item.tone]} ${TONE_BG[item.tone]}
        ${visible ? "translate-x-0 opacity-100" : "translate-x-8 opacity-0"}`}
    >
      {/* Progress bar */}
      <div
        className={`h-[2px] ${TONE_DOT[item.tone]} transition-all ease-linear ${
          visible && !hovered ? "w-0" : "w-full"
        }`}
        style={{
          transitionDuration: visible && !hovered ? `${AUTO_DISMISS_MS}ms` : "0ms",
        }}
      />

      <div className="flex items-start gap-3 p-4">
        <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${TONE_DOT[item.tone]}`} />
        <div className="min-w-0 flex-1">
          <p className={`text-sm font-semibold ${TONE_TITLE[item.tone]}`}>{item.title}</p>
          <p className="mt-1 text-xs leading-5 text-slate-300/90">{item.message}</p>
        </div>
        <button
          type="button"
          onClick={dismiss}
          aria-label="Bildirimi kapat"
          className="rounded-md border border-white/10 px-2 py-1 text-[11px] font-medium text-slate-400
            transition-colors hover:border-white/20 hover:text-white"
        >
          ✕
        </button>
      </div>
    </div>
  );
};

export const Toast: React.FC<ToastProps> = ({ toasts, onDismiss }) => {
  const ids = useMemo(() => toasts.map((t) => t.id), [toasts]);
  void ids; // keep deps stable

  if (toasts.length === 0) return null;

  return (
    <div className="pointer-events-none fixed bottom-20 right-4 z-50 flex w-[340px] max-w-[calc(100vw-2rem)] flex-col gap-2 sm:bottom-4">
      {toasts.map((toast) => (
        <SingleToast key={toast.id} item={toast} onDismiss={onDismiss} />
      ))}
    </div>
  );
};
