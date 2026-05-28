"""
Sentinel client for extended macro metric fields.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import re
from typing import Any, Dict

import httpx

logger = logging.getLogger(__name__)


class SentinelClient:
    """HTTP client for Sentinel AI detailed metric payloads."""

    DEFAULT_METRICS: Dict[str, Any] = {
        "dxy_trend_7d": 0.0,
        "us10y_trend_7d": 0.0,
        "vix_trend_7d": 0.0,
        "brent_trend_7d": 0.0,
        "sp500_vs_ma200": 1.0,
        "exchange_netflow_btc": 0.0,
        "miner_reserves_change_7d": 0.0,
        "stablecoin_supply_change_7d": 0.0,
        "btc_dominance_change_7d": 0.0,
        "hyg_lqd_ratio": 0.0,
        "put_call_ratio": 1.0,
        "credit_spread_ig": 120.0,
        "global_liquidity_index": 0.0,
        "btc_nasdaq_corr_30d": 0.0,
        "btc_dxy_corr_30d": 0.0,
        "divergence_flag": "none",
        "correlation_break_signal": False,
    }

    def __init__(self, base_url: str = "http://localhost:8004"):
        self.base_url = base_url.rstrip("/")
        self.timeout = 12.0

    async def fetch_macro_metrics(self) -> Dict[str, Any]:
        """Return macro metrics using only supported Sentinel endpoints."""
        metrics = dict(self.DEFAULT_METRICS)

        # Use only stable Sentinel event-risk endpoint to avoid 404 loops.
        event_payload = await self._get_json("/sentinel/event_risk?symbol=BTC")
        if event_payload:
            metrics["event_risk_score"] = float(event_payload.get("event_risk_score", 0.0))
            metrics["hours_to_event"] = float(event_payload.get("hours_to_event", 72.0))
            metrics["is_low_risk"] = bool(event_payload.get("is_low_risk", True))

        # Prometheus metrics parsing fallback for numeric/bool values.
        prom_text = await self._get_text("/metrics")
        if prom_text:
            metrics.update(self._extract_metrics_from_prometheus(prom_text))

        metrics["timestamp"] = datetime.now(timezone.utc).isoformat()
        return metrics

    async def _get_json(self, endpoint: str) -> Dict[str, Any] | None:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}{endpoint}")
                if response.status_code != 200:
                    return None
                data = response.json()
                return data if isinstance(data, dict) else None
        except Exception:
            return None

    async def _get_text(self, endpoint: str) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}{endpoint}")
                if response.status_code != 200:
                    return None
                return response.text
        except Exception:
            return None

    def _extract_metrics_from_json(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        extracted: Dict[str, Any] = {}

        candidates = [payload]
        metrics_node = payload.get("metrics")
        if isinstance(metrics_node, dict):
            candidates.append(metrics_node)

        for source in candidates:
            for key in self.DEFAULT_METRICS:
                if key in source:
                    extracted[key] = source[key]

        # Normalize known typed fields.
        if "divergence_flag" in extracted:
            extracted["divergence_flag"] = str(extracted["divergence_flag"])
        if "correlation_break_signal" in extracted:
            extracted["correlation_break_signal"] = bool(extracted["correlation_break_signal"])

        for key, default_val in self.DEFAULT_METRICS.items():
            if key not in extracted:
                continue
            if isinstance(default_val, float):
                try:
                    extracted[key] = float(extracted[key])
                except Exception:
                    extracted[key] = default_val

        return extracted

    def _extract_metrics_from_prometheus(self, raw_text: str) -> Dict[str, Any]:
        extracted: Dict[str, Any] = {}

        # Parse numeric values from Prometheus line format: metric_name value
        for key, default_val in self.DEFAULT_METRICS.items():
            if not isinstance(default_val, float):
                continue
            pattern = rf"^{re.escape(key)}(?:\{{[^}}]*\}})?\s+([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)$"
            match = re.search(pattern, raw_text, flags=re.MULTILINE)
            if match:
                try:
                    extracted[key] = float(match.group(1))
                except Exception:
                    pass

        # Optional labeled string-like metric pattern:
        # divergence_flag{value="macro_crypto_decouple"} 1
        divergence_match = re.search(
            r'^divergence_flag\{[^}]*value="([^"]+)"[^}]*\}\s+1(?:\.0+)?$',
            raw_text,
            flags=re.MULTILINE,
        )
        if divergence_match:
            extracted["divergence_flag"] = divergence_match.group(1)

        cbreak_pattern = r'^correlation_break_signal(?:\{[^}]*\})?\s+([-+]?\d*\.?\d+)$'
        cbreak_match = re.search(cbreak_pattern, raw_text, flags=re.MULTILINE)
        if cbreak_match:
            try:
                extracted["correlation_break_signal"] = float(cbreak_match.group(1)) > 0.5
            except Exception:
                pass

        return extracted
