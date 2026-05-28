# CODEX_PROJECT_STATE.md

## Current completed phases

- Phase 1: risky files copied to quarantine.
- Phase 2: `aegis_core` sidecar package created.
- Phase 3: old runtime decision/execution/fallback audit completed.
- Phase 4: safe `/aegis-core/*` endpoints added.
- Phase 5: Data Integrity Gate added.
- Phase 6: Risk Engine + Kill Switch wrappers added.
- Phase 7: OwnerBrief + Audit Record wrappers added.
- Phase 8: E-yAy integration contract + legacy isolation docs added.
- Dashboard stabilization patch: V2 selected horizon/timeframe now forwards through HTTP/SSE; fake fresh timestamps removed; data freshness badges added.

## Current runtime facts

- `http://localhost:3001` = React dashboard.
- `http://127.0.0.1:8000` = FastAPI backend with safe `/aegis-core/*`.
- `http://127.0.0.1:8005` = `consensus-api` when Docker service is running.
- `http://127.0.0.1:8007` = `analyzer-ai` when Docker service is running.
- `http://127.0.0.1:8502` = `dashboard-backend` when Docker service is running.

Known issue:

- Dashboard V2 may show hardcoded macro fallback values from `dashboard_react/backend/routes/macro.py`.
- These values must be clearly labeled fallback / not verified.

## Current priority

Before further E-yAy work:

1. Stabilize dashboard.
2. Make data freshness explicit.
3. Prevent fallback/mock/static values from looking live.
4. Then connect canonical live/verified data provider later.

## Do not repeat

Do not re-audit the whole repo unless explicitly requested. Use known files and targeted patches.
