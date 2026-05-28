# AEGIS v7.6 — Step 3 Prep: V1/V2 Incompatibility Matrix

## Scanned File Inventory

### V1 Components (Legacy)

| File | Location | API Client | Type System |
|------|----------|-----------|-------------|
| `Backtest.tsx` | `pages/Backtest.tsx` | `backtestApi` from `services/backtestApi.ts` | `BacktestResult`, `AIBacktestParams` |
| `Backtest.tsx.backup` | `archive/Backtest.tsx.backup` | Same as above | Same as above |
| `Dashboard.tsx` | `pages/Dashboard.tsx` (via `App.tsx` fallback) | `useMetrics`, `useLiveFeed` | Custom metrics types |
| `Dashboard.tsx.backup` | `archive/Dashboard.tsx.backup` | Same hooks | Same types |

### V2 Components (Current)

| File | Location | API Client | Type System |
|------|----------|-----------|-------------|
| `BacktestV2.tsx` | `pages/BacktestV2.tsx` (lazy-loaded) | Direct `fetch` to `/backtest/run` | `BacktestResultV2`, `BacktestParamsV2` from `types/backtestV2.ts` |
| `DashboardV2.tsx` | `pages/DashboardV2.tsx` | `fetchConsensus`, `fetchMacro` from `services/apiV2.ts` | `ConsensusResponse`, `MacroResponse` from `types/dashboardV2.ts` |

### API Clients

| File | Version | Transport | Base URL |
|------|---------|-----------|----------|
| `services/backtestApi.ts` | V1 | `fetch` wrapper | `VITE_API_URL \|\| localhost:8502` |
| `services/apiV2.ts` | V2 | `axios` + typed parsers | `VITE_API_URL \|\| localhost:8502` (gateway), `VITE_ANALYZER_API_URL`, `VITE_CONSENSUS_API_URL` |

### Type Definitions

| File | Version | Key Interfaces |
|------|---------|----------------|
| `types/backtestV2.ts` | V2 | `BacktestResultV2`, `BacktestParamsV2`, `BacktestModuleScores`, `BacktestTrade`, `PortfolioAllocationEntry` |
| `types/dashboardV2.ts` | V2 | `ConsensusResponse`, `MacroResponse`, `ModuleScores`, `ModuleWeights`, `CBRSummary`, `MultiTfSummary`, `SentinelSummary` |
| (inline in `backtestApi.ts`) | V1 | `BacktestResult`, `AIBacktestParams`, `BacktestMetrics`, `Trade` |

### Routing (App.tsx)

| Route | Component | Version |
|-------|-----------|---------|
| `/v2/backtest` | `BacktestV2` (lazy) | V2 |
| `/v2` or `/v2/*` | `DashboardV2` | V2 |
| `/*` (default) | `Dashboard` (V1) | V1 |

---

## Preliminary Comparison: Known Incompatibilities

### API Contract: POST /backtest/run

| Field | V1 (`AIBacktestParams`) | V2 (`BacktestParamsV2`) | Compatible? |
|-------|------------------------|------------------------|-------------|
| `symbol` | ✅ | ✅ | ✅ Same |
| `timeframe` | ✅ | ✅ | ✅ Same |
| `start_date` | ✅ | ✅ | ✅ Same |
| `end_date` | ✅ | ✅ | ✅ Same |
| `horizon` | ❌ missing | ✅ optional | ✅ V2 superset |
| `initial_capital` | ❌ missing | ✅ optional | ✅ V2 superset |
| `risk_per_trade` | ❌ missing | ✅ optional | ✅ V2 superset |
| `use_live_data` | ❌ missing | ✅ optional | ✅ V2 superset |
| `include_fees` | ❌ missing | ✅ optional | ✅ V2 superset |

### Response Contract: BacktestResult vs BacktestResultV2

| Field | V1 (`BacktestResult`) | V2 (`BacktestResultV2`) | Breaking? |
|-------|----------------------|------------------------|-----------|
| `success` | ✅ | ✅ | ✅ Same |
| `symbol` | ✅ | ✅ | ✅ Same |
| `timeframe` | ✅ | ✅ | ✅ Same |
| `strategy` | ✅ | ❌ removed | ⚠️ V1 reads it |
| `backtest_id` | ❌ missing | ✅ required | ⚠️ V1 ignores it |
| `date_range` | ✅ | ✅ | ✅ Same |
| `metrics.pnl` | ✅ (same shape) | ✅ | ✅ Same |
| `metrics.win_loss` | ✅ | ✅ | ✅ Same |
| `metrics.drawdown` | ✅ | ✅ | ✅ Same |
| `metrics.sharpe_ratio` | ✅ | ✅ | ✅ Same |
| `metrics.sortino_ratio` | ✅ | ✅ | ✅ Same |
| `metrics.initial_capital` | ✅ | ✅ | ✅ Same |
| `metrics.final_capital` | ✅ | ✅ | ✅ Same |
| `total_trades` | ✅ | ✅ | ✅ Same |
| `trades` | ✅ (optional) | ✅ (required) | ⚠️ V1 treats as optional |
| `data_points` | ✅ | ✅ | ✅ Same |
| `generated_at` | ✅ | ✅ (optional) | ✅ Same |
| `module_scores` | ❌ missing | ✅ required (5 modules) | ⚠️ V1 won't render |
| `score_attribution` | ❌ missing | ✅ optional | ✅ V1 ignores |
| `portfolio_allocation` | ❌ missing | ✅ optional | ✅ V1 ignores |
| `horizon` | ❌ missing | ✅ optional | ✅ V1 ignores |
| `regime` | ❌ missing | ✅ optional | ✅ V1 ignores |

### State Management

| Pattern | V1 | V2 |
|---------|----|----|
| Data fetching | `useMetrics` (polling hook) + `useLiveFeed` (SSE) | `fetchConsensus`/`fetchMacro` (apiV2) + `useRealTimeFeed` (SSE v2) |
| Global state | `useLiveFeed` local state | `ConsensusStoreProvider` (Context) + `useConsensusStore` |
| Backtest state | Component-local `useState` | Component-local `useState` + `useRef` + AbortController |
| HTTP client | `fetch` wrapper | `axios` instances (gateway, analyzer, consensus) |

### Component Props

| Component | V1 Props | V2 Equivalent | Breaking? |
|-----------|---------|---------------|-----------|
| Backtest page | None (self-contained) | None (self-contained) | ✅ Compatible |
| Dashboard | `useMetrics(symbol, tf, interval)` | `VadeProvider` + `useVadeContext()` | ❌ Different paradigm |
| Metric cards | `{metric: MetricData}` | `MetricCardV2 {value, label, trend, ...}` | ❌ Different props |
| Score display | N/A | `ScoreBar {value, label, weight, attribution}` | N/A (V2 only) |

---

## Step 3 Output Template

Target file: `audit_reports/03_v1_v2_incompatibility_matrix.md`

### Sections:
1. Executive Summary (counts: incompatible, breaking, backward-compatible)
2. API Contract Matrix (request + response field-by-field)
3. Type System Comparison (V1 interfaces vs V2 interfaces)
4. Component Mapping (V1 → V2 equivalents, new V2-only components)
5. State Management Migration Path
6. Deprecation Strategy (timeline + adapter approach)

---

*Prep completed: 2026-04-20*
