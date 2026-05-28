# AEGIS v7.5 Audit — Step 1: Project Structure & Import Analysis

**Date:** 2026-04-20  
**Scope:** Full project scan — .py, .tsx, .ts files  

---

## 1.1 File Inventory

| Category | Count |
|----------|-------|
| Python files (total) | **165** |
| Python — dashboard_react/backend/ | 16 |
| Python — strategies/ (5 AI modules) | 82 |
| Python — consensus_engine/ | 24 |
| Python — macro_bridge/ | 16 |
| Python — modules/news-ai-limited/ | 21 |
| Python — tests/ + scripts/ | 12 |
| TypeScript/TSX files (total) | **74** |
| TSX — pages | 5 (Dashboard, DashboardV2, Backtest, BacktestV2, PaperTrading) |
| TSX — components | 50 |
| TS — services/hooks/types/store | 14 |

---

## 1.2 Active Routing Map

```
App.tsx
├── /v2/backtest  → BacktestV2.tsx (lazy)   ← PRIMARY backtest page
├── /v2/*         → DashboardV2.tsx          ← PRIMARY dashboard
└── / (default)   → Dashboard.tsx (V1)       ← LEGACY (embeds Backtest.tsx)
```

**PaperTrading.tsx** — imported by DashboardV2 (embedded tab), not a standalone route.

---

## 1.3 Backend Route Architecture

### Mounted Routers (main.py)
| Router | Prefix | File | Line |
|--------|--------|------|------|
| `dashboard.router` | `/api` | routes/dashboard.py | L170 |
| `paper_trading.router` | `/api/paper` | routes/paper_trading.py | L173 |
| `macro.router` | `/api` | routes/macro.py | L176 |
| `stream.router` | `/api` | routes/stream.py | L179 |
| `backtest_routes.router` | `/backtest` | routes/backtest_routes.py | L192 (startup) |

### NOT Mounted (Dead Route Files)
| File | Would-be Prefix | Status |
|------|----------------|--------|
| `routes/consensus.py` | `/api/consensus/` | **Dead** — never imported |
| `routes/live_feed.py` | `/api/live-feed` | **Dead** — superseded by stream.py |
| `routes/metrics.py` | `/api/metrics/` | **Dead** — superseded by dashboard.py |

---

## 1.4 Duplicate/Shadowed Endpoints

**main.py** (~1337 lines) contains **inline endpoint definitions** that duplicate what routers already handle. FastAPI uses first-registered-wins, so **router versions execute**; main.py inline versions are dead code.

| Endpoint | Router (Active) | main.py (Dead) |
|----------|----------------|-----------------|
| `POST /backtest/run` | backtest_routes.py L123 | main.py ~L903 |
| `GET /backtest/status` | backtest_routes.py L296 | main.py ~L1110 |
| `GET /backtest/report/{id}` | backtest_routes.py L317 | main.py ~L1138 |
| `GET /backtest/supported-timeframes` | backtest_routes.py L1230 | main.py ~L876 |
| `GET /api/metrics/touche` | dashboard.py L30 | main.py L314 |
| `GET /api/metrics/fundamental` | dashboard.py L73 | main.py L357 |
| `GET /api/metrics/quantum` | dashboard.py L116 | main.py L396 |
| `GET /api/metrics/sentinel` | dashboard.py L159 | main.py L435 |
| `GET /api/metrics/news` | dashboard.py L202 | main.py L474 |
| `GET /api/consensus` | dashboard.py L292 | main.py L596 |
| `GET /api/health` | dashboard.py L373 | main.py L681 |

**Impact:** ~500 lines of dead inline endpoints in main.py.

---

## 1.5 Duplicate Frontend Components (V1 vs V2 Pairs)

These are NOT true duplicates — they are V1 (Dashboard.tsx) vs V2 (DashboardV2.tsx) variants, but same-named files in different directories cause confusion:

