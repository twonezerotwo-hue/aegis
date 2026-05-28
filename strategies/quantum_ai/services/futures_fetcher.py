# AEGIS v6.0 - Quantum AI Futures Extension | Purpose: Async Binance futures fetcher with TTL cache and fallback.
import logging
from datetime import datetime, timezone

import httpx

try:
    from models.futures import QuantumFuturesData, QuantumFuturesFallback
    from utils.cache import TTLCache
except ModuleNotFoundError:
    from strategies.quantum_ai.models.futures import QuantumFuturesData, QuantumFuturesFallback
    from strategies.quantum_ai.utils.cache import TTLCache

logger = logging.getLogger(__name__)

BASE_URL = "https://fapi.binance.com"
FUNDING_TTL = 28800
OI_RATIO_TTL = 900
HTTP_TIMEOUT = 3.0


class FuturesFetcher:
    def __init__(self, cache: TTLCache | None = None) -> None:
        self.cache = cache or TTLCache()

    async def _fetch_json(self, path: str, params: dict[str, str]) -> dict | list:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.get(f"{BASE_URL}{path}", params=params)
            response.raise_for_status()
            return response.json()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    async def get_futures_data(self, symbol: str = "BTCUSDT") -> QuantumFuturesData:
        sym = symbol.upper().strip()
        funding_key = f"quantum:futures:{sym}:funding"
        oi_key = f"quantum:futures:{sym}:oi"
        ratio_key = f"quantum:futures:{sym}:ratio"

        try:
            funding = await self.cache.get(funding_key)
            if funding is None:
                raw_funding = await self._fetch_json("/fapi/v1/premiumIndex", {"symbol": sym})
                funding = float((raw_funding or {}).get("lastFundingRate", 0.0))
                await self.cache.set(funding_key, funding, FUNDING_TTL)

            open_interest_usdt = await self.cache.get(oi_key)
            if open_interest_usdt is None:
                raw_oi = await self._fetch_json("/fapi/v1/openInterest", {"symbol": sym})
                open_interest_usdt = float((raw_oi or {}).get("openInterest", 0.0))
                await self.cache.set(oi_key, open_interest_usdt, OI_RATIO_TTL)

            long_short_ratio = await self.cache.get(ratio_key)
            if long_short_ratio is None:
                raw_ratio = await self._fetch_json(
                    "/futures/data/globalLongShortAccountRatio",
                    {"symbol": sym, "period": "5m", "limit": "3"},
                )
                if isinstance(raw_ratio, list) and raw_ratio:
                    long_short_ratio = float(raw_ratio[-1].get("longShortRatio", 1.0))
                else:
                    long_short_ratio = 1.0
                await self.cache.set(ratio_key, long_short_ratio, OI_RATIO_TTL)

            funding_rate = float(funding)
            funding_rate_pct = float(funding_rate * 100.0)
            oi = float(open_interest_usdt)
            ratio = float(long_short_ratio)

            modifier = 1.0
            futures_signal = "NEUTRAL"

            if funding_rate_pct > 0.01:
                futures_signal = "OVERLEVERAGED_LONG"
                modifier *= 0.80
            elif funding_rate_pct < -0.01:
                futures_signal = "OVERLEVERAGED_SHORT"
                modifier *= 0.80

            if ratio > 2.5 or ratio < 0.4:
                modifier *= 0.85

            modifier = max(0.60, min(1.0, modifier))

            return QuantumFuturesData(
                symbol=sym,
                funding_rate=funding_rate,
                funding_rate_pct=funding_rate_pct,
                open_interest_usdt=oi,
                long_short_ratio=ratio,
                futures_signal=futures_signal,
                modifier=modifier,
                timestamp=self._now(),
            )
        except Exception as exc:
            logger.warning("[quantum.futures] fetch failed, using fallback: %s", exc)
            return QuantumFuturesFallback(
                symbol=sym,
                funding_rate=0.0,
                funding_rate_pct=0.0,
                open_interest_usdt=0.0,
                long_short_ratio=1.0,
                modifier=1.0,
                timestamp=self._now(),
            )
