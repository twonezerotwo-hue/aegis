"""
Dashboard routes - aggregated metrics endpoint with timeframe support
"""
from fastapi import APIRouter, Query
from datetime import datetime, timezone
import asyncio
import logging
import os
import httpx
from typing import Any, Optional

from services.prometheus_client import PrometheusClient, TIMEFRAME_MAPPING

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["dashboard"])

# Available symbols
SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"]

# Valid timeframes
VALID_TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d", "1w", "1month"]

# Non-crypto assets derive scores from macro indicators instead of Prometheus
_MACRO_ASSETS = {"XAU", "XAG", "BOND", "CASH"}

# AI service base URLs
_TOUCHE_URL = os.environ.get("TOUCHE_URL", "http://touche-api:8001")
_FUNDAMENTAL_URL = os.environ.get("FUNDAMENTAL_URL", "http://fundamental-api:8002")
_NEWS_URL = os.environ.get("NEWS_URL", "http://news-ai-limited:8006")
_SENTINEL_URL = os.environ.get("SENTINEL_URL", "http://sentinel-api:8004")
_QUANTUM_URL = os.environ.get("QUANTUM_URL", "http://quantum-api:8003")


async def _fetch_live_scores(symbol: str, timeframe: str) -> dict[str, Optional[float]]:
    """
    Fetch real-time module scores directly from each AI service.
    Returns dict with keys: touche, fundamental, news, sentinel, quantum (all 0-1 or None).
    """
    symbol_binance = symbol.replace("/USDT", "").replace("/", "") + "USDT"  # BTC/USDT → BTCUSDT
    symbol_clean = symbol.replace("/USDT", "").replace("/", "")             # BTC/USDT → BTC

    async with httpx.AsyncClient(timeout=5.0) as client:
        results = await asyncio.gather(
            client.get(f"{_TOUCHE_URL}/touche/analyze", params={"symbol": symbol_binance, "timeframe": timeframe}),
            client.get(f"{_FUNDAMENTAL_URL}/fundamental/metrics", params={"symbol": symbol_clean, "timeframe": timeframe}),
            client.get(f"{_NEWS_URL}/signals", params={"symbol": symbol_clean, "timeframe": timeframe}),
            client.get(f"{_SENTINEL_URL}/sentinel/event_risk", params={"symbol": symbol_clean}),
            return_exceptions=True,
        )

    scores: dict[str, Optional[float]] = {"touche": None, "fundamental": None, "news": None, "sentinel": None, "quantum": 0.5}

    # Touche: prefer the per-timeframe signal score; fall back to global EQS.
    # The Touche service returns a single aggregated EQS plus per-TF signal labels.
    # To make the Metrikler tab respond to timeframe changes, we map the selected
    # TF's BUY/SELL/NEUTRAL label to a calibrated 0-1 score when available.
    _TF_SIGNAL_SCORE: dict[str, float] = {
        "BUY": 0.74,
        "HOLD": 0.50,
        "NEUTRAL": 0.50,
        "SELL": 0.26,
    }
    try:
        if not isinstance(results[0], Exception) and results[0].status_code == 200:
            d = results[0].json()
            tf_signals: dict = d.get("tf_signals") or {}
            tf_key = timeframe.lower()
            if tf_key in tf_signals:
                # Timeframe-specific signal available — use it as the primary score
                scores["touche"] = _TF_SIGNAL_SCORE.get(str(tf_signals[tf_key]).upper(), 0.50)
            else:
                # No per-TF signal for this timeframe — use global EQS aggregate
                eqs = float(d.get("eqs") or d.get("eqs_score") or 50.0)
                scores["touche"] = min(max(eqs / 100.0, 0.0), 1.0)
    except Exception as exc:
        logger.debug("live_score touche error: %s", exc)

    # Fundamental: derive from NUPL + MVRV Z-score
    try:
        if not isinstance(results[1], Exception) and results[1].status_code == 200:
            d = results[1].json()
            nupl = float(d.get("nupl") or 0.5)
            mvrv = float(d.get("mvrv_z_score") or 2.0)
            nupl_norm = min(max((nupl + 0.5) / 1.5, 0.0), 1.0)
            mvrv_norm = min(max((4.0 - mvrv) / 4.0, 0.0), 1.0)
            scores["fundamental"] = round(nupl_norm * 0.6 + mvrv_norm * 0.4, 4)
    except Exception as exc:
        logger.debug("live_score fundamental error: %s", exc)

    # News: crypto_impact_score is 0-100
    try:
        if not isinstance(results[2], Exception) and results[2].status_code == 200:
            d = results[2].json()
            signals = d.get("signals") or []
            if signals:
                impact = float(signals[0].get("crypto_impact_score") or 50.0)
                scores["news"] = min(max(impact / 100.0, 0.0), 1.0)
    except Exception as exc:
        logger.debug("live_score news error: %s", exc)

    # Sentinel: event_risk_score 0-1, inverted (low risk = good)
    try:
        if not isinstance(results[3], Exception) and results[3].status_code == 200:
            d = results[3].json()
            risk = float(d.get("event_risk_score") or 0.5)
            scores["sentinel"] = round(1.0 - min(max(risk, 0.0), 1.0), 4)
    except Exception as exc:
        logger.debug("live_score sentinel error: %s", exc)

    return scores


