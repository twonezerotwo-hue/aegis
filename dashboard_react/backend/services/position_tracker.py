"""
AEGIS Position Tracker — Gerçek Binance Bakiye → Portföy Ağırlığı

Sorun: allocation_current her zaman allocation_target'e eşit.
Portföy tablosu "hedef" gösteriyor, "mevcut" değil.

Çözüm: Binance /api/v3/account API'si ile gerçek spot bakiyeleri çek,
anlık fiyatlarla USDT değerine çevir, toplam içindeki yüzdeyi hesapla.

Desteklenen varlıklar:
  USDT/BUSD/USDC → cash
  BTC             → btc
  ETH             → (btc grubuna dahil — risk varlığı)
  XAU (piyasadan) → gold
  Diğer emtia     → commodity
  Tahvil ETF      → bond (çoğunlukla off-exchange)

Auth: BINANCE_API_KEY + BINANCE_API_SECRET (HMAC-SHA256 imzası)
Fallback: bakiye çekilemezse target döner (mevcut davranış)
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
import urllib.parse
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_BINANCE_BASE = "https://api.binance.com"
_CACHE_TTL = 60  # saniye
_cache: Optional[tuple[dict[str, float], float]] = None  # (weights, ts)

# Binance varlık → portföy kategorisi eşlemesi
_ASSET_MAP: dict[str, str] = {
    "USDT":  "cash",
    "BUSD":  "cash",
    "USDC":  "cash",
    "FDUSD": "cash",
    "BTC":   "btc",
    "ETH":   "btc",      # risk asset grubu
    "BNB":   "btc",      # risk asset grubu
    "SOL":   "btc",      # risk asset grubu
    "XRP":   "btc",
    "XAU":   "gold",
    "PAXG":  "gold",     # gold token
    "GLD":   "gold",
    "OIL":   "commodity",
    "XAG":   "commodity",
    "WTI":   "commodity",
    "LINK":  "commodity",
}


def _sign(params: dict, secret: str) -> str:
    qs = urllib.parse.urlencode(params)
    return hmac.new(secret.encode(), qs.encode(), hashlib.sha256).hexdigest()


async def _get_binance_balances(api_key: str, api_secret: str) -> dict[str, float]:
    """Binance spot hesabından non-zero bakiyeleri çek."""
    ts = int(time.time() * 1000)
    params = {"timestamp": ts, "recvWindow": 5000}
    params["signature"] = _sign(params, api_secret)

    async with httpx.AsyncClient(timeout=8.0) as client:
        r = await client.get(
            f"{_BINANCE_BASE}/api/v3/account",
            params=params,
            headers={"X-MBX-APIKEY": api_key},
        )
        if r.status_code != 200:
            logger.warning("binance_account_fail: %d %s", r.status_code, r.text[:100])
            return {}

        data = r.json()
        balances = {}
        for b in data.get("balances", []):
            free = float(b.get("free", 0))
            locked = float(b.get("locked", 0))
            total = free + locked
            if total > 0.0001:  # dust eşiği
                balances[b["asset"]] = total
        return balances


async def _get_prices(assets: list[str]) -> dict[str, float]:
    """Binance'ten USDT fiyatlarını toplu çek."""
    prices = {"USDT": 1.0, "BUSD": 1.0, "USDC": 1.0, "FDUSD": 1.0}
    symbols = [f"{a}USDT" for a in assets if a not in prices]
    if not symbols:
        return prices
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{_BINANCE_BASE}/api/v3/ticker/price",
            )
            if r.status_code == 200:
                for item in r.json():
                    sym = item["symbol"]
                    if sym.endswith("USDT"):
                        asset = sym[:-4]
                        prices[asset] = float(item["price"])
    except Exception as exc:
        logger.debug("prices_fetch_fail: %s", exc)
    return prices


def _balances_to_weights(
    balances: dict[str, float],
    prices: dict[str, float],
) -> dict[str, float]:
    """Bakiye × fiyat → USDT değeri → kategori ağırlığı."""
    category_usdt: dict[str, float] = {
        "gold": 0.0, "btc": 0.0, "bond": 0.0, "commodity": 0.0, "cash": 0.0,
    }

    for asset, qty in balances.items():
        price = prices.get(asset, 0.0)
        if price == 0:
            continue
        usdt_val = qty * price
        category = _ASSET_MAP.get(asset, "cash")  # bilinmeyenler cash'e gider
        if category in category_usdt:
            category_usdt[category] += usdt_val

    total = sum(category_usdt.values())
    if total < 1.0:  # çok az bakiye — anlamlı değil
        return {}

    return {cat: round(val / total, 4) for cat, val in category_usdt.items()}


async def get_current_allocation(
    fallback: dict[str, float],
) -> tuple[dict[str, float], str]:
    """
    Mevcut portföy ağırlığını döndür.

    Returns:
        (weights_dict, source) — source: "binance" | "paper" | "target"
    """
    global _cache

    # Cache kontrolü
    if _cache and time.time() - _cache[1] < _CACHE_TTL:
        return _cache[0], "binance_cached"

    api_key    = os.environ.get("BINANCE_API_KEY", "").strip()
    api_secret = os.environ.get("BINANCE_API_SECRET", "").strip()

    if not api_key or not api_secret:
        logger.debug("position_tracker: no binance credentials — using target")
        return fallback, "target"

    try:
        balances = await _get_binance_balances(api_key, api_secret)
        if not balances:
            return fallback, "target"

        prices = await _get_prices(list(balances.keys()))
        weights = _balances_to_weights(balances, prices)

        if not weights:
            return fallback, "target"

        # Eksik kategoriler → fallback'ten al
        for cat in ("gold", "btc", "bond", "commodity", "cash"):
            if cat not in weights:
                weights[cat] = fallback.get(cat, 0.0)

        # Yeniden normalize
        total = sum(weights.values())
        if total > 0:
            weights = {k: round(v / total, 4) for k, v in weights.items()}

        _cache = (weights, time.time())
        logger.info("position_tracker: binance balances → %s", weights)
        return weights, "binance"

    except Exception as exc:
        logger.warning("position_tracker_failed: %s — using target", exc)
        return fallback, "target"
