# E-yAy / BrainChain AEGIS Integration Contract

## Purpose

This document defines the only approved integration contract between E-yAy / BrainChain and AEGIS after the Phase 1-8 cleanup work.

AEGIS is now treated as a signal-only and evidence-only subsystem.

AEGIS must not:

- make final investment decisions
- emit action commands
- emit position sizing
- execute orders
- mutate optimizer state
- silently continue with hidden degraded fallbacks

## 1. Official Integration Surface

E-yAy / BrainChain may call only these routes:

- `GET /aegis-core/health`
- `POST /aegis-core/signal`
- `POST /aegis-core/backtest-evidence`

These routes are the only approved runtime boundary for AEGIS integration.

## 2. Explicitly Forbidden Legacy Surfaces For E-yAy

E-yAy must not call any legacy route or code path that bypasses `aegis_core`.

Forbidden surfaces include:

- `POST /execute`
- old `/signal` paths
- old `/process` paths
- paper trading routes
- optimizer routes
- bounded updater paths
- execution engine paths
- any route returning `action`
- any route returning `position_size`

Examples of forbidden runtime areas:

- `consensus_engine/main.py`
- `dashboard_react/backend/main.py` legacy execution and dashboard decision paths
- `dashboard_react/backend/routes/paper_trading.py`
- `dashboard_react/backend/routes/backtest_routes.py` legacy simulated trade logic
- `consensus_engine/src/final_allocator.py`
- `consensus_engine/src/position_optimizer.py`
- `consensus_engine/src/bounded_updater.py`
- `optimizer_service/`
- `strategies/execution_engine.py`

## 3. `POST /aegis-core/signal` Request Schema

Required top-level fields:

- `symbol: string`
- `timeframe: string`
- `raw_regime: string`
- `module_scores: object`

Optional top-level fields:

- `higher_tf_scores: object`
- `data_integrity: object`
- `risk_context: object`
- `kill_switch_context: object`

Expected request shape:

```json
{
  "symbol": "BTC",
  "timeframe": "4h",
  "raw_regime": "LIQUIDITY_EXPANSION",
  "module_scores": {
    "touche": 0.465,
    "fundamental": 0.860,
    "sentinel": 0.679,
    "news": 0.500,
    "quantum": 0.524
  },
  "higher_tf_scores": {
    "4h": 0.67,
    "1d": 0.70
  },
  "data_integrity": {
    "source": "provider_name",
    "backup_source": "backup_provider",
    "observation_date": "2026-05-01",
    "release_timestamp": "2026-05-01T15:30:00+03:00",
    "available_timestamp": "2026-05-01T15:31:05+03:00",
    "is_stale": false,
    "fallback_used": false,
    "data_confidence": 0.96,
    "critical_fields_present": true
  },
  "risk_context": {
    "contradiction_score": 25,
    "portfolio_daily_loss_pct": 0.0,
    "portfolio_weekly_loss_pct": 0.0,
    "max_daily_loss_pct": 3.0,
    "max_weekly_loss_pct": 7.0,
    "volatility_spike": false,
    "correlation_break": false,
    "stablecoin_depeg": false,
    "exchange_outage": false,
    "critical_risk_breach": false
  },
  "kill_switch_context": {
    "manual_kill_switch": false,
    "broker_api_error": false,
    "unexpected_correlation_break": false,
    "backtest_timestamp_violation": false,
    "system_integrity_error": false
  }
}
```

## 4. `POST /aegis-core/signal` Response Schema

Core response fields:

- `data_integrity_result`
- `aegis_signal`
- `brainchain_signal`
- `risk_result`
- `kill_switch_result`
- `ownerbrief`
- `audit_record`
- `blocked`
- `decision_permission`
- `final_decision`

Notes:

- `aegis_signal` and `brainchain_signal` are present for non-data-integrity-blocked flows.
- `ownerbrief` and `audit_record` must be present for both blocked and non-blocked flows.
- `final_decision` must always be `false`.

