/**
 * src/context/VadeContext.tsx
 * Global yatırım vadesi (horizon) state'i.
 * AbortController: vade değiştiğinde yürüyen tüm fetch'ler iptal edilir.
 * Spec: short→4H/1D·7g·0.15 | medium→1D/4H·30g·0.25 | long→1W/1D·90g·0.40
 */

import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";

export type Vade = "short" | "medium" | "long";

interface HorizonConfig {
  activeTFs: string[];
  primaryTF: string;
  newsWindowDays: number;
  kellyFraction: number;
  volatilityLookbackDays: number;
  cbrWindowDays: number;
  tfLabel: string;
  windowLabel: string;
  kellyLabel: string;
}

export interface VadeParams extends HorizonConfig {
  vade: Vade;
  /** Alias of primaryTF — backward-compat for existing consumers. */
  timeframe: string;
  /** Current AbortController for in-flight fetch management. */
  abortController: AbortController;
  /** Change horizon; automatically aborts in-flight requests. */
  setHorizon: (v: Vade) => void;
  /** Alias of setHorizon — backward-compat. */
  setVade: (v: Vade) => void;
}

// ── Spec table ────────────────────────────────────────────────────────────────
const HORIZON_MAP: Record<Vade, HorizonConfig> = {
  short: {
    activeTFs:               ["4h", "1d"],
    primaryTF:               "4h",
    newsWindowDays:          7,
    kellyFraction:           0.15,
    volatilityLookbackDays:  14,
    cbrWindowDays:           90,
    tfLabel:                 "TF: 4H/1D",
    windowLabel:             "Pencere: 7g",
    kellyLabel:              "Kelly: 0.15",
  },
  medium: {
    activeTFs:               ["1d", "4h"],
    primaryTF:               "1d",
    newsWindowDays:          30,
    kellyFraction:           0.25,
    volatilityLookbackDays:  30,
    cbrWindowDays:           180,
    tfLabel:                 "TF: 1D/4H",
    windowLabel:             "Pencere: 30g",
    kellyLabel:              "Kelly: 0.25",
  },
  long: {
    activeTFs:               ["1w", "1d"],
    primaryTF:               "1w",
    newsWindowDays:          90,
    kellyFraction:           0.40,
    volatilityLookbackDays:  60,
    cbrWindowDays:           730,
    tfLabel:                 "TF: 1W/1D",
    windowLabel:             "Pencere: 90g",
    kellyLabel:              "Kelly: 0.40",
  },
};

const VadeContext = createContext<VadeParams | null>(null);
VadeContext.displayName = "VadeContext";

export const VadeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [vade, setVadeState] = useState<Vade>("medium");

  // AbortController — mutable ref so abort() is callable inside callbacks
  const controllerRef = useRef<AbortController>(new AbortController());
  const [abortController, setAbortController] = useState<AbortController>(
    () => controllerRef.current
  );

  const setHorizon = useCallback((v: Vade) => {
    // Abort all in-flight requests for previous horizon
    controllerRef.current.abort();
    const next = new AbortController();
    controllerRef.current = next;
    setAbortController(next);
    setVadeState(v);
    // Push through microtask queue so batched React state updates
    // have settled before external listeners fire.
    setTimeout(
      () => window.dispatchEvent(new CustomEvent("aegis:horizon-changed", { detail: v })),
      0
    );
  }, []);

  const cfg = HORIZON_MAP[vade];

  const value = useMemo<VadeParams>(
    () => ({
      vade,
      ...cfg,
      timeframe:      cfg.primaryTF,   // backward-compat
      abortController,
      setHorizon,
      setVade: setHorizon,             // backward-compat alias
    }),
    [vade, cfg, abortController, setHorizon]
  );

  return <VadeContext.Provider value={value}>{children}</VadeContext.Provider>;
};

export const useVadeContext = (): VadeParams => {
  const ctx = useContext(VadeContext);
  if (ctx === null) {
    throw new Error("useVadeContext must be used within <VadeProvider>");
  }
  return ctx;
};
