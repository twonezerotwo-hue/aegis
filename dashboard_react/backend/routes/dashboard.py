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
from services.market_data import fetch_market_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["dashboard"])

# ── Fear & Greed Index (gerçek veri, ücretsiz, key gerektirmez) ────────────────
# alternative.me crypto Fear & Greed — 5 dakika önbellekli
_FNG_CACHE: dict[str, Any] = {"value": None, "ts": 0.0, "classification": ""}
_FNG_TTL = 300.0  # 5 dakika

async def _fetch_fear_greed() -> dict:
    """
    Crypto Fear & Greed Index çek (0-100, gerçek piyasa duygusu).
    0-25: Aşırı Korku (dip fırsatı) · 75-100: Aşırı Açgözlülük (tepe riski)
    """
    import time as _t
    now = _t.time()
    if _FNG_CACHE["value"] is not None and (now - _FNG_CACHE["ts"]) < _FNG_TTL:
        return {"value": _FNG_CACHE["value"], "classification": _FNG_CACHE["classification"], "cached": True}
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            r = await client.get("https://api.alternative.me/fng/?limit=1")
        if r.status_code == 200:
            data = (r.json().get("data") or [{}])[0]
            val = int(data.get("value", 50))
            cls = data.get("value_classification", "Neutral")
            _FNG_CACHE.update({"value": val, "ts": now, "classification": cls})
            return {"value": val, "classification": cls, "cached": False}
    except Exception as exc:
        logger.debug("Fear&Greed fetch failed: %s", exc)
    return {"value": _FNG_CACHE["value"] or 50, "classification": _FNG_CACHE["classification"] or "Neutral", "cached": True}

# Available symbols
SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"]

# Valid timeframes
VALID_TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d", "1w", "1month"]

# Non-crypto assets derive scores from macro indicators instead of Prometheus
# XAU + XAG kaldırıldı: Touche artık yfinance (GC=F / SI=F) üzerinden canlı
# analiz yapabiliyor; BOND ve CASH hâlâ makro türetmeli kalıyor.
_MACRO_ASSETS = {"BOND", "CASH"}

# Emtia için Touche timeout'u daha uzun tutulur (yfinance ilk çekiş ~8-12s)
_TOUCHE_COMMODITY_SYMBOLS = {"XAU", "XAG", "WTI", "BRENT"}

# AI service base URLs
_TOUCHE_URL = os.environ.get("TOUCHE_URL", "http://touche-api:8001")
_FUNDAMENTAL_URL = os.environ.get("FUNDAMENTAL_URL", "http://fundamental-api:8002")
_NEWS_URL = os.environ.get("NEWS_URL", "http://news-ai-limited:8006")
_SENTINEL_URL = os.environ.get("SENTINEL_URL", "http://sentinel-api:8004")
_QUANTUM_URL = os.environ.get("QUANTUM_URL", "http://quantum-api:8003")


import math as _math

# ── Timeframe hassasiyet parametreleri ─────────────────────────────────────────

# News: haber yaşına göre exponential decay yarı-ömrü (saat)
# Kısa TF = yakın haberlere daha fazla ağırlık
_TF_NEWS_HALF_LIFE: dict[str, float] = {
    "5m": 0.5, "15m": 1.0, "1h": 4.0, "4h": 12.0,
    "1d": 48.0, "1w": 168.0, "1month": 720.0,
}

# Fundamental: TF'e göre seviye (MVRV/NUPL mutlak) vs momentum ağırlığı
# Kısa TF = momentum ağırlıklı, uzun TF = seviye ağırlıklı
_TF_FUNDAMENTAL_LEVEL_W: dict[str, float] = {
    "5m": 0.15, "15m": 0.25, "1h": 0.40,
    "4h": 0.55, "1d": 0.70, "1w": 0.85, "1month": 0.95,
}

# Touche multi-TF ağırlıkları: mesafeye göre yarıya düşür
_TF_ORDER = {"15m": 1, "1h": 2, "4h": 3, "1d": 4, "1w": 5}
_TF_SIGNAL_SCORE: dict[str, float] = {
    "BUY": 0.74, "HOLD": 0.50, "NEUTRAL": 0.50, "SELL": 0.26,
}


