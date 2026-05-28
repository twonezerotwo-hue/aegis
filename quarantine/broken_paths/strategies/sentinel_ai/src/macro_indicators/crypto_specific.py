"""
SENTINEL AI - Crypto-Specific Macro Indicators

Standard makro dışında kripto-özgü:
- Stablecoin Supply (USDT, USDC) değişimi
- Regulatory Event Tracker (SEC, CFTC, EU, Asia)
- Bitcoin Dominance trendi
- Crypto Fear & Greed Index
"""
from typing import Dict, Optional, List
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger(__name__)


class StablecoinSupplyMonitor:
    """
    Stablecoin arzını izle

    High stablecoin supply = Likidite, buy pressure
    Low stablecoin supply = Çıkma sinyali
    """

    def __init__(self, config: dict = None):
        self.config = config or {}

    def analyze_stablecoin_flow(self, stablecoin_data: Dict) -> Dict:
        """
        Stablecoin arz değişimini analiz et

        Args:
            stablecoin_data: {
                'usdt_supply': float,          # USDT toplam arz
                'usdc_supply': float,          # USDC toplam arz
                'usdt_supply_24h_change': float,  # 24h değişim (%)
                'usdc_supply_24h_change': float,
                'usdt_exchange_inflow': float,    # Exchange'e gelen
                'usdc_exchange_inflow': float,
            }

        Returns:
            {
                'stablecoin_index': float,      # Composite index (0-100)
                'total_stablecoin_supply': float,
                'supply_trend': 'GROWING' | 'DECLINING' | 'STABLE',
                'exchange_pressure': 'INFLOW' | 'OUTFLOW' | 'BALANCED',
                'liquidity_signal': str,        # BULLISH, BEARISH, NEUTRAL
            }
        """
        try:
            usdt_supply = float(stablecoin_data.get("usdt_supply", 0))
            usdc_supply = float(stablecoin_data.get("usdc_supply", 0))
            total_supply = usdt_supply + usdc_supply

            usdt_change = float(stablecoin_data.get("usdt_supply_24h_change", 0))
            usdc_change = float(stablecoin_data.get("usdc_supply_24h_change", 0))
            avg_change = (usdt_change + usdc_change) / 2

            usdt_inflow = float(stablecoin_data.get("usdt_exchange_inflow", 0))
            usdc_inflow = float(stablecoin_data.get("usdc_exchange_inflow", 0))
            total_inflow = usdt_inflow + usdc_inflow

            # Supply trend
            if avg_change > 0.5:
                supply_trend = "GROWING"
                supply_score = 70
            elif avg_change < -0.5:
                supply_trend = "DECLINING"
                supply_score = 30
            else:
                supply_trend = "STABLE"
                supply_score = 50

            # Exchange pressure
            if total_inflow > 0:
                exchange_pressure = "INFLOW"
                pressure_score = 65
            elif total_inflow < 0:
                exchange_pressure = "OUTFLOW"
                pressure_score = 35
            else:
                exchange_pressure = "BALANCED"
                pressure_score = 50

            # Combined index
            stablecoin_index = (supply_score + pressure_score) / 2

            # Liquidity signal
            if stablecoin_index > 60:
                liquidity_signal = "BULLISH"  # Abundance of liquidity
            elif stablecoin_index < 40:
                liquidity_signal = "BEARISH"  # Liquidity draining
            else:
                liquidity_signal = "NEUTRAL"

            logger.info(
                "stablecoin_analysis",
                total_supply=round(total_supply, 0),
                avg_change_pct=round(avg_change, 2),
                exchange_inflow=round(total_inflow, 0),
                liquidity_signal=liquidity_signal,
            )

            return {
                "stablecoin_index": round(stablecoin_index, 2),
                "total_stablecoin_supply": round(total_supply, 0),
                "usdt_supply": round(usdt_supply, 0),
                "usdc_supply": round(usdc_supply, 0),
                "supply_24h_change_pct": round(avg_change, 2),
                "supply_trend": supply_trend,
                "exchange_inflow_24h": round(total_inflow, 0),
                "exchange_pressure": exchange_pressure,
                "liquidity_signal": liquidity_signal,
            }

        except Exception as e:
            logger.error("stablecoin_analysis_failed", error=str(e))
            return self._neutral_stablecoin()

    def _neutral_stablecoin(self) -> Dict:
        return {
            "stablecoin_index": 50.0,
            "total_stablecoin_supply": 0.0,
            "usdt_supply": 0.0,
            "usdc_supply": 0.0,
            "supply_24h_change_pct": 0.0,
            "supply_trend": "STABLE",
            "exchange_inflow_24h": 0.0,
            "exchange_pressure": "BALANCED",
            "liquidity_signal": "NEUTRAL",
        }


