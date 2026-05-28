# AEGIS Cleanup Phase 3 Audit

- Date: 2026-04-30
- Scope: Old AEGIS runtime audit only
- Runtime changes made: None
- Docker run: No
- Imports edited: No

## 1. Executive Summary

AEGIS still has multiple active runtime paths that violate the future `SIGNAL_ONLY_NOT_FINAL` boundary. The most important leak is still [consensus_engine/main.py](consensus_engine/main.py), where `/signal` and especially `/process` generate final `BUY` / `SELL` / `HOLD` actions and calculate `position_size`. The dashboard backend adds another live execution surface through `/execute`, while the backtest layer still performs simulated trade execution, Kelly-style sizing, portfolio allocation, and buy-and-hold fallback injection.

Execution and order semantics remain present in three forms:

1. Live or broker-like: [dashboard_react/backend/main.py](dashboard_react/backend/main.py) + [strategies/execution_engine.py](strategies/execution_engine.py)
2. Paper or simulated: [dashboard_react/backend/routes/paper_trading.py](dashboard_react/backend/routes/paper_trading.py), [dashboard_react/backend/routes/backtest_routes.py](dashboard_react/backend/routes/backtest_routes.py), [optimizer_service/src/backtest_engine.py](optimizer_service/src/backtest_engine.py)
3. Contract-level: [shared/proto/signals.proto](shared/proto/signals.proto)

Silent fallback is also widespread. In several places, missing upstream data is converted into neutral/default output and the pipeline continues, often without a caller-visible degraded-state contract. This is especially visible in `consensus_engine/main.py`, `dashboard_react/backend/main.py`, `dashboard_react/backend/routes/backtest_routes.py`, and the strategy service entrypoints.

Weight mutation and config drift are still live risks. AEGIS currently supports in-memory trade-feedback weight mutation, disk writes through `bounded_updater`, and full config overwrite/rollback through `optimizer_service`. There is also a schema drift bug in the optimizer path: [optimizer_service/main.py:45-55](optimizer_service/main.py) reads `cfg["weights"]`, while the canonical consensus config stores the active module block under `modules`.

Existing tests still reinforce old behavior in several places. Legacy tests explicitly validate BUY/SELL/HOLD decision flow, trade simulation, paper-trading behavior, fallback continuation, and optimizer learning flows. Those tests will need to be retired, quarantined, or rewritten before the old runtime can be safely deactivated.

## 2. Final-Decision Leaks

