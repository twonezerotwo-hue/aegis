import httpx
import logging
from typing import List
from models.schemas import ToucheAnalysis, FibonacciLevel

logger = logging.getLogger(__name__)

class ToucheAnalyzer:
    def __init__(self, touche_url: str):
        self.touche_url = touche_url
        self.client = httpx.AsyncClient(timeout=10.0)

    async def analyze(self, symbol: str, timeframe: str) -> ToucheAnalysis:
        try:
            # Fetch Touche score from API
            response = await self.client.get(
                f"{self.touche_url}/api/metrics/touche",
                params={"symbol": symbol, "timeframe": timeframe}
            )
            response.raise_for_status()
            touche_data = response.json()

            score = touche_data.get("score", 0.5)
            details = touche_data.get("details", {})

            # Calculate Fibonacci levels (example with BTC)
            price_high = float(details.get("price_high", 50000))
            price_low = float(details.get("price_low", 30000))
            current_price = float(details.get("current_price", 40000))

            diff = price_high - price_low
            fibonacci_levels = [
                FibonacciLevel(level="0.382", value=0.382, price=price_low + diff * 0.382),
                FibonacciLevel(level="0.5", value=0.5, price=price_low + diff * 0.5),
                FibonacciLevel(level="0.618", value=0.618, price=price_low + diff * 0.618),
            ]

            # Determine current Fibonacci level
            current_level = self._get_fibonacci_level(current_price, fibonacci_levels)

            # Extract technical indicators
            rsi = float(details.get("rsi", 50))
            rsi_status = self._rsi_status(rsi)

            macd_histogram = float(details.get("macd_histogram", 0))
            macd_status = "Pozitif, kesişim yukarı" if macd_histogram > 0 else "Negatif, kesişim aşağı"

            stoch_rsi = float(details.get("stoch_rsi", 50))
            stoch_rsi_status = self._stoch_rsi_status(stoch_rsi)

            candle_pattern = details.get("candle_pattern", "Normal mum")

            # Determine direction based on all indicators
            direction = self._determine_direction(score, rsi, macd_histogram, stoch_rsi)

            details_text = (
                f"Teknik göstergeler: RSI={rsi:.1f} {rsi_status}, "
                f"MACD={macd_status}, StochRSI={stoch_rsi:.1f} {stoch_rsi_status}. "
                f"Mum formasyonu: {candle_pattern}"
            )

            return ToucheAnalysis(
                direction=direction,
                confidence=score,
                fibonacci_levels=fibonacci_levels,
                current_price=current_price,
                current_level=current_level,
                rsi=rsi,
                rsi_description=rsi_status,
                macd_histogram=macd_histogram,
                macd_status=macd_status,
                stoch_rsi=stoch_rsi,
                stoch_rsi_status=stoch_rsi_status,
                candle_pattern=candle_pattern,
                details=details_text
            )

        except httpx.HTTPError as e:
            logger.error(f"Touche API error: {e}")
            # Return neutral analysis on error
            return ToucheAnalysis(
                direction="NÖTR",
                confidence=0.5,
                fibonacci_levels=[],
                current_price=0.0,
                current_level="Bilinmiyor",
                details=f"Veri alınamadı: {str(e)}"
            )

    def _get_fibonacci_level(self, current_price: float, levels: List[FibonacciLevel]) -> str:
        """Determine which Fibonacci level is closest to current price"""
        closest = min(levels, key=lambda x: abs(x.price - current_price))
        return closest.level

    def _rsi_status(self, rsi: float) -> str:
        if rsi > 70:
            return "Aşırı alım"
        elif rsi > 60:
            return "AL bölgesine yakın"
        elif rsi < 30:
            return "Aşırı satım"
        elif rsi < 40:
            return "SAT bölgesine yakın"
        else:
            return "Normal"

    def _stoch_rsi_status(self, stoch_rsi: float) -> str:
        if stoch_rsi > 80:
            return "Aşırı alım bölgesi"
        elif stoch_rsi > 70:
            return "Aşırı alım bölgesine yakın"
        elif stoch_rsi < 20:
            return "Aşırı satım bölgesi"
        elif stoch_rsi < 30:
            return "Aşırı satım bölgesine yakın"
        else:
            return "Normal"

    def _determine_direction(self, score: float, rsi: float, macd_histogram: float, stoch_rsi: float) -> str:
        """Determine direction based on all indicators"""
        if score > 0.65 and rsi > 45 and macd_histogram > 0 and stoch_rsi > 40:
            return "LONG"
        elif score < 0.35 and rsi < 55 and macd_histogram < 0 and stoch_rsi < 60:
            return "SHORT"
        else:
            return "NÖTR"

    async def close(self):
        await self.client.aclose()
