import httpx
import logging
from models.schemas import SentinelAnalysis

logger = logging.getLogger(__name__)

class SentinelAnalyzer:
    def __init__(self, sentinel_url: str):
        self.sentinel_url = sentinel_url
        self.client = httpx.AsyncClient(timeout=10.0)

    async def analyze(self, symbol: str, timeframe: str) -> SentinelAnalysis:
        try:
            # Fetch Sentinel score from API
            response = await self.client.get(
                f"{self.sentinel_url}/api/metrics/sentinel",
                params={"symbol": symbol, "timeframe": timeframe}
            )
            response.raise_for_status()
            sentinel_data = response.json()

            score = sentinel_data.get("score", 0.5)
            details = sentinel_data.get("details", {})

            # Extract risk metrics
            vix = float(details.get("vix", 15.0))
            dxy = float(details.get("dxy", 103.5))
            fear_greed = float(details.get("fear_greed_index", 50))
            fed_rate = float(details.get("fed_rate", 5.5))

            # Determine risk level
            risk_level = self._determine_risk_level(vix, dxy, fear_greed)

            # Determine direction (lower risk = more trading opportunity)
            direction = self._determine_direction(score, vix, fear_greed)

            details_text = (
                f"VIX: {vix:.1f} ({'düşük risk' if vix < 20 else 'yüksek risk'}), "
                f"DXY: {dxy:.1f} ({'dolar zayıf' if dxy < 105 else 'dolar güçlü'}), "
                f"Fear & Greed: {fear_greed:.0f} "
                f"({'Açgözlülük' if fear_greed > 70 else 'Korku' if fear_greed < 30 else 'Nötr'} bölgesi), "
                f"Fed Faiz: {fed_rate:.1f}%"
            )

            return SentinelAnalysis(
                direction=direction,
                confidence=score,
                vix=vix,
                dxy=dxy,
                fear_greed_index=fear_greed,
                fed_rate=fed_rate,
                risk_level=risk_level,
                details=details_text
            )

        except httpx.HTTPError as e:
            logger.error(f"Sentinel API error: {e}")
            return SentinelAnalysis(
                direction="NÖTR",
                confidence=0.5,
                details=f"Veri alınamadı: {str(e)}"
            )

    def _determine_risk_level(self, vix: float, dxy: float, fear_greed: float) -> str:
        """Determine overall risk level"""
        if vix > 30 or fear_greed < 25:
            return "Yüksek Risk (Korku)"
        elif vix > 20 or fear_greed > 75:
            return "Orta Risk"
        elif vix < 15 and fear_greed < 70:
            return "Düşük Risk"
        else:
            return "Normal Risk"

    def _determine_direction(self, score: float, vix: float, fear_greed: float) -> str:
        """Determine direction based on risk metrics"""
        # Lower VIX and lower Fear & Greed (but not extreme) is good for trading
        if score > 0.6 and vix < 20 and 40 < fear_greed < 70:
            return "LONG"
        elif score < 0.4 and (vix > 25 or fear_greed < 30 or fear_greed > 80):
            return "SHORT"
        else:
            return "NÖTR"

    async def close(self):
        await self.client.aclose()