| File / Location | Function / Endpoint | Risky Field or Behavior | Why It Violates `SIGNAL_ONLY_NOT_FINAL` | Recommended Action |
|---|---|---|---|---|
| `consensus_engine/main.py:438-512` | `get_signal` / `GET /signal` | Returns `signal` and `position_size_pct`; maps internal action to `BUY` / `SELL` / `HOLD` | Emits a final trade direction and a size hint | Replace with `aegis_core` signal wrapper |
| `consensus_engine/main.py:573-1129` | `process_signal` / `POST /process` | Returns `action`, `position_size`, gating result, thresholds, module sides, multi-TF final signal | This is the primary final-decision pipeline and directly violates the target boundary | Replace with `aegis_core`, then disable old path |
| `consensus_engine/main.py:851-998` | `process_signal` internals | Synthesizes timeframe sides, computes `five_module_action`, green-light gate, final `action`, and size | Converts module scores into an executable final stance | Replace with `aegis_core`; quarantine old logic |
| `consensus_engine/src/final_allocator.py:19-166` | `FinalAllocator` | Builds `ConsensusDecision`, position allocations, quantities, SL/TP metadata | Explicit final allocator and order/allocation logic | Quarantine and remove later |
| `consensus_engine/src/position_optimizer.py:16-170` | `PositionOptimizer` | Kelly fraction, action strength, `position_size`, stop-loss, take-profit | Sizing and risk outputs belong to BrainChain-side layers | Quarantine and remove later |
| `dashboard_react/backend/main.py:308-444` | `get_dashboard` / `GET /api/dashboard` | Computes `action` from weighted score | Dashboard endpoint still makes final direction calls | Legacy now, replace later with `aegis_core` summary only |
| `dashboard_react/backend/routes/dashboard.py:292-366` | `get_consensus` / `GET /consensus` | Returns `action`, `confidence`, weighted score | Old dashboard consensus route is still a decision engine | Replace with `aegis_core` contract |
| `dashboard_react/backend/routes/stream.py:184-286` | `_normalize_consensus` and `/live-feed` | Passes through `action`, `position_size`, multi-TF final signal, rebalance actions | UI streaming layer republishes final-decision semantics | Legacy UI only, quarantine before BrainChain integration |
| `dashboard_react/backend/routes/backtest_routes.py:793-794` | `add_ai_scores` | Creates `consensus_action` as `BUY` / `SELL` / `HOLD` | Backtest path still turns scores into final directional labels | Replace later with evidence-only `aegis_core` backtest layer |
| `dashboard_react/backend/routes/backtest_routes.py:1175-1325` | `calculate_position_size`, `execute_ai_driven_trades`, `calculate_backtest_metrics` | Simulated execution, fractional exposure, trade sizing | Final decision and sizing semantics are embedded in backtest path | Replace later with evidence-only wrapper, keep old path legacy-only for now |
| `strategies/analyzer_ai/main.py:35-82` | `/analyze` | Returns `recommendation` as `BUY` / `SELL` / `HOLD` | Analyzer service is still a decision endpoint, not a score provider | Legacy / remove later |
| `strategies/quantum_ai/main.py:186-212` | `/executor/liquidity_check` | Can change requested `BUY` to `HOLD` via `filtered_signal` | Directly alters final signal direction | Wrap or quarantine; do not place on BrainChain-facing side |
| `strategies/cbr_engine/main.py:267-327` | `/cbr/process` | Returns `action`, `confidence`, `position_size`, `entry_price`, `stop_loss`, `take_profit` | Full decision payload with sizing and order semantics | Quarantine |
| `strategies/cbr_engine/main.py:416-474` | `/cbr/decide` | Returns action and full trade setup | CBR directly makes trading decisions | Quarantine |
| `macro_bridge/run.py:12-75` | `run_pipeline` | Returns `decision`, `position_size`, `asset_allocation`, `rebalance_signal`, `stop_loss`, `hedge` | This is post-signal orchestration and allocation, not core AEGIS | Quarantine and replace at BrainChain layer |

## 3. Execution-Like Surfaces

| File | Route / Function | Surface Type | What It Does Today | Recommended Isolation Plan |
|---|---|---|---|---|
| `dashboard_react/backend/main.py:256-299` | `POST /execute` | Live / broker-like | Imports `BinanceTestnetExecutor` and places a testnet order | Disable before BrainChain integration; later remove |
| `strategies/execution_engine.py:63-158` | `BinanceTestnetExecutor.place_order` | Broker / order bridge | Dry-run or signed Binance testnet order submit | Keep only in quarantine; remove from active service imports later |
| `dashboard_react/backend/routes/paper_trading.py` | `/api/paper/*` | Paper trading | Starts sessions, records buy/sell trades, exports statements | Keep isolated as non-core legacy; disable in integration environment |
| `dashboard_react/backend/routes/backtest_routes.py:1217-1265` | `execute_ai_driven_trades` | Simulated execution | Opens and closes LONG / SHORT trades from consensus signals | Keep legacy-only until a pure evidence path replaces it |
| `dashboard_react/backend/main.py:492-706` | `POST /backtest/run` | Simulated execution | Inline backtest path with trade list, Kelly cap, portfolio allocation | Legacy only; remove after router migration |
| `optimizer_service/src/backtest_engine.py` | `_generate_mock_trades` | Simulated | Generates deterministic mock trades for optimizer search | Quarantine; never treat as canonical |
| `shared/proto/signals.proto:34-105` | `Order*`, `ExecutionService`, `RiskService` | Contract / order-like | Declares order submission, status, fills, and limit checks | Split signal-only proto from order/risk proto before integration |
| `strategies/touche_ai/main.py:416-450` | `GET /touche/exit_signal` | Paper / exit helper | Returns close instructions for position exit logic | Quarantine or move to BrainChain-side exit tooling |
| `strategies/quantum_ai/main.py:186-212` | `POST /executor/liquidity_check` | Executor-facing filter | Acts like a pre-execution liquidity and funding gate | Keep only as raw metrics provider after rewrite; do not let it edit final signal |
| `macro_bridge/executor/trade_executor.py` | `calculate_position_size`, `calculate_stop_loss`, `calculate_asset_allocation`, `generate_rebalance_signal` | Orchestration / portfolio | Post-signal allocation, sizing, hedge, rebalance logic | Quarantine; BrainChain should own this domain |

