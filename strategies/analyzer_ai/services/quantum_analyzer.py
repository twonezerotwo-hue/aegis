import httpx
import logging
from models.schemas import QuantumAnalysis

logger = logging.getLogger(__name__)

class QuantumAnalyzer:
    def __init__(self, quantum_url: str):
        self.quantum_url = quantum_url
        self.client = httpx.AsyncClient(timeout=10.0)

    async def analyze(self, symbol: str, timeframe: str) -> QuantumAnalysis:
        try:
            # Fetch Quantum score from API
            response = await self.client.get(
                f"{self.quantum_url}/api/metrics/quantum",
                params={"symbol": symbol, "timeframe": timeframe}
            )
            response.raise_for_status()
            quantum_data = response.json()

            score = quantum_data.get("score", 0.5)
            details = quantum_data.get("details", {})

            # Extract liquidity metrics
            order_book_depth = float(details.get("order_book_depth", 50))  # in millions
            spread = float(details.get("spread", 0.05))  # in percentage
            buy_ratio = float(details.get("buy_ratio", 0.55))
            sell_ratio = float(details.get("sell_ratio", 0.45))

            # Determine liquidity status
            if spread < 0.05:
                liquidity_status = "Çok yüksek (çok dar spread)"
            elif spread < 0.1:
                liquidity_status = "Yüksek (dar spread)"
            elif spread < 0.2:
                liquidity_status = "Orta"
            else:
                liquidity_status = "Düşük (geniş spread)"

            # Determine direction based on order flow imbalance
            direction = self._determine_direction(score, buy_ratio, sell_ratio)

            details_text = (
                f"Order Book Derinliği: ${order_book_depth:.0f}M ({liquidity_status}), "
                f"Spread: {spread:.3f}%, "
                f"Alış/Satış Dengesi: {buy_ratio*100:.0f}/{sell_ratio*100:.0f} "
                f"({'alış baskısı' if buy_ratio > 0.52 else 'satış baskısı' if sell_ratio > 0.52 else 'dengeli'})"
            )

            return QuantumAnalysis(
                direction=direction,
                confidence=score,
                order_book_depth=order_book_depth,
                order_book_depth_unit="$M",
                spread=spread,
                buy_sell_ratio=(buy_ratio, sell_ratio),
                liquidity_status=liquidity_status,
                details=details_text
            )

        except httpx.HTTPError as e:
            logger.error(f"Quantum API error: {e}")
            return QuantumAnalysis(
                direction="NÖTR",
                confidence=0.5,
                details=f"Veri alınamadı: {str(e)}"
            )

    def _determine_direction(self, score: float, buy_ratio: float, sell_ratio: float) -> str:
        """Determine direction based on order flow"""
        if score > 0.65 and buy_ratio > 0.55:
            return "LONG"
        elif score < 0.35 and sell_ratio > 0.55:
            return "SHORT"
        else:
            return "NÖTR"

    async def close(self):
        await self.client.aclose()