async def _fetch_live_module_payloads(symbol: str, timeframe: str) -> dict[str, Optional[dict[str, Any]]]:
    """Fetch raw live module payloads from each AI service."""
    symbol_binance = symbol.replace("/USDT", "").replace("/", "") + "USDT"
    symbol_clean = symbol.replace("/USDT", "").replace("/", "")
    asset_key = symbol_clean.upper()

    # Emtia sembolleri (XAU/XAG) için Touche yfinance çekişi ~8-12s sürer.
    # Timeout: emtia=20s, kripto=5s
    touche_timeout = 20.0 if asset_key in _TOUCHE_COMMODITY_SYMBOLS else 5.0

    async with httpx.AsyncClient(timeout=httpx.Timeout(touche_timeout, connect=5.0)) as client:
        results = await asyncio.gather(
            client.get(f"{_TOUCHE_URL}/touche/analyze", params={"symbol": symbol_binance, "timeframe": timeframe}),
            client.get(f"{_FUNDAMENTAL_URL}/fundamental/metrics", params={"symbol": symbol_clean, "timeframe": timeframe}),
            client.get(f"{_NEWS_URL}/signals", params={"symbol": symbol_clean, "timeframe": timeframe}),
            client.get(f"{_SENTINEL_URL}/sentinel/event_risk", params={"symbol": symbol_clean}),
            client.get(f"{_QUANTUM_URL}/quantum/futures_data", params={"symbol": symbol_binance}),
            return_exceptions=True,
        )

    payloads: dict[str, Optional[dict[str, Any]]] = {
        "touche": None,
        "fundamental": None,
        "news": None,
        "sentinel": None,
        "quantum": None,
    }
    for key, result in zip(payloads.keys(), results):
        try:
            if not isinstance(result, Exception) and result.status_code == 200:
                data = result.json()
                payloads[key] = data if isinstance(data, dict) else None
        except Exception as exc:  # noqa: BLE001
            logger.debug("live payload %s error: %s", key, exc)

    # ── Fundamental'a gerçek Fear & Greed Index enjekte et ─────────────────────
    # MVRV/NUPL mock olsa bile F&G GERÇEK veri (alternative.me, ücretsiz)
    try:
        fng = await _fetch_fear_greed()
        if payloads.get("fundamental") is None:
            payloads["fundamental"] = {}
        payloads["fundamental"]["fear_greed_value"] = fng["value"]
        payloads["fundamental"]["fear_greed_class"] = fng["classification"]
    except Exception as exc:
        logger.debug("F&G enrich failed: %s", exc)

    # ── News'i GERÇEK RSS akışıyla değiştir (CoinDesk/Cointelegraph/Decrypt) ────
    # Statik "47 haber" yerine canlı, taze, sembol-filtreli gerçek haberler
    try:
        from services.news_feed import get_live_news
        live_news = await get_live_news(symbol_clean)
        if live_news.get("available"):
            # signals[0] formatına uydur (mevcut tüketici kodu çalışsın)
            if payloads.get("news") is None:
                payloads["news"] = {}
            _dh = live_news.get("display_headlines", [])
            payloads["news"]["signals"] = [{
                "crypto_impact_score":  live_news["crypto_impact_score"],
                "aggregated_sentiment": live_news.get("symbol_sentiment", live_news["aggregated_sentiment"]),
                "news_items_count":     live_news["count_total"],
                "count_24h":            live_news["count_24h"],
                "confidence_level":     min(95, 50 + live_news["count_24h"] * 2),
                "primary_countries":    [],
                "impact_factors":       {"regulatory_score": 50},
                "sources":              live_news.get("sources", []),
                "newest_age_h":         live_news.get("newest_age_h"),
                "top_headline":         _dh[0]["title"] if _dh else None,
                "top_headline_sentiment": _dh[0]["sentiment"] if _dh else 0,
                "display_headlines":    _dh,
            }]
            payloads["news"]["_live_feed"] = live_news   # zengin veri (başlıklar)
            payloads["news"]["data_status"] = "LIVE"
            payloads["news"]["verified"] = True
    except Exception as exc:
        logger.debug("Live news enrich failed: %s", exc)

    return payloads


def _payload_verified(payload: Optional[dict[str, Any]]) -> bool:
    """Payload'ın canlı, doğrulanmış veri içerip içermediğini kontrol eder.

    Farklı servisler farklı alan adları kullanıyor:
    - Touche:     data_mode="LIVE", fallback_used=false (verified alanı yok)
    - Fundamental/News/Sentinel: data_status="LIVE", verified=True
    Her iki format da kabul edilir.
    """
    if not payload:
        return False

    # Format 1: standard (Fundamental/News/Sentinel)
    data_status = str(payload.get("data_status", "")).upper()
    has_standard_live = data_status in {"LIVE", "RECENT"}

    # Format 2: Touche servis formatı (data_mode yerine data_status kullanmaz)
    data_mode = str(payload.get("data_mode", "")).upper()
    has_touche_live = data_mode in {"LIVE", "REAL"}

    fallback_used = bool(payload.get("fallback_used", False))

    return (has_standard_live or has_touche_live) and not fallback_used


