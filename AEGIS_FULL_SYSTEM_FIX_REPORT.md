# AEGIS Full System Fix Report

**Finalized:** 2026-05-28 05:54 UTC  
**Scope:** `C:\Users\twone\Desktop\aegis_codex`  
**Version:** AEGIS v7.2

---

## Executive Summary

All system fix phases completed and verified. Root problems were:

1. `aegis-dashboard-backend` was running from stale `aegis_clean_v71-dashboard-backend` image — hardcoded market values were labelled "live" with no data provenance fields
2. `services/market_data.py` did not exist — there was no real API integration
3. Cross-network Docker isolation blocked the new container from reaching sentinel/consensus/analyzer
4. `main.py` crashed on startup due to `aegis_core_routes` path assumption failing inside the container
5. Optimizer tab was visible in the UI with no business logic gating

All five issues resolved. `/api/macro` returns `data_status: LIVE`, `verified: true`, all 11 fields from real sources.

---

## Fix 1 — Docker Image Correction

**Problem:** `aegis-dashboard-backend` ran from `aegis_clean_v71-dashboard-backend` (old stack image). The new code in `aegis_codex/dashboard_react/backend/` was never active.

**Resolution:**
```bash
cd C:\Users\twone\Desktop\aegis_codex
docker compose build dashboard-backend
docker compose up -d dashboard-backend
docker compose build dashboard-frontend
docker compose up -d dashboard-frontend
```

**Verified result:**
- `aegis-dashboard-backend` → image: `aegis_codex-dashboard-backend`
- `aegis-dashboard-frontend` → image: `aegis_codex-dashboard-frontend`

---

## Fix 2 — Cross-Network Isolation

**Problem:** New containers on `aegis_codex_aegis_network` could not reach `sentinel-api`, `consensus-api`, `analyzer-ai` which are on `aegis_clean_v71_aegis_network`.

**Runtime fix:**
```bash
docker network connect aegis_clean_v71_aegis_network aegis-dashboard-backend
docker network connect aegis_clean_v71_aegis_network aegis-dashboard-frontend
```

**Persistent fix (`docker-compose.yml`):**
```yaml
networks:
  aegis_network:
    driver: bridge
  aegis_clean_v71_aegis_network:
    external: true
```
Both services now declare both networks — survives `docker compose up` restarts.

**Verified result:**
- `aegis-dashboard-backend` networks: `aegis_codex_aegis_network`, `aegis_clean_v71_aegis_network`
- `aegis-dashboard-frontend` networks: `aegis_codex_aegis_network`, `aegis_clean_v71_aegis_network`

---

## Fix 3 — main.py Startup Crash

**Problem:** `from routes import aegis_core_routes` failed with `IndexError: list index out of range` at `parents[3]` — the path inside the container only had 3 levels.

**Resolution (`main.py`):** Changed hard import to optional:
```python
try:
    from routes import aegis_core_routes as _aegis_core_routes_mod
    _aegis_core_available = True
except Exception as _aegis_core_import_err:
    logger.warning("aegis_core_routes unavailable: %s", _aegis_core_import_err)
    _aegis_core_routes_mod = None
    _aegis_core_available = False
```

Container now starts cleanly. `aegis_core_routes` is logged as a warning and skipped.

---

## Fix 4 — Real Market Data (services/market_data.py)

**Created:** `dashboard_react/backend/services/market_data.py`

| Field | Source | Auth |
|-------|--------|------|
| DXY, VIX, US10Y, Brent, XAU, HG | yfinance (`yf.download`) | No key required |
| BTC.D, USDT.D | CoinGecko `/api/v3/global` | No key required |

Implementation:
- yfinance runs via `asyncio.to_thread` (non-blocking)
- CoinGecko via `httpx.AsyncClient` (async)
- Both fetched concurrently via `asyncio.gather`
- In-memory cache, TTL 60 seconds
- Each field returns canonical dict: `{value, source, timestamp, verified, fallback_used}`
- Graceful fallback on any failure — never crashes, always returns a value

Added `yfinance>=0.2.40` to `requirements.txt`.

---

## Fix 5 — Canonical Macro Endpoint (routes/macro.py)

Rewrote `dashboard_react/backend/routes/macro.py` to AEGIS v7.2 specification.

**Before (old image):** Returned hardcoded values from Sentinel's `macro_snapshot`, labelled `source: "sentinel-ai"`, `fallback: false` — even when Sentinel was using hardcoded data itself. No `data_status`, no `verified`, no per-field provenance.

**After (current):** Full field-level data provenance contract:

| Field | Meaning |
|-------|---------|
| `data_status` | `LIVE` / `PARTIAL_FALLBACK` / `FALLBACK` |
| `verified` | `true` only when ALL fields from live sources |
| `live` | alias of `verified` |
| `fallback_used` | `true` if any field is hardcoded |
| `fallback_fields` | sorted list of fields using hardcoded values |
| `verified_fields` | sorted list of fields from live sources |
| `field_sources` | `{field: source_string}` — frontend-compatible |
| `field_provenance` | `{field: {source, verified, fallback_used, timestamp}}` — full canonical |
| `warning` | human-readable summary when degraded |

