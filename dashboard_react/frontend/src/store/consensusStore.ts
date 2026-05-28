/**
 * store/consensusStore.ts
 * AEGIS v7.0 — Consensus state store (Context + useReducer)
 *
 * Slices: decision (v7 ConsensusResponse), weights, attribution, learningStatus
 * No Zustand — uses React Context to avoid package.json changes.
 *
 * Usage:
 *   Wrap your tree with <ConsensusStoreProvider>
 *   Access state via useConsensusStore()
 */

import React, { createContext, useContext, useReducer } from "react";
import type { ConsensusResponse, WeightsResponse, TradeAttributionResult } from "../types/dashboardV2";

// ── Learning status slice ─────────────────────────────────────────────────────

export interface LearningStatus {
  drift_total: number;
  drift_limit: number;
  drift_frozen: boolean;
  backup_exists: boolean;
  week_start: string;
  last_update_status: "updated" | "frozen" | "rollback" | "rollback_failed" | "error" | null;
}

// ── Full state shape ──────────────────────────────────────────────────────────

export interface ConsensusState {
  decision: ConsensusResponse | null;
  decisionLoading: boolean;
  decisionError: string | null;

  weights: WeightsResponse | null;
  weightsLoading: boolean;
  weightsError: string | null;

  attribution: TradeAttributionResult | null;
  attributionLoading: boolean;
  attributionError: string | null;

  learningStatus: LearningStatus | null;
}

const initialState: ConsensusState = {
  decision: null,
  decisionLoading: false,
  decisionError: null,

  weights: null,
  weightsLoading: false,
  weightsError: null,

  attribution: null,
  attributionLoading: false,
  attributionError: null,

  learningStatus: null,
};

// ── Actions ───────────────────────────────────────────────────────────────────

export type ConsensusAction =
  | { type: "SET_DECISION_LOADING"; payload: boolean }
  | { type: "SET_DECISION"; payload: ConsensusResponse }
  | { type: "SET_DECISION_ERROR"; payload: string }
  | { type: "SET_WEIGHTS_LOADING"; payload: boolean }
  | { type: "SET_WEIGHTS"; payload: WeightsResponse }
  | { type: "SET_WEIGHTS_ERROR"; payload: string }
  | { type: "SET_ATTRIBUTION_LOADING"; payload: boolean }
  | { type: "SET_ATTRIBUTION"; payload: TradeAttributionResult }
  | { type: "SET_ATTRIBUTION_ERROR"; payload: string }
  | { type: "PATCH_LEARNING_STATUS"; payload: Partial<LearningStatus> };

// ── Reducer ───────────────────────────────────────────────────────────────────

function consensusReducer(state: ConsensusState, action: ConsensusAction): ConsensusState {
  switch (action.type) {
    case "SET_DECISION_LOADING":
      return { ...state, decisionLoading: action.payload };
    case "SET_DECISION":
      return { ...state, decision: action.payload, decisionLoading: false, decisionError: null };
    case "SET_DECISION_ERROR":
      return { ...state, decisionLoading: false, decisionError: action.payload };

    case "SET_WEIGHTS_LOADING":
      return { ...state, weightsLoading: action.payload };
    case "SET_WEIGHTS": {
      const w = action.payload;
      return {
        ...state,
        weights: w,
        weightsLoading: false,
        weightsError: null,
        learningStatus: {
          drift_total: w.drift_total,
          drift_limit: w.drift_limit,
          drift_frozen: w.drift_frozen,
          backup_exists: w.backup_exists,
          week_start: w.week_start ?? "",
          last_update_status: state.learningStatus?.last_update_status ?? null,
        },
      };
    }
    case "SET_WEIGHTS_ERROR":
      return { ...state, weightsLoading: false, weightsError: action.payload };

    case "SET_ATTRIBUTION_LOADING":
      return { ...state, attributionLoading: action.payload };
    case "SET_ATTRIBUTION":
      return { ...state, attribution: action.payload, attributionLoading: false, attributionError: null };
    case "SET_ATTRIBUTION_ERROR":
      return { ...state, attributionLoading: false, attributionError: action.payload };

    case "PATCH_LEARNING_STATUS":
      return {
        ...state,
        learningStatus: {
          drift_total: 0,
          drift_limit: 0.15,
          drift_frozen: false,
          backup_exists: false,
          week_start: "",
          last_update_status: null,
          ...(state.learningStatus ?? {}),
          ...action.payload,
        },
      };

    default:
      return state;
  }
}

// ── Context ────────────────────────────────────────────────────────────────────

interface ConsensusStoreContextValue {
  state: ConsensusState;
  dispatch: React.Dispatch<ConsensusAction>;
}

const ConsensusStoreContext = createContext<ConsensusStoreContextValue | null>(null);
ConsensusStoreContext.displayName = "ConsensusStore";

// ── Provider ──────────────────────────────────────────────────────────────────

export const ConsensusStoreProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [state, dispatch] = useReducer(consensusReducer, initialState);
  return React.createElement(
    ConsensusStoreContext.Provider,
    { value: { state, dispatch } },
    children
  );
};

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useConsensusStore(): ConsensusStoreContextValue {
  const ctx = useContext(ConsensusStoreContext);
  if (ctx === null) {
    throw new Error("useConsensusStore must be used within <ConsensusStoreProvider>");
  }
  return ctx;
}