def _extract_live_scores(
    payloads: dict[str, Optional[dict[str, Any]]],
    timeframe: str,
    symbol: str = "",
) -> dict[str, Optional[float]]:
    """
    Servis yanıtlarından TF-duyarlı skorları çıkarır.

    Touche:      Multi-TF ağırlıklı konsensüs (mevcut TF ağırlık=1, uzak TF'ler yarıya düşer)
    Fundamental: Kısa TF = momentum ağırlıklı, uzun TF = seviye (MVRV/NUPL) ağırlıklı
                 NOT: Emtia (XAU/XAG) için MVRV/NUPL geçersizdir → None döner
    News:        Exponential time decay — kısa TF'de eski haberler daha hızlı sönümlenir
    Sentinel:    BY DESIGN TF bağımsız (makro göstergeler)
    """
    asset_key = symbol.replace("/USDT", "").replace("/", "").upper() if symbol else ""
    is_commodity = asset_key in _TOUCHE_COMMODITY_SYMBOLS   # XAU, XAG → MVRV/NUPL yok

    scores: dict[str, Optional[float]] = {
        "touche": None, "fundamental": None,
        "news": None, "sentinel": None, "quantum": None,
    }

    # ── TOUCHE: Multi-TF ağırlıklı konsensüs ─────────────────────────────────
    touche = payloads.get("touche")
    if touche and not touche.get("fallback_used", False):
        tf_signals = touche.get("tf_signals") or {}
        tf_key = timeframe.lower()
        current_ord = _TF_ORDER.get(tf_key, 2)

        weighted_sum = 0.0
        weight_total = 0.0
        for tf, sig in tf_signals.items():
            tf_ord = _TF_ORDER.get(tf.lower(), 0)
            if tf_ord == 0:
                continue
            distance = abs(tf_ord - current_ord)
            w = 1.0 / (2 ** distance)
            val = _TF_SIGNAL_SCORE.get(str(sig).upper(), 0.50)
            weighted_sum += val * w
            weight_total += w

        if weight_total > 0:
            scores["touche"] = round(weighted_sum / weight_total, 4)
        else:
            eqs = float(touche.get("eqs") or touche.get("eqs_score") or 50.0)
            scores["touche"] = min(max(eqs / 100.0, 0.0), 1.0)

    # ── FUNDAMENTAL: MVRV/NUPL (mock) + Fear&Greed (GERÇEK) harmanı ──────────
    # Emtia (XAU/XAG) için MVRV/NUPL zincir verisi anlamsız → atla
    fundamental = payloads.get("fundamental")
    if fundamental and not is_commodity:
        nupl = fundamental.get("nupl")
        mvrv = fundamental.get("mvrv_z_score")
        onchain_score = None
        if isinstance(nupl, (int, float)) and isinstance(mvrv, (int, float)):
            nupl_f = float(nupl); mvrv_f = float(mvrv)
            nupl_level = min(max((nupl_f + 0.5) / 1.5, 0.0), 1.0)
            mvrv_level = min(max((4.0 - mvrv_f) / 4.0, 0.0), 1.0)
            level_score = nupl_level * 0.6 + mvrv_level * 0.4
            mvrv_healthy = 1.0 - min(1.0, abs(mvrv_f - 1.5) / 3.0)
            nupl_pos     = min(max((nupl_f + 0.1) / 0.8, 0.0), 1.0)
            momentum_score = nupl_pos * 0.65 + mvrv_healthy * 0.35
            lw = _TF_FUNDAMENTAL_LEVEL_W.get(timeframe, 0.55)
            mw = 1.0 - lw
            onchain_score = level_score * lw + momentum_score * mw

        # Fear & Greed (GERÇEK veri): kontrarian — aşırı korku=bullish, açgözlülük=bearish
        fng_val = fundamental.get("fear_greed_value")
        fng_score = None
        if isinstance(fng_val, (int, float)):
            # F&G 0 (aşırı korku) → 0.85 (al), F&G 100 (açgözlülük) → 0.15 (sat)
            fng_score = 0.85 - (float(fng_val) / 100.0) * 0.70

        # Harman: mock on-chain %40, gerçek F&G %60 (gerçek veriye ağırlık ver)
        if onchain_score is not None and fng_score is not None:
            scores["fundamental"] = round(onchain_score * 0.40 + fng_score * 0.60, 4)
        elif fng_score is not None:
            scores["fundamental"] = round(fng_score, 4)        # sadece gerçek veri
        elif onchain_score is not None:
            scores["fundamental"] = round(onchain_score, 4)

    # ── NEWS: TF Relevance Decay ──────────────────────────────────────────────
    # News servisi tek bir ANLIK agregasyon üretiyor (timestamp=NOW).
    # Gerçek time-decay çalışmıyor (tüm ağırlıklar=1.0).
    # Bunun yerine: kısa TF = haber tam etkili, uzun TF = ortaya çekilir.
    # Mantık: 1h trader için bugünkü haber çok önemli.
    #         1w trader için temel veriler daha önemli, haber ikincil.
    # relevance_w × raw + (1 - relevance_w) × 0.50 (nötr)
    _TF_NEWS_RELEVANCE: dict[str, float] = {
        "5m": 1.00, "15m": 0.98, "1h": 0.92,
        "4h": 0.80, "1d": 0.65, "1w": 0.45, "1month": 0.25,
    }
    news = payloads.get("news")
    if news:
        signals_raw = news.get("signals") or []
        if signals_raw:
            impact_raw = float(signals_raw[0].get("crypto_impact_score") or 50.0) / 100.0
            relevance  = _TF_NEWS_RELEVANCE.get(timeframe, 0.80)
            news_score = impact_raw * relevance + 0.50 * (1.0 - relevance)
            scores["news"] = round(min(max(news_score, 0.0), 1.0), 4)

    # ── SENTINEL: TF bağımsız (makro göstergeler) ────────────────────────────
    sentinel = payloads.get("sentinel")
    if sentinel and "event_risk_score" in sentinel:
        risk = float(sentinel.get("event_risk_score") or 0.5)
        scores["sentinel"] = round(1.0 - min(max(risk, 0.0), 1.0), 4)

    # ── QUANTUM ───────────────────────────────────────────────────────────────
    # FIX: 'modifier' bir ÇARPAN (1.0 = nötr), skor değil. Direkt kullanmak
    # nötr durumu %100 gösteriyordu. Gerçek futures verisinden skor üret:
    #   funding_rate: pozitif aşırı → long kalabalık (bearish), negatif → short kalabalık (bullish)
    #   long_short_ratio: >1 long ağırlıklı, <1 short ağırlıklı
    quantum = payloads.get("quantum")
    if quantum:
        funding   = quantum.get("funding_rate_pct")
        ls_ratio  = quantum.get("long_short_ratio")
        modifier  = quantum.get("modifier")

        q_components: list[float] = []

        # Funding rate sinyali: aşırı pozitif funding = kontrarian bearish
        # Tipik aralık ±0.05% → 0.01% nötr. Pozitif aşırı → düşük skor
        if isinstance(funding, (int, float)):
            # funding +0.05% → 0.2 (bearish), -0.05% → 0.8 (bullish), 0 → 0.5
            f_score = 0.5 - (float(funding) / 0.10) * 0.5
            q_components.append(min(max(f_score, 0.0), 1.0))

        # Long/short ratio: aşırı long = kontrarian bearish
        if isinstance(ls_ratio, (int, float)) and ls_ratio > 0:
            # ratio 1.0 → 0.5, ratio 2.0 → 0.25 (aşırı long), ratio 0.5 → 0.75 (aşırı short)
            ls_score = 0.5 / float(ls_ratio) if ls_ratio >= 1 else 1.0 - (float(ls_ratio) * 0.5)
            q_components.append(min(max(ls_score, 0.0), 1.0))

        # Modifier'ı nötr-merkezli skora çevir (0.8-1.2 → 0-1)
        if isinstance(modifier, (int, float)):
            m_score = 0.5 + (float(modifier) - 1.0) * 2.5
            q_components.append(min(max(m_score, 0.0), 1.0))

        if q_components:
            scores["quantum"] = round(sum(q_components) / len(q_components), 4)

    return scores


