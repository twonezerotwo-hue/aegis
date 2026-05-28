"""
dashboard_react/backend/routes/stream.py
SSE live-feed: emits event:snapshot (2s), event:weights (2s),
event:alert (on state change), event:ping (30s heartbeat).
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from services.portfolio_allocator import build_allocation_plan

router = APIRouter(prefix="/api", tags=["stream"])

_DASHBOARD_SELF_URL = os.getenv("DASHBOARD_SELF_URL", "http://localhost:8502").rstrip("/")
_CONSENSUS_URL = os.getenv("CONSENSUS_URL", "http://localhost:8005").rstrip("/")
_ANALYZER_URL = os.getenv("ANALYZER_URL", "http://localhost:8007").rstrip("/")

_ALLOCATION_KEYS = ("gold", "btc", "bond", "commodity", "cash")

_PING_INTERVAL_TICKS = 15  # @ 2s/tick = 30s
_WEIGHTS_FETCH_TIMEOUT = 3.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_number(value: Any, fallback: float) -> float:
    return float(value) if isinstance(value, (int, float)) else fallback


def _get_string(value: Any, fallback: str) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def _clean_timestamp(value: Any) -> Optional[str]:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _data_status(timestamp: Optional[str], fallback_used: bool) -> str:
    if fallback_used:
        return "FALLBACK"
    return "LIVE" if timestamp else "UNKNOWN"


_CONSENSUS_STATUS_PRIORITY = ("FALLBACK", "MOCK", "MISSING", "STALE", "UNKNOWN", "RECENT", "LIVE")


def _merge_warnings(*warning_lists: Any) -> List[str]:
    merged: List[str] = []
    for warning_list in warning_lists:
        if not isinstance(warning_list, list):
            continue
        for warning in warning_list:
            if isinstance(warning, str) and warning and warning not in merged:
                merged.append(warning)
    return merged


def _pick_latest_timestamp(*timestamps: Any) -> Optional[str]:
    valid: List[Tuple[datetime, str]] = []
    for value in timestamps:
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            valid.append((datetime.fromisoformat(value.replace("Z", "+00:00")), value))
        except ValueError:
            continue
    if not valid:
        return None
    return max(valid, key=lambda item: item[0])[1]


def _aggregate_status(statuses: List[str]) -> str:
    normalized = [status.upper() for status in statuses if isinstance(status, str) and status.strip()]
    for candidate in _CONSENSUS_STATUS_PRIORITY:
        if candidate in normalized:
            return candidate
    return "UNKNOWN"


def _default_module_source(
    module: str,
    *,
    service: str = "stream-normalizer",
    source: str = "missing_module_source",
    warning: str = "Default neutral module score; module provenance unavailable.",
) -> Dict[str, Any]:
    return {
        "module": module,
        "service": service,
        "source": source,
        "source_data": module,
        "timestamp": None,
        "timestamp_source": "none",
        "data_status": "FALLBACK",
        "fallback_used": True,
        "verified": False,
        "asset_specific": False,
        "shared_score": False,
        "value": 0.5,
        "warnings": [warning],
    }


def _normalize_weights_alloc(weights: Dict[str, float]) -> Dict[str, float]:
    total = sum(float(weights.get(key, 0.0)) for key in _ALLOCATION_KEYS)
    if total <= 0:
        return {"gold": 0.2, "btc": 0.2, "bond": 0.25, "commodity": 0.15, "cash": 0.2}
    normalized = {key: round(float(weights.get(key, 0.0)) / total, 4) for key in _ALLOCATION_KEYS}
    diff = round(1 - sum(normalized.values()), 4)
    normalized["cash"] = round(normalized["cash"] + diff, 4)
    return normalized


def _derive_macro_score(metrics: Dict[str, Any]) -> float:
    score = (
        ((103 - _get_number(metrics.get("dxy"), 102.3)) * 0.06)
        + ((22 - _get_number(metrics.get("vix"), 18.4)) * 0.04)
        + ((4.6 - _get_number(metrics.get("us10y"), 4.18)) * 0.12)
        + ((90 - _get_number(metrics.get("brent"), 84.2)) * 0.01)
    )
    return round(max(-1.0, min(1.0, score)), 4)


def _derive_allocation_target(regime: str, macro_score: float, hedge: bool, horizon: str = "medium") -> Dict[str, float]:
    if "RISK_OFF" in regime:
        base = {"gold": 0.28, "btc": 0.06, "bond": 0.34, "commodity": 0.10, "cash": 0.22}
    elif "LIQUIDITY" in regime or "RISK_ON" in regime:
        base = {"gold": 0.12, "btc": 0.45, "bond": 0.10, "commodity": 0.18, "cash": 0.15}
    else:
        base = {"gold": 0.20, "btc": 0.20, "bond": 0.25, "commodity": 0.15, "cash": 0.20}

    adjusted = {
        "gold": base["gold"] - (0.03 * macro_score),
        "btc": base["btc"] + (0.18 * macro_score),
        "bond": base["bond"] - (0.10 * macro_score),
        "commodity": base["commodity"] + (0.01 * macro_score),
        "cash": base["cash"] - (0.06 * macro_score),
    }
    if hedge:
        adjusted["gold"] += 0.04
        adjusted["bond"] += 0.04
        adjusted["cash"] += 0.04
        adjusted["btc"] -= 0.08
        adjusted["commodity"] -= 0.04

    # Horizon adjustments: shift risk exposure
    _horizon_adj = {
        "short":  {"btc": -0.10, "commodity": -0.05, "cash": +0.10, "bond": +0.05},
        "medium": {},
        "long":   {"btc": +0.10, "commodity": +0.05, "cash": -0.10, "bond": -0.05},
    }
    for asset, delta in _horizon_adj.get(horizon, {}).items():
        adjusted[asset] = max(0.03, adjusted.get(asset, 0) + delta)

    return _normalize_weights_alloc(adjusted)


def _derive_current_allocation(target: Dict[str, float], supplied: Optional[Dict[str, Any]]) -> Dict[str, float]:
    if not supplied:
        return target
    if not any(isinstance(supplied.get(key), (int, float)) for key in _ALLOCATION_KEYS):
        return target
    return _normalize_weights_alloc({key: _get_number(supplied.get(key), target[key]) for key in _ALLOCATION_KEYS})


def _derive_rebalance_actions(
    target: Dict[str, float],
    current: Dict[str, float],
    direct_actions: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    if direct_actions:
        actions: List[Dict[str, Any]] = []
        for item in direct_actions:
            asset = _get_string(item.get("asset"), "").lower()
            if asset not in _ALLOCATION_KEYS:
                continue
            delta = _get_number(item.get("delta", item.get("deviation")), 0.0)
            actions.append({
                "asset": asset,
                "action": "SELL" if _get_string(item.get("action"), "BUY").upper() == "SELL" else "BUY",
                "delta": delta,
                "current_weight": _get_number(item.get("current_weight"), current[asset]),
                "target_weight": _get_number(item.get("target_weight"), target[asset]),
            })
        if actions:
            return actions

    derived: List[Dict[str, Any]] = []
    for asset in _ALLOCATION_KEYS:
        delta = round(target[asset] - current[asset], 4)
        if abs(delta) <= 0.05:
            continue
        derived.append({
            "asset": asset,
            "action": "BUY" if delta > 0 else "SELL",
            "delta": delta,
            "current_weight": current[asset],
            "target_weight": target[asset],
        })
    return derived


def _normalize_macro(response: Dict[str, Any], horizon: str = "medium") -> Dict[str, Any]:
    metrics = response.get("metrics") if isinstance(response.get("metrics"), dict) else {}
    fallback_fields_raw = response.get("fallback_fields") if isinstance(response.get("fallback_fields"), list) else []
    source_fields_raw = response.get("source_fields") if isinstance(response.get("source_fields"), list) else []
    field_sources_raw = response.get("field_sources") if isinstance(response.get("field_sources"), dict) else {}
    fallback_fields = [
        field_name for field_name in fallback_fields_raw
        if isinstance(field_name, str) and field_name.strip()
    ]
    source_fields = [
        field_name for field_name in source_fields_raw
        if isinstance(field_name, str) and field_name.strip()
    ]
    field_sources = {
        key: value
        for key, value in field_sources_raw.items()
        if isinstance(key, str) and key.strip() and isinstance(value, str) and value.strip()
    }
    has_field_level_fallback = bool(fallback_fields) or any(
        "fallback" in value.lower() for value in field_sources.values()
    )
    normalized_metrics: Dict[str, Any] = {
        "dxy": _get_number(metrics.get("dxy"), 98.5),
        "vix": _get_number(metrics.get("vix"), 22.0),
        "us10y": _get_number(metrics.get("us10y"), 4.25),
        "brent": _get_number(metrics.get("brent"), 92.0),
        "xau": _get_number(metrics.get("xau"), 4800),
        "btc_d": _get_number(metrics.get("btc_d"), 59.8),
        "usdt_d": _get_number(metrics.get("usdt_d"), 7.5),
        "hg": _get_number(metrics.get("hg"), 4.5),
        "event_risk_score": _get_number(metrics.get("event_risk_score"), 0.18),
        "hours_to_event": _get_number(metrics.get("hours_to_event"), 72),
    }
    regime = _get_string(
        response.get("regime") or metrics.get("regime") or metrics.get("market_regime") or metrics.get("current_regime"),
        "NORMALIZATION",
    ).upper()
    macro_score = _get_number(response.get("macro_score"), _derive_macro_score(normalized_metrics))
    timestamp = _clean_timestamp(response.get("last_updated")) or _clean_timestamp(response.get("timestamp"))
    fallback_used = bool(response.get("fallback_used", response.get("fallback", False)) or has_field_level_fallback)
    raw_status = _get_string(response.get("data_status"), _data_status(timestamp, fallback_used))
    data_status = "PARTIAL_FALLBACK" if has_field_level_fallback and raw_status != "FALLBACK" else raw_status
    verified = (
        False
        if data_status in {"FALLBACK", "PARTIAL_FALLBACK", "MOCK", "MISSING", "UNKNOWN"}
        else bool(response.get("verified")) if response.get("verified") is not None else data_status == "LIVE"
    )
    allocation_plan = build_allocation_plan(
        horizon=horizon,
        regime=regime,
        metrics=normalized_metrics,
        data_status=data_status,
        verified=verified,
        hedge_on=response.get("hedge") if isinstance(response.get("hedge"), bool) else None,
    )
    hedge_signal = allocation_plan["hedge_on"]
    hedge_unverified = bool(hedge_signal) and verified is False
    current = _derive_current_allocation(allocation_plan["weights"], response.get("allocation_current"))
    rebalance_actions = [] if allocation_plan["verified"] is False else _derive_rebalance_actions(
        allocation_plan["weights"],
        current,
        response.get("rebalance_actions"),
    )

    return {
        "status": _get_string(response.get("status"), "ok"),
        "source": _get_string(response.get("source"), "macro_stream_fallback" if fallback_used else "dashboard-gateway"),
        "timestamp": timestamp,
        "last_updated": timestamp,
        "fallback_used": fallback_used,
        "data_status": data_status,
        "fallback": fallback_used,
        "regime": regime,
        "macro_score": macro_score,
        "hedge": hedge_signal,
        "hedge_unverified": hedge_unverified,
        "hedge_source": "derived_from_unverified_macro" if hedge_unverified else "backend" if isinstance(response.get("hedge"), bool) else "derived",
        "verified": allocation_plan["verified"],
        "live": data_status == "LIVE" and allocation_plan["verified"] is True,
        "warning": _get_string(
            response.get("warning"),
            "Macro data is partially sourced from Sentinel and partially from fallback/hardcoded defaults; it is not verified live market data."
            if data_status == "PARTIAL_FALLBACK"
            else "Macro data is fallback/hardcoded and not verified live market data."
            if data_status == "FALLBACK"
            else "",
        ) or None,
        "fallback_fields": fallback_fields,
        "source_fields": source_fields,
        "field_sources": field_sources if field_sources else None,
        "position_size_pct": _get_number(response.get("position_size_pct"), 0.15),
        "stop_loss_pct": _get_number(response.get("stop_loss_pct"), 0.08),
        "allocation_target": allocation_plan["weights"],
        "allocation_current": current,
        "allocation_horizon": allocation_plan["allocation_horizon"],
        "allocation_profile": allocation_plan["allocation_profile"],
        "allocation_basis": allocation_plan["allocation_basis"],
        "warnings": allocation_plan["warnings"],
        "horizon_adjustments": allocation_plan["horizon_adjustments"],
        "rebalance_required": False if allocation_plan["verified"] is False else bool(response.get("rebalance_required", len(rebalance_actions) > 0)),
        "rebalance_actions": rebalance_actions,
        "metrics": normalized_metrics,
        "error": response.get("error"),
    }


def _normalize_consensus(
    gateway: Dict[str, Any],
    process: Dict[str, Any],
    symbol: str,
    timeframe: str,
) -> Dict[str, Any]:
    gateway_components = gateway.get("components") if isinstance(gateway.get("components"), dict) else {}
    gateway_module_sources = gateway.get("module_sources") if isinstance(gateway.get("module_sources"), dict) else {}
    process_module_sources = process.get("module_sources") if isinstance(process.get("module_sources"), dict) else {}
    module_scores = process.get("module_scores") if isinstance(process.get("module_scores"), dict) else {}
    module_weights = process.get("module_weights") if isinstance(process.get("module_weights"), dict) else {}
    action = _get_string(process.get("action") or gateway.get("action"), "HOLD").upper()
    failed_criteria = process.get("failed_criteria") if isinstance(process.get("failed_criteria"), list) else []
    cbr = process.get("cbr") if isinstance(process.get("cbr"), dict) else {}
    multi_tf = process.get("multi_tf") if isinstance(process.get("multi_tf"), dict) else {}
    sentinel = process.get("sentinel") if isinstance(process.get("sentinel"), dict) else {}
    sentinel_context = sentinel.get("regime_context") if isinstance(sentinel.get("regime_context"), dict) else {}
    criteria = process.get("criteria") if isinstance(process.get("criteria"), dict) else {}

    def _gc(name: str) -> Dict[str, Any]:
        val = gateway_components.get(name)
        return val if isinstance(val, dict) else {}

    def _pick_module_source(process_key: str, gateway_key: Optional[str] = None) -> Dict[str, Any]:
        process_candidate = process_module_sources.get(process_key)
        if isinstance(process_candidate, dict):
            return process_candidate
        if gateway_key:
            gateway_candidate = gateway_module_sources.get(gateway_key)
            if isinstance(gateway_candidate, dict):
                return gateway_candidate
        return _default_module_source(process_key)

    normalized_module_scores = {
        "touche": _get_number(module_scores.get("touche"), _get_number(_gc("touche").get("score"), 0.5)),
        "fundamental": _get_number(module_scores.get("fundamental"), _get_number(_gc("fundamental").get("score"), 0.5)),
        "news": _get_number(module_scores.get("news"), _get_number(_gc("news").get("score"), 0.5)),
        "sentinel": _get_number(module_scores.get("sentinel"), 0.5),
        "quantum": _get_number(module_scores.get("quantum"), 0.5),
    }
    normalized_module_weights = {
        "touche": _get_number(module_weights.get("touche"), 0.4),
        "fundamental": _get_number(module_weights.get("fundamental"), 0.3),
        "news": _get_number(module_weights.get("news"), 0.15),
        "sentinel": _get_number(module_weights.get("sentinel"), 0.1),
        "quantum": _get_number(module_weights.get("quantum"), 0.05),
    }
    five_module_score = _get_number(
        process.get("five_module_score"),
        round(sum(normalized_module_scores[key] * normalized_module_weights[key] for key in normalized_module_scores), 4),
    )

    normalized_provenance = {
        "technical": _pick_module_source("technical", "technical"),
        "fundamental": _pick_module_source("fundamental", "fundamental"),
        "news": _pick_module_source("news", "news"),
        "sentinel": _pick_module_source("sentinel"),
        "quantum": _pick_module_source("quantum"),
    }

    timestamp = _pick_latest_timestamp(
        _clean_timestamp(process.get("last_updated")),
        _clean_timestamp(process.get("timestamp")),
        _clean_timestamp(gateway.get("last_updated")),
        _clean_timestamp(gateway.get("timestamp")),
        *[_clean_timestamp(module_source.get("timestamp")) for module_source in normalized_provenance.values()],
    )
    fallback_used = bool(
        gateway.get("fallback_used", False)
        or process.get("fallback_used", False)
        or any(bool(module_source.get("fallback_used")) for module_source in normalized_provenance.values())
    )
    data_status = _aggregate_status([
        _get_string(process.get("data_status"), ""),
        _get_string(gateway.get("data_status"), ""),
        *[_get_string(module_source.get("data_status"), "") for module_source in normalized_provenance.values()],
    ])
    warnings = _merge_warnings(
        gateway.get("warnings"),
        process.get("warnings"),
        *[module_source.get("warnings") for module_source in normalized_provenance.values()],
    )
    if data_status in {"STALE", "FALLBACK", "MOCK", "MISSING", "UNKNOWN"}:
        warnings = _merge_warnings(warnings, ["Signal is not verified because source data is stale/fallback/mock."])
    verified = (
        data_status in {"LIVE", "RECENT"}
        and all(bool(module_source.get("verified")) for module_source in normalized_provenance.values())
        and process.get("verified", True) is not False
        and gateway.get("verified", True) is not False
    )
    source = (
        _clean_timestamp(process.get("source"))
        or _clean_timestamp(gateway.get("source"))
        or ("consensus_stream_fallback" if fallback_used else "dashboard-gateway")
    )
    asset = _get_string(
        process.get("asset") or gateway.get("asset"),
        symbol.replace("/USDT", "").replace("/", "").upper(),
    )

    return {
        "asset": asset,
        "action": action,
        "confidence": _get_number(process.get("confidence"), _get_number(gateway.get("confidence"), 0.5)),
        "weighted_score": _get_number(gateway.get("weighted_score"), five_module_score),
        "source": source,
        "last_updated": timestamp,
        "fallback_used": fallback_used,
        "verified": verified,
        "data_status": data_status,
        "warnings": warnings,
        "module_sources": normalized_provenance,
        "green_light": bool(process.get("green_light", False)),
        "green_light_reason": ", ".join(failed_criteria) if failed_criteria else "all_criteria_pass",
        "failed_criteria": failed_criteria,
        "criteria": {
            "regime_suitable": bool(criteria.get("regime_suitable", process.get("green_light", False))),
            "dynamic_threshold_pass": bool(criteria.get("dynamic_threshold_pass", process.get("green_light", False))),
            "modules_agree_3plus": bool(criteria.get("modules_agree_3plus", process.get("green_light", False))),
            "multi_tf_aligned": bool(criteria.get("multi_tf_aligned", process.get("green_light", False))),
            "cbr_edge_valid": bool(criteria.get("cbr_edge_valid", True)),
            "liquidity_ok": bool(criteria.get("liquidity_ok", True)),
            "risk_multiplier_ok": bool(criteria.get("risk_multiplier_ok", True)),
            "event_risk_ok": bool(criteria.get("event_risk_ok", True)),
        },
        "module_scores": normalized_module_scores,
        "module_weights": normalized_module_weights,
        "components": {
            "touche": {
                "score": _get_number(_gc("touche").get("score"), 0.5),
                "weight": _get_number(_gc("touche").get("weight"), 0.5),
            },
            "fundamental": {
                "score": _get_number(_gc("fundamental").get("score"), 0.5),
                "weight": _get_number(_gc("fundamental").get("weight"), 0.35),
            },
            "news": {
                "score": _get_number(_gc("news").get("score"), 0.5),
                "weight": _get_number(_gc("news").get("weight"), 0.15),
            },
        },
        "five_module_score": five_module_score,
        "position_size": _get_number(process.get("position_size"), 0.0),
        "symbol": _get_string(gateway.get("symbol"), symbol),
        "timeframe": _get_string(gateway.get("timeframe"), timeframe),
        "timestamp": timestamp,
        "cbr": {
            "sample_count": int(_get_number(cbr.get("sample_count"), 20)),
            "win_rate_pct": _get_number(cbr.get("win_rate_pct"), 60.0),
            "similarity_score": _get_number(cbr.get("similarity_score"), 0.7),
            "include_in_consensus": bool(cbr.get("include_in_consensus", True)),
            "is_historical_weak": bool(cbr.get("is_historical_weak", False)),
            "confidence_modifier": _get_number(cbr.get("confidence_modifier"), 1.0),
            "reason": _get_string(cbr.get("reason"), "cbr_edge_valid"),
        },
        "multi_tf": {
            "is_valid": bool(multi_tf.get("is_valid", True)),
            "final_signal": _get_string(multi_tf.get("final_signal"), action),
            "reason": _get_string(multi_tf.get("reason"), "aligned"),
            "holding_period_hours": _get_number(multi_tf.get("holding_period_hours"), 24),
        },
        "sentinel": {
            "risk_multiplier": _get_number(sentinel.get("risk_multiplier"), 0.8),
            "regime_context": {
                "event_risk_score": _get_number(sentinel_context.get("event_risk_score"), 0.18),
                "hours_to_event": _get_number(sentinel_context.get("hours_to_event"), 72),
                "is_low_risk": bool(sentinel_context.get("is_low_risk", True)),
                "source": _get_string(sentinel_context.get("source"), "derived"),
            },
        },
        "confidence_interval": process.get("confidence_interval"),
        "meta_score": process.get("meta_score"),
        "correlation_penalty": process.get("correlation_penalty"),
        "correlation_penalized_pairs": process.get("correlation_penalized_pairs"),
        "attribution_ref": process.get("attribution_ref"),
        "adjusted_module_weights": process.get("adjusted_module_weights"),
    }


def _empty_attribution(period: str) -> Dict[str, Any]:
    def _module(role: str) -> Dict[str, Any]:
        return {"total_trades": 0, "win_rate": 0.0, "attribution_score": 0.0, "role": role}
    return {
        "period": period,
        "modules": {
            "touche": _module("Momentum"),
            "fundamental": _module("Valuation"),
            "sentinel": _module("Risk Overlay"),
            "news": _module("Flow"),
            "quantum": _module("Probabilistic"),
        },
    }


def _normalize_attribution(response: Dict[str, Any], period: str) -> Dict[str, Any]:
    modules = response.get("modules") if isinstance(response.get("modules"), dict) else {}

    def _from_aliases(*aliases: str, role: str) -> Dict[str, Any]:
        found = next((modules.get(a) for a in aliases if isinstance(modules.get(a), dict)), {})
        return {
            "total_trades": int(_get_number(found.get("total_trades"), 0)),
            "win_rate": _get_number(found.get("win_rate"), 0.0),
            "attribution_score": _get_number(found.get("attribution_score"), 0.0),
            "role": _get_string(found.get("role"), role),
        }

    return {
        "period": _get_string(response.get("period"), period),
        "modules": {
            "touche":      _from_aliases("touche", "touche_ai",           role="Momentum"),
            "fundamental": _from_aliases("fundamental", "fundamental_ai", role="Valuation"),
            "sentinel":    _from_aliases("sentinel", "sentinel_ai",       role="Risk Overlay"),
            "news":        _from_aliases("news", "news_ai",               role="Flow"),
            "quantum":     _from_aliases("quantum", "quantum_ai",         role="Probabilistic"),
        },
    }


def _normalize_cbr(response: Dict[str, Any], symbol: str, consensus: Dict[str, Any]) -> Dict[str, Any]:
    matches_raw = response.get("matches") if isinstance(response.get("matches"), list) else []
    normalized_matches = []
    for idx, match in enumerate(matches_raw):
        if not isinstance(match, dict):
            continue
        normalized_matches.append({
            "id":         _get_string(match.get("id"), f"match-{idx + 1}"),
            "label":      _get_string(match.get("label"), f"Edge sample {idx + 1}"),
            "similarity": _get_number(match.get("similarity"), _get_number(response.get("similarity_score"), 0.7)),
            "outcome":    _get_string(match.get("outcome"), "NEUTRAL").upper(),
            "regime":     _get_string(match.get("regime"), "historical_edge"),
            "note":       _get_string(match.get("note"), _get_string(response.get("reason"), "historical_edge_context")),
        })
    cbr_defaults = consensus.get("cbr", {})

    return {
        "symbol":              _get_string(response.get("symbol"), symbol.replace("/USDT", "").replace("/", "")),
        "similarity_score":    _get_number(response.get("similarity_score"), _get_number(cbr_defaults.get("similarity_score"), 0.7)),
        "sample_count":        int(_get_number(response.get("sample_count"), _get_number(cbr_defaults.get("sample_count"), 20))),
        "win_rate_pct":        _get_number(response.get("win_rate_pct"), _get_number(cbr_defaults.get("win_rate_pct"), 60.0)),
        "include_in_consensus": bool(response.get("include_in_consensus", True)),
        "is_historical_weak":  bool(response.get("is_historical_weak", False)),
        "confidence_modifier": _get_number(response.get("confidence_modifier"), 1.0),
        "reason":              _get_string(response.get("reason"), _get_string(cbr_defaults.get("reason"), "cbr_edge_valid")),
        "matches":             normalized_matches,
    }


def _normalize_weights_response(response: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize the /weights endpoint response for SSE weights event."""
    weights = response.get("weights") if isinstance(response.get("weights"), dict) else {}
    return {
        "weights": {
            "touche":      _get_number(weights.get("touche"),      0.35),
            "fundamental": _get_number(weights.get("fundamental"), 0.30),
            "news":        _get_number(weights.get("news"),        0.20),
            "sentinel":    _get_number(weights.get("sentinel"),    0.10),
            "quantum":     _get_number(weights.get("quantum"),     0.05),
        },
        "drift_total":  _get_number(response.get("drift_total"), 0.0),
        "drift_limit":  _get_number(response.get("drift_limit"), 0.15),
        "drift_frozen": bool(response.get("drift_frozen", False)),
        "backup_exists": bool(response.get("backup_exists", False)),
        "week_start":   response.get("week_start", ""),
    }