async def _fetch_module_details(symbol: str, timeframe: str) -> dict:
    """
    Fetch raw module data for summary generation.
    Returns a dict with keys: touche, fundamental, news, sentinel (each a raw dict or None).
    """
    symbol_binance = symbol.replace("/USDT", "").replace("/", "") + "USDT"
    symbol_clean = symbol.replace("/USDT", "").replace("/", "")

    async with httpx.AsyncClient(timeout=5.0) as client:
        results = await asyncio.gather(
            client.get(f"{_TOUCHE_URL}/touche/analyze", params={"symbol": symbol_binance, "timeframe": timeframe}),
            client.get(f"{_FUNDAMENTAL_URL}/fundamental/metrics", params={"symbol": symbol_clean, "timeframe": timeframe}),
            client.get(f"{_NEWS_URL}/signals", params={"symbol": symbol_clean, "timeframe": timeframe}),
            client.get(f"{_SENTINEL_URL}/sentinel/event_risk", params={"symbol": symbol_clean}),
            return_exceptions=True,
        )

    details: dict = {"touche": None, "fundamental": None, "news": None, "sentinel": None}
    try:
        if not isinstance(results[0], Exception) and results[0].status_code == 200:
            details["touche"] = results[0].json()
    except Exception:
        pass
    try:
        if not isinstance(results[1], Exception) and results[1].status_code == 200:
            details["fundamental"] = results[1].json()
    except Exception:
        pass
    try:
        if not isinstance(results[2], Exception) and results[2].status_code == 200:
            d = results[2].json()
            sigs = d.get("signals") or []
            details["news"] = sigs[0] if sigs else None
    except Exception:
        pass
    try:
        if not isinstance(results[3], Exception) and results[3].status_code == 200:
            details["sentinel"] = results[3].json()
    except Exception:
        pass
    return details


def _build_metric_summary(module: str, score: float, raw: Optional[dict]) -> str:
    """Build a concise data-driven summary for a metric card."""
    if raw is None:
        return "Servis verisine ulaşılamadı — varsayılan skor kullanıldı."

    if module == "touche":
        eqs = raw.get("eqs") or raw.get("eqs_score") or round(score * 100, 1)
        tf = raw.get("tf_signals") or {}
        parts = [f"{k}: {v}" for k, v in tf.items() if k in ("15m", "1h", "4h", "1d")]
        signals = " · ".join(parts) if parts else "sinyal yok"
        buy_count = sum(1 for v in tf.values() if str(v).upper() == "BUY")
        sell_count = sum(1 for v in tf.values() if str(v).upper() == "SELL")
        if buy_count > sell_count:
            bias = "Çoğunluk AL"
        elif sell_count > buy_count:
            bias = "Çoğunluk SAT"
        else:
            bias = "Karışık sinyal"
        return f"EQS {eqs:.1f} (küresel) · {signals} · {bias}."

    if module == "fundamental":
        mvrv = raw.get("mvrv_z_score")
        nupl = raw.get("nupl")
        quality = raw.get("quality", "")
        parts = []
        if mvrv is not None:
            parts.append(f"MVRV Z: {mvrv:.2f}")
            if mvrv > 3.5:
                parts.append("(aşırı değerli)")
            elif mvrv < 0:
                parts.append("(düşük değerli)")
            else:
                parts.append("(değerleme normal)")
        if nupl is not None:
            parts.append(f"NUPL: {nupl:.2f}")
            if nupl > 0.75:
                parts.append("(öfori — riskli)")
            elif nupl < 0:
                parts.append("(kapitülasyon)")
            else:
                parts.append("(ılımlı kâr)")
        if quality == "mock":
            parts.append("⚠ Veri kaynağı: simüle")
        # On-chain metrics are inherently timeframe-independent
        parts.append("📊 TF bağımsız")
        return " · ".join(parts) + "." if parts else "On-chain veri bekleniyor."

    if module == "news":
        impact = raw.get("crypto_impact_score", round(score * 100, 1))
        conf = raw.get("confidence_level", 0)
        count = raw.get("news_items_count", 0)
        sentiment = raw.get("aggregated_sentiment", 0)
        countries = (raw.get("primary_countries") or [])[:2]
        reg = (raw.get("impact_factors") or {}).get("regulatory_score", 0)
        sent_str = "pozitif" if sentiment > 0.1 else "negatif" if sentiment < -0.1 else "nötr"
        country_str = f" · Ülkeler: {', '.join(countries)}" if countries else ""
        return (
            f"{count} haber analizi · Etki: {impact:.0f} · "
            f"Güven: {conf:.0f}% · Regulatory: {reg:.0f} · "
            f"Genel duygu: {sent_str}{country_str} · 📊 TF bağımsız."
        )

    if module == "sentinel":
        risk = raw.get("event_risk_score", 0.5)
        hours = raw.get("hours_to_event", 0)
        liq = (raw.get("liquidity_composite") or {}).get("liquidity_composite_score", 0)
        vol = (raw.get("volatility_composite") or {}).get("volatility_composite", 0)
        regime_dist = raw.get("regime_probability_distribution") or {}
        top_regime = max(regime_dist, key=lambda k: regime_dist[k]) if regime_dist else None
        top_pct = round(regime_dist.get(top_regime, 0) * 100, 1) if top_regime else 0
        regime_names = {"risk_on": "Risk-On", "risk_off": "Risk-Off", "normalization": "Normalizasyon", "accumulation": "Birikim"}
        regime_str = f" · Rejim: {regime_names.get(top_regime, top_regime)} ({top_pct}%)" if top_regime else ""
        hours_str = f" · {hours:.0f}s içinde kritik olay" if hours and hours < 72 else ""
        return (
            f"Olay riski: {risk*100:.0f}%{hours_str} · "
            f"Likidite: {liq:.0f}/100 · Oynaklık: {vol:.0f}/100{regime_str} · 📊 TF bağımsız."
        )

    if module == "quantum":
        return f"Likidite & tahmin skoru: {score*100:.0f}% — piyasa derinliği verisi henüz bağlanmadı, nötr varsayılan. 📊 TF bağımsız."

    return ""