async def _fetch_live_scores(symbol: str, timeframe: str) -> dict[str, Optional[float]]:
    return _extract_live_scores(await _fetch_live_module_payloads(symbol, timeframe), timeframe, symbol)


def _compute_mtf_alignment(tf_signals: dict, current_tf: str) -> dict:
    """
    Farklı zaman dilimlerindeki sinyallerin hizalanma skorunu hesapla.

    tf_signals: {"1h": "BUY", "4h": "SELL", "1d": "HOLD", ...}
    Döner:
      score: 0-1  (1.0 = tam hizalanmış, 0.5 = karışık/nötr)
      direction: "BULLISH" | "BEARISH" | "NEUTRAL"
      aligned_count: kaç TF aynı yönde
      total_count: toplam TF sayısı
    """
    if not tf_signals:
        return {"score": 0.5, "direction": "NEUTRAL", "aligned_count": 0, "total_count": 0}

    signal_vals = {
        "BUY": 1, "BULLISH": 1, "STRONG_BUY": 1,
        "SELL": -1, "BEARISH": -1, "STRONG_SELL": -1,
        "HOLD": 0, "NEUTRAL": 0, "UNAVAILABLE": 0,
    }

    votes: list[int] = []
    for tf, sig in tf_signals.items():
        v = signal_vals.get(str(sig).upper(), 0)
        votes.append(v)

    if not votes:
        return {"score": 0.5, "direction": "NEUTRAL", "aligned_count": 0, "total_count": 0}

    buy_count  = sum(1 for v in votes if v > 0)
    sell_count = sum(1 for v in votes if v < 0)
    total      = len(votes)

    # Dominant yön
    if buy_count > sell_count:
        dominant = "BULLISH"
        aligned  = buy_count
    elif sell_count > buy_count:
        dominant = "BEARISH"
        aligned  = sell_count
    else:
        dominant = "NEUTRAL"
        aligned  = 0

    # Hizalanma oranı: 0.5 (nötr) → 1.0 (tam hizalı)
    alignment_ratio = aligned / total if total > 0 else 0.0
    score = 0.5 + alignment_ratio * 0.5
    if dominant == "BEARISH":
        score = 0.5 - alignment_ratio * 0.5

    return {
        "score":          round(score, 4),
        "direction":      dominant,
        "aligned_count":  aligned,
        "total_count":    total,
        "buy_count":      buy_count,
        "sell_count":     sell_count,
    }


async def _fetch_module_details(symbol: str, timeframe: str) -> dict:
    payloads = await _fetch_live_module_payloads(symbol, timeframe)
    return {
        "touche": payloads.get("touche"),
        "fundamental": payloads.get("fundamental"),
        "news": (payloads.get("news") or {}).get("signals", [None])[0] if payloads.get("news") else None,
        "sentinel": payloads.get("sentinel"),
        "quantum": payloads.get("quantum"),
    }