async def _fetch_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    **kwargs: Any,
) -> Tuple[Dict[str, Any], str]:
    response = await client.request(method, url, **kwargs)
    response.raise_for_status()
    payload = response.json()
    return (payload if isinstance(payload, dict) else {}, "healthy")


def _detect_alerts(
    prev_consensus: Optional[Dict[str, Any]],
    curr_consensus: Dict[str, Any],
    curr_macro: Dict[str, Any],
    prev_hedge: Optional[bool],
) -> List[Dict[str, Any]]:
    """Derive alert events by comparing current vs previous state."""
    alerts: List[Dict[str, Any]] = []

    # Signal change alert
    prev_action = (prev_consensus or {}).get("action", "HOLD")
    curr_action = curr_consensus.get("action", "HOLD")
    if prev_consensus is not None and prev_action != curr_action:
        if "HOLD" not in (prev_action, curr_action) or curr_action in ("BUY", "SELL"):
            severity = "warning" if curr_action == "SELL" else "info"
            alerts.append({
                "type": "SIGNAL_CHANGE",
                "message": f"Sinyal değişti: {prev_action} → {curr_action}",
                "severity": severity,
                "timestamp": _now_iso(),
            })

    # Rebalance alert — emit once per rebalance_required=True edge
    if curr_macro.get("rebalance_required") and not (curr_consensus or {}).get("_rebalance_notified"):
        actions = curr_macro.get("rebalance_actions", [])
        if actions:
            top = actions[0]
            asset = str(top.get("asset", "")).upper()
            direction = str(top.get("action", "BUY"))
            delta_pct = round(abs(_get_number(top.get("delta"), 0)) * 100, 1)
            alerts.append({
                "type": "REBALANCE",
                "message": f"Rebalans: {asset} {direction} +{delta_pct}%",
                "severity": "warning",
                "timestamp": _now_iso(),
            })

    # Hedge toggle alert
    curr_hedge = curr_macro.get("hedge", False)
    if prev_hedge is not None and prev_hedge != curr_hedge:
        alerts.append({
            "type": "HEDGE_TOGGLE",
            "message": f"Hedge {'AKTİF' if curr_hedge else 'KAPANDI'}",
            "severity": "warning" if curr_hedge else "info",
            "timestamp": _now_iso(),
        })

    # Learning freeze alert (from weights if drift_frozen)
    return alerts