Regime derivation: when Sentinel doesn't return explicit `regime`, system derives it from `regime_probability_distribution` by selecting the max-probability key.

Allocation plan gated: `fallback_illustrative` profile forced when `data_status != "LIVE"` — no rebalance approval language shown to user.

---

## Fix 6 — Optimizer Tab Removal (Dashboard.tsx)

Removed from `dashboard_react/frontend/src/pages/Dashboard.tsx`:
- `import { OptimizerCard } from "../components/OptimizerCard"`
- `"optimizer"` from `TabType` union
- `{ id: "optimizer", label: "Optimizer", icon: "⚙️" }` from tabs array
- Optimizer render block

No backend files modified. `OptimizerCard.tsx`, optimizer routes, and `aegis-optimizer` container unchanged.

---

## Test Results

### Backend (pytest)
```
25 passed, 0 failed — 1.04s
```

| File | Passed |
|------|--------|
| test_asset_consensus_provenance_static.py | 4/4 |
| test_dashboard_partial_fallback_render_static.py | 7/7 |
| test_frontend_allocation_static.py | 3/3 |
| test_macro_fallback_metadata.py | 3/3 |
| test_portfolio_allocator_horizon.py | 8/8 |

`test_macro_fallback_metadata.py` was updated to match the v7.2 API contract — tests now mock `fetch_market_data` properly and assert the correct source strings.

### TypeScript
```
tsc --noEmit: 0 errors
```

### Frontend Build
```
✓ built in 6.50s — 932 modules — 0 errors
```

---

## Runtime Verification (2026-05-28 05:54 UTC)

### Health Endpoints

| Endpoint | Response |
|----------|----------|
| http://localhost:8502/health | `{"status":"healthy","service":"aegis-dashboard-api"}` |
| http://localhost:8005/health | `{"status":"healthy","service":"consensus-engine"}` |
| http://localhost:8007/health | `{"status":"healthy","service":"analyzer-ai"}` |
| http://localhost:3001 | HTTP 200 |
| http://localhost:3001/v2 | HTTP 200 |
| http://localhost:8000/aegis-core/health | Not deployed (no container on port 8000) |

### Macro Endpoint

`GET http://localhost:8502/api/macro?horizon=medium`

```
status          : ok
data_status     : LIVE
verified        : True
live            : True
fallback_used   : False
fallback_fields : []
source          : market_data_live
sentinel_ok     : True
warning         : None
allocation_profile: balanced
regime          : NORMALIZATION
```

### Verified Fields

| Field | Value | Source |
|-------|-------|--------|
| DXY | 99.42 | yfinance:DX-Y.NYB |
| VIX | 16.29 | yfinance:^VIX |
| US10Y | 4.481% | yfinance:^TNX |
| Brent | 95.08 | yfinance:BZ=F |
| XAU | 4419.7 | yfinance:GC=F |
| HG | 6.296 | yfinance:HG=F |
| BTC.D | 57.70% | coingecko_public:btc_dominance |
| USDT.D | 7.48% | coingecko_public:usdt_dominance |
| event_risk_score | 0.471 | sentinel-ai |
| hours_to_event | 48 | sentinel-ai |
| regime | NORMALIZATION | sentinel-ai:regime_probability_distribution |

---

## Container State

| Container | Image | Port | Status |
|-----------|-------|------|--------|
| aegis-dashboard-backend | **aegis_codex-dashboard-backend** | 8502 | healthy |
| aegis-dashboard-frontend | **aegis_codex-dashboard-frontend** | 3001 | healthy |
| aegis-sentinel | aegis_clean_v71-sentinel-api | 8004 | healthy |
| aegis-consensus | aegis_clean_v71-consensus-api | 8005 | healthy |
| aegis-analyzer | aegis_clean_v71-analyzer-ai | 8007 | healthy |
| aegis-optimizer | aegis_clean_v71-optimizer-api | 8008 | healthy |
| aegis-nginx | nginx:alpine | 8080 | healthy |
| aegis-grafana | grafana/grafana:latest | 3000 | healthy |
| aegis-redis | redis:7-alpine | 6379 | healthy |
| aegis-postgres | postgres:15-alpine | 5432 | healthy |
| aegis-macro-bridge | aegis_clean_v71-macro-bridge | 8503 | healthy |

---

## Files Modified

| File | Change |
|------|--------|
| `dashboard_react/backend/requirements.txt` | Added `yfinance>=0.2.40` |
| `dashboard_react/backend/services/market_data.py` | Created — real API fetcher |
| `dashboard_react/backend/routes/macro.py` | Rewritten — v7.2 provenance contract |
| `dashboard_react/backend/main.py` | aegis_core_routes import made optional |
| `dashboard_react/frontend/src/pages/Dashboard.tsx` | Optimizer tab removed |
| `dashboard_react/backend/tests/test_macro_fallback_metadata.py` | Updated to v7.2 contract |
| `docker-compose.yml` | External network + both networks on dashboard services |

---

## Hard Rules Compliance

- No live trading executed
- No broker execution code added or modified
- No system-wide or global settings changed
- All work confined to `C:\Users\twone\Desktop\aegis_codex`
- Optimizer backend untouched — UI-only removal
- No secrets, tokens, or API keys written to any file or report
