# AEGIS Remaining Tech Debt

Date: 2026-06-08

## Highest Priority

1. Move module manifests from static Python definitions to per-module manifest files.
2. Convert provider registry from metadata-only to a read-only fetch abstraction.
3. Refactor `/api/macro` to call provider contract fetchers directly while preserving current response contract.
4. Add dashboard System Modules panel using `/api/system/modules` and `/api/system/providers`.
5. Keep optimizer/paper routes disabled unless explicitly feature-flagged.

## Legacy Isolation

Still present and intentionally not deleted:

- `optimizer_service/`
- `dashboard_react/backend/routes/paper_trading.py`
- `dashboard_react/backend/routes/paper_autotrader_routes.py`
- `dashboard_react/backend/routes/optimizer_agent_routes.py`
- execution/order modules under legacy strategy paths

These must not be imported by `aegis_core` or default dashboard controls.

## Provider Work

Needed:

- yfinance `DataSnapshot` fetcher with field timestamps.
- CoinGecko dominance provider wrapper.
- Sentinel provider wrapper for event risk/regime.
- FRED and NewsAPI credential-aware fetchers.
- CCXT read-only allowlist before any import is used in runtime.

## Testing Gaps

Needed:

- Full missing-provider simulation for yfinance/CoinGecko/Sentinel fetch failures.
- Dashboard browser verification for System Modules UI once added.
- Docker image rebuild validation after new backend route deployment. Runtime was verified with controlled file copy and restart.
- Static import guard that safe core never imports optimizer/paper/execution modules.

Current broad-suite blockers:

- `python -m pytest tests -v --tb=short` hits a pytest capture cleanup error because `tests/test_phase_2_5_validation.py` reassigns `sys.stdout`.
- `tests/test_touche_live_integration.py` has 6 remaining failures:
  - `TestToucheAnalyze::test_analyze_includes_data_mode_and_data_range` has a test-side `NameError` from an undefined `i` in `mock_row`.
  - `TestToucheHealth::test_health_returns_data_mode`, `TestToucheAnalyze::test_analyze_fallback_still_returns_200`, and `TestFundamentalMetrics::test_fundamental_metrics_glassnode_live` patch `httpx.AsyncClient.get` globally, so the ASGI test client's own `client.get(...)` is mocked before the app route runs.
  - `TestBinanceDataFetcher::test_fallback_to_mock_on_timeout` and `TestBinanceDataFetcher::test_mock_mode_skips_binance` expect silent mock fallback; current safe fetcher requires explicit fallback/cache/mock state instead of presenting fallback as live.

## Docker Gaps

- External network `aegis_clean_v71_aegis_network` remains documented compatibility debt.
- Runtime container should be inspected after deploy to ensure current project images serve ports 8502 and 3001.

## License Gaps

- GPL/AGPL repos remain architecture-only references.
- `NOASSERTION` repos require manual license review before dependency or vendoring.