## 4. Silent Fallback Risks

| File / Location | Behavior | What Happens Today | Why It Is Unsafe | Replacement Proposal |
|---|---|---|---|---|
| `consensus_engine/main.py:501-511` | `/signal` top-level fallback | Any exception returns `HOLD` and `position_size_pct=0.05` | A failure is silently converted into a valid-looking signal with size | Return `503` or degraded response with warnings and no size field |
| `consensus_engine/main.py:635-667` | Sentinel fetch fallback in `/process` | Uses neutral multiplier and default event-risk values | Missing macro risk data still feeds final action logic | Require explicit degraded-state field or fail closed for missing sentinel data |
| `consensus_engine/main.py:707-734` | News fetch failure in `/process` | Logs error, continues without hard caller-visible failure | Missing module input changes decision quality silently | Add warnings list and explicit `module_missing.news=true`; do not silently neutralize |
| `consensus_engine/main.py:807-821` | Quantum futures fetch fallback | Uses modifier `1.0` and `CACHE_FALLBACK` | Missing futures risk becomes near-neutral signal continuation | Return warnings and mark quantum modifier unavailable |
| `consensus_engine/main.py:876-893` | Market depth / spread fallback | Defaults to `600000` depth and `0.05` spread on error | Liquidity gating can pass using synthetic values | Fail closed on unavailable liquidity unless explicit override is present |
| `consensus_engine/main.py:851-854` | Missing `tf_signals` | Builds timeframe signals from internal recommended action | Missing confluence input is fabricated from the outcome it later validates | Mark confluence unavailable; never synthesize TF agreement from the same decision |
| `consensus_engine/main.py:1122-1129` | `/process` outer exception fallback | Returns `{error, action=HOLD, position_size=0}` | A runtime failure still produces a valid-looking decision payload | Return degraded error object with no decision fields |
| `consensus_engine/main.py:1208-1215` | `/weights` fallback | Returns status `fallback` and production weights | Weight source failure becomes silent default state | Return `503` or read-only snapshot with explicit source failure |
| `consensus_engine/src/attribution_engine.py:209-235` | DB write failure swallowed | Attribution ref is returned even if DB persistence fails | Audit trail can appear complete when persistence failed | Return explicit `audit_persisted=false` warning |
| `dashboard_react/backend/main.py:634-662` | Inline backtest fallback | AI engine failure triggers buy-and-hold result so endpoint never 500s | Engine failure is hidden as a real backtest outcome | Return degraded backtest error or evidence-only empty result |
| `dashboard_react/backend/main.py:665-677` | Portfolio allocator fallback | Allocation errors become `{}` with warning only | Consumer sees incomplete result with no enforcement | Return explicit `allocation_available=false` field |
| `dashboard_react/backend/routes/backtest_routes.py:47-69` | `BacktestEngine` import fallback | Missing engine becomes `_SimpleCache` | Broken engine state is hidden at startup | Fail route initialization or return `engine_unavailable` |
| `dashboard_react/backend/routes/backtest_routes.py:155-157` | Regime detection fallback | Returns `None` or defaults to `NORMALIZATION` / `default` path | Missing regime data still drives weights | Return explicit degraded-state warnings from weight loader |
| `dashboard_react/backend/routes/backtest_routes.py:318-338` | Buy-and-hold fallback when no trades | Injects synthetic trade record with `BUY_AND_HOLD` | Signal engine failure can look like a legitimate strategy result | Return `no_trades` evidence instead of synthetic trading result |
| `dashboard_react/backend/routes/backtest_routes.py:571-597` | Mock historical data fallback | No real data fetch can degrade into mock generation | Real-vs-mock provenance is not strong enough for governance | Return `data_mode=degraded` and reject production-facing use |
| `dashboard_react/backend/routes/backtest_routes.py:930-931` | `except: pass` in multi-TF confluence | Missing higher TF request is ignored completely | Confluence multiplier becomes unverifiable | Return warning list per failed timeframe |
| `dashboard_react/backend/routes/backtest_routes.py:935-952` | Correlation fallback | Returns neutral correlation context | Missing macro correlation is normalized into valid signal flow | Return `correlation_available=false` with warnings |
| `strategies/sentinel_ai/main.py:228-277` | Macro snapshot fallback | Returns fallback or partial-fallback snapshot | Regime and risk outputs continue from synthetic macro data | Keep fallback only if caller-visible and Data Integrity Gate blocks final use |
| `strategies/touche_ai/main.py:365-412` | Live fetch fallback | Falls back to deterministic EQS and still returns a normal 200 response | Synthetic technical score can be consumed as authoritative | Add degraded-state warning and policy gate |
| `strategies/fundamental_ai/main.py` | Deterministic fallback mode | Continues serving scores when live keys are missing | Synthetic fundamental score can be treated as real | Same as above: explicit degraded-state plus policy gate |
| `strategies/quantum_ai/main.py:189-190, 235-238` | Random defaults and `CACHE_FALLBACK` | Depth/spread can be random if absent; futures data returns generic signal alias | Unstable fallback feeds executor-side logic | Require explicit inputs for liquidity check; keep futures fallback visibly degraded |
| `strategies/analyzer_ai/main.py:132-140` | Exit attribution fallback | Missing data returns empty result | Audit-like data is silently incomplete | Return empty result plus explicit `warnings` |