class RegulatoryEventTracker:
    """
    Regulatör olmayan ETkinlikleri izle

    Track:
    - SEC kararları (XRP, ETH, Bitcoin ETF)
    - CFTC haberleri
    - EU MiCA
    - Asya düzenlemeleri
    """

    SEVERITY_LEVELS = {
        "CRITICAL": 100,  # ETF onayı, XRP case sonucu
        "HIGH": 75,       # Yeni regulasyon
        "MEDIUM": 50,     # Konuşmalar
        "LOW": 25,        # İnceleme açıldı
    }

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.event_history: List[Dict] = []

    def track_regulatory_event(self, event: Dict) -> Dict:
        """
        Düzenleme etkinliğini kaydet ve puanla

        Args:
            event: {
                'date': int (timestamp),
                'authority': 'SEC' | 'CFTC' | 'EU' | 'ASIA' | etc,
                'symbol': 'BTC' | 'ETH' | 'XRP' | etc,
                'type': 'APPROVAL' | 'REJECTION' | 'INVESTIGATION' | 'CONSULTATION',
                'severity': 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW',
                'impact': 'BULLISH' | 'BEARISH' | 'NEUTRAL',
                'description': str,
            }

        Returns:
            {
                'event_impact_score': float,       # 0-100
                'time_relevance': float,            # 0-1 (ne kadar yeni)
                'regulatory_sentiment': str,        # POSITIVE, NEGATIVE, NEUTRAL
                'affected_assets': list,
                'market_impact': str,
            }
        """
        try:
            severity_score = self.SEVERITY_LEVELS.get(event.get("severity", "MEDIUM"), 50)
            impact_direction = event.get("impact", "NEUTRAL")

            # Time relevance (ne kadar yakında gerçekleşti?)
            event_date = event.get("date", 0)
            current_time = datetime.now().timestamp()
            days_ago = (current_time - event_date) / 86400

            # 30 gün içinde maksimum relevance
            if days_ago <= 1:
                time_relevance = 1.0  # Son 24 saat
            elif days_ago <= 7:
                time_relevance = 0.8  # Son haftada
            elif days_ago <= 30:
                time_relevance = 0.5
            else:
                time_relevance = 0.0  # Eski haber

            # Impact skoru
            if impact_direction == "BULLISH":
                regulatory_sentiment = "POSITIVE"
                impact_score = severity_score * 0.8  # 80% of severity
            elif impact_direction == "BEARISH":
                regulatory_sentiment = "NEGATIVE"
                impact_score = -severity_score * 0.8
            else:
                regulatory_sentiment = "NEUTRAL"
                impact_score = 0

            # Time-adjusted final score
            event_impact_score = impact_score * time_relevance

            # Etkinliği history'ye ekle
            self.event_history.append({
                "timestamp": current_time,
                "authority": event.get("authority"),
                "symbol": event.get("symbol"),
                "type": event.get("type"),
                "impact_score": event_impact_score,
            })

            # Keep last 30 days
            cutoff_time = current_time - (30 * 86400)
            self.event_history = [e for e in self.event_history if e["timestamp"] > cutoff_time]

            logger.info(
                "regulatory_event_tracked",
                authority=event.get("authority"),
                type=event.get("type"),
                severity=event.get("severity"),
                impact=event.get("impact"),
                time_relevance=round(time_relevance, 2),
                impact_score=round(event_impact_score, 2),
            )

            return {
                "event_impact_score": round(event_impact_score, 2),
                "time_relevance": round(time_relevance, 2),
                "regulatory_sentiment": regulatory_sentiment,
                "affected_symbols": [event.get("symbol", "")],
                "authority": event.get("authority"),
                "event_type": event.get("type"),
                "description": event.get("description", ""),
            }

        except Exception as e:
            logger.error("regulatory_tracking_failed", error=str(e))
            return self._neutral_regulatory()

    def get_regulatory_composite_score(self) -> float:
        """
        Son 30 günün tüm etkinliklerinden composite score
        """
        if not self.event_history:
            return 0.0

        scores = [e["impact_score"] for e in self.event_history]
        # Weighted average (son etkinlikler daha ağırlıklı)
        weights = [i / sum(range(1, len(scores) + 1)) for i in range(1, len(scores) + 1)]
        weighted_score = sum(s * w for s, w in zip(scores, weights))

        return round(weighted_score, 2)

    def _neutral_regulatory(self) -> Dict:
        return {
            "event_impact_score": 0.0,
            "time_relevance": 0.0,
            "regulatory_sentiment": "NEUTRAL",
            "affected_symbols": [],
            "authority": "NONE",
            "event_type": "NONE",
            "description": "",
        }


