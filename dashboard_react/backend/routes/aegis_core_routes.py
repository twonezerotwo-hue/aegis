"""Safe API surface for signal-only AEGIS Core.

This router intentionally exposes only non-final signal and evidence outputs.
It does not import execution, sizing, optimizer, or legacy decision modules.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter
from pydantic import BaseModel, Field

try:
    from aegis_core.audit.logger import build_audit_record
    from aegis_core.adapters.brainchain_adapter import to_brainchain_signal
    from aegis_core.data.integrity import validate_data_integrity
    from aegis_core.engine.backtest import format_backtest_evidence
    from aegis_core.engine.confluence import apply_multi_tf_confluence
    from aegis_core.engine.consensus import build_aegis_signal
    from aegis_core.reports.ownerbrief import build_ownerbrief
    from aegis_core.risk.kill_switch import evaluate_kill_switch
    from aegis_core.risk.risk_engine import evaluate_signal_risk
except ModuleNotFoundError:
    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from aegis_core.audit.logger import build_audit_record
    from aegis_core.adapters.brainchain_adapter import to_brainchain_signal
    from aegis_core.data.integrity import validate_data_integrity
    from aegis_core.engine.backtest import format_backtest_evidence
    from aegis_core.engine.confluence import apply_multi_tf_confluence
    from aegis_core.engine.consensus import build_aegis_signal
    from aegis_core.reports.ownerbrief import build_ownerbrief
    from aegis_core.risk.kill_switch import evaluate_kill_switch
    from aegis_core.risk.risk_engine import evaluate_signal_risk


router = APIRouter(prefix="/aegis-core", tags=["aegis_core"])


class AegisCoreSignalRequest(BaseModel):
    symbol: str = "BTC"
    timeframe: str = "1h"
    raw_regime: str = "NORMALIZATION"
    module_scores: Dict[str, Any] = Field(default_factory=dict)
    higher_tf_scores: Dict[str, Any] = Field(default_factory=dict)
    data_integrity: Dict[str, Any] | None = None
    risk_context: Dict[str, Any] | None = None
    kill_switch_context: Dict[str, Any] | None = None


class AegisCoreBacktestEvidenceRequest(BaseModel):
    symbol: str = "BTC"
    timeframe: str = "1h"
    metrics: Dict[str, Any] = Field(default_factory=dict)


def _merge_warnings(*warning_lists: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for warning_list in warning_lists:
        for warning in warning_list or []:
            item = str(warning)
            if item not in seen:
                seen.add(item)
                merged.append(item)
    return merged


@router.get("/health")
async def aegis_core_health() -> dict:
    return {
        "success": True,
        "engine": "AEGIS_CORE",
        "status": "ok",
        "decision_permission": "SIGNAL_ONLY_NOT_FINAL",
        "final_decision": False,
    }


@router.post("/signal")
async def aegis_core_signal(request: AegisCoreSignalRequest) -> dict:
    request_payload = request.model_dump()
    data_integrity_result = validate_data_integrity(request.data_integrity)
    gate_warnings = _merge_warnings(data_integrity_result.get("warnings", []))

    if data_integrity_result.get("hard_block"):
        risk_result = evaluate_signal_risk(
            aegis_signal=None,
            brainchain_signal=None,
            data_integrity_result=data_integrity_result,
            risk_context=request.risk_context,
        )
        kill_switch_result = evaluate_kill_switch(
            data_integrity_result=data_integrity_result,
            risk_result=risk_result,
            kill_switch_context=request.kill_switch_context,
        )
        warnings = _merge_warnings(
            gate_warnings,
            risk_result.get("warnings", []),
            kill_switch_result.get("warnings", []),
        )
        ownerbrief = build_ownerbrief(
            aegis_signal=None,
            brainchain_signal=None,
            data_integrity_result=data_integrity_result,
            risk_result=risk_result,
            kill_switch_result=kill_switch_result,
            request_context=request_payload,
        )
        audit_record = build_audit_record(
            route="/aegis-core/signal",
            request_payload=request_payload,
            data_integrity_result=data_integrity_result,
            aegis_signal=None,
            brainchain_signal=None,
            risk_result=risk_result,
            kill_switch_result=kill_switch_result,
            ownerbrief=ownerbrief,
        )
        return {
            "success": False,
            "blocked": True,
            "symbol": request.symbol,
            "timeframe": request.timeframe,
            "decision_permission": "BLOCKED_BY_DATA_INTEGRITY",
            "final_decision": False,
            "data_integrity_result": data_integrity_result,
            "risk_result": risk_result,
            "kill_switch_result": kill_switch_result,
            "ownerbrief": ownerbrief,
            "audit_record": audit_record,
            "warnings": _merge_warnings(warnings, ownerbrief.get("warnings", [])),
        }

    base_signal = build_aegis_signal(
        symbol=request.symbol,
        timeframe=request.timeframe,
        module_scores=request.module_scores,
        raw_regime=request.raw_regime,
    )

    confluence = apply_multi_tf_confluence(
        base_score=base_signal.get("consensus_score", 50.0),
        higher_tf_scores=request.higher_tf_scores,
    )

    aegis_signal = {
        **base_signal,
        "confluence": confluence,
        "confluence_adjusted_score": confluence["adjusted_score"],
        "warnings": _merge_warnings(
            gate_warnings,
            base_signal.get("warnings", []),
            confluence.get("warnings", []),
        ),
    }

    brainchain_signal = to_brainchain_signal(aegis_signal)
    risk_result = evaluate_signal_risk(
        aegis_signal=aegis_signal,
        brainchain_signal=brainchain_signal,
        data_integrity_result=data_integrity_result,
        risk_context=request.risk_context,
    )
    kill_switch_result = evaluate_kill_switch(
        data_integrity_result=data_integrity_result,
        risk_result=risk_result,
        kill_switch_context=request.kill_switch_context,
    )
    warnings = _merge_warnings(
        gate_warnings,
        aegis_signal.get("warnings", []),
        brainchain_signal.get("warnings", []),
        brainchain_signal.get("cross_validation", {}).get("warnings", []),
        risk_result.get("warnings", []),
        kill_switch_result.get("warnings", []),
    )

    aegis_signal["warnings"] = warnings
    brainchain_signal["warnings"] = _merge_warnings(
        brainchain_signal.get("warnings", []),
        aegis_signal.get("warnings", []),
        risk_result.get("warnings", []),
        kill_switch_result.get("warnings", []),
    )

    blocked = bool(risk_result.get("hard_block") or kill_switch_result.get("hard_block"))
    ownerbrief = build_ownerbrief(
        aegis_signal=aegis_signal,
        brainchain_signal=brainchain_signal,
        data_integrity_result=data_integrity_result,
        risk_result=risk_result,
        kill_switch_result=kill_switch_result,
        request_context=request_payload,
    )
    audit_record = build_audit_record(
        route="/aegis-core/signal",
        request_payload=request_payload,
        data_integrity_result=data_integrity_result,
        aegis_signal=aegis_signal,
        brainchain_signal=brainchain_signal,
        risk_result=risk_result,
        kill_switch_result=kill_switch_result,
        ownerbrief=ownerbrief,
    )

    return {
        "success": not blocked,
        "blocked": blocked,
        "decision_permission": "BLOCKED_BY_RISK_OR_KILL_SWITCH" if blocked else "SIGNAL_ONLY_NOT_FINAL",
        "final_decision": False,
        "data_integrity_result": data_integrity_result,
        "risk_result": risk_result,
        "kill_switch_result": kill_switch_result,
        "aegis_signal": aegis_signal,
        "brainchain_signal": brainchain_signal,
        "ownerbrief": ownerbrief,
        "audit_record": audit_record,
        "warnings": _merge_warnings(warnings, ownerbrief.get("warnings", [])),
    }


@router.post("/backtest-evidence")
async def aegis_core_backtest_evidence(request: AegisCoreBacktestEvidenceRequest) -> dict:
    evidence = format_backtest_evidence(request.metrics)
    warnings = _merge_warnings(evidence.get("warnings", []))

    return {
        "success": True,
        "symbol": request.symbol,
        "timeframe": request.timeframe,
        **evidence,
        "warnings": warnings,
    }