## 5. Weight Mutation / Config Drift Risks

| File / Location | Behavior | Writes Config or Changes Live Weights? | Recommended Governance Plan |
|---|---|---|---|
| `consensus_engine/main.py:373-384` | `/consensus/weights` updates `current_regime` and `current_module_weights` | In-memory live weights | Keep read-only in future or remove; do not let external services mutate consensus state directly |
| `consensus_engine/main.py:387-415` | `/consensus/feedback/trade` calls `ModuleDynamicWeights.update_from_trade` | In-memory live weights | Quarantine; trade feedback belongs above AEGIS Core |
| `consensus_engine/main.py:1166-1172` | `/attribution/calculate` can call `bounded_updater.update` with `apply_update=true` | Yes, via bounded updater | Disable before integration; move governance to BrainChain audit/risk workflow |
| `consensus_engine/main.py:1218-1238` | `/bounded_updater/update` manual mutation endpoint | Yes | Quarantine and remove from active runtime boundary |
| `consensus_engine/src/bounded_updater.py:64-75, 109-113, 288-310` | Writes `consensus_weights.yaml`, `consensus_weights_backup.yaml`, `drift_log.yaml`; supports rollback | Yes, on disk | Keep quarantined; future config changes must go through governed review, not runtime mutation |
| `consensus_engine/src/dynamic_weights.py:382-421` | `update_from_trade` changes learned adjustments used in live weight reads | In-memory live weights | Quarantine from BrainChain-facing signal core |
| `consensus_engine/src/dynamic_weights.py:215-229` | `save_state` writes learned adjustments to YAML | Yes, on disk | Archive or quarantine; no autonomous persistence in core runtime |
| `consensus_engine/src/dynamic_weights_simple.py` | Trade-based weight updates and YAML persistence | Yes | Quarantine; duplicate mutable weight system |
| `optimizer_service/main.py:45-55` | `_current_weights()` reads `cfg["weights"]` not canonical `modules` block | Drift / schema mismatch | Fix later during optimizer retirement or migration; do not trust as canonical |
| `optimizer_service/main.py:257-292` | `/optimizer/apply/{study_id}` and `/optimizer/rollback` | Yes, overwrites/restores config | Quarantine entire apply/rollback surface |
| `optimizer_service/src/optimizer_engine.py:375-469` | `apply_config` and `rollback` write new configs and backups | Yes | Quarantine; future tuning artifacts should be offline only |
| `optimizer_service/src/optimizer_engine.py:495-529` | `_save_config` and changelog writes | Yes, artifacts | Keep only as offline archive tooling |
| `dashboard_react/backend/main.py:935-1089` | `/api/optimizer/*` records trades, optimizes, saves/loads configs | Yes, in-memory and on disk | Quarantine these routes before integration |
| `strategies/touche_ai/src/engine/unified_optimizer.py` | Records trade history and saves/loads optimizer config | Yes | Keep as research-only legacy or quarantine |

