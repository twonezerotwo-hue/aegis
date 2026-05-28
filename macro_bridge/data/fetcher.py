from typing import Dict

import requests
import yfinance as yf

from macro_bridge.config.settings import Settings
from macro_bridge.data.cache import DataCache
from macro_bridge.utils.helpers import safe_float


class DataFetcher:
    def __init__(self) -> None:
        self.settings = Settings()
        self.cache = DataCache(redis_url=self.settings.redis_url)

    def _get_last_close(self, ticker: str, period: str = "5d") -> float:
        cache_key = f"yf:{ticker}:{period}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return float(cached)

        data = yf.Ticker(ticker).history(period=period)
        if data.empty:
            raise ValueError(f"No data for ticker {ticker}")

        value = float(data["Close"].iloc[-1])
        self.cache.set(cache_key, value, ttl_sec=120)
        return value

    def _fetch_coingecko_global(self) -> Dict:
        cache_key = "coingecko:global"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        response = requests.get("https://api.coingecko.com/api/v3/global", timeout=self.settings.timeout_sec)
        response.raise_for_status()
        payload = response.json().get("data", {})
        self.cache.set(cache_key, payload, ttl_sec=120)
        return payload

    def get_dxy(self) -> float:
        return self._get_last_close("DX-Y.NYB")

    def get_us10y(self) -> float:
        return self._get_last_close("^TNX")

    def get_vix(self) -> float:
        return self._get_last_close("^VIX")

    def get_brent(self) -> float:
        return self._get_last_close("BZ=F")

    def get_xau(self) -> float:
        return self._get_last_close("GC=F")

    def get_btc_dominance(self) -> float:
        payload = self._fetch_coingecko_global()
        btc_d = payload.get("market_cap_percentage", {}).get("btc", 52.0)
        return safe_float(btc_d, 52.0)

    def get_usdt_dominance(self) -> float:
        payload = self._fetch_coingecko_global()
        usdt_d = payload.get("market_cap_percentage", {}).get("usdt", 4.0)
        return safe_float(usdt_d, 4.0)

    def get_hg(self) -> float:
        # Copper futures ticker on Yahoo Finance.
        return self._get_last_close("HG=F")