async def _build_snapshot(
    client: httpx.AsyncClient,
    symbol: str,
    timeframe: str,
    period: str,
    horizon: str = "medium",
) -> Dict[str, Any]:
    symbol_short = symbol.replace("/USDT", "").replace("/", "")
    service_states: Dict[str, str] = {
        "macro": "healthy",
        "consensus": "healthy",
        "attribution": "healthy",
        "cbr": "healthy",
    }

    async def _safe(label: str, coro: Any, fallback: Dict[str, Any]) -> Dict[str, Any]:
        try:
            payload, state = await coro
            service_states[label] = state
            return payload
        except Exception:
            service_states[label] = "degraded"
            return fallback

    macro_raw = await _safe(
        "macro",
        _fetch_json(client, "GET", f"{_DASHBOARD_SELF_URL}/api/macro", params={"horizon": horizon}),
        {
            "status": "degraded",
            "fallback": True,
            "fallback_used": True,
            "data_status": "FALLBACK",
            "source": "macro_stream_fallback",
            "warning": "Macro data is fallback/hardcoded and not verified live market data.",
            "fallback_fields": ["dxy", "vix", "us10y", "brent", "xau", "btc_d", "usdt_d", "hg", "event_risk_score", "hours_to_event", "regime"],
            "field_sources": {
                "dxy": "hardcoded_fallback",
                "vix": "hardcoded_fallback",
                "us10y": "hardcoded_fallback",
                "brent": "hardcoded_fallback",
                "xau": "hardcoded_fallback",
                "btc_d": "hardcoded_fallback",
                "usdt_d": "hardcoded_fallback",
                "hg": "hardcoded_fallback",
                "event_risk_score": "hardcoded_fallback",
                "hours_to_event": "hardcoded_fallback",
                "regime": "hardcoded_fallback",
            },
            "metrics": {},
            "timestamp": None,
            "last_updated": None,
        },
    )
    gateway_consensus = await _safe(
        "consensus",
        _fetch_json(
            client, "GET", f"{_DASHBOARD_SELF_URL}/api/consensus",
            params={"symbol": symbol, "timeframe": timeframe, "horizon": horizon},
        ),
        {"action": "HOLD", "confidence": 0.5, "weighted_score": 0.5, "components": {}, "timestamp": None, "last_updated": None, "source": "gateway_stream_fallback", "fallback_used": True, "data_status": "FALLBACK"},
    )
    # Extract live scores from gateway to feed into /process
    _gw_components = gateway_consensus.get("components") or {}
    _gw_ts = gateway_consensus.get("timestamp") or gateway_consensus.get("last_updated")
    _process_body: dict = {"symbol": symbol_short, "timeframe": timeframe, "horizon": horizon}
    if _gw_ts:
        _process_body["timestamp"] = _gw_ts
    _touche_score = (_gw_components.get("touche") or {}).get("score")
    _fundamental_score = (_gw_components.get("fundamental") or {}).get("score")
    _news_score = (_gw_components.get("news") or {}).get("score")
    if _touche_score is not None:
        _process_body["touche_eqs"] = round(float(_touche_score) * 100, 2)
        if _gw_ts:
            _process_body["touche_timestamp"] = _gw_ts
    if _fundamental_score is not None:
        _process_body["fundamental_score"] = round(float(_fundamental_score) * 100, 2)
        if _gw_ts:
            _process_body["fundamental_timestamp"] = _gw_ts
    if _news_score is not None:
        _process_body["news_sentiment"] = round(float(_news_score), 4)

    process_consensus = await _safe(
        "consensus",
        _fetch_json(
            client, "POST", f"{_CONSENSUS_URL}/process",
            json=_process_body,
        ),
        {
            "action": "HOLD", "green_light": False,
            "module_scores": {}, "module_weights": {},
            "cbr": {}, "timestamp": None, "last_updated": None, "source": "process_stream_fallback", "fallback_used": True, "data_status": "FALLBACK",
        },
    )
    attribution_raw = await _safe(
        "attribution",
        _fetch_json(
            client, "GET", f"{_ANALYZER_URL}/dashboard/exit_attribution",
            params={"period": period},
        ),
        _empty_attribution(period),
    )

    macro = _normalize_macro(macro_raw, horizon=horizon)
    consensus = _normalize_consensus(gateway_consensus, process_consensus, symbol, timeframe)

    cbr_raw = await _safe(
        "cbr",
        _fetch_json(
            client, "GET", f"{_CONSENSUS_URL}/consensus/historical_edge",
            params={
                "symbol": symbol_short,
                "sample_count": consensus["cbr"]["sample_count"],
                "win_rate_pct": consensus["cbr"]["win_rate_pct"],
                "similarity_score": consensus["cbr"]["similarity_score"],
            },
        ),
        {},
    )

    all_healthy = all(s == "healthy" for s in service_states.values())

    return {
        "timestamp": _now_iso(),
        "system_health": {
            "status": "HEALTHY" if all_healthy and macro["status"].lower() == "ok" else "DEGRADED",
            "services": service_states,
        },
        "snapshot": {
            "macro": macro,
            "consensus": consensus,
            "attribution": _normalize_attribution(attribution_raw, period),
            "cbr": _normalize_cbr(cbr_raw, symbol, consensus),
        },
    }