## 6. Runtime Routes Inventory

| Route | Source File | Purpose | Decision | Notes |
|---|---|---|---|---|
| `GET /health` | `consensus_engine/main.py` | Service health | Keep | Safe operational route |
| `GET /health/clickhouse` | `consensus_engine/main.py` | CBR analytics health | Legacy | Only useful while CBR remains active |
| `GET /health/cbr` | `consensus_engine/main.py` | CBR readiness health | Legacy | CBR is not part of future core |
| `GET /metrics` | `consensus_engine/main.py` | Prometheus metrics | Keep | Operational only |
| `GET /signal` | `consensus_engine/main.py` | Consensus signal output | Replace with `aegis_core` | Currently emits direction and size |
| `POST /process` | `consensus_engine/main.py` | Main consensus pipeline | Replace with `aegis_core` | Current leak center |
| `POST /consensus/weights` | `consensus_engine/main.py` | Runtime regime/weight update | Quarantine | Mutates live runtime state |
| `POST /consensus/feedback/trade` | `consensus_engine/main.py` | Trade-feedback learning | Quarantine | Trade feedback belongs outside core |
| `GET /consensus/historical_edge` | `consensus_engine/main.py` | Historical edge metadata | Legacy | Safe only if used as metadata, not live decisioning |
| `POST /attribution/calculate` | `consensus_engine/main.py` | Closed-trade attribution | Legacy | BrainChain audit should own this later |
| `GET /weights` | `consensus_engine/main.py` | Runtime weights/drift status | Replace with `aegis_core` read-only config view later | Current path exposes mutable weight state |
| `POST /bounded_updater/update` | `consensus_engine/main.py` | Manual weight mutation | Quarantine | Direct config-drift surface |
| `POST /execute` | `dashboard_react/backend/main.py` | Testnet order execution | Quarantine | Must be disabled before integration |
| `GET /api/dashboard` | `dashboard_react/backend/main.py` | Aggregated dashboard payload | Legacy | Still computes final action |
| `POST /backtest/run` | `dashboard_react/backend/main.py` | Deprecated inline backtest | Legacy | Keep only until callers migrate |
| `GET /backtest/status*`, `GET /backtest/report/*` | `dashboard_react/backend/main.py` | Legacy backtest status/report | Legacy | Still tied to old backtest shape |
| `GET /metrics/*` | `dashboard_react/backend/routes/dashboard.py` | UI metric endpoints | Legacy | Dashboard-only surfaces |
| `GET /consensus` | `dashboard_react/backend/routes/dashboard.py` | Old 3-way decision endpoint | Replace with `aegis_core` | Returns BUY/SELL/HOLD |
| `GET /live-feed` | `dashboard_react/backend/routes/stream.py` | SSE snapshot with action, size, rebalance | Quarantine | Not BrainChain-safe as-is |
| `GET /macro`, `GET /risk/profiles`, `POST /simulator` | `dashboard_react/backend/routes/macro.py` | Macro dashboard helper routes | Legacy | Allocation and simulation semantics remain |
| `/api/paper/*` | `dashboard_react/backend/routes/paper_trading.py` | Paper trading | Quarantine | Non-core trading surface |
| `POST /backtest/run` and `/backtest/*` | `dashboard_react/backend/routes/backtest_routes.py` | Canonical old backtest API | Replace later with `aegis_core` backtest evidence API | Keep legacy runtime stable for now |
| `/api/optimizer/*` | `dashboard_react/backend/main.py` | Touche optimizer control | Quarantine | Trade-history and config mutation |
| `GET /touche/analyze` | `strategies/touche_ai/main.py` | Technical score provider | Keep / Wrap | Good upstream candidate, but fallback must become explicit |
| `GET /touche/exit_signal` | `strategies/touche_ai/main.py` | Exit helper for positions | Quarantine | Exit execution semantics |
| `GET /fundamental/metrics` | `strategies/fundamental_ai/main.py` | Fundamental score provider | Keep / Wrap | Good upstream candidate with degraded-mode cleanup needed |
| `GET /sentinel/event_risk` | `strategies/sentinel_ai/main.py` | Macro event-risk provider | Keep / Wrap | Valuable upstream input |
| `GET /sentinel/macro` | `strategies/sentinel_ai/main.py` | Regime and macro provider | Keep / Wrap | Valuable upstream input but fallback-heavy |
| `GET /sentinel/analyze` | `strategies/sentinel_ai/main.py` | Derived macro analysis | Legacy | Not needed if BrainChain consumes raw macro/risk fields |
| `POST /sentinel/simulate` | `strategies/sentinel_ai/main.py` | Simulation helper | Legacy | Research/debug only |
| `POST /executor/liquidity_check` | `strategies/quantum_ai/main.py` | Executor-facing liquidity gate | Quarantine | Changes requested signal |
| `GET /quantum/futures_metrics` | `strategies/quantum_ai/main.py` | Futures risk metrics | Keep / Wrap | Good upstream candidate |
| `GET /quantum/futures_data` | `strategies/quantum_ai/main.py` | Futures modifier + generic signal field | Wrap | Keep metrics, remove signal alias later |
| `POST /cbr/process`, `POST /cbr/decide` | `strategies/cbr_engine/main.py` | CBR decision engine | Quarantine | Direct decision and sizing |
| `POST /cbr/fingerprint`, `POST /cbr/search` | `strategies/cbr_engine/main.py` | CBR analysis helpers | Legacy / Quarantine | Only keep if reused as offline analysis |
| `POST /analyze`, `GET /analyze` | `strategies/analyzer_ai/main.py` | Recommendation service | Legacy / Remove later | Returns BUY/SELL/HOLD |
| `GET /dashboard/attribution`, `GET /dashboard/exit_attribution` | `strategies/analyzer_ai/main.py` | Dashboard-only analytics | Legacy | Not part of future core |
| `POST /optimizer/run`, `/optimizer/status/*`, `/optimizer/results/*`, `/optimizer/apply/*`, `/optimizer/rollback`, `GET /backtest/analyze` | `optimizer_service/main.py` | Optimizer and synthetic backtest service | Quarantine | Config drift and simulated-trade surface |