| V1 (root components/) | V2 (subfolder) | Used By |
|----------------------|----------------|---------|
| `CBRMatches.tsx` | `cbr/CBRMatches.tsx` | V1: Dashboard / V2: DashboardV2 |
| `Header.tsx` | `layout/Header.tsx` | V1: Dashboard / V2: layout/GlobalHeader |
| `RegimeBadge.tsx` | `ui/RegimeBadge.tsx` | V1: Dashboard / V2: DashboardV2 |
| `ConsensusGauge.tsx` | `ui/ConsensusGauge.tsx` | V1: Dashboard / V2: DashboardV2 |
| `ExitSignalPanel.tsx` | `ui/ExitSignalPanel.tsx` | V1: Dashboard / V2: DashboardV2 |

---

## 1.6 Unused Code Inventory

### Backend — Dead Variables (main.py)
| Variable | Line | Status |
|----------|------|--------|
| `CONSENSUS_URL` | ~L200 | Declared, never referenced |
| `metrics_cache` | ~L225 | Dict declared, never read/written |
| `SYMBOLS` | ~L236 | Array declared, never referenced |
| `backtest_router_cache` | ~L133 | Set to None, never used |

### Frontend — Unused Files (never imported anywhere)
| File | Type |
|------|------|
| `hooks/useSystemState.ts` | Hook — never imported |
| `hooks/useRealTimeData.ts` | Hook — never imported |
| `components/WeightMonitor.tsx` | Component — never imported |
| `components/AttributionPanel.tsx` | Component — never imported |

### Frontend — Potentially Unused
| File | Note |
|------|------|
| `pages/Backtest.tsx` | V1 only — embedded in Dashboard.tsx (legacy) |
| `services/backtestApi.ts` | V1 backtest API — used only by Backtest.tsx (legacy) |
| `services/api.ts` | V1 API layer — used only by Dashboard.tsx (legacy) |

### Backup Files (should be removed)
- `pages/Backtest.tsx.backup`
- `pages/Dashboard.tsx.backup`

---

## 1.7 Circular Import Risk Assessment

| Risk | Path | Severity |
|------|------|----------|
| main.py ↔ backtest_routes.py cross-dependency | Each imports functions from the other | **Medium** — tight coupling hazard |
| routes/consensus.py → consensus_engine.src via sys.path.insert | Fragile path hack | **Low** — file is dead anyway |

**No actual circular imports at runtime.**

---

## 1.8 AI Module Python Structure

```
strategies/
├── touche_ai/        # Technical analysis (7 phases, scoring, EQS)
│   ├── main.py       # FastAPI :8001
│   └── src/engine/   # scoring.py, unified_optimizer.py, multi_timeframe_analyzer.py
├── fundamental_ai/   # On-chain metrics (MVRV, netflow, active addresses)
│   ├── main.py       # FastAPI :8002
│   └── src/scoring/  # onchain_scorer.py, dynamic_weight_engine.py
├── quantum_ai/       # Market microstructure (Avellaneda-Stoikov MM, VaR, funding arb)
│   ├── main.py       # FastAPI :8003
│   └── src/mm_engine/# spread_optimizer.py, skew_manager.py
├── sentinel_ai/      # Macro regime detection (DXY, VIX, US10Y, correlation)
│   ├── main.py       # FastAPI :8004
│   └── src/macro_indicators/  # dxy_monitor.py, vix_monitor.py, etc.
├── cbr_engine/       # Case-Based Reasoning (fingerprint, similarity, Qdrant)
│   ├── main.py       # FastAPI :8006
│   └── 20 modules    # fingerprint, similarity, auto_labeler, etc.
├── analyzer_ai/      # Report generation (attribution, consensus analysis)
│   └── main.py       # FastAPI :8007
└── execution_engine.py  # Binance testnet bridge (standalone, no FastAPI)
```

---

## Summary Statistics

| Metric | Value |
|--------|-------|
| Total source files | **239** (.py + .tsx + .ts) |
| Dead backend route files | **3** |
| Dead inline endpoints (main.py) | **~11 endpoints (~500 lines)** |
| Dead frontend files | **4 confirmed + 2 backups** |
| Dead backend variables | **4** |
| V1/V2 component pairs (confusing names) | **5** |
| Circular import risk | **Low-Medium (main.py ↔ backtest_routes.py)** |

---

*Step 1 Complete — awaiting approval before proceeding to Step 2 (Architecture Flow Diagram)*