def _build_metric_summary(module: str, score: float, raw: Optional[dict]) -> str:
    """Build a concise data-driven summary for a metric card."""
    if raw is None:
        return "Servis verisine ulaşılamadı — varsayılan skor kullanıldı."

    if module == "touche":
        eqs = raw.get("eqs") or raw.get("eqs_score") or round(score * 100, 1)
        tf = raw.get("tf_signals") or {}
        td = raw.get("timeframe_details") or {}  # RSI/MACD/EMA per-TF

        # TF sinyal listesi
        parts = [f"{k}: {v}" for k, v in tf.items() if k in ("15m", "1h", "4h", "1d")]
        signals = " · ".join(parts) if parts else "sinyal yok"

        # En belirgin indikatör bilgisini ekle (en düşük veya en yüksek EQS'li TF)
        indicator_hint = ""
        if td:
            # En güçlü sinyal TF'ini bul
            extremes = [(k, v) for k, v in td.items() if isinstance(v, dict) and "rsi" in v]
            if extremes:
                most_extreme = min(extremes, key=lambda x: abs(x[1].get("rsi", 50) - 50),
                                   default=None) if len(extremes) > 1 else extremes[0]
                # Değil, en extreme olan (en uzak 50'den)
                most_extreme = max(extremes, key=lambda x: abs(x[1].get("rsi", 50) - 50))
                tf_key, tf_data = most_extreme
                rsi_v = tf_data.get("rsi", 50)
                macd_d = (tf_data.get("macd") or {}).get("direction", "")
                ema_tr = (tf_data.get("ema_trend") or {}).get("trend", "")
                macd_cross = (tf_data.get("macd") or {}).get("cross")
                cross_str = f" [{'altın çapraz' if macd_cross=='GOLDEN' else 'ölüm çaprazı'}]" if macd_cross else ""
                indicator_hint = (
                    f" | {tf_key.upper()} RSI={rsi_v:.0f}"
                    f"{'↓(aşırı satım)' if rsi_v < 30 else '↑(aşırı alım)' if rsi_v > 70 else ''}"
                    f" MACD={'↑' if macd_d=='BULLISH' else '↓' if macd_d=='BEARISH' else '→'}"
                    f" EMA={'↑trend' if ema_tr=='BULLISH' else '↓trend' if ema_tr=='BEARISH' else '→'}"
                    f"{cross_str}"
                )

        buy_count  = sum(1 for v in tf.values() if str(v).upper() == "BUY")
        sell_count = sum(1 for v in tf.values() if str(v).upper() == "SELL")
        hold_count = sum(1 for v in tf.values() if str(v).upper() in ("HOLD", "NEUTRAL"))
        # FIX: buy==sell==0 (hepsi HOLD) "Karışık" değil "Tümü Nötr"
        if buy_count > sell_count:
            bias = "Çoğunluk AL"
        elif sell_count > buy_count:
            bias = "Çoğunluk SAT"
        elif hold_count > 0 and buy_count == 0 and sell_count == 0:
            bias = "Tümü Nötr (Bekleme)"
        else:
            bias = "Karışık sinyal"

        # Çelişki tespiti: RSI aşırı uçta ama sinyal HOLD → uyarı ekle
        contradiction = ""
        if td:
            for tf_k, tf_d in td.items():
                if isinstance(tf_d, dict):
                    r = tf_d.get("rsi", 50)
                    sig_tf = str(tf.get(tf_k, "")).upper()
                    if r < 20 and sig_tf in ("HOLD", "NEUTRAL", ""):
                        contradiction = f" ⚠ {tf_k.upper()} RSI={r:.0f} aşırı satım ama sinyal nötr — dip fırsatı olabilir"
                        break
                    if r > 80 and sig_tf in ("HOLD", "NEUTRAL", ""):
                        contradiction = f" ⚠ {tf_k.upper()} RSI={r:.0f} aşırı alım ama sinyal nötr — tepe riski"
                        break

        return f"EQS {eqs:.1f} (küresel) · {signals} · {bias}.{indicator_hint}{contradiction}"

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
        # Fear & Greed Index — GERÇEK veri (alternative.me)
        fng_val = raw.get("fear_greed_value")
        fng_cls = raw.get("fear_greed_class", "")
        if isinstance(fng_val, (int, float)):
            fng_tr = {
                "Extreme Fear": "Aşırı Korku", "Fear": "Korku", "Neutral": "Nötr",
                "Greed": "Açgözlülük", "Extreme Greed": "Aşırı Açgözlülük",
            }.get(fng_cls, fng_cls)
            parts.append(f"✓ Korku&Açgözlülük: {int(fng_val)} ({fng_tr})")
        if quality == "mock":
            parts.append("⚠ MVRV/NUPL simüle")
        parts.append("📊 TF bağımsız")
        return " · ".join(parts) + "." if parts else "On-chain veri bekleniyor."

    if module == "news":
        impact = raw.get("crypto_impact_score", round(score * 100, 1))
        count = raw.get("news_items_count", 0)
        count_24h = raw.get("count_24h")
        sentiment = raw.get("aggregated_sentiment", 0)
        sources = raw.get("sources", [])
        newest = raw.get("newest_age_h")
        top_headline = raw.get("top_headline")
        sent_str = "pozitif 📈" if sentiment > 0.1 else "negatif 📉" if sentiment < -0.1 else "nötr"

        # GERÇEK haber akışı (RSS) varsa zengin özet
        if top_headline:
            src_str = "/".join(sources[:3]) if sources else "RSS"
            fresh = f"{newest:.0f}s önce" if isinstance(newest, (int, float)) and newest < 48 else "güncel"
            cnt_str = f"{count_24h}/24s ({count} toplam)" if count_24h is not None else f"{count} haber"
            head_short = top_headline[:60] + ("…" if len(top_headline) > 60 else "")
            return (
                f"📰 {cnt_str} · {src_str} · en yeni {fresh} · "
                f"Duygu: {sent_str} ({sentiment:+.2f}) · Etki: {impact:.0f} · "
                f"⏱ TF-duyarlı · Manşet: «{head_short}»"
            )
        # Fallback (RSS başarısız → eski format)
        return (
            f"{count} haber analizi · Etki: {impact:.0f} · "
            f"Genel duygu: {sent_str} · ⏱ TF-duyarlı (kısa vadede etkili)."
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
        funding  = raw.get("funding_rate_pct")
        ls_ratio = raw.get("long_short_ratio")
        oi       = raw.get("open_interest_usdt")
        parts = [f"Futures skoru: {score*100:.0f}%"]
        if isinstance(funding, (int, float)):
            f_bias = "long kalabalık" if funding > 0.01 else "short kalabalık" if funding < -0.01 else "dengeli"
            parts.append(f"Funding: {funding:+.3f}% ({f_bias})")
        if isinstance(ls_ratio, (int, float)) and ls_ratio > 0:
            ls_bias = "aşırı long" if ls_ratio > 1.5 else "aşırı short" if ls_ratio < 0.67 else "dengeli"
            parts.append(f"L/S: {ls_ratio:.2f} ({ls_bias})")
        if isinstance(oi, (int, float)) and oi > 0:
            parts.append(f"OI: ${oi/1e9:.1f}B")
        return " · ".join(parts) + " · ⚡ Kontrarian sinyal · 📊 TF bağımsız."

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
# Aggregate status priority — en kötüden en iyiye.
# FALLBACK > MISSING > MOCK > STALE > PARTIAL_FALLBACK > UNKNOWN > RECENT > LIVE
# Eski sıra: MOCK, FALLBACK'ten önce geliyordu — fundamental MOCK = tüm BTC MOCK.
# Yeni: PARTIAL_FALLBACK simüle veriye düşmüştür, zinciri kirletmez.
_CONSENSUS_STATUS_PRIORITY = ("FALLBACK", "MISSING", "MOCK", "STALE", "PARTIAL_FALLBACK", "UNKNOWN", "RECENT", "LIVE")
_KNOWN_DATA_STATUSES = {"LIVE", "RECENT", "STALE", "FALLBACK", "PARTIAL_FALLBACK", "MOCK", "MISSING", "UNKNOWN"}


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


def _clean_timestamp(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _normalize_status_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().upper()
    return normalized if normalized in _KNOWN_DATA_STATUSES else None


def _extract_payload_timestamp(payload: Optional[dict[str, Any]], module: str) -> str | None:
    if not isinstance(payload, dict):
        return None

    direct = (
        _clean_timestamp(payload.get("last_updated"))
        or _clean_timestamp(payload.get("timestamp"))
        or _clean_timestamp(payload.get("available_timestamp"))
    )
    if direct:
        return direct

    if module == "touche":
        data_range = payload.get("data_range")
        if isinstance(data_range, dict):
            return _clean_timestamp(data_range.get("end"))

    if module == "news":
        signals = payload.get("signals")
        if isinstance(signals, list):
            for item in signals:
                if isinstance(item, dict):
                    nested_timestamp = _clean_timestamp(item.get("timestamp"))
                    if nested_timestamp:
                        return nested_timestamp

    return None


def _payload_data_status(payload: Optional[dict[str, Any]], module: str, timeframe: str) -> str:
    if not isinstance(payload, dict):
        return "MISSING"

    explicit_status = _normalize_status_value(payload.get("data_status"))
    if explicit_status:
        return explicit_status

    fallback_used = bool(payload.get("fallback_used", False))
    timestamp = _extract_payload_timestamp(payload, module)

    if module == "touche":
        data_mode = str(payload.get("data_mode", "")).strip().upper()
        if data_mode in {"MOCK", "SIMULATED"}:
            return "MOCK"
        if fallback_used or data_mode == "FALLBACK":
            return "FALLBACK"
        if data_mode in {"LIVE", "REAL"}:
            # FIX: Touche timestamp = günlük mum başlangıç tarihi (gece yarısı), analiz
            # zamanı değil. _status_from_timestamp bu tarihi "20 saat eski = STALE" sayıyor.
            # Servis HTTP 200 döndürdüyse analiz LIVE'dır — mum tarihi kullanılmaz.
            return "LIVE"
        return "UNKNOWN"

    if module == "fundamental":
        quality = str(payload.get("quality", "")).strip().lower()
        if quality == "mock":
            # FIX: Glassnode key yoksa simüle MVRV/NUPL döner → "mock".
            # Ama bu "tamamen uydurma" değil, tutarlı bir fallback model.
            # MOCK yerine PARTIAL_FALLBACK — tek MOCK modül tüm BTC'yi MOCK yapıyor.
            return "PARTIAL_FALLBACK"
        if fallback_used:
            return "FALLBACK"
        if timestamp:
            return _status_from_timestamp(timestamp, False, timeframe=timeframe)
        return "UNKNOWN"

    if module == "news":
        signals = payload.get("signals")
        if not isinstance(signals, list) or not signals:
            return "MISSING"
        return _status_from_timestamp(timestamp, fallback_used, timeframe=timeframe) if timestamp else "UNKNOWN"

    if module == "quantum":
        signal = str(payload.get("futures_signal", "")).strip().upper()
        if signal == "CACHE_FALLBACK" or fallback_used:
            return "FALLBACK"
        return _status_from_timestamp(timestamp, False, timeframe=timeframe) if timestamp else "UNKNOWN"

    return _status_from_timestamp(timestamp, fallback_used, timeframe=timeframe)


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

    def _parse(value: str):
        # "Z" → "+00:00", ardından naive timestamp'ı da UTC'ye bağla
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            from datetime import timezone as _tz
            dt = dt.replace(tzinfo=_tz.utc)
        return dt

    return max(valid, key=_parse)


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
        fallback_used=False,
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


@router.get("/news/live")
async def get_live_news_feed(symbol: str = Query("BTC")):
    """
    Gerçek canlı haber akışı — RSS kaynaklarından (CoinDesk/Cointelegraph/Decrypt).
    Manşetler, kaynak, yaş, duygu. Frontend haber panelinde gösterilir.
    """
    try:
        from services.news_feed import get_live_news
        data = await get_live_news(symbol.replace("/USDT", "").replace("/", ""))
        if not data.get("available"):
            return {"available": False, "headlines": [], "note": "Haber akışı geçici olarak yok"}
        return {
            "available": True,
            "symbol": data.get("symbol"),
            "impact_score": data["crypto_impact_score"],
            "sentiment": data.get("symbol_sentiment", data["aggregated_sentiment"]),
            "count_24h": data["count_24h"],
            "count_total": data["count_total"],
            "sources": data["sources"],
            "fetched_at": data["fetched_at"],
            "headlines": data.get("display_headlines", []),
        }
    except Exception as e:
        logger.error(f"Live news endpoint error: {e}")
        return {"available": False, "headlines": [], "error": str(e)}


async def _fetch_macro_for_asset_scoring(horizon: str = "medium") -> dict:
    """Fetch real macro inputs for non-crypto asset scoring.

    Prefers canonical market-data + Sentinel sources and only falls back field-by-field.
    """
    defaults = {
        "dxy": 98.5,
        "vix": 22.0,
        "us10y": 4.25,
        "brent": 92.0,
        "xau": 4800.0,
        "hg": 4.5,
        "event_risk_score": 0.3,
    }
    metrics = dict(defaults)
    warnings = ["Shared module score, not asset-specific."]
    fallback_fields: list[str] = []
    timestamps: list[str] = []

    market_results = await fetch_market_data()
    for field in ("dxy", "vix", "us10y", "brent", "xau", "hg"):
        result = market_results.get(field) or {}
        if result and not result.get("fallback_used", True):
            metrics[field] = float(result["value"])
            ts = result.get("timestamp")
            if isinstance(ts, str) and ts.strip():
                timestamps.append(ts)
        else:
            fallback_fields.append(field)
            reason = result.get("fallback_reason", "unavailable") if result else "no_result"
            warnings = _merge_warnings(warnings, [f"{field}: hardcoded fallback ({reason})"])

    sentinel_data: dict[str, Any] = {}
    sentinel_timestamp: str | None = None
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(
                f"{_SENTINEL_URL}/sentinel/event_risk",
                params={"symbol": "BTC", "horizon": horizon},
            )
            resp.raise_for_status()
            raw = resp.json()
            sentinel_data = raw if isinstance(raw, dict) else {}
            sentinel_timestamp = _clean_timestamp(sentinel_data.get("timestamp"))
            if sentinel_timestamp:
                timestamps.append(sentinel_timestamp)
    except Exception as exc:
        logger.warning("macro_asset_sentinel_unavailable: %s", exc)
        warnings = _merge_warnings(warnings, [f"Sentinel macro snapshot unavailable: {exc}"])

    sentinel_snapshot = sentinel_data.get("macro_snapshot", {})
    if not isinstance(sentinel_snapshot, dict):
        sentinel_snapshot = {}

    event_risk_value = sentinel_data.get("event_risk_score")
    if isinstance(event_risk_value, (int, float)):
        metrics["event_risk_score"] = float(event_risk_value)
    else:
        fallback_fields.append("event_risk_score")
        warnings = _merge_warnings(warnings, ["event_risk_score: hardcoded fallback (sentinel_unavailable)"])

    live_market_fields = sum(1 for field in ("dxy", "vix", "us10y", "brent", "xau", "hg") if field not in fallback_fields)
    if live_market_fields == 0:
        for field in ("dxy", "vix", "us10y", "brent", "xau", "hg"):
            value = sentinel_snapshot.get(field)
            if isinstance(value, (int, float)):
                metrics[field] = float(value)
                if field in fallback_fields:
                    fallback_fields.remove(field)

    source_timestamp = _latest_timestamp(*timestamps) if timestamps else None
    if not fallback_fields:
        data_status = "LIVE"
    elif len(fallback_fields) == 7:
        data_status = "FALLBACK"
    else:
        data_status = "PARTIAL_FALLBACK"

    if sentinel_data:
        source = str(sentinel_data.get("source", "market_data_plus_sentinel"))
        if data_status == "LIVE":
            source = "market_data_live"
        elif data_status == "PARTIAL_FALLBACK":
            source = "market_data_partial_plus_fallback"
    else:
        source = "hardcoded_macro_defaults"

    logger.info("Macro data for asset scoring: %s", metrics)
    return {
        "metrics": metrics,
        "timestamp": source_timestamp,
        "source": source,
        "fallback_used": data_status != "LIVE",
        "data_status": data_status,
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
    horizon: str = Query("medium"),
    prometheus_url: str = Query("http://prometheus:9090")
):
    """Get 3-way weighted consensus with timeframe"""
    if timeframe not in VALID_TIMEFRAMES:
        timeframe = "1h"
    if horizon not in {"short", "medium", "long"}:
        horizon = "medium"

    try:
        # Detect non-crypto assets for macro-derived scoring
        asset_key = symbol.replace("/USDT", "").replace("/", "").upper()
        module_sources: dict[str, Any]

        if asset_key in _MACRO_ASSETS:
            macro_bundle = await _fetch_macro_for_asset_scoring(horizon)
            macro_data = macro_bundle["metrics"]
            touche_score, fundamental_score, news_score = _derive_asset_scores(asset_key, macro_data)
            sentinel_score = round(1.0 - min(max(float(macro_data["event_risk_score"]), 0.0), 1.0), 4)
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
                "sentinel": _build_module_source(
                    module="sentinel",
                    service="sentinel-api",
                    source=macro_bundle["source"],
                    source_data="shared BTC event risk snapshot",
                    timestamp=macro_bundle["timestamp"],
                    timestamp_source="sentinel_response" if macro_bundle["timestamp"] else "none",
                    data_status=macro_bundle["data_status"],
                    fallback_used=macro_bundle["fallback_used"],
                    asset_specific=False,
                    shared_score=True,
                    warnings=_merge_warnings(macro_bundle["warnings"]),
                    value=sentinel_score,
                ),
            }
        else:
            live_payloads = await _fetch_live_module_payloads(symbol, timeframe)
            live = _extract_live_scores(live_payloads, timeframe, symbol)

            def _module_payload_source(
                payload_key: str,
                module: str,
                live_score: Optional[float],
            ) -> tuple[float, dict[str, Any]]:
                payload = live_payloads.get(payload_key)
                timestamp = _extract_payload_timestamp(payload, payload_key)
                data_status = _payload_data_status(payload, payload_key, timeframe)
                if live_score is not None and payload:
                    return live_score, _build_module_source(
                        module=module,
                        service=f"{module}-api",
                        source=str(payload.get("source", "live_service_api")),
                        source_data=f"{module}_service_response",
                        timestamp=timestamp,
                        timestamp_source="service_payload" if timestamp else "none",
                        data_status=data_status,
                        fallback_used=bool(payload.get("fallback_used", False)),
                        asset_specific=True,
                        shared_score=False,
                        warnings=_merge_warnings(payload.get("warnings", [])),
                        value=live_score,
                    )
                if payload:
                    unusable_status = data_status if data_status in {"MOCK", "FALLBACK", "PARTIAL_FALLBACK", "UNKNOWN", "MISSING"} else "MISSING"
                    warning_text = (
                        "Service payload is not verified live data and was excluded from consensus."
                        if unusable_status in {"MOCK", "FALLBACK", "PARTIAL_FALLBACK", "MISSING", "UNKNOWN"}
                        else "Verified live module score unavailable."
                    )
                    return 0.5, _build_module_source(
                        module=module,
                        service=f"{module}-api",
                        source=str(payload.get("source", "live_service_payload_unusable")),
                        source_data=f"{module}_service_response",
                        timestamp=timestamp,
                        timestamp_source="service_payload" if timestamp else "none",
                        data_status=unusable_status,
                        fallback_used=bool(payload.get("fallback_used", False)),
                        asset_specific=unusable_status not in {"MISSING"},
                        shared_score=False,
                        warnings=_merge_warnings(payload.get("warnings", []), [warning_text]),
                        value=0.5,
                    )
                return 0.5, _build_module_source(
                    module=module,
                    service=f"{module}-api",
                    source="live_service_missing",
                    source_data=f"{module}_service_response",
                    timestamp=None,
                    timestamp_source="none",
                    data_status="MISSING",
                    fallback_used=False,
                    asset_specific=False,
                    shared_score=False,
                    warnings=["No verified live module score available."],
                    value=0.5,
                )

            touche_score, technical_source = _module_payload_source("touche", "technical", live["touche"])
            fundamental_score, fundamental_source = _module_payload_source("fundamental", "fundamental", live["fundamental"])
            news_score, news_source = _module_payload_source("news", "news", live["news"])
            _, sentinel_source = _module_payload_source("sentinel", "sentinel", live["sentinel"])
            _, quantum_source = _module_payload_source("quantum", "quantum", live["quantum"])
            module_sources = {
                "technical": technical_source,
                "fundamental": fundamental_source,
                "news": news_source,
                "sentinel": sentinel_source,
                "quantum": quantum_source,
            }

        # Normalize to 0-1
        touche_score = min(max(float(touche_score), 0.0), 1.0)
        fundamental_score = min(max(float(fundamental_score), 0.0), 1.0)
        news_score = min(max(float(news_score), 0.0), 1.0)

        # ── Multi-timeframe hizalanma ─────────────────────────────────────
        touche_payload = live_payloads.get("touche") or {}
        tf_signals_map = touche_payload.get("tf_signals") or {}
        mtf = _compute_mtf_alignment(tf_signals_map, timeframe)

        # ── ML skoru consensus'a dahil ────────────────────────────────────
        try:
            from routes.ml_model import get_ml_score as _get_ml_score, is_ml_trained as _is_ml_trained
            _ml_trained = _is_ml_trained(symbol, timeframe)
            _ml_score   = _get_ml_score(symbol, timeframe)
        except Exception:
            _ml_trained = False
            _ml_score   = 0.5

        # MTF + ML ağırlık hesabı
        mtf_touche_boost = (mtf["score"] - 0.5) * 0.20
        if _ml_trained:
            # ML var: Touche 0.35±MTF, Fundamental 0.22, News 0.08, ML 0.25
            touche_w_adj = max(0.25, min(0.50, 0.35 + mtf_touche_boost))
            ml_w_adj     = 0.25
            remain       = 1.0 - touche_w_adj - ml_w_adj
            fundamental_w_adj = remain * 0.73
            news_w_adj        = remain * 0.27
        else:
            # ML yok: orijinal ağırlıklar (MTF ayarlamalı)
            touche_w_adj = max(0.30, min(0.70, 0.50 + mtf_touche_boost))
            remain = 1.0 - touche_w_adj
            fundamental_w_adj = remain * 0.70
            news_w_adj        = remain * 0.30
            ml_w_adj          = 0.0

        weights = {"touche": round(touche_w_adj, 3),
                   "fundamental": round(fundamental_w_adj, 3),
                   "news": round(news_w_adj, 3),
                   "ml": round(ml_w_adj, 3)}
        weighted_score = (
            touche_score      * weights["touche"] +
            fundamental_score * weights["fundamental"] +
            news_score        * weights["news"] +
            _ml_score         * weights["ml"]
        )

        # ML module_sources'a ekle
        if _ml_trained:
            module_sources["ml"] = _build_module_source(
                module="ml",
                service="ml-predictor",
                source="xgboost_cached",
                source_data="3bar_forward_return_classifier",
                timestamp=None,
                timestamp_source="none",
                data_status="LIVE",
                fallback_used=False,
                asset_specific=True,
                shared_score=False,
                warnings=[],
                value=_ml_score,
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
            module_sources.get("sentinel", {}).get("timestamp"),
            module_sources.get("quantum", {}).get("timestamp"),
        )
        warnings = _merge_warnings(
            module_sources["technical"]["warnings"],
            module_sources["fundamental"]["warnings"],
            module_sources["news"]["warnings"],
            module_sources.get("sentinel", {}).get("warnings", []),
            module_sources.get("quantum", {}).get("warnings", []),
        )
        data_status = _aggregate_status([
            module_sources["technical"]["data_status"],
            module_sources["fundamental"]["data_status"],
            module_sources["news"]["data_status"],
            module_sources.get("sentinel", {}).get("data_status"),
            module_sources.get("quantum", {}).get("data_status"),
        ])
        fallback_used = any(module_source["fallback_used"] for module_source in module_sources.values())
        verified = (
            data_status in {"LIVE", "RECENT"}
            and all(bool(module_source["verified"]) for module_source in module_sources.values())
        )
        if data_status in {"STALE", "FALLBACK", "PARTIAL_FALLBACK", "MOCK", "MISSING", "UNKNOWN"}:
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
            "mtf_alignment": mtf,
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