## 7. Migration Plan

### Old paths that should eventually point to `aegis_core`

1. `consensus_engine/main.py`:
   `GET /signal` and `POST /process`
   These should become thin wrappers over `aegis_core.engine.regime_weights`, `aegis_core.engine.confluence`, `aegis_core.engine.consensus`, and `aegis_core.adapters.brainchain_adapter`.

2. `dashboard_react/backend/routes/dashboard.py`:
   `GET /consensus`
   This should stop computing BUY/SELL/HOLD and should instead expose a signal-only summary derived from `aegis_core`.

3. `dashboard_react/backend/main.py`:
   `GET /api/dashboard`
   This should eventually present scores, consensus score, warnings, and degraded-state information only, with no final action.

4. `dashboard_react/backend/routes/backtest_routes.py`:
   Regime-weight loading and multi-TF confluence should eventually be replaced with `aegis_core.engine.regime_weights` and `aegis_core.engine.confluence`.
   The route itself should later evolve into evidence-only output built from `aegis_core.engine.backtest`.

5. Strategy services:
   - `touche_ai`: keep as technical score source
   - `fundamental_ai`: keep as fundamental score source
   - `sentinel_ai`: keep as macro/regime source
   - `quantum_ai`: keep only raw futures/liquidity metrics, not signal filtering