## 5. Non-Negotiable Safety Rules

- No final investment decision.
- No `action`.
- No `position_size`.
- No buy/sell/hold command.
- No `broker`, `order`, or `execution` field.
- No optimizer mutation.
- No silent fallback.
- `final_decision` is always `false`.
- `decision_permission` must be one of:
  - `SIGNAL_ONLY_NOT_FINAL`
  - `BLOCKED_BY_DATA_INTEGRITY`
  - `BLOCKED_BY_RISK_OR_KILL_SWITCH`
  - `EVIDENCE_ONLY_NOT_FINAL`

## 6. Status Matrix

| Data Integrity | Risk | Kill Switch | Resulting Behavior |
|---|---|---|---|
| `PASS` | `PASS` | `OFF` | Return normal signal-only payload |
| `DEGRADED_PASS` | `PASS` | `OFF` | Return signal-only payload with warnings |
| `PASS` | `DEGRADED_PASS` | `OFF` | Return signal-only payload with warnings |
| `DEGRADED_PASS` | `DEGRADED_PASS` | `OFF` | Return signal-only payload with warnings |
| `FAIL` | any | `ON` | Return blocked payload with `BLOCKED_BY_DATA_INTEGRITY` |
| `PASS` or `DEGRADED_PASS` | `BLOCK` | `ON` | Return blocked payload with `BLOCKED_BY_RISK_OR_KILL_SWITCH` |
| `PASS` or `DEGRADED_PASS` | any | `ON` | Return blocked payload with `BLOCKED_BY_RISK_OR_KILL_SWITCH` |

## 7. E-yAy Routing Rule

- E-yAy must only call `/aegis-core/*`.
- E-yAy Data Integrity Gate may supersede the local AEGIS gate.
- E-yAy Risk Engine is the final risk authority.
- The AEGIS Risk wrapper is local pre-risk safety only.
- Execution Control remains outside AEGIS.
- Kill Switch handling remains outside AEGIS for actual execution control, even though AEGIS reports a local kill-switch state.

## 8. Migration Notes

Legacy-only runtime pieces that remain untouched:

- `consensus_engine/`
- `dashboard_react/backend/main.py` legacy decision and execution paths
- `dashboard_react/backend/routes/paper_trading.py`
- `dashboard_react/backend/routes/backtest_routes.py`
- `optimizer_service/`
- `macro_bridge/`
- execution and sizing helpers now mirrored under `quarantine/`

E-yAy must never import:

- `consensus_engine/main.py`
- `consensus_engine/src/final_allocator.py`
- `consensus_engine/src/position_optimizer.py`
- `consensus_engine/src/bounded_updater.py`
- `dashboard_react/backend/routes/paper_trading.py`
- `optimizer_service/*`
- `strategies/execution_engine.py`

Safe import surface:

- package: `aegis_core` only

Safe modules include:

- `aegis_core.engine.regime_weights`
- `aegis_core.engine.confluence`
- `aegis_core.engine.consensus`
- `aegis_core.engine.backtest`
- `aegis_core.adapters.brainchain_adapter`
- `aegis_core.data.integrity`
- `aegis_core.risk.risk_engine`
- `aegis_core.risk.kill_switch`
- `aegis_core.reports.ownerbrief`
- `aegis_core.audit.logger`

## 9. Example Valid Response

