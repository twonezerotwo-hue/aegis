"""
AEGIS Price Validator — Çapraz kaynak fiyat doğrulaması

Sorun: Tüm fiyatlar tek kaynaktan geliyor. Kaynakta hata/manipülasyon
varsa sistem fark edemiyor.

Çözüm: İki farklı kaynaktan fiyat çek, sapma > eşik → UNVERIFIED işaretle.

Kaynaklar (öncelik sırası):
  1. Binance REST (ana kaynak)
  2. CoinGecko public (ücretsiz)
  3. yfinance (hisse/endeks için)

Eşik: |fiyat1 - fiyat2| / ortalama > %0.5 → uyarı
       > %1.0 → UNVERIFIED (sinyal üretilemez)
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, float]] = {}  # symbol → (price, ts)
_CACHE_TTL = 30  # saniye

# CoinGecko sembol → coin_id eşlemesi
_CG_ID: dict[str, str] = {
    "BTC":  "bitcoin",
    "ETH":  "ethereum",
    "BNB":  "binancecoin",
    "SOL":  "solana",
    "XRP":  "ripple",
    "XAU":  "gold",      # CoinGecko goldprice
    "XAG":  "silver",
}

_WARN_PCT  = 0.005   # %0.5 sapma → uyarı
_ERROR_PCT = 0.010   # %1.0 sapma → UNVERIFIED


async def _fetch_binance(symbol: str) -> Optional[float]:
    """Binance spot fiyatı (public, auth gereksiz)."""
    ticker = symbol.upper().replace("/", "") + ("USDT" if "/" not in symbol else "")
    try:
        async with httpx.AsyncClient(timeout=4.0) as c:
            r = await c.get(
                "https://api.binance.com/api/v3/ticker/price",
                params={"symbol": ticker},
            )
            if r.status_code == 200:
                return float(r.json()["price"])
    except Exception as exc:
        logger.debug("binance_price_fail %s: %s", symbol, exc)
    return None


async def _fetch_coingecko(symbol: str) -> Optional[float]:
    """CoinGecko public fiyat (rate-limited ama ücretsiz)."""
    base = symbol.split("/")[0].upper()
    coin_id = _CG_ID.get(base)
    if not coin_id:
        return None
    try:
        async with httpx.AsyncClient(timeout=4.0) as c:
            r = await c.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": coin_id, "vs_currencies": "usd"},
            )
            if r.status_code == 200:
                data = r.json()
                return float(data.get(coin_id, {}).get("usd", 0)) or None
    except Exception as exc:
        logger.debug("coingecko_price_fail %s: %s", symbol, exc)
    return None


async def _fetch_yfinance(symbol: str) -> Optional[float]:
    """yfinance fiyatı — hisse ve endeksler için."""
    base = symbol.split("/")[0].upper()
    yf_ticker_map = {"XAU": "GC=F", "BTC": "BTC-USD", "ETH": "ETH-USD",
                     "XAG": "SI=F", "OIL": "CL=F"}
    yf_ticker = yf_ticker_map.get(base, f"{base}-USD")
    try:
        import yfinance as yf
        import asyncio
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None,
            lambda: yf.download(yf_ticker, period="1d", interval="1m",
                                 progress=False, auto_adjust=True),
        )
        if not data.empty:
            return float(data["Close"].iloc[-1])
    except Exception as exc:
        logger.debug("yfinance_price_fail %s: %s", symbol, exc)
    return None


class PriceValidation:
    """Fiyat doğrulama sonucu."""
    __slots__ = ("symbol", "price", "source1", "price1", "source2", "price2",
                 "deviation_pct", "verified", "warning", "error")

    def __init__(self, symbol: str, price: float, source1: str, price1: float,
                 source2: Optional[str], price2: Optional[float]):
        self.symbol = symbol
        self.price  = price
        self.source1 = source1
        self.price1  = price1
        self.source2 = source2
        self.price2  = price2

        if price2 is not None and price2 > 0:
            avg = (price1 + price2) / 2
            self.deviation_pct = abs(price1 - price2) / avg
        else:
            self.deviation_pct = 0.0

        self.verified = self.deviation_pct <= _ERROR_PCT
        self.warning  = _WARN_PCT < self.deviation_pct <= _ERROR_PCT
        self.error    = self.deviation_pct > _ERROR_PCT

    def to_dict(self) -> dict:
        return {
            "symbol":        self.symbol,
            "price":         round(self.price, 6),
            "source_primary":  self.source1,
            "price_primary":   round(self.price1, 6),
            "source_secondary": self.source2,
            "price_secondary":  round(self.price2, 6) if self.price2 else None,
            "deviation_pct":   round(self.deviation_pct * 100, 4),
            "verified":        self.verified,
            "warning":         self.warning,
            "unverified":      self.error,
            "status": (
                "UNVERIFIED" if self.error
                else "WARNING" if self.warning
                else "VERIFIED"
            ),
        }


async def validate_price(symbol: str) -> PriceValidation:
    """
    İki kaynaktan fiyat çek, sapma analizi yap.

    Kullanım:
        vld = await validate_price("BTC/USDT")
        if vld.error:
            raise ValueError(f"Fiyat güvenilir değil: {vld.to_dict()}")
    """
    # Cache kontrolü
    cached = _CACHE.get(symbol)
    if cached and time.time() - cached[1] < _CACHE_TTL:
        # Cache'den doğrulama yap (tek değer — zaten doğrulandı)
        return PriceValidation(symbol, cached[0], "cache", cached[0], None, None)

    # Kaynak 1: Binance
    price1 = await _fetch_binance(symbol)
    source1 = "binance"

    # Kaynak 2: CoinGecko
    price2 = await _fetch_coingecko(symbol)
    source2 = "coingecko" if price2 else None

    # Eğer CoinGecko yoksa yfinance dene
    if price2 is None:
        price2 = await _fetch_yfinance(symbol)
        source2 = "yfinance" if price2 else None

    # Birincil fiyat belirle
    primary = price1 or price2
    if primary is None:
        logger.warning("price_validate_all_failed: %s", symbol)
        return PriceValidation(symbol, 0.0, "none", 0.0, None, None)

    if price1 is None:
        price1 = price2
        source1 = source2 or "unknown"
        price2 = None

    # Cache'e yaz
    _CACHE[symbol] = (primary, time.time())

    vld = PriceValidation(symbol, primary, source1, price1 or 0.0, source2, price2)

    if vld.error:
        logger.warning(
            "PRICE_UNVERIFIED %s: %s=%.4f vs %s=%.4f deviation=%.2f%%",
            symbol, source1, price1, source2, price2 or 0,
            vld.deviation_pct * 100,
        )
    elif vld.warning:
        logger.info(
            "PRICE_WARNING %s: %.2f%% sapma (%s vs %s)",
            symbol, vld.deviation_pct * 100, source1, source2,
        )

    return vld