### What should remain legacy-only

1. Dashboard UI and streaming routes:
   - `dashboard_react/backend/routes/stream.py`
   - `dashboard_react/backend/routes/macro.py`
   - most of `dashboard_react/backend/routes/dashboard.py`

2. Historical report/export surfaces:
   - backtest HTML/CSV export
   - older dashboard report generators

3. Research / simulation helpers:
   - `sentinel/simulate`
   - analyzer UI summaries
   - old attribution presentation routes

### What should be disabled before E-yAy / BrainChain integration

1. `POST /execute`
2. `/api/paper/*`
3. `POST /bounded_updater/update`
4. `POST /consensus/feedback/trade`
5. `POST /consensus/weights`
6. `POST /attribution/calculate` with `apply_update=true`
7. All `dashboard_react` optimizer routes
8. `optimizer_service` apply / rollback routes
9. `POST /cbr/process` and `POST /cbr/decide`
10. `GET /touche/exit_signal`
11. `POST /executor/liquidity_check` until it stops mutating signals

## 8. Test Recommendations

### New tests needed to prevent future leakage

1. Contract test:
   Any future BrainChain-facing AEGIS runtime response must fail if it contains `action`, `position_size`, `order`, `execution`, or `broker`.

2. Schema test:
   Validate all BrainChain-facing signal payloads against `aegis_core/schemas/aegis_signal.schema.json`.

3. Route regression test:
   Replacement for `GET /signal` and `POST /process` must assert:
   - `decision_permission == "SIGNAL_ONLY_NOT_FINAL"`
   - `final_decision == false`
   - no `action`
   - no `position_size`

4. Degraded-state test:
   Missing Sentinel, News, or Quantum upstream data must produce explicit warnings or fail-closed behavior, not silent neutral defaults.

5. Confluence test:
   Missing `tf_signals` must not synthesize higher-timeframe agreement from an internal action.

6. Backtest evidence test:
   Future backtest wrappers must return evidence-only output and must not inject synthetic `BUY_AND_HOLD` trades on engine failure.

7. Weight governance test:
   BrainChain-facing deployment must fail if `/bounded_updater/update`, `/consensus/feedback/trade`, `/optimizer/apply/*`, or `/optimizer/rollback` are enabled.

8. Static search test:
   CI should grep active, non-quarantine runtime packages for forbidden response fields:
   - `action`
   - `position_size`
   - `order_id`
   - `broker`
   - `execution`

9. Adapter test:
   Inputs from `touche_ai`, `fundamental_ai`, `sentinel_ai`, and `quantum_ai` must normalize into `aegis_core` scores only; none of those providers should be allowed to set a final trade side.

10. Fallback policy test:
    Any route returning fallback data must include either:
    - `warnings`
    - `fallback=true`
    - `degraded=true`
    or must fail closed.

### Existing tests that currently reinforce legacy leakage

The following tests should be reviewed, quarantined, or rewritten during later phases because they normalize legacy decision, paper-trading, optimizer, or fallback continuation behavior:

- `tests/test_aegis_v6_master.py`
- `tests/test_dynamic_exit_signal.py`
- `tests/test_phase_1_refactoring.py`
- `tests/test_phase_2_5_validation.py`
- `tests/test_quantum_futures_extension.py`
- `tests/test_touche_live_integration.py`
- `tests/test_clickhouse_write.py`
- `tests/test_v2_consistency.py`

## Patch Proposal Summary For Next Phase

This phase made no runtime edits. Based on the audit, the lowest-risk next patch sequence is:

1. Add explicit warnings and degraded-state fields to old runtime wrappers before changing any imports.
2. Stop old wrappers from returning final `action` and `position_size` once their `aegis_core` replacements exist.
3. Disable live, paper, optimizer-apply, and bounded-updater routes in the BrainChain-facing deployment profile before wiring E-yAy integration.
4. Replace silent or neutralizing fallbacks with either fail-closed behavior or caller-visible degraded-state contracts.

## Final Reminder

AEGIS Core must remain `SIGNAL_ONLY_NOT_FINAL`.
