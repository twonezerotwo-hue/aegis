"""
services/market_data.py
Real market data fetcher for AEGIS dashboard.
Sources:
  yfinance   — DXY, VIX, US10Y, Brent, Gold, Copper (no key required)
  Binance    — BTC price via public REST API (no auth required for price data)
  CoinGecko  — BTC.D, USDT.D via public /api/v3/global (no key required)

Each field returns a dict:
  {value, source, timestamp, verified, fallback_used}

Results are cached for CACHE_TTL_SECONDS to avoid hammering external APIs.
Source timestamps are preserved only when the upstream provides them.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Cache to avoid hitting APIs on every request
_CACHE: dict[str, dict] = {}
CACHE_TTL_SECONDS = 60

_BINANCE_BASE = "https://api.binance.com"
_COINGECKO_BASE = "https://api.coingecko.com/api/v3"

# yfinance ticker symbols for each metric field
_YFINANCE_SYMBOLS: dict[str, str] = {
    "dxy": "DX-Y.NYB",
    "vix": "^VIX",
    "us10y": "^TNX",
    "brent": "BZ=F",
    "xau": "GC=F",
    "hg": "HG=F",
}

# Hardcoded fallback values — used only when live APIs fail
_FALLBACK_VALUES: dict[str, float] = {
    "dxy": 98.5,
    "vix": 22.0,
    "us10y": 4.25,
    "brent": 92.0,
    "xau": 4800.0,
    "btc_d": 59.8,
    "usdt_d": 7.5,
    "hg": 4.5,
}


def _is_cache_valid(key: str) -> bool:
    if key not in _CACHE:
        return False
    age = (datetime.now(timezone.utc) - _CACHE[key]["fetched_at"]).total_seconds()
    return age < CACHE_TTL_SECONDS


def _live_result(value: float, source: str, timestamp: str | None) -> dict:
    return {
        "value": round(float(value), 6),
        "source": source,
        "timestamp": timestamp,
        "verified": True,
        "fallback_used": False,
    }


def _fallback_result(field: str, reason: str) -> dict:
    return {
        "value": _FALLBACK_VALUES.get(field, 0.0),
        "source": f"hardcoded_fallback",
        "timestamp": None,
        "verified": False,
        "fallback_used": True,
        "fallback_reason": reason,
    }


async def _fetch_yfinance_prices() -> dict[str, dict]:
    """Fetch DXY, VIX, US10Y, Brent, Gold, Copper via yfinance in a thread."""
    try:
        import yfinance as yf  # noqa: PLC0415

        symbols = list(_YFINANCE_SYMBOLS.values())

        def _sync_download() -> dict:
            # Download last 5 days of daily data to get the most recent close
            raw = yf.download(
                symbols,
                period="5d",
                interval="1d",
                progress=False,
                auto_adjust=True,
                threads=False,
            )
            out: dict[str, dict] = {}
            for field, sym in _YFINANCE_SYMBOLS.items():
                try:
                    # multi-ticker: Close has symbol-level columns
                    if hasattr(raw.columns, "levels"):
                        col = raw["Close"][sym] if "Close" in raw.columns.get_level_values(0) else None
                    else:
                        col = raw["Close"] if len(symbols) == 1 else None

                    if col is not None and not col.dropna().empty:
                        series = col.dropna()
                        val = float(series.iloc[-1])
                        idx = series.index[-1]
                        timestamp = idx.isoformat() if hasattr(idx, "isoformat") else None
                        out[field] = _live_result(val, f"yfinance:{sym}", timestamp)
                    else:
                        out[field] = _fallback_result(field, "yfinance_empty_series")
                except Exception as e:
                    out[field] = _fallback_result(field, f"yfinance_parse_error:{e}")
            return out

        results = await asyncio.to_thread(_sync_download)
        return results

    except ImportError:
        logger.warning("yfinance not installed; all yfinance fields will use hardcoded fallback")
        return {k: _fallback_result(k, "yfinance_not_installed") for k in _YFINANCE_SYMBOLS}
    except Exception as exc:
        logger.warning("yfinance batch download failed: %s", exc)
        return {k: _fallback_result(k, f"yfinance_exception:{exc}") for k in _YFINANCE_SYMBOLS}


async def _fetch_coingecko_dominance() -> dict[str, dict]:
    """Fetch BTC.D and USDT.D from CoinGecko public global endpoint."""
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"{_COINGECKO_BASE}/global",
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            payload = resp.json().get("data", {})
            pct: dict = payload.get("market_cap_percentage", {})
            updated_at = payload.get("updated_at")
            ts = (
                datetime.fromtimestamp(float(updated_at), timezone.utc).isoformat()
                if isinstance(updated_at, (int, float))
                else None
            )

            btc_d = pct.get("btc")
            usdt_d = pct.get("usdt")
            return {
                "btc_d": (
                    _live_result(float(btc_d), "coingecko_public:btc_dominance", ts)
                    if btc_d is not None
                    else _fallback_result("btc_d", "coingecko_no_btc_field")
                ),
                "usdt_d": (
                    _live_result(float(usdt_d), "coingecko_public:usdt_dominance", ts)
                    if usdt_d is not None
                    else _fallback_result("usdt_d", "coingecko_no_usdt_field")
                ),
            }
    except Exception as exc:
        logger.warning("CoinGecko dominance fetch failed: %s", exc)
        return {
            "btc_d": _fallback_result("btc_d", f"coingecko_error:{exc}"),
            "usdt_d": _fallback_result("usdt_d", f"coingecko_error:{exc}"),
        }


async def fetch_market_data() -> dict[str, dict]:
    """
    Fetch all market metrics concurrently.
    Returns dict of field_name → {value, source, timestamp, verified, fallback_used}.
    Results cached for CACHE_TTL_SECONDS.
    """
    cache_key = "market_data_v1"
    if _is_cache_valid(cache_key):
        return _CACHE[cache_key]["data"]  # type: ignore[return-value]

    yf_task = asyncio.ensure_future(_fetch_yfinance_prices())
    cg_task = asyncio.ensure_future(_fetch_coingecko_dominance())

    yf_res, cg_res = await asyncio.gather(yf_task, cg_task, return_exceptions=True)

    if isinstance(yf_res, Exception):
        logger.warning("yfinance gather exception: %s", yf_res)
        yf_res = {k: _fallback_result(k, "gather_exception") for k in _YFINANCE_SYMBOLS}

    if isinstance(cg_res, Exception):
        logger.warning("coingecko gather exception: %s", cg_res)
        cg_res = {
            "btc_d": _fallback_result("btc_d", "gather_exception"),
            "usdt_d": _fallback_result("usdt_d", "gather_exception"),
        }

    combined: dict[str, dict] = {**yf_res, **cg_res}  # type: ignore[misc]

    _CACHE[cache_key] = {
        "data": combined,
        "fetched_at": datetime.now(timezone.utc),
    }

    live_count = sum(1 for v in combined.values() if not v.get("fallback_used", True))
    logger.info(
        "market_data_fetch: %d/%d fields live, %d fallback",
        live_count,
        len(combined),
        len(combined) - live_count,
    )
    return combined
