import httpx
import logging
from models.schemas import FundamentalAnalysis

logger = logging.getLogger(__name__)

class FundamentalAnalyzer:
    def __init__(self, fundamental_url: str):
        self.fundamental_url = fundamental_url
        self.client = httpx.AsyncClient(timeout=10.0)

    async def analyze(self, symbol: str, timeframe: str) -> FundamentalAnalysis:
        try:
            # Fetch Fundamental score from API
            response = await self.client.get(
                f"{self.fundamental_url}/api/metrics/fundamental",
                params={"symbol": symbol, "timeframe": timeframe}
            )
            response.raise_for_status()
            fundamental_data = response.json()

            score = fundamental_data.get("score", 0.5)
            details = fundamental_data.get("details", {})

            # Extract on-chain metrics
            mvrv_z_score = float(details.get("mvrv_z_score", 1.5))
            puell_multiple = float(details.get("puell_multiple", 1.0))
            exchange_netflow = float(details.get("exchange_netflow", -10000))
            stablecoin_supply_change = float(details.get("stablecoin_supply_change", 0.5))
            active_addresses_change = float(details.get("active_addresses_change", 5.0))

            # Determine direction based on on-chain metrics
            direction = self._determine_direction(
                score, mvrv_z_score, puell_multiple, exchange_netflow
            )

            details_text = (
                f"MVRV Z-Score: {mvrv_z_score:.2f} (normal bölge), "
                f"Puell Multiple: {puell_multiple:.2f} (miner aktivitesi), "
                f"Exchange Netflow: {exchange_netflow:,.0f} BTC (ağ akışı), "
                f"Stablecoin Supply: +{stablecoin_supply_change:.1f}% (alım gücü), "
                f"Aktif Adresler: +{active_addresses_change:.1f}% (ağ aktivitesi)"
            )

            return FundamentalAnalysis(
                direction=direction,
                confidence=score,
                mvrv_z_score=mvrv_z_score,
                puell_multiple=puell_multiple,
                exchange_netflow=abs(exchange_netflow),
                exchange_netflow_unit="BTC",
                stablecoin_supply_change=stablecoin_supply_change,
                active_addresses_change=active_addresses_change,
                details=details_text
            )

        except httpx.HTTPError as e:
            logger.error(f"Fundamental API error: {e}")
            return FundamentalAnalysis(
                direction="NÖTR",
                confidence=0.5,
                details=f"Veri alınamadı: {str(e)}"
            )

    def _determine_direction(self, score: float, mvrv: float, puell: float, netflow: float) -> str:
        """Determine direction based on on-chain metrics"""
        positive_signals = 0

        # MVRV Z-Score: 1.0-2.0 is normal, >2.5 is overvalued
        if mvrv < 2.5:
            positive_signals += 1

        # Puell Multiple: <1.0 is good buying opportunity
        if puell < 1.0:
            positive_signals += 1

        # Exchange Netflow: negative means coins leaving (buying pressure)
        if netflow < 0:
            positive_signals += 1

        # Overall score
        if score > 0.65 and positive_signals >= 2:
            return "LONG"
        elif score < 0.35 and positive_signals < 1:
            return "SHORT"
        else:
            return "NÖTR"

    async def close(self):
        await self.client.aclose()
