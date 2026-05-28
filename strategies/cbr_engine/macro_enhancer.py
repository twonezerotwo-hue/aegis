"""
AEGIS CBR Engine - Macro Enhancer

Kategori 5: AEGIS modul ozetleri
Kategori 6: Zaman/olay riski
Kategori 7: Pozisyon baglami
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict


class CBRMacroEnhancer:
    """CBR pipeline icin makro/bağlamsal ozellik zenginlestirici."""

    def enrich(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        base_macro = dict(market_data.get("macro", {}) or {})

        category5 = self._category5_module_summaries(market_data)
        category6 = self._category6_time_event_risk(market_data)
        category7 = self._category7_position_context(market_data)

        # Duz map olarak da expose edelim ki fingerprint pipeline kolayca kullansin.
        flattened = {
            **category5,
            **category6,
            **category7,
        }

        enriched = {
            **base_macro,
            **flattened,
            "category5_module_summaries": category5,
            "category6_time_event_risk": category6,
            "category7_position_context": category7,
        }
        return enriched

    def _category5_module_summaries(self, market_data: Dict[str, Any]) -> Dict[str, float]:
        """Kategori 5: AEGIS modul ozetleri."""
        module_metrics = market_data.get("module_metrics", {}) or {}
        consensus = market_data.get("consensus", {}) or {}

        return {
            "mod_touche_score": float(module_metrics.get("touche_score", 0.0)),
            "mod_fundamental_score": float(module_metrics.get("fundamental_score", 0.0)),
            "mod_quantum_score": float(module_metrics.get("quantum_score", 0.0)),
            "mod_sentinel_score": float(module_metrics.get("sentinel_score", 0.0)),
            "mod_news_score": float(module_metrics.get("news_score", 0.0)),
            "mod_consensus_confidence": float(consensus.get("confidence", 0.0)),
            "mod_consensus_weighted_score": float(consensus.get("weighted_score", 0.0)),
        }

    def _category6_time_event_risk(self, market_data: Dict[str, Any]) -> Dict[str, float]:
        """Kategori 6: Zaman/olay riski."""
        ts_raw = market_data.get("timestamp")
        try:
            ts = datetime.fromisoformat(str(ts_raw)) if ts_raw else datetime.now(timezone.utc)
        except Exception:
            ts = datetime.now(timezone.utc)

        event_flags = market_data.get("event_flags", {}) or {}
        hour = ts.hour
        weekday = ts.weekday()

        # Basit saat riski: US seansi acilisi/volatil saatler.
        intraday_risk = 1.0 if hour in {12, 13, 14, 15, 16, 17, 18, 19} else 0.3
        weekend_risk = 1.0 if weekday >= 5 else 0.0
        macro_event_risk = 1.0 if bool(event_flags.get("macro_event_window", False)) else 0.0
        earnings_risk = 1.0 if bool(event_flags.get("earnings_window", False)) else 0.0

        return {
            "time_intraday_risk": float(intraday_risk),
            "time_weekend_risk": float(weekend_risk),
            "time_macro_event_risk": float(macro_event_risk),
            "time_earnings_risk": float(earnings_risk),
            "time_event_risk_score": float((intraday_risk + weekend_risk + macro_event_risk + earnings_risk) / 4.0),
        }

    def _category7_position_context(self, market_data: Dict[str, Any]) -> Dict[str, float]:
        """Kategori 7: Pozisyon baglami."""
        position_ctx = market_data.get("position_context", {}) or {}

        open_positions = float(position_ctx.get("open_positions", 0.0))
        exposure_pct = float(position_ctx.get("exposure_pct", 0.0))
        drawdown_pct = float(position_ctx.get("drawdown_pct", 0.0))
        leverage = float(position_ctx.get("leverage", 1.0))

        heat = min(1.0, max(0.0, (exposure_pct * 0.5) + (abs(drawdown_pct) * 0.3) + ((leverage - 1.0) * 0.2)))

        return {
            "pos_open_positions": open_positions,
            "pos_exposure_pct": exposure_pct,
            "pos_drawdown_pct": drawdown_pct,
            "pos_leverage": leverage,
            "pos_heat_score": float(heat),
            "pos_has_open_position": 1.0 if open_positions > 0 else 0.0,
        }
