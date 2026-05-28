/**
 * components/ui/ErrorBoundary.tsx
 * AEGIS v7.0 — React class-based error boundary
 * Catches render errors in child tree, shows fallback with retry capability.
 * Use: <ErrorBoundary fallback="Panel crashed"><Component /></ErrorBoundary>
 */

import React from "react";

interface ErrorBoundaryProps {
  children: React.ReactNode;
  /** Short label shown in the fallback title bar */
  fallback?: string;
}

interface ErrorBoundaryState {
  hasError: boolean;
  errorMessage: string;
  errorCount: number;
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, errorMessage: "", errorCount: 0 };
  }

  static getDerivedStateFromError(error: unknown): Partial<ErrorBoundaryState> {
    const msg = error instanceof Error ? error.message : String(error);
    return { hasError: true, errorMessage: msg };
  }

  componentDidCatch(error: unknown, info: React.ErrorInfo) {
    console.error("[ErrorBoundary] Caught render error:", error, info.componentStack);
  }

  private handleReset = () => {
    this.setState((prev) => ({
      hasError: false,
      errorMessage: "",
      errorCount: prev.errorCount + 1,
    }));
  };

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    const { fallback = "Panel" } = this.props;

    return (
      <div
        className="rounded-2xl border border-amber-500/30 bg-amber-500/5 p-4 shadow-md shadow-slate-950/20"
        role="alert"
      >
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-amber-500/30 bg-slate-900 text-amber-400">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="h-5 w-5">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v4m0 4h.01M10.29 3.86l-8 14A1 1 0 003.15 19h17.7a1 1 0 00.86-1.5l-8-14a1 1 0 00-1.72 0z" />
            </svg>
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-400">
              {fallback} render hatası
            </p>
            <p className="mt-1 text-xs text-slate-400 line-clamp-2">{this.state.errorMessage}</p>
            <button
              type="button"
              onClick={this.handleReset}
              className="mt-3 rounded-lg border border-amber-500/20 bg-slate-900/60 px-3 py-1.5 text-xs font-medium text-amber-300
                transition-colors hover:border-amber-500/40 hover:bg-slate-800"
            >
              Tekrar dene
            </button>
          </div>
        </div>
      </div>
    );
  }
}