async def _fetch_weights(client: httpx.AsyncClient) -> Optional[Dict[str, Any]]:
    """Fetch /weights from consensus service; return None on error."""
    try:
        resp = await client.get(
            f"{_CONSENSUS_URL}/weights",
            timeout=_WEIGHTS_FETCH_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return _normalize_weights_response(data if isinstance(data, dict) else {})
    except Exception:
        return None


async def _event_stream(
    request: Request,
    symbol: str,
    timeframe: str,
    period: str,
    horizon: str = "medium",
) -> AsyncGenerator[str, None]:
    """
    Async generator for SSE events.
    Emits:
      event:snapshot every 2s (full normalized system snapshot)
      event:weights  every 2s (consensus module weights + drift)
      event:alert    on state transitions (signal change, rebalance, hedge toggle)
      event:ping     every 30s (heartbeat)
    """
    timeout = httpx.Timeout(8.0, connect=3.0)
    yield "retry: 2000\n\n"

    tick = 0
    prev_consensus: Optional[Dict[str, Any]] = None
    prev_hedge: Optional[bool] = None

    async with httpx.AsyncClient(timeout=timeout) as client:
        while True:
            if await request.is_disconnected():
                break

            # ── Heartbeat ping ────────────────────────────────────────
            if tick > 0 and tick % _PING_INTERVAL_TICKS == 0:
                yield f"event: ping\ndata: {json.dumps({'ts': _now_iso()})}\n\n"

            # ── Main snapshot ─────────────────────────────────────────
            try:
                payload = await _build_snapshot(client, symbol, timeframe, period, horizon=horizon)
                yield f"event: snapshot\ndata: {json.dumps(payload)}\n\n"

                curr_consensus = payload["snapshot"]["consensus"]
                curr_macro = payload["snapshot"]["macro"]

                # ── Alert detection ───────────────────────────────────
                alerts = _detect_alerts(prev_consensus, curr_consensus, curr_macro, prev_hedge)
                for alert in alerts:
                    yield f"event: alert\ndata: {json.dumps(alert)}\n\n"

                prev_consensus = curr_consensus
                prev_hedge = curr_macro.get("hedge", False)

            except Exception as exc:
                error_payload = {
                    "timestamp": _now_iso(),
                    "system_health": {"status": "DEGRADED", "services": {"stream": "degraded"}},
                    "error": str(exc),
                }
                yield f"event: error\ndata: {json.dumps(error_payload)}\n\n"

            # ── Weights event ─────────────────────────────────────────
            try:
                weights = await _fetch_weights(client)
                if weights is not None:
                    # Alert if drift frozen state changed
                    if (
                        prev_consensus is not None
                        and weights.get("drift_frozen")
                        and not getattr(_event_stream, "_prev_frozen", False)
                    ):
                        yield (
                            f"event: alert\ndata: {json.dumps({'type': 'LEARNING_FREEZE', 'message': 'Haftalık drift limiti aşıldı — ağırlık güncellemesi donduruldu.', 'severity': 'warning', 'timestamp': _now_iso()})}\n\n"
                        )
                    yield f"event: weights\ndata: {json.dumps(weights)}\n\n"
            except Exception:
                pass

            tick += 1
            await asyncio.sleep(2)


@router.get("/live-feed")
async def live_feed(
    request: Request,
    symbol: str = Query("BTC/USDT", description="Asset symbol, e.g. BTC/USDT"),
    timeframe: str = Query("1h", description="Consensus timeframe"),
    period: str = Query("7d", description="Attribution period"),
    horizon: str = Query("medium", description="Investment horizon: short/medium/long"),
) -> StreamingResponse:
    """
    SSE endpoint: emits snapshot/weights/alert/ping events continuously.

    Connect with:
      const es = new EventSource('/api/live-feed?symbol=BTC%2FUSDT');
      es.addEventListener('snapshot', (e) => { ... });
      es.addEventListener('weights',  (e) => { ... });
      es.addEventListener('alert',    (e) => { ... });
    """
    return StreamingResponse(
        _event_stream(request, symbol, timeframe, period, horizon=horizon),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