class BitcoinDominanceMonitor:
    """
    Bitcoin dominance trend'ini izle

    Yüksek dominance = Risk-on (alts düşüyor)
    Düşük dominance = Risk-off (alts havaya kalkıyor)
    """

    def __init__(self, config: dict = None):
        self.config = config or {}

    def analyze_btc_dominance(self, dominance_data: Dict) -> Dict:
        """
        BTC dominance eğilimini analiz et

        Args:
            dominance_data: {
                'btc_dominance_pct': float,     # Mevcut BTC dominance (%)
                'btc_dominance_24h_change': float,  # 24h değişim (puan)
                'btc_dominance_7d_trend': str,  # 'UP' | 'DOWN' | 'STABLE'
            }

        Returns:
            {
                'btc_dominance_pct': float,
                'dominance_trend': str,        # 'INCREASING' | 'DECREASING' | 'STABLE'
                'dominance_direction': str,    # 'RISK_ON' | 'RISK_OFF' | 'BALANCED'
                'altcoin_signal': str,         # BULLISH, BEARISH, NEUTRAL
            }
        """
        try:
            dominance = float(dominance_data.get("btc_dominance_pct", 50))
            change_24h = float(dominance_data.get("btc_dominance_24h_change", 0))
            trend_7d = dominance_data.get("btc_dominance_7d_trend", "STABLE")

            # Trend belirleme
            if change_24h > 0.5:
                trend = "INCREASING"
            elif change_24h < -0.5:
                trend = "DECREASING"
            else:
                trend = "STABLE"

            # Dominance levels
            # 40-50% = Altseason (alts strong)
            # 50-60% = Balanced
            # 60%+ = BTC season (alts weak)
            if dominance < 50:
                alt_strength = "STRONG"
                altcoin_signal = "BULLISH"
            elif dominance > 60:
                alt_strength = "WEAK"
                altcoin_signal = "BEARISH"
            else:
                alt_strength = "BALANCED"
                altcoin_signal = "NEUTRAL"

            # Dominance-Change uyumu
            if trend == "DECREASING" and alt_strength == "STRONG":
                direction = "RISK_ON"  # Alts güçleniyor
            elif trend == "INCREASING" and alt_strength == "WEAK":
                direction = "RISK_OFF"  # BTC şu an dominant
            else:
                direction = "BALANCED"

            logger.info(
                "btc_dominance_analyzed",
                dominance_pct=round(dominance, 2),
                24h_change=round(change_24h, 2),
                trend=trend,
                altcoin_signal=altcoin_signal,
            )

            return {
                "btc_dominance_pct": round(dominance, 2),
                "btc_dominance_24h_change": round(change_24h, 2),
                "dominance_trend": trend,
                "altcoin_strength": alt_strength,
                "dominance_direction": direction,
                "altcoin_signal": altcoin_signal,
            }

        except Exception as e:
            logger.error("btc_dominance_analysis_failed", error=str(e))
            return self._neutral_dominance()

    def _neutral_dominance(self) -> Dict:
        return {
            "btc_dominance_pct": 50.0,
            "btc_dominance_24h_change": 0.0,
            "dominance_trend": "STABLE",
            "altcoin_strength": "BALANCED",
            "dominance_direction": "BALANCED",
            "altcoin_signal": "NEUTRAL",
        }


class CryptoFearGreedMonitor:
    """
    Crypto Fear & Greed Index monitörü

    Index: 0-100
    - 0-25: Extreme Fear
    - 25-50: Fear
    - 50-75: Greed
    - 75-100: Extreme Greed
    """

    SENTIMENT_LEVELS = {
        (0, 25): ("Extreme Fear", "STRONG_BUY"),
        (25, 50): ("Fear", "BUY"),
        (50, 75): ("Greed", "SELL"),
        (75, 100): ("Extreme Greed", "STRONG_SELL"),
    }

    def analyze_fear_greed(self, index_value: float, sources: Dict = None) -> Dict:
        """
        Fear & Greed Index'i analiz et

        Args:
            index_value: 0-100 index değeri
            sources: Index oluşturan komponentler (opsiyonel)
                {
                    'volatility': float,
                    'market_momentum': float,
                    'social_media': float,
                    'dominance': float,
                    'trends': float,
                }

        Returns:
            {
                'fear_greed_index': float,
                'sentiment': str,              # Fear / Greed seviyesi
                'trading_signal': str,         # STRONG_BUY, BUY, SELL, STRONG_SELL
                'confidence': float,
            }
        """
        try:
            # Sentiment kartı
            sentiment = "Neutral"
            signal = "HOLD"
            for (low, high), (sent, sig) in self.SENTIMENT_LEVELS.items():
                if low <= index_value < high:
                    sentiment = sent
                    signal = sig
                    break

            # Confidence = distance from midpoint (50)
            confidence = abs(index_value - 50) / 50.0

            logger.info(
                "fear_greed_analyzed",
                index=round(index_value, 2),
                sentiment=sentiment,
                signal=signal,
                confidence=round(confidence, 2),
            )

            result = {
                "fear_greed_index": round(index_value, 2),
                "sentiment": sentiment,
                "trading_signal": signal,
                "confidence": round(confidence, 2),
            }

            # Kaynakları ekle (varsa)
            if sources:
                result["component_breakdown"] = {
                    k: round(v, 2) for k, v in sources.items()
                }

            return result

        except Exception as e:
            logger.error("fear_greed_analysis_failed", error=str(e))
            return {
                "fear_greed_index": 50.0,
                "sentiment": "Neutral",
                "trading_signal": "HOLD",
                "confidence": 0.0,
            }