```json
{
  "success": true,
  "blocked": false,
  "decision_permission": "SIGNAL_ONLY_NOT_FINAL",
  "final_decision": false,
  "data_integrity_result": {
    "status": "PASS",
    "data_quality_score": 96,
    "hard_block": false,
    "warnings": [],
    "decision_permission": "DATA_GATE_ONLY_NOT_FINAL"
  },
  "aegis_signal": {
    "source_engine": "AEGIS",
    "source_version": "7.2_core",
    "symbol": "BTC",
    "timeframe": "4h",
    "consensus_score": 65.42,
    "decision_permission": "SIGNAL_ONLY_NOT_FINAL",
    "final_decision": false,
    "warnings": []
  },
  "brainchain_signal": {
    "source_engine": "AEGIS",
    "source_version": "7.2_core",
    "signal_type": "market_signal",
    "symbol": "BTC",
    "timeframe": "4h",
    "consensus_score": 65.42,
    "final_decision": false,
    "decision_permission": "SIGNAL_ONLY_NOT_FINAL",
    "warnings": []
  },
  "risk_result": {
    "status": "PASS",
    "hard_block": false,
    "warnings": [],
    "decision_permission": "RISK_ENGINE_ONLY_NOT_FINAL",
    "final_decision": false
  },
  "kill_switch_result": {
    "status": "OFF",
    "hard_block": false,
    "warnings": [],
    "decision_permission": "KILL_SWITCH_ONLY_NOT_FINAL",
    "final_decision": false
  },
  "ownerbrief": {
    "brief_type": "AEGIS_CORE_OWNERBRIEF",
    "mode": "AEGIS_CORE_SIGNAL_ONLY",
    "decision_permission": "NO_EXECUTION_SIGNAL_ONLY",
    "final_decision": false,
    "summary": "Signal-only output generated for downstream review with no final authority.",
    "warnings": []
  },
  "audit_record": {
    "audit_type": "AEGIS_CORE_SIGNAL_AUDIT",
    "model_version": "aegis_core_7.2",
    "route": "/aegis-core/signal",
    "symbol": "BTC",
    "timeframe": "4h",
    "decision_permission": "NO_EXECUTION_SIGNAL_ONLY",
    "final_decision": false,
    "source_engine": "AEGIS",
    "warnings": []
  },
  "warnings": []
}
```

## 10. Example Blocked Response

```json
{
  "success": false,
  "blocked": true,
  "decision_permission": "BLOCKED_BY_DATA_INTEGRITY",
  "final_decision": false,
  "data_integrity_result": {
    "status": "FAIL",
    "data_quality_score": 40,
    "hard_block": true,
    "warnings": [
      "source_missing"
    ],
    "decision_permission": "DATA_GATE_ONLY_NOT_FINAL"
  },
  "risk_result": {
    "status": "BLOCK",
    "hard_block": true,
    "warnings": [
      "blocked_due_to_data_integrity_fail"
    ],
    "decision_permission": "RISK_ENGINE_ONLY_NOT_FINAL",
    "final_decision": false
  },
  "kill_switch_result": {
    "status": "ON",
    "hard_block": true,
    "warnings": [
      "kill_switch_data_integrity_block",
      "kill_switch_risk_engine_block"
    ],
    "decision_permission": "KILL_SWITCH_ONLY_NOT_FINAL",
    "final_decision": false
  },
  "ownerbrief": {
    "brief_type": "AEGIS_CORE_OWNERBRIEF",
    "mode": "AEGIS_CORE_SIGNAL_ONLY",
    "decision_permission": "NO_EXECUTION_SIGNAL_ONLY",
    "final_decision": false,
    "summary": "Signal blocked by data integrity review; downstream use should pause until metadata is corrected.",
    "warnings": [
      "source_missing"
    ]
  },
  "audit_record": {
    "audit_type": "AEGIS_CORE_SIGNAL_AUDIT",
    "model_version": "aegis_core_7.2",
    "route": "/aegis-core/signal",
    "symbol": "BTC",
    "timeframe": "4h",
    "decision_permission": "NO_EXECUTION_SIGNAL_ONLY",
    "final_decision": false,
    "source_engine": "AEGIS",
    "warnings": [
      "source_missing"
    ]
  },
  "warnings": [
    "source_missing"
  ]
}
```

## Final Integration Rule

E-yAy / BrainChain must treat `aegis_core` as a signal-only pre-decision subsystem.

Nothing in AEGIS is authorized to become final execution control.