_TIMEFRAME_SECONDS = {
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
    "1w": 604800,
    "1month": 2592000,
}
_CONSENSUS_STATUS_PRIORITY = ("FALLBACK", "MOCK", "MISSING", "STALE", "UNKNOWN", "RECENT", "LIVE")


def _status_from_timestamp(
    timestamp: str | None,
    fallback_used: bool,
    mock_used: bool = False,
    missing_used: bool = False,
    timeframe: str = "1h",
) -> str:
    if mock_used:
        return "MOCK"
    if missing_used:
        return "MISSING"
    if fallback_used:
        return "FALLBACK"
    if not timestamp:
        return "UNKNOWN"

    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return "UNKNOWN"

    age_seconds = max(0.0, (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds())
    timeframe_seconds = _TIMEFRAME_SECONDS.get(timeframe, 3600)
    live_age_seconds = max(300, min(3600, timeframe_seconds // 8))
    recent_age_seconds = max(1800, min(86400, timeframe_seconds // 2))

    if age_seconds <= live_age_seconds:
        return "LIVE"
    if age_seconds <= recent_age_seconds:
        return "RECENT"
    return "STALE"


def _normalize_score(value: float | None) -> float | None:
    if value is None:
        return None
    normalized = float(value)
    if normalized > 1:
        normalized = normalized / 100.0
    return min(max(normalized, 0.0), 1.0)


def _merge_warnings(*warning_lists: list[str]) -> list[str]:
    merged: list[str] = []
    for warning_list in warning_lists:
        for warning in warning_list:
            if warning and warning not in merged:
                merged.append(warning)
    return merged


def _latest_timestamp(*timestamps: str | None) -> str | None:
    valid = [ts for ts in timestamps if isinstance(ts, str) and ts.strip()]
    if not valid:
        return None
    return max(valid, key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")))


def _aggregate_status(statuses: list[str]) -> str:
    normalized = [status.upper() for status in statuses if isinstance(status, str) and status.strip()]
    for candidate in _CONSENSUS_STATUS_PRIORITY:
        if candidate in normalized:
            return candidate
    return "UNKNOWN"


def _build_module_source(
    *,
    module: str,
    service: str,
    source: str,
    source_data: str,
    timestamp: str | None,
    timestamp_source: str,
    data_status: str,
    fallback_used: bool,
    asset_specific: bool,
    shared_score: bool,
    warnings: list[str],
    value: float,
) -> dict[str, Any]:
    verified = data_status in {"LIVE", "RECENT"} and not fallback_used and asset_specific and not shared_score
    return {
        "module": module,
        "service": service,
        "source": source,
        "source_data": source_data,
        "timestamp": timestamp,
        "timestamp_source": timestamp_source,
        "data_status": data_status,
        "fallback_used": fallback_used,
        "verified": verified,
        "asset_specific": asset_specific,
        "shared_score": shared_score,
        "value": round(value, 4),
        "warnings": warnings,
    }


async def _prometheus_module_snapshot(
    client: PrometheusClient,
    *,
    metric_name: str,
    timeframe: str,
    symbol: str | None,
    module: str,
    allow_unlabelled_fallback: bool,
) -> tuple[float, dict[str, Any]]:
    duration = TIMEFRAME_MAPPING.get(timeframe, "1h")
    candidates: list[tuple[str, str, str, bool, bool]] = []

    if symbol:
        label = symbol.replace('"', '\\"')
        candidates.append((
            f'avg_over_time({metric_name}{{symbol="{label}"}}[{duration}])',
            f'{metric_name}{{symbol="{label}"}}',
            "prometheus_symbol_average",
            True,
            False,
        ))
    if allow_unlabelled_fallback:
        candidates.append((
            f"avg_over_time({metric_name}[{duration}])",
            metric_name,
            "prometheus_unlabelled_average",
            False,
            True,
        ))

    for range_query, instant_query, source_name, asset_specific, shared_score in candidates:
        averaged = await client.query(range_query)
        if not averaged:
            continue

        latest = await client.query(instant_query)
        timestamp = None
        if latest and isinstance(latest.get("timestamp"), (int, float)):
            timestamp = datetime.fromtimestamp(float(latest["timestamp"]), timezone.utc).isoformat()

        warnings: list[str] = []
        if shared_score:
            warnings.append("Shared module score, not asset-specific.")
        if timestamp is None:
            warnings.append("Prometheus historical value available, but latest sample timestamp is unavailable.")

        data_status = _status_from_timestamp(timestamp, False, timeframe=timeframe) if timestamp else "STALE"
        normalized_value = _normalize_score(float(averaged["value"]))
        if normalized_value is None:
            continue

        return normalized_value, _build_module_source(
            module=module,
            service="prometheus",
            source=source_name,
            source_data=metric_name,
            timestamp=timestamp,
            timestamp_source="prometheus_sample" if timestamp else "none",
            data_status=data_status,
            fallback_used=False,
            asset_specific=asset_specific,
            shared_score=shared_score,
            warnings=warnings,
            value=normalized_value,
        )

    return 0.5, _build_module_source(
        module=module,
        service="prometheus",
        source="prometheus_missing_metric",
        source_data=metric_name,
        timestamp=None,
        timestamp_source="none",
        data_status="MISSING",
        fallback_used=True,
        asset_specific=False,
        shared_score=False,
        warnings=["Default neutral module score; Prometheus metric unavailable."],
        value=0.5,
    )


def get_prometheus_client(prometheus_url: str = "http://localhost:9090") -> PrometheusClient:
    """Get Prometheus client instance"""
    return PrometheusClient(prometheus_url)


@router.get("/metrics/touche")
async def get_touche_metrics(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("1h"),
    prometheus_url: str = Query("http://prometheus:9090")
):
    """Get Touche EQS score with timeframe"""
    if timeframe not in VALID_TIMEFRAMES:
        timeframe = "1h"

    try:
        client = get_prometheus_client(prometheus_url)
        score = await client.get_touche_score(symbol, timeframe)

        if score is None:
            score = 0.5

        status = "healthy" if score > 0.5 else "warning" if score > 0.3 else "down"

        return {
            "name": "Touche EQS",
            "score": score,
            "health": status,
            "color": "#3B82F6",
            "symbol": symbol,
            "timeframe": timeframe,
            "source": "prometheus",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Error fetching touche score: {e}")
        return {
            "name": "Touche EQS",
            "score": 0.5,
            "health": "warning",
            "color": "#3B82F6",
            "symbol": symbol,
            "timeframe": timeframe,
            "source": "cache",
            "error": str(e),
        }


@router.get("/metrics/fundamental")
async def get_fundamental_metrics(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("1h"),
    prometheus_url: str = Query("http://prometheus:9090")
):
    """Get Fundamental score with timeframe"""
    if timeframe not in VALID_TIMEFRAMES:
        timeframe = "1h"

    try:
        client = get_prometheus_client(prometheus_url)
        score = await client.get_fundamental_score(symbol, timeframe)

        if score is None:
            score = 0.5

        status = "healthy" if score > 0.5 else "warning" if score > 0.3 else "down"

        return {
            "name": "Fundamental Score",
            "score": score,
            "health": status,
            "color": "#10B981",
            "symbol": symbol,
            "timeframe": timeframe,
            "source": "prometheus",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Error fetching fundamental score: {e}")
        return {
            "name": "Fundamental Score",
            "score": 0.5,
            "health": "warning",
            "color": "#10B981",
            "symbol": symbol,
            "timeframe": timeframe,
            "source": "cache",
            "error": str(e),
        }


@router.get("/metrics/quantum")
async def get_quantum_metrics(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("1h"),
    prometheus_url: str = Query("http://prometheus:9090")
):
    """Get Quantum score with timeframe"""
    if timeframe not in VALID_TIMEFRAMES:
        timeframe = "1h"

    try:
        client = get_prometheus_client(prometheus_url)
        score = await client.get_quantum_pnl(symbol, timeframe)

        if score is None:
            score = 0.5

        status = "healthy" if score > 0.5 else "warning" if score > 0.3 else "down"

        return {
            "name": "Quantum Score",
            "score": score,
            "health": status,
            "color": "#F59E0B",
            "symbol": symbol,
            "timeframe": timeframe,
            "source": "prometheus",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Error fetching quantum score: {e}")
        return {
            "name": "Quantum Score",
            "score": 0.5,
            "health": "warning",
            "color": "#F59E0B",
            "symbol": symbol,
            "timeframe": timeframe,
            "source": "cache",
            "error": str(e),
        }


@router.get("/metrics/sentinel")
async def get_sentinel_metrics(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("1h"),
    prometheus_url: str = Query("http://prometheus:9090")
):
    """Get Sentinel score with timeframe"""
    if timeframe not in VALID_TIMEFRAMES:
        timeframe = "1h"

    try:
        client = get_prometheus_client(prometheus_url)
        score = await client.get_sentinel_multiplier(symbol, timeframe)

        if score is None:
            score = 0.5

        status = "healthy" if score > 0.5 else "warning" if score > 0.3 else "down"

        return {
            "name": "Sentinel Score",
            "score": score,
            "health": status,
            "color": "#8B5CF6",
            "symbol": symbol,
            "timeframe": timeframe,
            "source": "prometheus",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Error fetching sentinel score: {e}")
        return {
            "name": "Sentinel Score",
            "score": 0.5,
            "health": "warning",
            "color": "#8B5CF6",
            "symbol": symbol,
            "timeframe": timeframe,
            "source": "cache",
            "error": str(e),
        }


@router.get("/metrics/news")
async def get_news_metrics(
    timeframe: str = Query("1h"),
    prometheus_url: str = Query("http://prometheus:9090")
):
    """Get News sentiment score with timeframe"""
    if timeframe not in VALID_TIMEFRAMES:
        timeframe = "1h"

    try:
        client = get_prometheus_client(prometheus_url)
        score = await client.get_news_sentiment_score(timeframe)

        if score is None:
            score = 0.5

        status = "healthy" if score > 0.5 else "warning" if score > 0.3 else "down"

        return {
            "name": "News Sentiment",
            "score": score,
            "health": status,
            "color": "#EC4899",
            "timeframe": timeframe,
            "source": "prometheus",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Error fetching news score: {e}")
        return {
            "name": "News Sentiment",
            "score": 0.5,
            "health": "warning",
            "color": "#EC4899",
            "timeframe": timeframe,
            "source": "cache",
            "error": str(e),
        }


async def _fetch_macro_for_asset_scoring() -> dict:
    """Fetch sentinel macro indicators for non-crypto asset scoring."""
    SENTINEL_URL = "http://sentinel-api:8004"
    defaults = {"dxy": 98.5, "vix": 22.0, "us10y": 4.25, "brent": 92.0, "xau": 4800.0, "hg": 4.5, "event_risk_score": 0.3}
    timestamp = None
    fallback_used = True
    source = "hardcoded_macro_defaults"
    warnings = ["Shared module score, not asset-specific."]
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{SENTINEL_URL}/sentinel/event_risk", params={"symbol": "BTC"})
            if resp.status_code == 200:
                data = resp.json()
                data = data if isinstance(data, dict) else {}
                timestamp = data.get("timestamp")
                defaults["event_risk_score"] = float(data.get("event_risk_score", 0.3))
                snap = data.get("macro_snapshot", {})
                for key in ("dxy", "vix", "us10y", "brent", "xau", "hg"):
                    if key in snap:
                        defaults[key] = float(snap[key])
                fallback_used = False
                source = "sentinel_btc_macro_snapshot_shared"
    except Exception as e:
        logger.warning(f"Macro fetch failed, using defaults: {e}")
    logger.info(f"Macro data for scoring: {defaults}")
    return {
        "metrics": defaults,
        "timestamp": timestamp if isinstance(timestamp, str) and timestamp.strip() else None,
        "source": source,
        "fallback_used": fallback_used,
        "data_status": _status_from_timestamp(timestamp, fallback_used, timeframe="1h"),
        "warnings": warnings,
    }


def _derive_asset_scores(asset_key: str, m: dict) -> tuple:
    """Derive (touche, fundamental, news) scores for non-crypto assets from macro data.
    Returns 0-1 normalized scores."""
    _clamp = lambda v: max(0.05, min(0.95, v))
    dxy, vix, us10y = m["dxy"], m["vix"], m["us10y"]
    brent, xau, hg = m["brent"], m["xau"], m["hg"]
    ev_risk = m["event_risk_score"]

    if asset_key == "XAU":
        touche = 0.50 + (99 - dxy) * 0.04 + (xau - 4800) * 0.00005
        fundamental = 0.50 + (99 - dxy) * 0.05 + (4.25 - us10y) * 0.08 + (vix - 22) * 0.015
        news = 0.50 + ev_risk * 0.30 + (vix - 22) * 0.02
    elif asset_key == "XAG":
        touche = 0.50 + (hg - 4.5) * 0.12 + (brent - 92) * 0.005
        fundamental = 0.50 + (hg - 4.5) * 0.10 + (99 - dxy) * 0.03 + (4.25 - us10y) * 0.05
        news = 0.50 + ev_risk * 0.15 + (brent - 92) * 0.003
    elif asset_key == "BOND":
        touche = 0.50 + (4.25 - us10y) * 0.15 + (vix - 22) * 0.01
        fundamental = 0.50 + (4.25 - us10y) * 0.20 + (dxy - 99) * 0.02
        news = 0.50 + ev_risk * 0.25 + (vix - 22) * 0.015
    elif asset_key == "CASH":
        touche = 0.50 + (dxy - 99) * 0.05 + (22 - vix) * 0.01
        fundamental = 0.50 + (dxy - 99) * 0.04 + (us10y - 4.25) * 0.06
        news = 0.50 + (22 - vix) * 0.02 + (1 - ev_risk) * 0.15
    else:
        touche = fundamental = news = 0.50

    return _clamp(touche), _clamp(fundamental), _clamp(news)


@router.get("/consensus")
async def get_consensus(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("1h"),
    prometheus_url: str = Query("http://prometheus:9090")
):
    """Get 3-way weighted consensus with timeframe"""
    if timeframe not in VALID_TIMEFRAMES:
        timeframe = "1h"

    try:
        # Detect non-crypto assets for macro-derived scoring
        asset_key = symbol.replace("/USDT", "").replace("/", "").upper()
        module_sources: dict[str, Any]

        if asset_key in _MACRO_ASSETS:
            macro_bundle = await _fetch_macro_for_asset_scoring()
            macro_data = macro_bundle["metrics"]
            touche_score, fundamental_score, news_score = _derive_asset_scores(asset_key, macro_data)
            logger.info(f"Macro-derived scores for {asset_key}: T={touche_score:.4f} F={fundamental_score:.4f} N={news_score:.4f}")
            module_sources = {
                "technical": _build_module_source(
                    module="technical",
                    service="sentinel-api",
                    source=macro_bundle["source"],
                    source_data="shared BTC macro snapshot -> technical asset formula",
                    timestamp=macro_bundle["timestamp"],
                    timestamp_source="sentinel_response" if macro_bundle["timestamp"] else "none",
                    data_status=macro_bundle["data_status"],
                    fallback_used=macro_bundle["fallback_used"],
                    asset_specific=False,
                    shared_score=True,
                    warnings=_merge_warnings(macro_bundle["warnings"]),
                    value=touche_score,
                ),
                "fundamental": _build_module_source(
                    module="fundamental",
                    service="sentinel-api",
                    source=macro_bundle["source"],
                    source_data="shared BTC macro snapshot -> fundamental asset formula",
                    timestamp=macro_bundle["timestamp"],
                    timestamp_source="sentinel_response" if macro_bundle["timestamp"] else "none",
                    data_status=macro_bundle["data_status"],
                    fallback_used=macro_bundle["fallback_used"],
                    asset_specific=False,
                    shared_score=True,
                    warnings=_merge_warnings(macro_bundle["warnings"]),
                    value=fundamental_score,
                ),
                "news": _build_module_source(
                    module="news",
                    service="sentinel-api",
                    source=macro_bundle["source"],
                    source_data="shared BTC event risk -> macro-derived news proxy",
                    timestamp=macro_bundle["timestamp"],
                    timestamp_source="sentinel_response" if macro_bundle["timestamp"] else "none",
                    data_status=macro_bundle["data_status"],
                    fallback_used=macro_bundle["fallback_used"],
                    asset_specific=False,
                    shared_score=True,
                    warnings=_merge_warnings(macro_bundle["warnings"]),
                    value=news_score,
                ),
            }
        else:
            # Try live service calls first, fall back to Prometheus
            live = await _fetch_live_scores(symbol, timeframe)
            now_ts = datetime.now(timezone.utc).isoformat()

            def _live_or_prometheus_source(
                module: str,
                live_score: Optional[float],
                prometheus_score: float,
                prometheus_source_name: str,
            ) -> tuple[float, dict[str, Any]]:
                if live_score is not None:
                    return live_score, _build_module_source(
                        module=module,
                        service=f"{module}-api",
                        source="live_service_api",
                        source_data=f"{module}_service_response",
                        timestamp=now_ts,
                        timestamp_source="service_response_time",
                        data_status="LIVE",
                        fallback_used=False,
                        asset_specific=True,
                        shared_score=False,
                        warnings=[],
                        value=live_score,
                    )
                return prometheus_score, _build_module_source(
                    module=module,
                    service="prometheus",
                    source=prometheus_source_name,
                    source_data=f"{module}_prometheus_metric",
                    timestamp=None,
                    timestamp_source="none",
                    data_status="MISSING",
                    fallback_used=True,
                    asset_specific=False,
                    shared_score=False,
                    warnings=["Live service unavailable; using Prometheus fallback (may be neutral)."],
                    value=prometheus_score,
                )

            touche_score, technical_source = _live_or_prometheus_source(
                "technical", live["touche"], 0.5, "prometheus_missing_metric"
            )
            fundamental_score, fundamental_source = _live_or_prometheus_source(
                "fundamental", live["fundamental"], 0.5, "prometheus_missing_metric"
            )
            news_score, news_source = _live_or_prometheus_source(
                "news", live["news"], 0.5, "prometheus_missing_metric"
            )
            module_sources = {
                "technical": technical_source,
                "fundamental": fundamental_source,
                "news": news_source,
            }

        # Normalize to 0-1
        touche_score = min(max(float(touche_score), 0.0), 1.0)
        fundamental_score = min(max(float(fundamental_score), 0.0), 1.0)
        news_score = min(max(float(news_score), 0.0), 1.0)

        # 3-way weighted consensus
        weights = {"touche": 0.50, "fundamental": 0.35, "news": 0.15}
        weighted_score = (
            touche_score * weights["touche"] +
            fundamental_score * weights["fundamental"] +
            news_score * weights["news"]
        )

        # Determine action
        if weighted_score > 0.65:
            action = "BUY"
            confidence = weighted_score
        elif weighted_score < 0.35:
            action = "SELL"
            confidence = 1.0 - weighted_score
        else:
            action = "HOLD"
            confidence = 0.5

        source_timestamp = _latest_timestamp(
            module_sources["technical"]["timestamp"],
            module_sources["fundamental"]["timestamp"],
            module_sources["news"]["timestamp"],
        )
        warnings = _merge_warnings(
            module_sources["technical"]["warnings"],
            module_sources["fundamental"]["warnings"],
            module_sources["news"]["warnings"],
        )
        data_status = _aggregate_status([
            module_sources["technical"]["data_status"],
            module_sources["fundamental"]["data_status"],
            module_sources["news"]["data_status"],
        ])
        fallback_used = any(module_source["fallback_used"] for module_source in module_sources.values())
        verified = (
            data_status in {"LIVE", "RECENT"}
            and all(bool(module_source["verified"]) for module_source in module_sources.values())
        )
        if data_status in {"STALE", "FALLBACK", "MOCK", "MISSING"}:
            warnings = _merge_warnings(warnings, ["Signal is not verified because source data is stale/fallback/mock."])
        source = "dashboard_gateway_macro_derived_consensus" if asset_key in _MACRO_ASSETS else "dashboard_gateway_prometheus_consensus"
        return {
            "asset": asset_key,
            "weighted_score": round(weighted_score, 4),
            "action": action,
            "confidence": round(confidence, 4),
            "weights": weights,
            "timeframe": timeframe,
            "components": {
                "touche": {"score": round(touche_score, 4), "weight": 0.50},
                "fundamental": {"score": round(fundamental_score, 4), "weight": 0.35},
                "news": {"score": round(news_score, 4), "weight": 0.15},
            },
            "symbol": symbol,
            "source": source,
            "timestamp": source_timestamp,
            "last_updated": source_timestamp,
            "fallback_used": fallback_used,
            "verified": verified,
            "data_status": data_status,
            "module_sources": module_sources,
            "warnings": warnings,
        }

    except Exception as e:
        logger.error(f"Error computing consensus: {e}")
        warnings = [
            "Signal is not verified because source data is stale/fallback/mock.",
            "Consensus gateway returned a fallback response after an internal error.",
        ]
        return {
            "asset": symbol.replace("/USDT", "").replace("/", "").upper(),
            "weighted_score": 0.5,
            "action": "HOLD",
            "confidence": 0.5,
            "weights": {"touche": 0.50, "fundamental": 0.35, "news": 0.15},
            "timeframe": timeframe,
            "symbol": symbol,
            "source": "consensus_error_fallback",
            "timestamp": None,
            "last_updated": None,
            "fallback_used": True,
            "verified": False,
            "data_status": _status_from_timestamp(None, True),
            "module_sources": {
                "technical": _build_module_source(
                    module="technical",
                    service="dashboard-gateway",
                    source="consensus_error_fallback",
                    source_data="gateway_error",
                    timestamp=None,
                    timestamp_source="none",
                    data_status="FALLBACK",
                    fallback_used=True,
                    asset_specific=False,
                    shared_score=False,
                    warnings=["Default neutral module score; gateway error fallback applied."],
                    value=0.5,
                ),
                "fundamental": _build_module_source(
                    module="fundamental",
                    service="dashboard-gateway",
                    source="consensus_error_fallback",
                    source_data="gateway_error",
                    timestamp=None,
                    timestamp_source="none",
                    data_status="FALLBACK",
                    fallback_used=True,
                    asset_specific=False,
                    shared_score=False,
                    warnings=["Default neutral module score; gateway error fallback applied."],
                    value=0.5,
                ),
                "news": _build_module_source(
                    module="news",
                    service="dashboard-gateway",
                    source="consensus_error_fallback",
                    source_data="gateway_error",
                    timestamp=None,
                    timestamp_source="none",
                    data_status="FALLBACK",
                    fallback_used=True,
                    asset_specific=False,
                    shared_score=False,
                    warnings=["Default neutral module score; gateway error fallback applied."],
                    value=0.5,
                ),
            },
            "warnings": warnings,
            "error": str(e),
        }


@router.get("/health")
async def dashboard_health():
    """Health check for dashboard API"""
    return {
        "status": "healthy",
        "service": "dashboard-routes",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# YENİ ENDPOINTS - REVIZED MODÜLLER (Multi-timeframe, Performance, etc)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/metrics/touche/multiframe")
async def get_touche_multiframe_metrics(
    symbol: str = Query("BTC/USDT"),
):
    """Touche multi-timeframe analizi (15m, 1h, 4h, 1d)"""
    return {
        "module": "Touche AI",
        "symbol": symbol,
        "volatility_regime": "NORMAL",
        "dynamic_params": {
            "zone_tolerance_atr": 0.3,
            "confluence_min": 2,
            "signal_threshold": 50.0,
        },
        "timeframes": {
            "15m": {"signal": "BULLISH", "score": 72, "atr": 0.0045},
            "1h": {"signal": "BULLISH", "score": 68, "atr": 0.0062},
            "4h": {"signal": "BEARISH", "score": 45, "atr": 0.0089},
            "1d": {"signal": "NEUTRAL", "score": 50, "atr": 0.0125},
        },
        "confluence_score": 65.5,
        "alignment": "moderate",
        "final_signal": "WAIT",  # Zaman dilimleri uyumsuz
        "confidence": 0.42,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/metrics/fundamental/onchain-flows")
async def get_fundamental_onchain_flows(
    symbol: str = Query("BTC"),
):
    """Fundamental on-chain flows (Whale, Miner, ETF)"""
    return {
        "module": "Fundamental AI",
        "symbol": symbol,
        "coin_normalization": {
            "mvrv_bounds": {"min": 0.5, "max": 4.0},
            "mvrv_value": 1.85,
            "signal": "NEUTRAL"
        },
        "whale_tracking": {
            "whale_buy_volume_usd": 4_500_000,
            "whale_sell_volume_usd": 2_100_000,
            "large_transaction_count": 12,
            "whale_sentiment": "ACCUMULATING",
            "signal": "BULLISH"
        },
        "miner_flows": {
            "miner_inflow": 2.5,
            "miner_outflow": 0.8,
            "miner_trend": "SELLING_PRESSURE",
            "signal": "BEARISH"
        },
        "etf_flows": {
            "etf_net_flow_usd": 125_000_000,
            "etf_trend": "INFLOW",
            "etf_signal": "BULLISH"
        } if symbol == "BTC" else {},
        "composite_signal": "BULLISH",
        "confidence": 0.68,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/metrics/quantum/liquidity-analysis")
async def get_quantum_liquidity_analysis(
    symbol: str = Query("BTC/USDT"),
):
    """Quantum likidite analizi (Slippage, Market Impact, DoM)"""
    return {
        "module": "Quantum AI",
        "symbol": symbol,
        "slippage_analysis": {
            "buy_slippage_pct": 0.0342,
            "sell_slippage_pct": 0.0385,
            "available_buy_liquidity": 2450.5,
            "available_sell_liquidity": 2180.3,
            "slippage_risk": "LOW"
        },
        "market_impact": {
            "impact_pct": 0.125,
            "permanent_impact_pct": 0.075,
            "temporary_impact_pct": 0.050,
            "impact_severity": "LOW"
        },
        "hidden_orders": {
            "accumulation_pattern": True,
            "distribution_pattern": False,
            "pattern_signal": "ACCUMULATING"
        },
        "depth_of_market": {
            "bid_depth_ratio": 1.15,
            "ask_depth_ratio": 0.92,
            "imbalance_ratio": 0.092,
            "depth_squeeze": False,
            "dom_signal": "BULLISH"
        },
        "liquidity_verdict": "GOOD",
        "confidence": 0.84,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/metrics/sentinel/crypto-macro")
async def get_sentinel_crypto_macro():
    """Sentinel kripto-spesifik makro göstergeleri"""
    return {
        "module": "Sentinel AI",
        "stablecoin_supply": {
            "stablecoin_index": 62.3,
            "total_supply_usd": 142_500_000_000,
            "supply_24h_change_pct": 0.85,
            "liquidity_signal": "BULLISH"
        },
        "regulatory_events": {
            "latest_event": "ETF_APPROVAL",
            "authority": "SEC",
            "time_relevance": 0.95,
            "regulatory_sentiment": "POSITIVE",
            "impact_score": 78.5
        },
        "btc_dominance": {
            "btc_dominance_pct": 59.8,
            "24h_change": 0.45,
            "dominance_trend": "INCREASING",
            "altcoin_strength": "WEAK",
            "dominance_direction": "RISK_OFF"
        },
        "fear_greed_index": {
            "index": 68,
            "sentiment": "Greed",
            "trading_signal": "SELL"
        },
        "macro_composite": "MIXED",
        "confidence": 0.71,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/metrics/news/source-reliability")
async def get_news_source_reliability():
    """News kaynak güvenilirlik & impact duration"""
    return {
        "module": "News AI",
        "recent_news": [
            {
                "headline": "SEC Approves Bitcoin ETF",
                "source": "sec.gov",
                "source_reliability": 100,
                "sentiment": 0.95,
                "fud_risk_score": 2,
                "credibility": "VERIFIED",
                "impact_duration": {
                    "expected_duration_hours": 72,
                    "impact_phase": "PEAK",
                    "intensity": 0.92
                }
            },
            {
                "headline": "Bitcoin Will 100x This Year!",
                "source": "twitter",
                "source_reliability": 35,
                "sentiment": 0.88,
                "fud_risk_score": 78,
                "credibility": "SUSPICIOUS",
                "impact_duration": {
                    "expected_duration_hours": 2,
                    "impact_phase": "RISING",
                    "intensity": 0.3
                }
            }
        ],
        "weighted_sentiment": 0.72,
        "sentiment_confidence": 0.85,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/metrics/consensus/performance-feedback")
async def get_consensus_performance_feedback():
    """Consensus dinamik ağırlıklandırma & performans tracking"""
    return {
        "module": "Consensus Engine",
        "current_weights": {
            "Touche": 0.48,
            "Fundamental": 0.38,
            "News": 0.14
        },
        "default_weights": {
            "Touche": 0.50,
            "Fundamental": 0.35,
            "News": 0.15
        },
        "weight_adjustments": {
            "reason": "Performance feedback (7-day accuracy)",
            "last_updated": "2 days ago",
            "adjustments": {
                "Touche": -0.02,  # Accuracy düştü
                "Fundamental": +0.03,  # Accuracy arttı
                "News": -0.01
            }
        },
        "module_performance": {
            "Touche": {"accuracy_7d": 0.72, "accuracy_30d": 0.75, "win_rate": 0.71},
            "Fundamental": {"accuracy_7d": 0.81, "accuracy_30d": 0.78, "win_rate": 0.79},
            "News": {"accuracy_7d": 0.58, "accuracy_30d": 0.62, "win_rate": 0.60}
        },
        "conflict_resolution": {
            "conflicts_detected_24h": 3,
            "conflicts_resolved": 3,
            "resolution_success_rate": 0.95
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
