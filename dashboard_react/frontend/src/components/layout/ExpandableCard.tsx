/**
 * components/layout/ExpandableCard.tsx
 * AEGIS v7.0 — Animated expandable card wrapper
 * max-h animation, icon rotation, aria-expanded, configurable maxOpenHeight.
 */

import React, { useState } from "react";

interface ExpandableCardProps {
  title: string;
  icon: React.ReactNode;
  summary: string;
  children: React.ReactNode;
  /** Tailwind max-height class used when open. Default: "max-h-[600px]" */
  maxOpenHeight?: string;
  defaultOpen?: boolean;
}

export const ExpandableCard: React.FC<ExpandableCardProps> = ({
  title,
  icon,
  summary,
  children,
  maxOpenHeight = "max-h-[600px]",
  defaultOpen = false,
}) => {
  const [isOpen, setIsOpen] = useState<boolean>(defaultOpen);
  const panelId = React.useId();

  return (
    <div
      className={`rounded-2xl border bg-slate-900 shadow-md transition-all duration-300
        ${isOpen
          ? "border-slate-600 shadow-slate-950/40"
          : "border-slate-700/60 shadow-slate-950/20 hover:border-slate-600 hover:shadow-lg hover:shadow-slate-950/30"
        }`}
    >
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        aria-expanded={isOpen}
        aria-controls={panelId}
        className="flex w-full items-start justify-between gap-4 p-5 text-left"
      >
        <div className="flex min-w-0 items-start gap-3">
          <div
            className={`mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border shadow-inner
              transition-colors duration-200
              ${isOpen
                ? "border-sky-500/30 bg-sky-500/10 text-sky-300"
                : "border-slate-700 bg-slate-800 text-sky-400"
              }`}
          >
            {icon}
          </div>
          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">
              {title}
            </p>
            <p className="mt-1.5 text-sm leading-6 text-slate-300">{summary}</p>
          </div>
        </div>

        {/* Chevron */}
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
          className={`mt-1.5 h-4 w-4 shrink-0 text-slate-500 transition-transform duration-250 ease-in-out ${
            isOpen ? "rotate-180" : "rotate-0"
          }`}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      <div
        id={panelId}
        role="region"
        className={`overflow-hidden transition-all duration-250 ease-in-out ${
          isOpen ? maxOpenHeight : "max-h-0"
        }`}
      >
        <div className="border-t border-slate-700/60 px-5 pb-5 pt-4 text-sm text-slate-300">
          {children}
        </div>
      </div>
    </div>
  );
};
